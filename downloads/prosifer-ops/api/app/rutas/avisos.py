"""Avisos de entrada: el cliente (o el agente en su nombre) anuncia material que va a llegar al patio."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import unidad
from app.errores import ErrorNegocio
from app.esquemas import Anulacion, AvisoEntradaIn, AvisoEntradaOut, EnlaceEntradaAviso, NotaAviso
from app.seguridad import Actor, actor, editor
from app.servicios import avisos

ruta = APIRouter(prefix="/api/avisos-entrada", tags=["avisos de entrada"])


def _ver(s: Session, a: Actor, id_: int) -> AvisoEntradaOut:
    out = consultas.aviso_entrada(s, a.empresa_id, a.cliente, id_)
    if out is None:
        raise HTTPException(404, "aviso inexistente")
    return out


@ruta.post("", response_model=AvisoEntradaOut, status_code=201,
           summary="Anunciar material que va a llegar al patio (no mueve inventario)")
def crear(datos: AvisoEntradaIn, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    hoy = dt.datetime.now(ZoneInfo("America/Caracas")).date()
    try:
        d = avisos.crear(unidad(s, a.empresa_id), datos, cliente=a.cliente, usuario=a.usuario, origen=a.origen, hoy=hoy)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    s.flush()
    return _ver(s, a, d.id)


@ruta.get("", response_model=list[AvisoEntradaOut], summary="Avisos, el más reciente arriba (el cliente ve solo los suyos)")
def listar(estado: str | None = Query(default=None, pattern="^(pendiente|recibido|rechazado|cancelado)$"),
           limite: int = Query(default=200, le=1000), s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return consultas.avisos_entrada(s, a.empresa_id, a.cliente, estado=estado, limite=limite)


@ruta.get("/{id_}", response_model=AvisoEntradaOut)
def ver(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return _ver(s, a, id_)


@ruta.post("/{id_}/cancelar", response_model=AvisoEntradaOut, summary="El cliente retira su aviso pendiente")
def cancelar(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    try:
        avisos.cancelar(unidad(s, a.empresa_id), id_, datos.motivo, cliente=a.cliente, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return _ver(s, a, id_)


@ruta.post("/{id_}/recibir", response_model=AvisoEntradaOut, summary="Marcar el aviso como recibido (material en patio)")
def recibir(id_: int, datos: NotaAviso, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        avisos.recibir(unidad(s, a.empresa_id), id_, datos.nota, usuario=a.usuario, origen=a.origen, forzar=datos.forzar)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return _ver(s, a, id_)


@ruta.post("/{id_}/renglones/{indice}/entrada", response_model=AvisoEntradaOut,
           summary="Enlazar al renglón del aviso la entrada que se registró (pieza o existencia que sumó)")
def enlazar(id_: int, indice: int, datos: EnlaceEntradaAviso, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        avisos.enlazar_entrada(unidad(s, a.empresa_id), id_, indice, datos.pieza_id, datos.texto,
                               usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    s.flush()
    return _ver(s, a, id_)


@ruta.post("/{id_}/rechazar", response_model=AvisoEntradaOut, summary="Rechazar el aviso o marcar que no llegó (el cliente ve el motivo)")
def rechazar(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        avisos.rechazar(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return _ver(s, a, id_)
