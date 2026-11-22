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
from app.esquemas import (
    AjusteIn, Anulacion, CorreccionNEIn, DescargaHistoricaIn, DetalleDocumento, DocumentoOut, EncabezadoNE, LiberacionIn, MovimientoOut, NotaEntregaIn,
    ResumenCorreccionNE, ResumenSalida,
)
from app.seguridad import Actor, actor, editor, socio, socio_o_agente
from app.servicios import salidas

ruta = APIRouter(prefix="/api", tags=["salidas"])
TIPOS = "^(nota_entrega|nota_salida|liberacion|ajuste|entrada)$"   # las entradas solo si se piden


def _error(exc: ErrorNegocio) -> HTTPException:
    return HTTPException(exc.codigo, str(exc))


@ruta.post("/salidas/nota-entrega", response_model=ResumenSalida,
           summary="Registrar una nota de entrega (primero con confirmar=false para revisar)")
def nota_entrega(datos: NotaEntregaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return salidas.nota_entrega(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.post("/salidas/liberacion", response_model=ResumenSalida,
           summary="Liberar piezas completas a otro dueño (primero con confirmar=false para revisar)")
def liberacion(datos: LiberacionIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return salidas.liberacion(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.post("/piezas/{id_}/ajuste", response_model=MovimientoOut,
           summary="Ajustar el saldo de una pieza (socio, o el agente con aprobación; con motivo)")
def ajuste(id_: int, datos: AjusteIn, s: Session = Depends(sesion), a: Actor = Depends(socio_o_agente)):
    try:
        mv = salidas.ajustar(unidad(s, a.empresa_id), id_, datos.saldo_nuevo_kg, datos.motivo, fecha=datos.fecha,
                             usuario=a.usuario, origen=a.origen, saldo_nuevo_unidades=datos.saldo_nuevo_unidades)
    except ErrorNegocio as exc:
        raise _error(exc) from exc
    return consultas.movimiento_out(mv, "ajuste", None, para_cliente=False)


@ruta.get("/documentos", response_model=list[DocumentoOut])
def documentos(tipo: str | None = Query(default=None, pattern=TIPOS), numero: str | None = None,
               tercero_id: int | None = None, desde: dt.date | None = None, hasta: dt.date | None = None,
               incluir_anulados: bool = False, limite: int = Query(default=200, le=2000),
               s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return consultas.documentos(s, a.empresa_id, a.cliente, tipo=tipo, numero=numero, tercero_id=tercero_id,
                                desde=desde, hasta=hasta, incluir_anulados=incluir_anulados, limite=limite)


@ruta.get("/documentos/{id_}", response_model=DetalleDocumento)
def documento(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    d = consultas.detalle_documento(s, a.empresa_id, a.cliente, id_)
    if d is None:
        raise HTTPException(404, "documento inexistente")
    return d


@ruta.post("/documentos/{id_}/descargar", response_model=ResumenSalida,
           summary="Descargar del inventario lo que salió con una NE histórica (solo socio; primero confirmar=false)")
def descargar_historica(id_: int, datos: DescargaHistoricaIn, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    try:
        return salidas.descargar_historica(unidad(s, a.empresa_id), id_, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.get("/documentos/{id_}/pdf", summary="Nota de entrega en PDF, formato de Prosifer",
          response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def pdf_nota(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    ne = consultas.ne_impresa(s, a.empresa_id, a.cliente, id_)
    if ne is None:
        raise HTTPException(404, "nota de entrega inexistente")
    nombre = re.sub(r'[\\/:*?"<>|]+', "-", f"Nota de Entrega {ne.numero} {ne.cliente}").strip()[:150] + ".pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._,-]+", "", nombre)
    return Response(generador_documentos().nota_entrega(ne), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})


def _numero_recibo(s: Session, a: Actor, id_: int) -> int:
    """El recibo toma su número la primera vez que se pide y lo guarda en todas las entradas del grupo."""
    from app.adaptadores.sql.numerador import NumeradorSql

    d = consultas.documento_visible(s, a.empresa_id, a.cliente, id_)
    if d is None or d.tipo != "entrada":
        raise HTTPException(404, "entrada inexistente")
    grupo = consultas.grupo_entrada(s, a.empresa_id, d)
    numero = next((int(g.encabezado["recibo"]) for g in grupo if g.encabezado and g.encabezado.get("recibo")), None)
    if numero is None:
        numero = NumeradorSql(s, a.empresa_id).siguiente("recibo_entrada")
        for g in grupo:
            g.encabezado = {**(g.encabezado or {}), "recibo": numero}
        s.flush()
    return numero


@ruta.post("/documentos/{id_}/recibo/numero", summary="Número del recibo de entrada (lo asigna si aún no tiene)")
def numero_recibo(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return {"numero": _numero_recibo(s, a, id_)}


@ruta.get("/documentos/{id_}/recibo", summary="Recibo de entrada de material en PDF (agrupa las entradas del "
          "mismo cliente, documento y fecha)", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def recibo_entrada(id_: int, mitad: str = Query(default="arriba", pattern="^(arriba|abajo)$"),
                   s: Session = Depends(sesion), a: Actor = Depends(actor)):
    numero = _numero_recibo(s, a, id_)
    recibo = consultas.recibo_entrada(s, a.empresa_id, a.cliente, id_, numero)
    if recibo is None:
        raise HTTPException(404, "entrada inexistente")
    nombre = re.sub(r'[\\/:*?"<>|]+', "-", f"Recibo de Entrada Nro {numero} - {recibo.cliente}").strip()[:150] + ".pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._,-]+", "", nombre)
    return Response(generador_documentos().recibo_entrada(recibo, mitad == "abajo"), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})


@ruta.put("/documentos/{id_}/encabezado", response_model=DocumentoOut,
          summary="Completar los datos de la NE impresa (chofer, placa, domicilio…); no mueve inventario")
def encabezado(id_: int, datos: EncabezadoNE, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        salidas.editar_encabezado(unidad(s, a.empresa_id), id_, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc
    d = consultas.detalle_documento(s, a.empresa_id, None, id_)
    return d.documento


@ruta.post("/documentos/{id_}/correccion", response_model=ResumenCorreccionNE,
           summary="Corregir cantidad o producto de una NE de la app (primero con confirmar=false)")
def corregir(id_: int, datos: CorreccionNEIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    if consultas.documento_visible(s, a.empresa_id, a.cliente, id_) is None:
        raise HTTPException(404, "documento inexistente")
    try:
        return salidas.corregir_nota(unidad(s, a.empresa_id), id_, datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc


@ruta.delete("/documentos/{id_}", response_model=DocumentoOut,
             summary="Anular una nota de entrega, liberación o ajuste (solo socio)")
def anular(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    if consultas.documento_visible(s, a.empresa_id, a.cliente, id_) is None:
        raise HTTPException(404, "documento inexistente")
    try:
        salidas.anular(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise _error(exc) from exc
    return consultas.documento_out(consultas.documento_visible(s, a.empresa_id, None, id_), 0, 0)
