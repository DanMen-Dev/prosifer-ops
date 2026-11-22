"""Reporte: qué código y nombre le da la regla nueva a cada producto del catálogo. No cambia nada.

    python -m importador.reporte_codigos                 # resumen por familia
    python -m importador.reporte_codigos --csv > r.csv   # todas las filas, para abrir en Excel

Estados:
    igual           el código y el nombre ya siguen la regla
    cambia_codigo   el código cambia (el nombre ya está bien)
    cambia_nombre   solo se ordena el nombre (espacios, comillas, decimales)
    cambian_ambos   cambian los dos
    choque          con la regla, dos productos quedarían con el mismo código: revisar a mano
                    (suelen ser duplicados del catálogo o nombres mal escritos)
    sin_regla       el nombre no sigue ninguna familia conocida: queda como está
"""
from __future__ import annotations

import collections
import csv
import sys

from sqlalchemy import select

from app import modelos as m
from app.config import config
from app.db import SesionLocal
from app.dominio import generador as g


def filas(s, empresa_id: int) -> list[g.FilaComparacion]:
    productos = s.execute(select(m.Producto.codigo, m.Producto.nombre)
                          .where(m.Producto.empresa_id == empresa_id, m.Producto.activo.is_(True))
                          .order_by(m.Producto.codigo)).all()
    return g.comparar([(c, n) for c, n in productos])


def resumen(res: list[g.FilaComparacion]) -> str:
    total = collections.Counter(f.estado for f in res)
    por_familia = collections.Counter((f.familia or "(sin regla)", f.estado) for f in res)
    lineas = [f"{len(res)} productos activos en el catálogo", ""]
    lineas += [f"  {e:14} {total.get(e, 0):5}" for e in g.ORDEN_ESTADOS]
    lineas += ["", "Por familia:"]
    familias = sorted({k[0] for k in por_familia})
    for fam in familias:
        partes = ", ".join(f"{e} {por_familia[(fam, e)]}" for e in g.ORDEN_ESTADOS if por_familia.get((fam, e)))
        lineas.append(f"  {fam:20} {partes}")
    choques = [f for f in res if f.estado == "choque"]
    if choques:
        lineas += ["", "Choques (revisar a mano):"]
        lineas += [f"  {f.codigo_actual:32} {f.nombre_actual}  ->  {f.nota}" for f in choques]
    lineas += ["", "Para ver todas las filas: agrega --csv y guarda la salida en un archivo."]
    return "\n".join(lineas)


def main(argv: list[str]) -> int:
    with SesionLocal() as s:
        res = filas(s, config.empresa_id)
    if "--csv" in argv:
        w = csv.writer(sys.stdout, delimiter=";")
        w.writerow(["estado", "familia", "codigo_actual", "codigo_nuevo", "nombre_actual", "nombre_nuevo", "nota"])
        orden = {e: i for i, e in enumerate(g.ORDEN_ESTADOS)}
        for f in sorted(res, key=lambda f: (orden[f.estado], f.familia or "", f.codigo_actual)):
            w.writerow([f.estado, f.familia or "", f.codigo_actual, f.codigo_nuevo or "", f.nombre_actual,
                        f.nombre_nuevo or "", f.nota])
    else:
        print(resumen(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
