"""Carga clientes y productos del libro de formatos de NE y cotizaciones.

    python -m importador.cargar_catalogos /datos/Formato_General_Cotizaciones_-_Notas_Entrega.xlsm            # solo muestra
    python -m importador.cargar_catalogos /datos/Formato_General_Cotizaciones_-_Notas_Entrega.xlsm --cargar   # y guarda

Se puede repetir sin duplicar nada:
- Un cliente que ya existe (por ejemplo, un dueño de bobinas que entró con el inventario) se
  reconoce por el nombre sin puntos, tildes ni mayúsculas. Solo se le llenan los datos vacíos:
  lo que la oficina corrigió en la app no se pisa.
- Un producto que ya existe se reconoce por el código; solo se le pone el peso si no tenía.
"""
from __future__ import annotations

import sys
from dataclasses import fields

from sqlalchemy import select

from app import modelos as m
from app.config import config
from app.db import SesionLocal
from importador import catalogos_excel as ce

CAMPOS_FICHA = [f.name for f in fields(ce.Cliente) if f.name not in ("fila", "nombre")]


def cargar(s, cat: ce.Catalogos, empresa_id: int) -> dict:
    res = {"clientes_nuevos": 0, "clientes_completados": 0, "productos_nuevos": 0, "productos_con_peso": 0}

    existentes = {ce.clave_nombre(t.nombre): t for t in s.scalars(
        select(m.Tercero).where(m.Tercero.empresa_id == empresa_id))}
    for c in cat.clientes:
        t = existentes.get(ce.clave_nombre(c.nombre))
        if t is None:
            t = m.Tercero(empresa_id=empresa_id, nombre=c.nombre[:160], es_cliente=True,
                          **{k: getattr(c, k) for k in CAMPOS_FICHA})
            s.add(t)
            existentes[ce.clave_nombre(c.nombre)] = t
            res["clientes_nuevos"] += 1
            continue
        lleno = False
        for k in CAMPOS_FICHA:
            if getattr(t, k) is None and getattr(c, k) is not None:
                setattr(t, k, getattr(c, k))
                lleno = True
        if not t.es_cliente:
            t.es_cliente, lleno = True, True
        res["clientes_completados"] += lleno

    productos = {p.codigo: p for p in s.scalars(select(m.Producto).where(m.Producto.empresa_id == empresa_id))}
    for p in cat.productos:
        actual = productos.get(p.codigo)
        if actual is None:
            s.add(m.Producto(empresa_id=empresa_id, codigo=p.codigo, nombre=p.nombre[:200],
                             peso_unitario_kg=p.peso_unitario_kg))
            res["productos_nuevos"] += 1
        elif actual.peso_unitario_kg is None and p.peso_unitario_kg is not None:
            actual.peso_unitario_kg = p.peso_unitario_kg
            res["productos_con_peso"] += 1
    s.flush()
    return res


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cat = ce.leer(argv[0])
    print(f"En el libro: {len(cat.clientes)} clientes y {len(cat.productos)} productos")
    for a in cat.avisos:
        print(" -", a)
    with SesionLocal() as s:
        res = cargar(s, cat, config.empresa_id)
        print("Resultado:", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in res.items()))
        if "--cargar" in argv:
            s.commit()
            print("Guardado.")
        else:
            s.rollback()
            print("Vista previa: no se guardó nada. Agrega --cargar para guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
