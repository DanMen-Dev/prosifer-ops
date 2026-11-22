"""Flejes y órdenes de slitter del libro de bobinas: lectura, reglas y paridad.

Hojas:
    FlejesTotal              un rollo de fleje por fila (código "FLE… / bobina / peso / rollo")
    ProductoF                órdenes de corte en slitter (una por fila)
    ProductoFlejes           consumo de flejes en maquila de perfiles
    SalidasAjustadasFlejes   notas de entrega, liberaciones y reenvíos a Entradas
    ConsolidadoFlejes        resultado del consolidado del Excel (para la paridad)

Reglas de importación:
1. Cada rollo es una pieza "fleje", hija de su bobina, ligada a la OC de slitter
   que la produjo (misma bobina; si la bobina tuvo varias OC, la de la misma fecha).
2. Su historia: producción (+peso), consumo en maquila (−kg), notas de entrega (−kg),
   liberaciones (cambian el dueño si liberan todo lo que quedaba).
3. "Reenvío a Almacén Bobinas": el Excel copia el rollo a Entradas con el mismo código
   y peso. En la app es la misma pieza: el rollo ya entró con el libro de bobinas y aquí
   solo se le agrega su origen (bobina madre y OC). No se crea una pieza nueva.
4. Una salida registrada dos veces (mismo código, documento, número y kg) cuenta una vez.

Uso:
    python -m importador.flejes /ruta/Inventario_de_Bobinas.xlsm
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

import openpyxl

from app.dominio import saldos
from importador.excel import _fecha, _kg, _num, _txt

CERO = Decimal("0")
TOLERANCIA_KG = Decimal("1")


def clave(codigo: str | None) -> str:
    return " ".join(str(codigo or "").split()).upper()


def producto_de(codigo: str | None) -> str | None:
    return (codigo or "").split("/")[0].strip() or None


@dataclass(frozen=True)
class Rollo:
    fila: int
    fecha: dt.date | None
    codigo: str
    codigo_bobina: str | None
    tipo_acero: str | None
    norma: str | None
    espesor: Decimal | None
    ancho: Decimal | None
    calidad: str | None
    peso: Decimal
    propietario: str | None


@dataclass(frozen=True)
class OtSlitter:
    fila: int
    numero: int | None
    codigo_bobina: str | None
    fecha: dt.date | None
    estatus: str | None
    kg: Decimal
    scrap_ancho: Decimal | None
    scrap_kg: Decimal
    paradas: int | None
    calidad: str | None
    propietario: str | None
    cortes: tuple  # ((ancho, kg, rollos), ...)


@dataclass(frozen=True)
class ConsumoMaquila:
    fila: int
    ot: str | None
    codigo: str
    kg: Decimal
    fecha: dt.date | None


@dataclass(frozen=True)
class SalidaFleje:
    fila: int
    codigo: str
    kg: Decimal
    propietario: str | None
    documento: str | None
    numero: str | None
    fecha: dt.date | None


@dataclass(frozen=True)
class FilaConsolidadoFleje:
    fila: int
    codigo: str
    disponible: Decimal
    estado: str | None
    propietario: str | None


@dataclass
class LibroFlejes:
    rollos: list[Rollo]
    ots: list[OtSlitter]
    consumos: list[ConsumoMaquila]
    salidas: list[SalidaFleje]
    consolidado: list[FilaConsolidadoFleje]
    codigos_entradas: set[str]


def _c(r, i):
    return r[i] if i < len(r) else None


def _int(v) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def leer(ruta: str) -> LibroFlejes:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    filas = lambda hoja, desde, hasta=None: enumerate(  # noqa: E731
        wb[hoja].iter_rows(min_row=desde, max_row=hasta, values_only=True), start=desde)

    rollos = [
        Rollo(i, _fecha(r[0]), _txt(r[2]), _txt(r[1]), _txt(r[4]), _txt(r[5]), _num(r[6]), _num(r[7]),
              _txt(r[8]), _kg(_c(r, 63)), _txt(_c(r, 64)))
        for i, r in filas("FlejesTotal", 4) if _txt(r[2])
    ]
    ots = []
    for i, r in filas("ProductoF", 4):
        if not _txt(r[2]):
            continue
        cortes = tuple(
            (_num(r[8 + 2 * k]), _kg(r[9 + 2 * k]), _int(_c(r, 61 + 2 * k)) or 0)
            for k in range(6) if _num(r[8 + 2 * k]))
        ots.append(OtSlitter(i, _int(r[1]), _txt(r[2]), _fecha(_c(r, 26)), _txt(_c(r, 23)), _kg(_c(r, 24)),
                             _num(_c(r, 20)), _kg(_c(r, 21)), _int(_c(r, 25)), _txt(_c(r, 37)), _txt(_c(r, 72)),
                             cortes))
    consumos = [
        ConsumoMaquila(i, _txt(r[1]), _txt(r[3]), _kg(_c(r, 30)), _fecha(_c(r, 27)))
        for i, r in filas("ProductoFlejes", 4) if _txt(r[3])
    ]
    salidas = [
        SalidaFleje(i, _txt(r[2]), _kg(r[11]), _txt(r[14]), _txt(r[15]), _txt(r[16]), _fecha(r[17]))
        for i, r in filas("SalidasAjustadasFlejes", 4, 20000) if _txt(r[2]) and _txt(r[2]) != "INICIO"
    ]
    consolidado = [
        FilaConsolidadoFleje(i, _txt(r[2]), _kg(r[12]), _txt(r[13]), _txt(r[14]))
        for i, r in filas("ConsolidadoFlejes", 4) if _txt(r[2])
    ]
    codigos_entradas = {clave(r[5]) for _, r in filas("Entradas", 4) if _txt(r[5])}
    return LibroFlejes(rollos, ots, consumos, salidas, consolidado, codigos_entradas)


@dataclass
class Mov:
    tipo: str
    kg: Decimal
    fecha: dt.date | None
    documento_tipo: str
    documento_numero: str | None
    propietario_nuevo: str | None = None
    nota: str | None = None
    fila_origen: str | None = None


@dataclass
class RolloPlan:
    rollo: Rollo
    ot: OtSlitter | None
    fusionado: bool                      # ya entró por Entradas (reenvío): solo se enriquece
    movimientos: list[Mov] = field(default_factory=list)
    saldo: Decimal = CERO
    estado: str = "agotado"
    propietario: str | None = None


@dataclass
class Incidencia:
    tipo: str
    codigo: str
    detalle: str


@dataclass
class PlanFlejes:
    rollos: dict[str, RolloPlan]
    ots: list[OtSlitter]
    incidencias: list[Incidencia]


def es_reenvio(documento: str | None) -> bool:
    return (documento or "").lower().startswith("reenvio")


def construir(libro: LibroFlejes) -> PlanFlejes:
    incidencias: list[Incidencia] = []
    ots_por_bobina: dict[str, list[OtSlitter]] = defaultdict(list)
    for o in libro.ots:
        ots_por_bobina[clave(o.codigo_bobina)].append(o)

    rollos: dict[str, RolloPlan] = {}
    for r in libro.rollos:
        k = clave(r.codigo)
        if k in rollos:
            incidencias.append(Incidencia("rollo_duplicado", r.codigo, f"FlejesTotal fila {r.fila}; se descarta"))
            continue
        candidatas = ots_por_bobina.get(clave(r.codigo_bobina), [])
        ot = candidatas[0] if len(candidatas) == 1 else next(
            (o for o in candidatas if o.fecha and o.fecha == r.fecha), None)
        if ot is None:
            incidencias.append(Incidencia("rollo_sin_oc", r.codigo,
                                          f"FlejesTotal fila {r.fila}: no se encontró su OC de slitter"))
        rollos[k] = RolloPlan(r, ot, fusionado=k in libro.codigos_entradas, propietario=r.propietario)

    pendientes: dict[str, list[Mov]] = defaultdict(list)
    for c in libro.consumos:
        k = clave(c.codigo)
        if c.kg <= 0:
            continue
        if k not in rollos:
            incidencias.append(Incidencia("consumo_sin_rollo", c.codigo, f"ProductoFlejes fila {c.fila}"))
            continue
        pendientes[k].append(Mov("consumo", -c.kg, c.fecha, "ot_maquila", c.ot, fila_origen=f"ProductoFlejes!{c.fila}"))

    vistas: set[tuple] = set()
    for s in libro.salidas:
        k = clave(s.codigo)
        if k not in rollos:
            incidencias.append(Incidencia("salida_sin_rollo", s.codigo, f"SalidasAjustadasFlejes fila {s.fila}"))
            continue
        firma = (k, s.documento, s.numero, s.kg)
        if firma in vistas:
            incidencias.append(Incidencia("salida_duplicada", s.codigo,
                                          f"fila {s.fila}: {s.documento} {s.numero} ya registrada; cuenta una vez"))
            continue
        vistas.add(firma)
        origen = f"SalidasAjustadasFlejes!{s.fila}"
        doc = (s.documento or "").lower()
        if doc.startswith("liberaci"):
            pendientes[k].append(Mov("liberacion", CERO, s.fecha, "liberacion", s.numero,
                                     propietario_nuevo=s.propietario, nota=str(s.kg), fila_origen=origen))
        elif es_reenvio(s.documento):
            pendientes[k].append(Mov("salida", -s.kg, s.fecha, "reenvio_bobinas", s.numero,
                                     nota="Reenvío a Almacén Bobinas: el rollo sigue en Entradas", fila_origen=origen))
        else:
            tipo_doc = "nota_entrega" if doc.startswith("nota de entrega") else "otro"
            nota = None if tipo_doc == "nota_entrega" else f"documento original: {s.documento}"
            pendientes[k].append(Mov("salida", -s.kg, s.fecha, tipo_doc, s.numero, nota=nota, fila_origen=origen))

    for k, rp in rollos.items():
        r = rp.rollo
        saldo = r.peso
        rp.movimientos = [Mov("produccion", r.peso, r.fecha, "ot_slitter",
                              str(rp.ot.numero) if rp.ot and rp.ot.numero else None,
                              fila_origen=f"FlejesTotal!{r.fila}")]
        for mv in sorted(pendientes[k], key=lambda m: m.fecha or r.fecha or dt.date(1900, 1, 1)):
            if mv.tipo == "liberacion":
                liberado = Decimal(mv.nota)
                mv.nota = f"el libro registró {liberado} kg liberados"
                if liberado < saldo - TOLERANCIA_KG:
                    incidencias.append(Incidencia("liberacion_parcial", r.codigo,
                                                  f"{mv.fila_origen}: libera {liberado} de {saldo} kg; el dueño no cambia"))
                    mv.propietario_nuevo = None
            saldo = saldos.aplicar(saldo, mv.tipo, mv.kg, permitir_negativo=True).saldo_kg
            if mv.propietario_nuevo:
                rp.propietario = mv.propietario_nuevo
            rp.movimientos.append(mv)
        if saldo < -TOLERANCIA_KG:
            incidencias.append(Incidencia("saldo_negativo", r.codigo,
                                          f"se consumió o entregó más de lo producido: saldo {saldo} kg"))
        if rp.fusionado and not any(m.documento_tipo == "reenvio_bobinas" for m in rp.movimientos):
            incidencias.append(Incidencia("fusionado_sin_reenvio", r.codigo,
                                          "el código aparece en Entradas sin un reenvío registrado"))
        rp.saldo = saldo
        rp.estado = saldos.estado_para(saldo)
    return PlanFlejes(rollos, libro.ots, incidencias)


def comparar(libro: LibroFlejes, plan: PlanFlejes) -> dict:
    cons = {clave(f.codigo): f for f in libro.consolidado}
    diferencias = []
    posteriores = []  # rollos cortados después de la última vez que se pulsó "Consolidar" en el Excel
    for k, rp in plan.rollos.items():
        f = cons.get(k)
        if f is None:
            posteriores.append(rp)
        elif abs(f.disponible - rp.saldo) > TOLERANCIA_KG:
            diferencias.append((rp.rollo.codigo, "kg", rp.saldo, f.disponible))
    disp_libro = [f for f in libro.consolidado if f.estado == "Disponible"]
    disp_nuevo = [rp for rp in plan.rollos.values() if rp.estado == "disponible"]
    return {
        "rollos": len(plan.rollos),
        "fusionados": sum(1 for rp in plan.rollos.values() if rp.fusionado),
        "ots": len(plan.ots),
        "disponibles_libro": (len(disp_libro), sum((f.disponible for f in disp_libro), CERO)),
        "disponibles_nuevo": (len(disp_nuevo), sum((rp.saldo for rp in disp_nuevo), CERO)),
        "posteriores": posteriores,
        "diferencias": diferencias,
        "incidencias": plan.incidencias,
    }


def _kg_txt(x: Decimal) -> str:
    return f"{x:,.0f}".replace(",", ".")


def informe(r: dict) -> bool:
    nl, kl = r["disponibles_libro"]
    nn, kn = r["disponibles_nuevo"]
    print(f"Rollos de fleje: {r['rollos']} ({r['fusionados']} ya están en Entradas por reenvío)")
    print(f"OC de slitter: {r['ots']}")
    print(f"Disponible según ConsolidadoFlejes: {nl} rollos, {_kg_txt(kl)} kg")
    print(f"Disponible según la app:            {nn} rollos, {_kg_txt(kn)} kg")
    post = [rp for rp in r["posteriores"] if rp.estado == "disponible"]
    kp = sum((rp.saldo for rp in post), CERO)
    if r["posteriores"]:
        print(f"Cortados después del último consolidado del Excel: {len(r['posteriores'])} rollos "
              f"({len(post)} disponibles, {_kg_txt(kp)} kg)")
        for rp in r["posteriores"]:
            print(f"   {rp.rollo.codigo}  {rp.saldo} kg  ({rp.rollo.fecha})")
    print(f"\nDiferencias: {len(r['diferencias'])}")
    for d in r["diferencias"]:
        print("  ", d)
    print(f"\nIncidencias para revisar: {dict(Counter(i.tipo for i in r['incidencias']))}")
    for i in r["incidencias"]:
        print(f"   [{i.tipo}] {i.codigo}: {i.detalle}")
    ok = nl + len(post) == nn and abs(kl + kp - kn) <= TOLERANCIA_KG and not r["diferencias"]
    print("\nExistencia de flejes (rollos y kg): " + ("PARIDAD OK" if ok else "CON DIFERENCIAS"))
    return ok


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    libro = leer(argv[1])
    return 0 if informe(comparar(libro, construir(libro))) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
