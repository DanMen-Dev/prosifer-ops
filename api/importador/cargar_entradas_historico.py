"""Carga el histórico de entradas de material de los libros de Láminas y de Productos Generales.

    python -m importador.cargar_entradas_historico "/datos/Inventario_de_Laminas.xlsm" "/datos/Inventario_de_Productos_Generales.xlsm"            # vista previa
    python -m importador.cargar_entradas_historico "/datos/Inventario_de_Laminas.xlsm" "/datos/Inventario_de_Productos_Generales.xlsm" --cargar   # guarda

- Solo consulta: quedan en Entradas › Documentos y recibos como "Histórico del Excel" y no mueven
  inventario (el saldo de apertura ya incluye este material).
- Se puede repetir: una entrada ya cargada (mismo dueño, documento y fecha) no se vuelve a cargar.
- Avisa si en la app ya hay una entrada registrada con el mismo número de documento: puede ser la misma
  nota cargada dos veces (en el Excel y en la app). Revísala.
- Los kg: en láminas, piezas x peso por pieza del libro; en generales, piezas x peso unitario del catálogo.
"""
from __future__ import annotations

import re
import sys
from decimal import Decimal

from sqlalchemy import select

from app import modelos as m
from app.config import config
from app.db import SesionLocal
from importador import entradas_historico_excel as eh
from importador.catalogos_excel import clave_nombre

USUARIO = "importador"
ORIGEN = "excel"


def _digitos(texto: str | None) -> str:
    return "".join(re.findall(r"\d+", texto or ""))


def cargar(s, entradas: list[eh.EntradaHistorica], empresa_id: int) -> tuple[dict, list[str]]:
    avisos: list[str] = []
    res = {"nuevas": 0, "ya_estaban": 0, "renglones": 0, "clientes_nuevos": 0, "kg_del_catalogo": 0}
    terceros = {clave_nombre(t.nombre): t for t in s.scalars(select(m.Tercero).where(m.Tercero.empresa_id == empresa_id))}
    pesos = {p.codigo: p.peso_unitario_kg for p in s.scalars(select(m.Producto).where(m.Producto.empresa_id == empresa_id))}
    ya = {(d.tercero_id, (d.numero or "").lower(), d.fecha) for d in s.scalars(
        select(m.Documento).where(m.Documento.empresa_id == empresa_id, m.Documento.tipo == "entrada",
                                  m.Documento.origen == ORIGEN))}
    # entradas registradas en la app (no historicas), por los digitos de su documento
    de_app: dict[str, list[m.Documento]] = {}
    for d in s.scalars(select(m.Documento).where(m.Documento.empresa_id == empresa_id, m.Documento.tipo == "entrada",
                                                 m.Documento.origen != ORIGEN)):
        if len(_digitos(d.numero)) >= 4:
            de_app.setdefault(_digitos(d.numero), []).append(d)

    def tercero_de(nombre: str | None):
        if not nombre:
            return None
        t = terceros.get(clave_nombre(nombre))
        if t is None:
            t = m.Tercero(empresa_id=empresa_id, nombre=nombre[:160], es_cliente=True)
            s.add(t)
            s.flush()
            terceros[clave_nombre(nombre)] = t
            res["clientes_nuevos"] += 1
        return t

    for e in entradas:
        t = tercero_de(e.propietario)
        clave = (t.id if t else None, e.documento[:80].lower(), e.fecha)
        for a in e.avisos:
            avisos.append(f"{e.libro} · {e.hoja} fila {e.fila} · {e.documento}: {a}")
        for d in de_app.get(_digitos(e.documento), []):
            if d.tercero_id == (t.id if t else None):
                avisos.append(f"{e.documento} ({e.propietario}, {e.fecha}): en la app ya hay una entrada con ese documento "
                              f"({d.numero}, {d.fecha}) — ¿cargada dos veces?")
        if clave in ya:
            res["ya_estaban"] += 1
            continue
        obs = "; ".join(e.avisos) or None
        doc = m.Documento(empresa_id=empresa_id, tipo="entrada", numero=e.documento[:80], fecha=e.fecha,
                          tercero_id=t.id if t else None, observacion=obs, anulado=False, origen=ORIGEN,
                          creado_por=USUARIO, encabezado={"libro": e.libro, "documento": e.documento})
        s.add(doc)
        s.flush()
        for r in e.renglones:
            kg = r.kg
            if kg is None and r.cantidad and pesos.get(r.codigo):
                kg = (r.cantidad * Decimal(pesos[r.codigo])).quantize(Decimal("0.001"))
                res["kg_del_catalogo"] += 1
            s.add(m.DocumentoLinea(documento_id=doc.id, posicion=r.posicion, codigo=(r.codigo or None) and r.codigo[:60],
                                   descripcion=(r.descripcion or None) and r.descripcion[:250], cantidad=r.cantidad,
                                   unidad="pzas", kg=kg))
            res["renglones"] += 1
        ya.add(clave)
        res["nuevas"] += 1
    s.flush()
    return res, avisos


def juntar(entradas: list[eh.EntradaHistorica]) -> list[eh.EntradaHistorica]:
    """La misma nota puede traer láminas (libro de Láminas) y generales (libro de Generales): un solo documento."""
    por_clave: dict[tuple, eh.EntradaHistorica] = {}
    for e in entradas:
        previa = por_clave.get(e.clave)
        if previa is None:
            por_clave[e.clave] = e
            continue
        for r in e.renglones:
            r.posicion = len(previa.renglones) + 1
            previa.renglones.append(r)
        if e.libro not in previa.libro:
            previa.libro = f"{previa.libro} + {e.libro}"
        previa.avisos += [a for a in e.avisos if a not in previa.avisos]
    return list(por_clave.values())


def main(argv: list[str]) -> int:
    rutas = [a for a in argv if not a.startswith("--")]
    if not rutas:
        print(__doc__)
        return 2
    entradas: list[eh.EntradaHistorica] = []
    for ruta in rutas:
        leidas = eh.leer(ruta)
        print(f"{ruta.rsplit('/', 1)[-1]}: {len(leidas)} entradas, {sum(len(e.renglones) for e in leidas)} renglones")
        entradas += leidas
    entradas = juntar(entradas)
    print(f"En total: {len(entradas)} entradas (una nota con láminas y generales cuenta una vez)")
    with SesionLocal() as s:
        res, avisos = cargar(s, entradas, config.empresa_id)
        for a in avisos:
            print(" -", a)
        print("Resultado:", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in res.items()))
        if "--cargar" in argv:
            s.commit()
            print("Guardado (solo consulta: no mueve inventario).")
        else:
            s.rollback()
            print("Vista previa: no se guardó nada. Agrega --cargar para guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
