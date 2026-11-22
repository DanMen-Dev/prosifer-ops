from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import generador_documentos, unidad
from app.errores import ErrorNegocio
from app.esquemas import (
    Anulacion, DetalleOrden, OrdenOut, OtLaminaIn, OtMaquilaIn, OtSlitterIn, PlanOtIn, PlanOtOut, ResumenOtLamina,
    ResumenOtMaquila, ResumenOtSlitter,
)
from app.seguridad import Actor, actor, editor, socio
from app.servicios import impresion, ordenes, planificacion

ruta = APIRouter(prefix="/api/ot", tags=["órdenes de trabajo"])
TIPOS = "^(slitter|lamina|ctf|maquila|losacero)$"


@ruta.post("/slitter", response_model=ResumenOtSlitter,
           summary="Registrar una orden de corte en slitter (primero con confirmar=false para revisar)")
def slitter(datos: OtSlitterIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return ordenes.registrar_slitter(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen,
                                         generador=generador_documentos())
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.post("/lamina", response_model=ResumenOtLamina,
           summary="Registrar una orden de corte a lámina, laminadora o CTF (primero con confirmar=false)")
def lamina(datos: OtLaminaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return ordenes.registrar_lamina(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen,
                                        generador=generador_documentos())
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.post("/maquila", response_model=ResumenOtMaquila,
           summary="Registrar una orden de maquila de perfiles (primero con confirmar=false)")
def maquila(datos: OtMaquilaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return ordenes.registrar_maquila(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen,
                                         generador=generador_documentos())
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.post("/planificar", response_model=PlanOtOut, status_code=201,
           summary="Crear una OC planificada: deja la pieza en proceso y permite imprimir la hoja de trabajo")
def planificar(datos: PlanOtIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return planificacion.planificar(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.get("/{id_}/hoja-trabajo", summary="Hoja de trabajo (antes del corte) de una OC planificada, en PDF",
          response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def hoja_trabajo(id_: int, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    if consultas.orden_visible(s, a.empresa_id, None, id_) is None:
        raise HTTPException(404, "orden inexistente")
    uow = unidad(s, a.empresa_id)
    o = ordenes.obtener(uow, id_)
    if o.estado not in ("planificada", "ejecutada", "anulada") or not (o.detalle or {}).get("plan"):
        raise HTTPException(404, "esta orden no se planificó: su hoja es la de resultados")
    if o.tipo == "slitter":   # el slitter usa la Orden de Slitter aprobada: el operador solo firma
        try:
            pdf = generador_documentos().orden_slitter(impresion.orden_slitter_planificada(uow, o))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        pdf = generador_documentos().hoja_trabajo(impresion.hoja_trabajo(uow, o))
    nombre = f"OC {o.tipo} {o.numero} - hoja de trabajo.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nombre}"'})


@ruta.post("/{id_}/cancelar-plan", response_model=OrdenOut,
           summary="Anular una OC planificada (todavía sin resultados): libera la pieza")
def cancelar_plan(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    if consultas.orden_visible(s, a.empresa_id, None, id_) is None:
        raise HTTPException(404, "orden inexistente")
    uow = unidad(s, a.empresa_id)
    if ordenes.obtener(uow, id_).estado != "planificada":
        raise HTTPException(422, "solo se cancelan órdenes planificadas; las demás las anula un socio")
    try:
        ordenes.anular(uow, id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return consultas.orden_out(consultas.orden_visible(s, a.empresa_id, None, id_), 0)


@ruta.get("/siguiente-numero")
def siguiente(tipo: str = Query(default="slitter", pattern=TIPOS), s: Session = Depends(sesion),
              a: Actor = Depends(editor)) -> dict:
    return {"tipo": tipo, "numero": ordenes.siguiente_numero(unidad(s, a.empresa_id), tipo)}


@ruta.get("", response_model=list[OrdenOut])
def listar(tipo: str | None = Query(default=None, pattern=TIPOS),
           desde: dt.date | None = None, hasta: dt.date | None = None,
           codigo: str | None = Query(default=None, description="Código de la pieza de entrada"),
           numero: int | None = None, incluir_anuladas: bool = False,
           estado: str | None = Query(default=None, pattern="^(planificada|ejecutada|cerrada|anulada)$",
                                      description="planificada = las OC por ejecutar"),
           limite: int = Query(default=200, le=2000),
           s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return consultas.ordenes(s, a.empresa_id, a.cliente, tipo=tipo, desde=desde, hasta=hasta, codigo=codigo,
                             numero=numero, incluir_anuladas=incluir_anuladas, limite=limite, estado=estado)


@ruta.get("/{id_}", response_model=DetalleOrden)
def detalle(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    d = consultas.detalle_orden(s, a.empresa_id, a.cliente, id_)
    if d is None:
        raise HTTPException(404, "orden inexistente")
    return d


@ruta.delete("/{id_}", response_model=OrdenOut,
             summary="Anular una orden (solo socio) si nada de lo producido se ha movido")
def anular(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    if consultas.orden_visible(s, a.empresa_id, a.cliente, id_) is None:
        raise HTTPException(404, "orden inexistente")
    try:
        ordenes.anular(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return consultas.orden_out(consultas.orden_visible(s, a.empresa_id, None, id_), 0)


@ruta.get("/{id_}/pdf/{doc}", summary="Hoja de la orden o etiquetas en PDF (copia guardada o reimpresión)",
          response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def pdf(id_: int, doc: str, piezas: str | None = Query(default=None, description="ids de piezas separados por coma"),
        atados: str | None = Query(default=None, description="Láminas y perfiles: números de atado o paquete, separados por coma"),
        regenerar: bool = False, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    if doc not in impresion.NOMBRES:
        raise HTTPException(404, "documento inexistente")
    if consultas.orden_visible(s, a.empresa_id, a.cliente, id_) is None:
        raise HTTPException(404, "orden inexistente")
    uow = unidad(s, a.empresa_id)
    o = ordenes.obtener(uow, id_)
    if o.tipo in ("lamina", "ctf"):
        nums = [int(x) for x in atados.split(",") if x.strip().isdigit()] if atados else None
        contenido = impresion.pdf_lamina(uow, o, doc, generador_documentos(), atados=nums, regenerar=regenerar)
    elif o.tipo == "maquila":
        nums = [int(x) for x in atados.split(",") if x.strip().isdigit()] if atados else None
        contenido = impresion.pdf_maquila(uow, o, doc, generador_documentos(), paquetes=nums, regenerar=regenerar)
    elif o.tipo == "slitter":
        ids = [int(x) for x in piezas.split(",") if x.strip().isdigit()] if piezas else None
        contenido = impresion.pdf_slitter(uow, o, doc, generador_documentos(), piezas=ids, regenerar=regenerar)
    else:
        raise HTTPException(422, f"todavía no hay PDF para órdenes de {o.tipo}")
    maquina = {"slitter": "Slitter", "lamina": "Laminadora", "ctf": "CTF", "maquila": "Maquila"}[o.tipo]
    nombre = f"{'OC' if doc == 'orden' else 'Etiquetas_OC'}_{maquina}_{o.numero}.pdf"
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nombre}"'})
