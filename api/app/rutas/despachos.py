"""Órdenes de despacho del cliente y notas de salida.

Pensadas también para el agente de IA: todo entra y sale en JSON, y cada escritura se revisa
primero con confirmar=false. El agente usa X-Api-Key con X-Usuario y X-Origen=agente, e indica el
cliente (tercero_id); un usuario cliente no lo indica: siempre pide sobre su propio inventario.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import generador_documentos, unidad
from app.errores import ErrorNegocio
from app.esquemas import Anulacion, NotaSalidaIn, OrdenDespachoIn, OrdenDespachoOut, ResumenSalida
from app.seguridad import Actor, actor, editor
from app.servicios import despachos

ruta = APIRouter(prefix="/api", tags=["despachos"])


def _error(exc: ErrorNegocio) -> HTTPException:
    return HTTPException(exc.codigo, str(exc))


def _pdf(contenido: bytes, nombre: str) -> Response:
    nombre = re.sub(r'[\\/:*?"<>|]+', "-", nombre).strip()[:150] + ".pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._,-]+", "", nombre)
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})


@ruta.post("/despachos", response_model=OrdenDespachoOut,
           summary="Crear una orden de despacho (primero con confirmar=false para revisar)")
def crear(datos: OrdenDespachoIn, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    try:
        return despachos.crear(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen, cliente=a.cliente)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.get("/despachos", response_model=list[OrdenDespachoOut],
          summary="Órdenes de despacho, la más reciente arriba (el cliente ve solo las suyas)")
def listar(estado: str | None = Query(default=None, pattern="^(pendiente|despachada|anulada)$"),
           tercero_id: int | None = None, desde: dt.date | None = None, hasta: dt.date | None = None,
           limite: int = Query(default=200, le=1000), s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return consultas.despachos(s, a.empresa_id, a.cliente, estado=estado, tercero_id=tercero_id, desde=desde,
                               hasta=hasta, limite=limite)


@ruta.get("/despachos/{id_}", response_model=OrdenDespachoOut)
def ver(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    d = consultas.despacho(s, a.empresa_id, a.cliente, id_)
    if d is None:
        raise HTTPException(404, "orden de despacho inexistente")
    return d


@ruta.post("/despachos/{id_}/anular", response_model=OrdenDespachoOut,
           summary="Anular una orden pendiente y liberar el material (el cliente, solo las suyas)")
def anular(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    try:
        return despachos.anular(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen,
                                cliente=a.cliente)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.post("/despachos/{id_}/nota-salida", response_model=ResumenSalida,
           summary="Emitir la nota de salida de una orden pendiente (primero con confirmar=false)")
def nota_salida(id_: int, datos: NotaSalidaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return despachos.nota_salida(unidad(s, a.empresa_id), id_, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.get("/despachos/{id_}/pdf", summary="Orden de despacho en PDF", response_class=Response,
          responses={200: {"content": {"application/pdf": {}}}})
def pdf_orden(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    d = consultas.despacho_impreso(s, a.empresa_id, a.cliente, id_)
    if d is None or d.tipo != "orden_despacho":
        raise HTTPException(404, "orden de despacho inexistente")
    return _pdf(generador_documentos().despacho(d), f"Orden de Despacho Nro {d.numero} - {d.cliente}")


@ruta.get("/notas-salida/{id_}/pdf", summary="Nota de salida en PDF (id del documento)", response_class=Response,
          responses={200: {"content": {"application/pdf": {}}}})
def pdf_nota_salida(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    d = consultas.despacho_impreso(s, a.empresa_id, a.cliente, id_)
    if d is None or d.tipo != "nota_salida":
        raise HTTPException(404, "nota de salida inexistente")
    return _pdf(generador_documentos().despacho(d), f"Nota de Salida Nro {d.numero} - {d.cliente}")
