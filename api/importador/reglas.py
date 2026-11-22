"""Convierte las hojas del libro en piezas y movimientos según las reglas nuevas.

Reglas de importación (doc de reglas, secciones Existencias y Decisiones):

1. Una entrada por código de bobina. Si el código se repite, vale la primera
   carga y las siguientes se reportan como incidencia (no se suman).
2. Cada corte de lámina (Producto) o de slitter (ProductoF) es un consumo con
   su número de OT.
3. Una nota de entrega registrada dos veces (misma bobina, número y kg) cuenta
   una sola vez.
4. "Ajuste Inventario Interno" deja la pieza en cero: se importa como ajuste
   por el saldo que quedaba en ese momento.
5. Una liberación no descuenta peso. Cambia el dueño si libera la pieza
   completa; si es parcial se reporta (la regla nueva no la permite).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from app.dominio import saldos
from importador.excel import Entrada, Libro

CERO = Decimal("0")
FECHA_MINIMA = dt.date(1900, 1, 1)


def clave(codigo: str | None) -> str:
    return (codigo or "").strip().upper()


def es_liberacion(documento: str | None) -> bool:
    return (documento or "").lower().startswith("liberaci")


def es_ajuste(documento: str | None, numero: str | None) -> bool:
    texto = f"{documento or ''} {numero or ''}".lower()
    return "ajuste" in texto


@dataclass
class Movimiento:
    tipo: str
    kg: Decimal
    fecha: dt.date | None
    documento_tipo: str  # entrada | ot_lamina | ot_slitter | nota_entrega | liberacion | ajuste
    documento_numero: str | None
    propietario_nuevo: str | None = None
    nota: str | None = None
    fila_origen: str | None = None


@dataclass
class PiezaPlan:
    entrada: Entrada
    movimientos: list[Movimiento] = field(default_factory=list)
    saldo: Decimal = CERO
    estado: str = "agotado"
    propietario: str | None = None


@dataclass
class Incidencia:
    tipo: str
    codigo: str
    detalle: str


@dataclass
class Plan:
    piezas: dict[str, PiezaPlan]
    incidencias: list[Incidencia]


def construir(libro: Libro) -> Plan:
    piezas: dict[str, PiezaPlan] = {}
    incidencias: list[Incidencia] = []

    # Si un código se repite, vale la carga más antigua (decidido 8 nov 2026).
    for e in sorted(libro.entradas, key=lambda x: (x.fecha or FECHA_MINIMA, x.fila)):
        k = clave(e.codigo_bobina)
        if k in piezas:
            primera = piezas[k].entrada
            incidencias.append(Incidencia(
                "entrada_duplicada", e.codigo_bobina,
                f"fila {e.fila} ({e.documento}, {e.fecha}, {e.peso} kg) repite la fila {primera.fila} "
                f"({primera.documento}, {primera.fecha}); se descarta"))
            continue
        piezas[k] = PiezaPlan(entrada=e, propietario=e.propietario)

    pendientes: dict[str, list[Movimiento]] = {k: [] for k in piezas}

    for c in libro.cortes:
        if c.kg <= 0:
            continue  # filas de registro sin peso (p. ej. "OT Entrada" de flejes)
        k = clave(c.codigo_bobina)
        if k not in piezas:
            incidencias.append(Incidencia("corte_sin_entrada", c.codigo_bobina,
                                          f"{c.hoja} fila {c.fila}, OT {c.ot}, {c.kg} kg"))
            continue
        pendientes[k].append(Movimiento(
            "consumo", -c.kg, c.fecha, "ot_lamina" if c.hoja == "Producto" else "ot_slitter", c.ot,
            fila_origen=f"{c.hoja}!{c.fila}"))

    vistas: set[tuple] = set()
    for s in libro.salidas:
        k = clave(s.codigo_bobina)
        if k not in piezas:
            incidencias.append(Incidencia("salida_sin_entrada", s.codigo_bobina,
                                          f"SalidasAjustadas fila {s.fila}, {s.documento} {s.numero}"))
            continue
        firma = (k, s.documento, s.numero, s.kg)
        if firma in vistas:
            incidencias.append(Incidencia("salida_duplicada", s.codigo_bobina,
                                          f"fila {s.fila}: {s.documento} {s.numero} ({s.kg} kg) ya registrada; cuenta una vez"))
            continue
        vistas.add(firma)
        origen = f"SalidasAjustadas!{s.fila}"
        if es_liberacion(s.documento):
            # Se decide al recorrer la pieza si libera todo lo que quedaba.
            pendientes[k].append(Movimiento(
                "liberacion", CERO, s.fecha, "liberacion", s.numero,
                propietario_nuevo=s.propietario, nota=str(s.kg), fila_origen=origen))
        elif es_ajuste(s.documento, s.numero):
            pendientes[k].append(Movimiento(
                "ajuste", CERO, s.fecha, "ajuste", s.numero,
                nota=f"Ajuste Inventario Interno (el libro registró {s.kg} kg); deja la pieza en cero",
                fila_origen=origen))
        else:
            nota = None if s.documento and s.documento.startswith("Nota de Entrega") else f"documento original: {s.documento}"
            pendientes[k].append(Movimiento(
                "salida", -s.kg, s.fecha, "nota_entrega", s.numero, nota=nota, fila_origen=origen))

    for k, pieza in piezas.items():
        e = pieza.entrada
        # Orden por fecha (las filas viejas sin fecha van con la entrada); los ajustes de cierre al final.
        movs = sorted(pendientes[k], key=lambda m: (m.tipo == "ajuste", m.fecha or e.fecha or FECHA_MINIMA))
        pieza.movimientos = [Movimiento("entrada", e.peso, e.fecha, "entrada", e.documento, fila_origen=f"Entradas!{e.fila}")]
        saldo = e.peso
        for m in movs:
            if m.tipo == "ajuste":
                m.kg = -saldo
            if m.tipo == "liberacion":
                liberado = Decimal(m.nota)
                m.nota = f"el libro registró {liberado} kg liberados"
                if liberado < saldo - saldos.UMBRAL_AGOTADO_KG:
                    incidencias.append(Incidencia(
                        "liberacion_parcial", e.codigo_bobina,
                        f"{m.fila_origen}: libera {liberado} de {saldo} kg; el dueño no cambia"))
                    m.propietario_nuevo = None
            r = saldos.aplicar(saldo, m.tipo, m.kg, permitir_negativo=True)
            saldo = r.saldo_kg
            if m.propietario_nuevo:
                pieza.propietario = m.propietario_nuevo
            pieza.movimientos.append(m)
        if saldo < -saldos.UMBRAL_AGOTADO_KG:
            incidencias.append(Incidencia("saldo_negativo", e.codigo_bobina,
                                          f"se procesó o entregó más de lo que entró: saldo {saldo} kg"))
        pieza.saldo = saldo
        pieza.estado = saldos.estado_para(saldo)
    return Plan(piezas, incidencias)
