from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import modelos as m
from app.db import sesion
from app.esquemas import CambioCatalogo, NormaIn, NormaOut, TipoAceroIn, TipoAceroOut
from app.seguridad import Actor, actor, editor
from app.adaptadores.sql import crud

ruta = APIRouter(prefix="/api/catalogos", tags=["catálogos"])


def _crear(s: Session, objeto):
    s.add(objeto)
    try:
        s.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "ya existe un registro con ese nombre o código") from exc
    return objeto


def _propio(s: Session, modelo, id_: int, a: Actor):
    obj = s.get(modelo, id_)
    if obj is None or obj.empresa_id != a.empresa_id:
        raise HTTPException(404, "no existe")
    return obj


@ruta.get("/tipos-acero", response_model=list[TipoAceroOut])
def tipos_acero(s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return s.scalars(select(m.TipoAcero).where(m.TipoAcero.empresa_id == a.empresa_id)
                     .order_by(m.TipoAcero.codigo)).all()


@ruta.post("/tipos-acero", response_model=TipoAceroOut, status_code=201)
def crear_tipo_acero(datos: TipoAceroIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    return _crear(s, m.TipoAcero(empresa_id=a.empresa_id, codigo=datos.codigo.upper(), nombre=datos.nombre))


@ruta.patch("/tipos-acero/{id_}", response_model=TipoAceroOut)
def editar_tipo_acero(id_: int, datos: CambioCatalogo, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    obj = _propio(s, m.TipoAcero, id_, a)
    crud.editar(s, a.empresa_id, obj, datos.model_dump(exclude_unset=True), tabla="tipo_acero",
                      usuario=a.usuario, origen=a.origen)
    return obj


@ruta.get("/normas", response_model=list[NormaOut])
def normas(s: Session = Depends(sesion), a: Actor = Depends(actor)):
    return s.scalars(select(m.Norma).where(m.Norma.empresa_id == a.empresa_id).order_by(m.Norma.nombre)).all()


@ruta.post("/normas", response_model=NormaOut, status_code=201)
def crear_norma(datos: NormaIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    return _crear(s, m.Norma(empresa_id=a.empresa_id, nombre=datos.nombre.strip()))


@ruta.patch("/normas/{id_}", response_model=NormaOut)
def editar_norma(id_: int, datos: CambioCatalogo, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    obj = _propio(s, m.Norma, id_, a)
    cambios = datos.model_dump(exclude_unset=True)
    cambios.pop("codigo", None)
    crud.editar(s, a.empresa_id, obj, cambios, tabla="norma", usuario=a.usuario, origen=a.origen)
    return obj
