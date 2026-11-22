"""Carga el histórico de notas de entrega del Excel, solo para consulta y respaldo.

    python -m importador.cargar_ne_historico "/datos/Formato_General_Cotizaciones_-_Notas_Entrega.xlsm"            # vista previa
    python -m importador.cargar_ne_historico "/datos/Formato_General_Cotizaciones_-_Notas_Entrega.xlsm" --cargar   # guarda

- No mueve inventario: el saldo de apertura de láminas, perfiles y generales ya descuenta estas NE.
- Se puede repetir mientras el Excel siga en uso: solo agrega los números que todavía no están.
- Las NE que despacharon bobinas o flejes ya existen, creadas por la carga del libro de Slitter
  (origen "importacion", con sus movimientos). No son choques: son la misma NE, así que se completan
  con los renglones del Excel (y el cliente u observación si faltaban) sin tocar sus movimientos.
- Si un número ya existe como NE emitida en la app, no se toca y se avisa (choque de numeración).
- Al final dice cuál es la última NE del libro y cuál será la próxima de la app.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app import modelos as m
from app.adaptadores.sql.numerador import NumeradorSql
from app.config import config
from app.db import SesionLocal
from importador import ne_historico_excel as nh
from importador.catalogos_excel import clave_nombre

USUARIO = "importador"
ORIGEN = "excel"
DEL_SLITTER = "importacion"   # NE creadas al cargar bobinas y flejes del libro de Slitter


def cargar(s, notas: list[nh.NotaHistorica], empresa_id: int) -> tuple[dict, list[str]]:
    avisos: list[str] = []
    existentes = {d.numero: d for d in s.scalars(
        select(m.Documento).where(m.Documento.empresa_id == empresa_id, m.Documento.tipo == "nota_entrega"))}
    con_lineas = set(s.scalars(select(m.DocumentoLinea.documento_id).distinct()))
    terceros = {clave_nombre(t.nombre): t for t in s.scalars(select(m.Tercero).where(m.Tercero.empresa_id == empresa_id))}
    res = {"nuevas": 0, "completadas": 0, "ya_estaban": 0, "fechas_corregidas": 0, "choques": 0,
           "clientes_nuevos": 0, "renglones": 0}

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

    def renglones(doc_id: int, n: nh.NotaHistorica):
        for r in n.renglones:
            s.add(m.DocumentoLinea(documento_id=doc_id, posicion=r.posicion, codigo=(r.codigo or None) and r.codigo[:60],
                                   descripcion=(r.descripcion or None) and r.descripcion[:250], cantidad=r.cantidad,
                                   unidad=(r.unidad or None) and r.unidad[:20], kg=r.kg))
            res["renglones"] += 1
        con_lineas.add(doc_id)

    for n in notas:
        previa = existentes.get(n.numero)
        if previa is not None:
            if previa.origen == DEL_SLITTER:
                if previa.id in con_lineas:
                    res["ya_estaban"] += 1
                    continue
                if previa.tercero_id is None and (t := tercero_de(n.cliente)) is not None:
                    previa.tercero_id = t.id
                if not previa.observacion and n.observacion:
                    previa.observacion = n.observacion
                if not previa.encabezado and n.encabezado:
                    previa.encabezado = n.encabezado
                renglones(previa.id, n)
                res["completadas"] += 1
            elif previa.origen != ORIGEN:
                res["choques"] += 1
                avisos.append(f"NE {n.numero}: ya existe una NE con ese número emitida en la app; no se carga la del Excel")
            else:
                res["ya_estaban"] += 1
                if n.fecha_excel and previa.fecha != n.fecha:
                    # cargada antes con la fecha imposible del Excel: se corrige y se anota
                    previa.fecha = n.fecha
                    previa.observacion = n.observacion
                    res["fechas_corregidas"] += 1
                    avisos.append(f"NE {n.numero}: fecha {n.fecha_excel:%d/%m/%Y} corregida a {n.fecha:%d/%m/%Y}")
            continue
        tercero = tercero_de(n.cliente)
        doc = m.Documento(empresa_id=empresa_id, tipo="nota_entrega", numero=n.numero, fecha=n.fecha,
                          tercero_id=tercero.id if tercero else None, observacion=n.observacion, anulado=n.anulada,
                          origen=ORIGEN, creado_por=USUARIO, encabezado=n.encabezado)
        s.add(doc)
        s.flush()
        renglones(doc.id, n)
        existentes[n.numero] = doc
        res["nuevas"] += 1
    s.flush()
    return res, avisos


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    notas = nh.leer(argv[0])
    ultima = nh.ultima(notas)
    print(f"En el libro: {len(notas)} notas de entrega, la última es la {ultima}")
    with SesionLocal() as s:
        res, avisos = cargar(s, notas, config.empresa_id)
        for a in avisos:
            print(" -", a)
        print("Resultado:", ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in res.items()))
        proxima = NumeradorSql(s, config.empresa_id).ver_siguiente("nota_entrega")
        print(f"Próxima NE de la app: {proxima}")
        if ultima and proxima <= ultima:
            print(f"   ATENCIÓN: la app emitiría un número que ya usó el Excel. El día del corte fija la secuencia:\n"
                  f"   python -m app.secuencias fijar nota_entrega {ultima}")
        if "--cargar" in argv:
            s.commit()
            print("Guardado (solo consulta: no mueve inventario).")
        else:
            s.rollback()
            print("Vista previa: no se guardó nada. Agrega --cargar para guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
