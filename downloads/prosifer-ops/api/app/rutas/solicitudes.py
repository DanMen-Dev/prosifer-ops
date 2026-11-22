"""Solicitudes de orden de corte que precarga el cliente (o el agente en su nombre).

El cliente la envía; Prosifer la autoriza (pasándola, con cambios si hace falta, a una OC planificada)
o la rechaza con un motivo; el cliente puede cancelarla mientras está pendiente.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import unidad
from app.errores import ErrorNegocio
from app.esquemas import Anulacion, AprobacionSolicitudIn, PlanOtOut, SolicitudCorteIn, SolicitudCorteOut
from app.seguridad import Actor, actor, editor
from app.servicios import solicitudes

ruta = APIRouter(prefix="/api/solicitudes-corte", tags=["solicitudes de corte"])


def _ver(s: Session, a: Actor, id_: int) -> SolicitudCorteOut:
    out = consultas.solicitud_corte(s, a.empresa_id, a.cliente, id_)
    if out is None:
        raise HTTPException(404, "solicitud inexistente")
    return out


@ruta.post("", response_model=SolicitudCorteOut, status_code=201,
           summary="Enviar una solicitud de orden de corte (slitter, láminas o maquila) para que Prosifer la revise")
def crear(datos: SolicitudCorteIn, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    try:
        d = solicitudes.crear(unidad(s, a.empresa_id), datos, cliente=a.cliente, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    s.flush()
    return _ver(s, a, d.id)


@ruta.get("", response_model=list[SolicitudCorteOut],
          summary="Solicitudes, la más reciente arriba (el cliente ve solo las suyas)")
def listar(estado: str | None = Query(default=None, pattern="^(pendiente|aprobada|rechazada|cancelada)$"),
           limite: int = Query(default=200, le=1000), s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return consultas.solicitudes_corte(s, a.empresa_id, a.cliente, estado=estado, limite=limite)


@ruta.get("/{id_}", response_model=SolicitudCorteOut)
def ver(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return _ver(s, a, id_)


@ruta.post("/{id_}/cancelar", response_model=SolicitudCorteOut, summary="El cliente retira su solicitud pendiente")
def cancelar(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    try:
        solicitudes.cancelar(unidad(s, a.empresa_id), id_, datos.motivo, cliente=a.cliente, usuario=a.usuario,
                             origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return _ver(s, a, id_)


@ruta.post("/{id_}/rechazar", response_model=SolicitudCorteOut, summary="Rechazar una solicitud (el cliente ve el motivo)")
def rechazar(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        solicitudes.rechazar(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return _ver(s, a, id_)


@ruta.post("/{id_}/aprobar", response_model=PlanOtOut, status_code=201,
           summary="Autorizar: crea la OC planificada definitiva (con los cambios de Prosifer) y enlaza la solicitud")
def aprobar(id_: int, datos: AprobacionSolicitudIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return solicitudes.aprobar(unidad(s, a.empresa_id), id_, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
