"""Carga el libro de bobinas en la base de datos.

Uso (dentro del contenedor de la API):
    python -m importador.cargar /datos/Inventario_de_Bobinas.xlsm
    python -m importador.cargar /datos/Inventario_de_Bobinas.xlsm --reemplazar

Antes de escribir corre la prueba de paridad y la imprime. Sin --reemplazar
se niega a cargar si ya hay piezas en la base.
"""
from __future__ import annotations

import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import modelos as m
from app.config import config
from app.db import SesionLocal
from app.dominio import codigos
from importador import excel, paridad, reglas

USUARIO = "importador"


def _norm(nombre: str | None) -> str:
    return " ".join((nombre or "").split()).upper()


SUFIJOS = (", C.A.", " C.A.", ", C.A", " C.A", ", CA", " CA", ", S.A.", " S.A.")


def sin_sufijo(nombre: str | None) -> str:
    """"Aceros del Valle, C.A." y "Aceros del Valle" son el mismo tercero."""
    k = _norm(nombre).rstrip(".")
    for s in SUFIJOS:
        s = s.upper().rstrip(".")
        if k.endswith(s):
            return k[: -len(s)].rstrip(" ,")
    return k


class Cache:
    def __init__(self, s: Session, empresa_id: int):
        self.s, self.e = s, empresa_id
        self.terceros = {_norm(t.nombre): t for t in s.scalars(select(m.Tercero).where(m.Tercero.empresa_id == empresa_id))}
        self.terceros_base = {sin_sufijo(n): t for n, t in self.terceros.items()}
        self.normas = {_norm(n.nombre): n for n in s.scalars(select(m.Norma).where(m.Norma.empresa_id == empresa_id))}
        self.tipos = {}
        for t in s.scalars(select(m.TipoAcero).where(m.TipoAcero.empresa_id == empresa_id)):
            self.tipos[_norm(t.nombre)] = t
            self.tipos[t.codigo] = t
        self.docs: dict[tuple, m.Documento] = {}

    def tercero(self, nombre: str | None, *, siderurgica: bool = False) -> m.Tercero | None:
        k = _norm(nombre)
        if not k:
            return None
        t = self.terceros.get(k) or self.terceros_base.get(sin_sufijo(k))
        if t is None:
            t = m.Tercero(empresa_id=self.e, nombre=" ".join(nombre.split()), es_cliente=not siderurgica,
                          es_siderurgica=siderurgica)
            self.s.add(t)
            self.terceros[k] = t
            self.terceros_base[sin_sufijo(k)] = t
        elif siderurgica:
            t.es_siderurgica = True
        return t

    def norma(self, nombre: str | None) -> m.Norma | None:
        k = _norm(nombre)
        if not k:
            return None
        n = self.normas.get(k)
        if n is None:
            n = m.Norma(empresa_id=self.e, nombre=" ".join(nombre.split()))
            self.s.add(n)
            self.normas[k] = n
        return n

    def tipo(self, nombre: str | None) -> m.TipoAcero | None:
        k = _norm(nombre)
        if not k:
            return None
        if k in self.tipos:
            return self.tipos[k]
        try:
            return self.tipos.get(codigos.codigo_tipo(k))
        except codigos.CodigoInvalido:
            return None

    def documento(self, tipo: str, numero: str | None, fecha, observacion: str | None = None) -> m.Documento:
        k = (tipo, numero, fecha)
        d = self.docs.get(k)
        if d is None:
            d = m.Documento(empresa_id=self.e, tipo=tipo, numero=numero, fecha=fecha, observacion=observacion,
                            origen="importacion", creado_por=USUARIO)
            self.s.add(d)
            self.docs[k] = d
        return d


def cargar(s: Session, plan: reglas.Plan, empresa_id: int) -> int:
    c = Cache(s, empresa_id)
    sin_dueno = c.tercero("Sin propietario registrado")
    for p in plan.piezas.values():
        e = p.entrada
        tipo_pieza = codigos.tipo_pieza_por_codigo(e.codigo_producto)
        tipo = c.tipo(e.tipo_acero)
        # Los flejes reingresados traen la genealogía en el código ("FLEHP0850200 / HT2BF2048 / 171 / 6"):
        # el código de producto es el primer tramo; la genealogía queda en el código físico.
        codigo_producto = (e.codigo_producto or "").split("/")[0].strip() or None
        if not codigo_producto and tipo and e.espesor and e.ancho:
            try:
                codigo_producto = codigos.codigo_producto(tipo_pieza, tipo.codigo, e.espesor, e.ancho)
            except codigos.CodigoInvalido:
                codigo_producto = None
        dueno_inicial = c.tercero(e.propietario) or sin_dueno
        pieza = m.Pieza(
            empresa_id=empresa_id, tipo=tipo_pieza, codigo_fisico=e.codigo_bobina,
            codigo_producto=(codigo_producto or "")[:40] or None, descripcion=(e.descripcion or "")[:200] or None,
            tipo_acero=tipo, norma=c.norma(e.norma), espesor_mm=e.espesor, ancho_mm=e.ancho,
            propietario=c.tercero(p.propietario) or dueno_inicial, buque=(e.buque or "")[:80] or None,
            fecha_entrada=e.fecha, peso_entrada_kg=e.peso, saldo_kg=p.saldo, estado=p.estado, creado_por=USUARIO)
        sid = c.tercero(e.siderurgica, siderurgica=True)
        s.add(pieza)
        s.flush()  # también guarda los terceros nuevos y les da id
        if sid is not None:
            pieza.siderurgica_id = sid.id
        dueno_actual = dueno_inicial
        saldo = 0
        for mv in p.movimientos:
            saldo += mv.kg
            doc = c.documento(mv.documento_tipo, mv.documento_numero, mv.fecha)
            nuevo = c.tercero(mv.propietario_nuevo) if mv.propietario_nuevo else None
            if mv.tipo == "entrada":
                nuevo = dueno_inicial
            s.flush()
            s.add(m.Movimiento(
                empresa_id=empresa_id, pieza_id=pieza.id, tipo=mv.tipo, kg=mv.kg, saldo_despues_kg=saldo,
                propietario_anterior_id=dueno_actual.id if nuevo is not None and mv.tipo != "entrada" else None,
                propietario_nuevo_id=nuevo.id if nuevo is not None else None, documento_id=doc.id,
                fecha=mv.fecha, origen="importacion",
                observacion="; ".join(x for x in (mv.nota, mv.fila_origen) if x), creado_por=USUARIO))
            if nuevo is not None:
                dueno_actual = nuevo
    s.flush()
    return len(plan.piezas)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    reemplazar = "--reemplazar" in argv
    if len(args) != 1:
        print(__doc__)
        return 2
    libro = excel.leer(args[0])
    plan = reglas.construir(libro)
    codigo = paridad.main(["paridad", args[0]])
    if codigo != 0:
        print("\nNo se carga: la existencia no coincide con el Consolidado.")
        return codigo
    with SesionLocal() as s:
        existentes = s.scalar(select(func.count(m.Pieza.id)).where(m.Pieza.empresa_id == config.empresa_id))
        if existentes and not reemplazar:
            print(f"\nYa hay {existentes} piezas en la base. Usa --reemplazar para borrar y volver a cargar.")
            return 1
        if existentes:
            # Borra también las órdenes de trabajo y los flejes: después hay que volver a cargar flejes.
            s.execute(text("UPDATE pieza SET orden_trabajo_id = NULL, pieza_origen_id = NULL WHERE empresa_id = :e"),
                      {"e": config.empresa_id})
            for tabla in ("movimiento", "auditoria", "orden_trabajo", "pieza", "documento"):
                s.execute(text(f"DELETE FROM {tabla} WHERE empresa_id = :e"), {"e": config.empresa_id})
        n = cargar(s, plan, config.empresa_id)
        s.commit()
    print(f"\nCargadas {n} piezas.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
