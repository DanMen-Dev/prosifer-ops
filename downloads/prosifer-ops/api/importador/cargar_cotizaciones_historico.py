"""Carga el histórico de cotizaciones del Excel, solo para consulta y respaldo.

    python -m importador.cargar_cotizaciones_historico "/datos/Formato_General_Cotizaciones_-_Notas_Entrega.xlsm"            # vista previa
    python -m importador.cargar_cotizaciones_historico "/datos/Formato_General_Cotizaciones_-_Notas_Entrega.xlsm" --cargar   # guarda

- Se puede repetir mientras el Excel siga en uso: solo agrega las que todavía no están (número + cliente).
- Si un número ya existe como cotización emitida en la app, no se toca y se avisa (choque de numeración).
- Los clientes que no estén en la app se crean (como en el histórico de notas de entrega).
- Al final dice cuál es la última cotización del libro y cuál será la próxima de la app.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app import modelos as m
from app.adaptadores.sql.numerador import NumeradorSql
from app.config import config
from app.db import SesionLocal
from importador import cotizaciones_excel as cx
from importador.catalogos_excel import clave_nombre

USUARIO = "importador"
ORIGEN = "excel"
TIPO = "cotizacion"


def cargar(s, cotizaciones: list[cx.CotizacionHistorica], empresa_id: int) -> tuple[dict, list[str]]:
    avisos: list[str] = []
    terceros = {clave_nombre(t.nombre): t for t in s.scalars(select(m.Tercero).where(m.Tercero.empresa_id == empresa_id))}
    existentes: dict[tuple[str, str], m.Documento] = {}
    de_la_app: set[str] = set()
    for d in s.scalars(select(m.Documento).where(m.Documento.empresa_id == empresa_id, m.Documento.tipo == TIPO)):
        nombre = d.tercero.nombre if d.tercero else (d.encabezado or {}).get("cliente_excel") or ""
        existentes[(d.numero, clave_nombre(nombre))] = d
        if d.origen != ORIGEN:
            de_la_app.add(d.numero)
    res = {"nuevas": 0, "ya_estaban": 0, "choques": 0, "clientes_nuevos": 0, "renglones": 0}

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

    # de la más vieja a la más reciente: así los id quedan en el orden en que se emitieron
    for q in reversed(cotizaciones):
        if q.numero in de_la_app:
            res["choques"] += 1
            avisos.append(f"Cotización {q.numero}: ya existe una emitida en la app con ese número; no se carga la del Excel")
            continue
        clave = (q.numero, clave_nombre(q.cliente or ""))
        if clave in existentes:
            res["ya_estaban"] += 1
            continue
        t = tercero_de(q.cliente)
        d = m.Documento(empresa_id=empresa_id, tipo=TIPO, numero=q.numero, fecha=q.fecha, tercero_id=t.id if t else None,
                        anulado=q.anulada, origen=ORIGEN, creado_por=USUARIO, encabezado=q.encabezado)
        s.add(d)
        existentes[clave] = d
        res["nuevas"] += 1
        res["renglones"] += len(q.renglones)
    s.flush()
    return res, avisos


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    qs = cx.leer(argv[0])
    ultima = cx.ultima(qs)
    print(f"En el libro: {len(qs)} cotizaciones, la última es la D-{ultima}")
    with SesionLocal() as s:
        res, avisos = cargar(s, qs, config.empresa_id)
        for a in avisos:
            print(" -", a)
        print("Resultado:", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in res.items()))
        proxima = NumeradorSql(s, config.empresa_id).ver_siguiente(TIPO)
        print(f"Próxima cotización de la app: D-{proxima}")
        if ultima and proxima <= ultima:
            print(f"   ATENCIÓN: la app emitiría un número que ya usó el Excel. El día del corte fija la secuencia:\n"
                  f"   python -m app.secuencias fijar {TIPO} {ultima}")
        if "--cargar" in argv:
            s.commit()
            print("Guardado (solo consulta).")
        else:
            s.rollback()
            print("Vista previa: no se guardó nada. Agrega --cargar para guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
