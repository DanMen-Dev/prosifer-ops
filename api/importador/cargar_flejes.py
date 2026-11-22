"""Carga los flejes y las órdenes de slitter del libro de bobinas.

Requiere que las bobinas ya estén cargadas (importador.cargar). Uso:
    python -m importador.cargar_flejes /datos/Inventario_de_Bobinas.xlsm

Antes de escribir corre la paridad contra ConsolidadoFlejes. Se niega si ya hay
órdenes de slitter en la base. Para repetir la carga: importador.cargar --reemplazar
(borra bobinas, flejes y órdenes) y después este comando.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from sqlalchemy import func, select

from app import modelos as m
from app.config import config
from app.db import SesionLocal
from app.dominio import slitter
from importador import flejes
from importador.cargar import Cache

USUARIO = "importador-flejes"


def _estatus(txt: str | None) -> str | None:
    t = (txt or "").strip().lower()
    return t if t in ("total", "parcial") else None


def cargar(s, plan: flejes.PlanFlejes, empresa_id: int) -> dict:
    c = Cache(s, empresa_id)
    piezas = {flejes.clave(p.codigo_fisico): p for p in s.scalars(
        select(m.Pieza).where(m.Pieza.empresa_id == empresa_id, m.Pieza.anulada.is_(False)))}
    docs_ot = {(d.numero, d.fecha): d for d in s.scalars(
        select(m.Documento).where(m.Documento.empresa_id == empresa_id, m.Documento.tipo == "ot_slitter"))}

    # 1. Órdenes de slitter
    ot_id: dict[int, m.OrdenTrabajo] = {}
    for o in plan.ots:
        bobina = piezas.get(flejes.clave(o.codigo_bobina))
        dueno = c.tercero(o.propietario) if o.propietario else (bobina.propietario if bobina else None)
        producido = sum((kg for _, kg, _ in o.cortes), Decimal("0"))
        doc = docs_ot.get((str(o.numero) if o.numero else None, o.fecha))
        orden = m.OrdenTrabajo(
            empresa_id=empresa_id, tipo="slitter", numero=o.numero or 0, fecha=o.fecha, estado="cerrada",
            pieza_id=bobina.id if bobina else None, propietario=dueno, estatus_corte=_estatus(o.estatus),
            kg_consumido=o.kg, kg_producido=producido, kg_scrap=o.scrap_kg, paradas=o.paradas, calidad=o.calidad,
            documento_id=doc.id if doc else None, origen="importacion", creado_por=USUARIO,
            observacion=None if bobina else f"bobina {o.codigo_bobina} no encontrada",
            detalle={
                "ancho_bobina_mm": str(bobina.ancho_mm) if bobina and bobina.ancho_mm else None,
                "cortes": [{"posicion": i, "ancho_mm": str(a), "rollos": n, "kg": str(kg)}
                           for i, (a, kg, n) in enumerate(o.cortes, start=1)],
                "scrap": {"ancho_mm": str(o.scrap_ancho) if o.scrap_ancho else "0", "kg": str(o.scrap_kg)},
                "fila_excel": f"ProductoF!{o.fila}",
            })
        s.add(orden)
        ot_id[o.fila] = orden
    s.flush()

    # 2. Rollos de fleje
    creados = enriquecidos = 0
    for rp in plan.rollos.values():
        r = rp.rollo
        madre = piezas.get(flejes.clave(r.codigo_bobina))
        orden = ot_id.get(rp.ot.fila) if rp.ot else None
        if rp.fusionado and flejes.clave(r.codigo) in piezas:
            # Reenviado a Entradas: ya existe como pieza. Solo se le agrega su origen.
            p = piezas[flejes.clave(r.codigo)]
            p.pieza_origen_id = madre.id if madre else None
            p.orden_trabajo_id = orden.id if orden else None
            p.tipo = "fleje"
            if not p.calidad and r.calidad:
                p.calidad = r.calidad[:10]
            enriquecidos += 1
            continue
        tipo = c.tipo(r.tipo_acero)
        descripcion = None
        if tipo and r.espesor and r.ancho:
            descripcion = slitter.descripcion_fleje(tipo.codigo, r.espesor, r.ancho)
        dueno_inicial = c.tercero(r.propietario) or (madre.propietario if madre else c.tercero("Sin propietario registrado"))
        dueno_final = c.tercero(rp.propietario) or dueno_inicial
        p = m.Pieza(
            empresa_id=empresa_id, tipo="fleje", codigo_fisico=r.codigo,
            codigo_producto=(flejes.producto_de(r.codigo) or "")[:40] or None, descripcion=descripcion,
            tipo_acero=tipo, norma=c.norma(r.norma), espesor_mm=r.espesor, ancho_mm=r.ancho,
            calidad=(r.calidad or "")[:10] or None, propietario=dueno_final,
            pieza_origen_id=madre.id if madre else None, orden_trabajo_id=orden.id if orden else None,
            fecha_entrada=r.fecha, peso_entrada_kg=r.peso, saldo_kg=rp.saldo, estado=rp.estado, creado_por=USUARIO)
        s.add(p)
        s.flush()
        saldo = Decimal("0")
        dueno_actual = dueno_inicial
        for mv in rp.movimientos:
            saldo += mv.kg
            doc = c.documento(mv.documento_tipo, mv.documento_numero, mv.fecha)
            nuevo = dueno_inicial if mv.tipo == "produccion" else (
                c.tercero(mv.propietario_nuevo) if mv.propietario_nuevo else None)
            s.flush()
            s.add(m.Movimiento(
                empresa_id=empresa_id, pieza_id=p.id, tipo=mv.tipo, kg=mv.kg, saldo_despues_kg=saldo,
                propietario_anterior_id=dueno_actual.id if nuevo is not None and mv.tipo != "produccion" else None,
                propietario_nuevo_id=nuevo.id if nuevo is not None else None, documento_id=doc.id, fecha=mv.fecha,
                origen="importacion", observacion="; ".join(x for x in (mv.nota, mv.fila_origen) if x),
                creado_por=USUARIO))
            if nuevo is not None:
                dueno_actual = nuevo
        creados += 1
    s.flush()
    return {"ordenes": len(ot_id), "rollos_creados": creados, "rollos_enriquecidos": enriquecidos}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    libro = flejes.leer(argv[1])
    plan = flejes.construir(libro)
    if not flejes.informe(flejes.comparar(libro, plan)):
        print("\nNo se carga: la existencia de flejes no coincide con ConsolidadoFlejes.")
        return 1
    with SesionLocal() as s:
        bobinas = s.scalar(select(func.count(m.Pieza.id)).where(m.Pieza.empresa_id == config.empresa_id))
        if not bobinas:
            print("\nPrimero carga las bobinas: python -m importador.cargar <libro>")
            return 1
        ots = s.scalar(select(func.count(m.OrdenTrabajo.id)).where(
            m.OrdenTrabajo.empresa_id == config.empresa_id, m.OrdenTrabajo.tipo == "slitter"))
        if ots:
            print(f"\nYa hay {ots} órdenes de slitter en la base. Para repetir la carga usa primero "
                  "importador.cargar --reemplazar.")
            return 1
        r = cargar(s, plan, config.empresa_id)
        s.commit()
    print(f"\nCargadas {r['ordenes']} órdenes de slitter y {r['rollos_creados']} rollos de fleje; "
          f"{r['rollos_enriquecidos']} rollos que ya estaban en Entradas quedaron ligados a su bobina y su OC.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
