from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.adaptadores.sql import consultas
from app.db import sesion
from app.dependencias import generador_documentos, unidad
from app.errores import ErrorNegocio
from app.esquemas import (
    Anulacion, CambioPieza, EntradaBobinaIn, EntradaExistenciaIn, Existencias, FichaPieza, PiezaOut, ResumenEntrada,
    ResumenEntradaExistencia, UnionExistencias,
)
from app.seguridad import Actor, actor, editor, socio
from app.servicios import inventario, planificacion

ruta = APIRouter(prefix="/api", tags=["inventario"])
pieza_out = consultas.pieza_out  # la usan otras rutas


@ruta.post("/entradas/bobinas", response_model=ResumenEntrada,
           summary="Registrar la entrada de una bobina (primero con confirmar=false para validar)")
def entrada_bobina(datos: EntradaBobinaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return inventario.registrar_entrada_bobina(unidad(s, a.empresa_id), datos, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.post("/entradas/existencias", response_model=ResumenEntradaExistencia,
           summary="Entrada por piezas de láminas, perfiles o productos generales (primero con confirmar=false)")
def entrada_existencia(datos: EntradaExistenciaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    try:
        return inventario.registrar_entrada_existencia(unidad(s, a.empresa_id), datos, usuario=a.usuario,
                                                       origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.get("/existencias", response_model=Existencias)
def existencias(
    tipo: str | None = Query(default=None, pattern="^(bobina|fleje|lamina|perfil|general)$"),
    propietario_id: int | None = None,
    tipo_acero: str | None = Query(default=None, description="Código: HP, HN, GV, ES, PP, AL"),
    espesor_mm: Decimal | None = None,
    ancho_mm: Decimal | None = None,
    codigo: str | None = Query(default=None, description="Busca en el código físico o de producto (también parte del código)"),
    espesor_aprox: Decimal | None = Query(default=None, gt=0,
                                          description="Espesor con tolerancia de ±0,06 mm (0,58 encuentra 0,60)"),
    ancho_aprox: Decimal | None = Query(default=None, gt=0, description="Ancho con tolerancia de ±2 %"),
    q: str | None = Query(default=None, max_length=120,
                          description="Palabras que deben estar en la descripción o los códigos"),
    incluir_agotadas: bool = False,
    limite: int = Query(default=500, le=5000),
    s: Session = Depends(sesion), a: Actor = Depends(actor),
):
    r = consultas.existencias(s, a.empresa_id, a.cliente, tipo=tipo, propietario_id=propietario_id,
                              tipo_acero=tipo_acero, espesor_mm=espesor_mm, ancho_mm=ancho_mm, codigo=codigo,
                              incluir_agotadas=incluir_agotadas, limite=limite, espesor_aprox=espesor_aprox,
                              ancho_aprox=ancho_aprox, texto=q)
    planificacion.marcar_ocupadas(unidad(s, a.empresa_id), r.piezas)
    return r


NOMBRE_REPORTE = {"bobina": "Inventario de Bobinas", "fleje": "Inventario de Flejes", "lamina": "Inventario de Laminas",
                  "perfil": "Inventario de Perfiles", "general": "Inventario de Productos Generales",
                  "todas": "Inventario Total"}


@ruta.get("/reportes/inventario", summary="Reporte de inventario en PDF de un cliente, por categoría o total, "
          "para auditar en patio", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def reporte_inventario(
    categoria: str = Query(default="todas", pattern="^(bobina|fleje|lamina|perfil|general|todas)$"),
    propietario_id: int | None = Query(default=None, description="Cliente dueño. Un usuario cliente ve solo lo suyo"),
    s: Session = Depends(sesion), a: Actor = Depends(actor),
):
    if a.cliente is None and propietario_id is None:
        raise HTTPException(422, "elige el cliente del reporte")
    tipos = list(consultas.CATEGORIAS) if categoria == "todas" else [categoria]
    r = consultas.reporte_inventario(s, a.empresa_id, a.cliente, propietario_id or 0, tipos,
                                     "Prosifer" if a.es_cliente else a.usuario)
    if r is None:
        raise HTTPException(404, "cliente inexistente")
    nombre = re.sub(r'[\\/:*?"<>|]+', "-", f"{NOMBRE_REPORTE[categoria]} - {r.cliente} - {r.generado:%d-%m-%Y}")
    nombre = nombre.strip()[:150] + ".pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._,-]+", "", nombre)
    return Response(generador_documentos().reporte_inventario(r), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})


@ruta.get("/piezas/{id_}", response_model=FichaPieza)
def ficha(id_: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    f = consultas.ficha(s, a.empresa_id, a.cliente, id_)
    if f is None:
        raise HTTPException(404, "pieza inexistente")
    planificacion.marcar_ocupadas(unidad(s, a.empresa_id), [f.pieza])
    return f


def _visible(s: Session, a: Actor, id_: int) -> None:
    if consultas.pieza_visible(s, a.empresa_id, a.cliente, id_) is None:
        raise HTTPException(404, "pieza inexistente")


@ruta.patch("/piezas/{id_}", response_model=PiezaOut,
            summary="Corregir datos descriptivos de una pieza (queda en la auditoría)")
def editar_pieza(id_: int, datos: CambioPieza, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    _visible(s, a, id_)
    try:
        p = inventario.editar_pieza(unidad(s, a.empresa_id), id_, datos.model_dump(exclude_unset=True),
                                    usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return consultas.pieza_out(p)


@ruta.post("/piezas/{id_}/unir", response_model=PiezaOut,
           summary="Unir esta existencia a otra del mismo dueño (el mismo material con dos códigos). Solo socio")
def unir(id_: int, datos: UnionExistencias, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    _visible(s, a, id_)
    _visible(s, a, datos.destino_id)
    try:
        inventario.unir_existencias(unidad(s, a.empresa_id), id_, datos.destino_id, datos.motivo,
                                    usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    s.flush()
    return consultas.pieza_out(consultas.pieza_visible(s, a.empresa_id, None, datos.destino_id))


@ruta.delete("/piezas/{id_}", response_model=PiezaOut,
             summary="Anular una pieza (solo socio). No se borra: queda marcada como anulada con su motivo")
def anular_pieza(id_: int, datos: Anulacion, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    _visible(s, a, id_)
    try:
        p = inventario.anular_pieza(unidad(s, a.empresa_id), id_, datos.motivo, usuario=a.usuario, origen=a.origen)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
    return consultas.pieza_out(p)
