"""Cotizaciones (USD): servicios de corte y maquila, carga y manejo, almacenamiento y venta de material."""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import modelos as m
from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import generador_documentos, unidad
from app.errores import ErrorNegocio
from app.esquemas import AbonoCotizacion, Anulacion, ComprobanteIn, BorradorCotizacion, CotizacionIn, CotizacionOut
from app.seguridad import Actor, actor, editor
from app.servicios import cotizaciones

ruta = APIRouter(prefix="/api/cotizaciones", tags=["cotizaciones"])


def _ver(s: Session, a: Actor, id_: int) -> CotizacionOut:
    r = consultas.cotizacion(s, a.empresa_id, id_, a.cliente)
    if r is None:
        raise HTTPException(404, "cotización inexistente")
    return consultas.cotizacion_out(r, para_cliente=a.cliente is not None)


@ruta.get("", response_model=list[CotizacionOut],
          summary="Cotizaciones, la más reciente arriba (un cliente ve solo las emitidas a su nombre)")
def listar(tercero_id: int | None = None, q: str | None = Query(default=None, description="Número (D-2940) o cliente"),
           orden_trabajo_id: int | None = None, desde: dt.date | None = None, hasta: dt.date | None = None,
           incluir_anuladas: bool = True, limite: int = Query(default=200, le=2000),
           s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return consultas.cotizaciones(s, a.empresa_id, tercero_id=tercero_id, q=q, orden_trabajo_id=orden_trabajo_id,
                                  limite=limite, cliente=a.cliente, desde=desde, hasta=hasta,
                                  incluir_anuladas=incluir_anuladas)


@ruta.get("/desde-orden/{orden_id}", response_model=BorradorCotizacion,
          summary="Borrador para cotizar una orden de corte o maquila (servicio según máquina y acero, y los kg)")
def desde_orden(orden_id: int, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return cotizaciones.borrador_desde_orden(unidad(s, a.empresa_id), orden_id)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.post("", response_model=CotizacionOut, status_code=201, summary="Emitir una cotización (número correlativo)")
def crear(datos: CotizacionIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    uow = unidad(s, a.empresa_id)
    capturas = [_decodificar(x.comprobante) for x in datos.abonos]
    try:
        d = cotizaciones.crear(uow, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    if d.id is None:   # vista previa: no se guardó nada
        t = uow.terceros.obtener(d.tercero_id)
        return cotizaciones.vista(d, t.nombre if t else None)
    s.flush()
    if any(x is not None for x in capturas):   # con clave repetida no se duplican: ya tienen comprobante_id
        r = consultas.cotizacion(s, a.empresa_id, d.id)
        for i, (x, contenido) in enumerate(zip(datos.abonos, capturas)):
            if contenido is not None:
                _adjuntar(s, a, r, i, x.comprobante, contenido)
        s.flush()
    return _ver(s, a, d.id)


@ruta.get("/{id_}", response_model=CotizacionOut)
def ver(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return _ver(s, a, id_)


@ruta.post("/{id_}/anular", response_model=CotizacionOut)
def anular(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        cotizaciones.anular(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    s.flush()
    return _ver(s, a, id_)


def _decodificar(c: ComprobanteIn | None) -> bytes | None:
    if c is None:
        return None
    try:
        contenido = base64.b64decode(c.base64.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "el comprobante no es un base64 válido") from exc
    if len(contenido) > 6 * 1024 * 1024:
        raise HTTPException(422, "el comprobante pasa de 6 MB")
    return contenido


def _adjuntar(s: Session, a: Actor, r, i: int, c: ComprobanteIn, contenido: bytes) -> None:
    """Guarda la captura del pago y la enlaza al abono i (si ese abono no tiene ya una)."""
    abonos = list((r.encabezado or {}).get("abonos", []))
    if not (0 <= i < len(abonos)) or abonos[i].get("comprobante_id"):
        return
    arch = m.Archivo(empresa_id=a.empresa_id, ref_tabla="cotizacion", ref_id=r.id, creado_por=a.usuario,
                     nombre=(c.nombre or "comprobante")[:120], tipo_mime=c.tipo_mime, contenido=contenido)
    s.add(arch)
    s.flush()
    abonos[i] = {**abonos[i], "comprobante_id": arch.id}
    r.encabezado = {**(r.encabezado or {}), "abonos": abonos}


@ruta.post("/{id_}/abonos", response_model=CotizacionOut,
           summary="Anotar un pago recibido, con su referencia y, si se tiene, la captura del pago")
def abonar(id_: int, datos: AbonoCotizacion, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    contenido = _decodificar(datos.comprobante)
    try:
        cotizaciones.abonar(unidad(s, a.empresa_id), id_, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    if contenido is not None:
        s.flush()
        r = consultas.cotizacion(s, a.empresa_id, id_)
        _adjuntar(s, a, r, len((r.encabezado or {}).get("abonos", [])) - 1, datos.comprobante, contenido)
    s.flush()
    return _ver(s, a, id_)


@ruta.get("/{id_}/comprobantes/{archivo_id}", summary="La captura de un pago de la cotización",
          response_class=Response)
def comprobante(id_: int, archivo_id: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    if consultas.cotizacion(s, a.empresa_id, id_, a.cliente) is None:
        raise HTTPException(404, "cotización inexistente")
    arch = s.get(m.Archivo, archivo_id)
    if arch is None or arch.empresa_id != a.empresa_id or arch.ref_tabla != "cotizacion" or arch.ref_id != id_:
        raise HTTPException(404, "comprobante inexistente")
    nombre = re.sub(r"[^A-Za-z0-9 ._-]+", "", arch.nombre) or "comprobante"
    return Response(arch.contenido, media_type=arch.tipo_mime,
                    headers={"Content-Disposition": f'inline; filename="{nombre}"'})


@ruta.get("/{id_}/pdf", summary="Cotización en PDF, formato de Prosifer", response_class=Response,
          responses={200: {"content": {"application/pdf": {}}}})
def pdf(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    q = consultas.cotizacion_impresa(s, a.empresa_id, id_, a.cliente)
    if q is None:
        raise HTTPException(404, "cotización inexistente")
    nombre = re.sub(r'[\\/:*?"<>|]+', "-", f"Cotizacion D-{q.numero} {q.cliente}").strip()[:150] + ".pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._,-]+", "", nombre)
    return Response(generador_documentos().cotizacion(q), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})
