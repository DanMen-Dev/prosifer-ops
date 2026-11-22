"""Conteos físicos en patio (auditorías de material).

Cada conteo queda registrado aunque cuadre: así el próximo descuadre se explica desde el último conteo
y no desde el inicio de los tiempos. Si no cuadra queda "pendiente" hasta que un socio (o Prosi, con
aprobación en el grupo) lo ajusta o lo descarta; también se puede ajustar al registrarlo (ajustar=true).

Quién: cualquiera del personal registra el conteo (socio, asistente, agente). Ajustar o descartar,
solo socio o agente, como los ajustes de inventario.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import modelos as m
from app.adaptadores.pdf.reportlab_conteos import pdf_conteos
from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import unidad
from app.errores import ErrorNegocio
from app.esquemas import ConteoIn, ConteoOut, ResolverConteoIn
from app.seguridad import Actor, editor, socio_o_agente
from app.servicios import salidas

ruta = APIRouter(prefix="/api", tags=["conteos"])
PUEDEN_AJUSTAR = ("socio", "integracion")


def _cantidad(n: Decimal, unidad_: str) -> str:
    return f"{int(n)} pzas" if unidad_ == "pzas" else f"{n:.3f} kg".replace(".000 kg", " kg")


def _saldo(p: m.Pieza) -> tuple[Decimal, str]:
    return (Decimal(p.saldo_unidades), "pzas") if p.saldo_unidades is not None else (p.saldo_kg, "kg")


def _ajustar(s: Session, a: Actor, c: m.Conteo, motivo_extra: str | None) -> None:
    motivo = "Conteo físico en patio"
    if c.contado_por:
        motivo += f" ({c.contado_por})"
    motivo += f": había {_cantidad(c.sistema, c.unidad)}, se contaron {_cantidad(c.contado, c.unidad)}"
    for extra in (c.observacion, motivo_extra):
        if extra and extra.strip():
            motivo += f" · {extra.strip()}"
    try:
        mv = salidas.ajustar(unidad(s, a.empresa_id), c.pieza_id, c.contado if c.unidad == "kg" else Decimal("0"),
                             motivo[:500], fecha=c.fecha, usuario=a.usuario, origen=a.origen,
                             saldo_nuevo_unidades=int(c.contado) if c.unidad == "pzas" else None)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    c.estado = "ajustado"
    c.ajuste_documento_id = mv.documento_id
    c.resolucion = motivo_extra
    c.resuelto_por, c.resuelto_en = a.usuario, dt.datetime.now(dt.timezone.utc)


@ruta.post("/piezas/{id_}/conteo", response_model=ConteoOut,
           summary="Registrar un conteo físico de la existencia (cuadre o no); ajustar=true para corregir el saldo")
def registrar(id_: int, datos: ConteoIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    if datos.clave_idempotencia:
        previo = s.scalar(select(m.Conteo).where(m.Conteo.empresa_id == a.empresa_id,
                                                 m.Conteo.clave_idempotencia == datos.clave_idempotencia))
        if previo is not None:
            return consultas.conteo_out(previo)
    p = consultas.pieza_visible(s, a.empresa_id, None, id_)
    if p is None or p.anulada:
        raise HTTPException(404, "pieza inexistente")
    sistema, unidad_ = _saldo(p)
    if unidad_ == "pzas" and datos.contado != datos.contado.to_integral_value():
        raise HTTPException(422, "esta existencia se cuenta en piezas enteras")
    diferencia = datos.contado - sistema
    if datos.ajustar and diferencia != 0 and a.rol not in PUEDEN_AJUSTAR:
        raise HTTPException(403, "registra el conteo sin ajustar: el ajuste lo hace un socio")
    c = m.Conteo(empresa_id=a.empresa_id, pieza_id=p.id, propietario_id=p.propietario_id,
                 fecha=datos.fecha or dt.date.today(), unidad=unidad_, sistema=sistema, contado=datos.contado,
                 diferencia=diferencia, estado="cuadra" if diferencia == 0 else "pendiente",
                 contado_por=(datos.contado_por or "").strip() or None,
                 observacion=(datos.observacion or "").strip() or None, origen=a.origen,
                 clave_idempotencia=datos.clave_idempotencia, creado_por=a.usuario)
    c.pieza, c.propietario = p, p.propietario
    if not datos.confirmar:
        return consultas.conteo_out(c).model_copy(update={"guardado": False, "id": None})
    s.add(c)
    s.flush()
    if datos.ajustar and diferencia != 0:
        _ajustar(s, a, c, None)
        s.flush()
    return consultas.conteo_out(c)


@ruta.post("/conteos/{id_}/resolver", response_model=ConteoOut,
           summary="Conteo pendiente: ajustar el saldo a lo contado, o descartarlo (el sistema estaba bien)")
def resolver(id_: int, datos: ResolverConteoIn, s: Session = Depends(sesion), a: Actor = Depends(socio_o_agente)):
    c = s.get(m.Conteo, id_)
    if c is None or c.empresa_id != a.empresa_id:
        raise HTTPException(404, "conteo inexistente")
    if c.estado != "pendiente":
        raise HTTPException(409, f"el conteo ya está {c.estado}")
    if datos.accion == "descartar":
        if not (datos.motivo or "").strip():
            raise HTTPException(422, "indica por qué se descarta")
        c.estado, c.resolucion = "descartado", datos.motivo.strip()
        c.resuelto_por, c.resuelto_en = a.usuario, dt.datetime.now(dt.timezone.utc)
        return consultas.conteo_out(c)
    p = s.get(m.Pieza, c.pieza_id)
    actual, _ = _saldo(p)
    if actual != c.sistema:
        raise HTTPException(409, f"el saldo cambió desde el conteo (había {_cantidad(c.sistema, c.unidad)}, ahora "
                                 f"{_cantidad(actual, c.unidad)}): cuenta de nuevo")
    _ajustar(s, a, c, (datos.motivo or "").strip() or None)
    s.flush()
    return consultas.conteo_out(c)


@ruta.get("/conteos", response_model=list[ConteoOut], summary="Historial de conteos físicos, el más reciente primero")
def listar(tercero_id: int | None = None, pieza_id: int | None = None, desde: dt.date | None = None,
           hasta: dt.date | None = None, estado: str | None = Query(default=None, description="cuadra,pendiente,…"),
           texto: str | None = None, limite: int = Query(default=500, le=5000),
           s: Session = Depends(sesion), a: Actor = Depends(editor)):
    return consultas.conteos(s, a.empresa_id, pieza_id=pieza_id, tercero_id=tercero_id, desde=desde, hasta=hasta,
                             estado=estado, texto=texto, limite=limite)


@ruta.get("/conteos/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}},
          summary="Resumen de conteos en PDF (fecha, producto, antes, ajuste, después), por cliente y fechas")
def listar_pdf(tercero_id: int | None = None, desde: dt.date | None = None, hasta: dt.date | None = None,
               estado: str | None = None, texto: str | None = None,
               s: Session = Depends(sesion), a: Actor = Depends(editor)):
    if desde and hasta and hasta < desde:
        raise HTTPException(422, "la fecha final es anterior a la inicial")
    lista = consultas.conteos(s, a.empresa_id, tercero_id=tercero_id, desde=desde, hasta=hasta, estado=estado,
                              texto=texto, limite=5000)
    tercero = None
    if tercero_id:
        t = s.get(m.Tercero, tercero_id)
        if t is None or t.empresa_id != a.empresa_id:
            raise HTTPException(404, "cliente inexistente")
        tercero = t.nombre
    nombre = "Conteos en patio" + (f" {tercero}" if tercero else "") + \
        (f" {desde:%d-%m-%Y}" if desde else "") + (f" al {hasta:%d-%m-%Y}" if hasta else "") + ".pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._-]+", "", nombre) or "conteos.pdf"
    return Response(pdf_conteos(lista, tercero=tercero, desde=desde, hasta=hasta), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})
