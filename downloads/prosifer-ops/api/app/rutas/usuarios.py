from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import modelos as m
from app.db import sesion
from app.esquemas import CambioUsuario, Ingreso, Sesion, UsuarioIn, UsuarioOut
from app.seguridad import Actor, actor, iniciar_sesion, socio
from app.adaptadores.sql import usuarios
from app.errores import ErrorNegocio

ruta = APIRouter(prefix="/api", tags=["usuarios"])


@ruta.post("/auth/ingresar", response_model=Sesion, summary="Iniciar sesión con correo y clave")
def ingresar(datos: Ingreso, s: Session = Depends(sesion)):
    ficha, u = iniciar_sesion(s, datos.correo, datos.clave)
    out = UsuarioOut.model_validate(u)
    if u.tercero_id:
        out.empresa = s.scalar(select(m.Tercero.nombre).where(m.Tercero.id == u.tercero_id))
    else:
        out.empresa = s.scalar(select(m.Empresa.nombre).where(m.Empresa.id == u.empresa_id))
    return Sesion(ficha=ficha, usuario=out)


@ruta.get("/auth/yo", summary="Quién soy y con qué rol")
def yo(a: Actor = Depends(actor)) -> dict:
    return {"usuario": a.usuario, "rol": a.rol, "usuario_id": a.usuario_id, "tercero_id": a.tercero_id,
            "origen": a.origen}


@ruta.get("/usuarios", response_model=list[UsuarioOut])
def listar(s: Session = Depends(sesion), a: Actor = Depends(socio)):
    return s.scalars(select(m.Usuario).where(m.Usuario.empresa_id == a.empresa_id)
                     .order_by(m.Usuario.rol, m.Usuario.nombre)).all()


@ruta.post("/usuarios", response_model=UsuarioOut, status_code=201)
def crear(datos: UsuarioIn, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    try:
        return usuarios.crear(s, a.empresa_id, **datos.model_dump())
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc


@ruta.patch("/usuarios/{id_}", response_model=UsuarioOut)
def cambiar(id_: int, datos: CambioUsuario, s: Session = Depends(sesion), a: Actor = Depends(socio)):
    u = s.get(m.Usuario, id_)
    if u is None or u.empresa_id != a.empresa_id:
        raise HTTPException(404, "no existe")
    try:
        return usuarios.cambiar(s, a.empresa_id, u, datos.model_dump(exclude_unset=True), usuario=a.usuario,
                                origen=a.origen, quien_id=a.usuario_id)
    except ErrorNegocio as exc:
        raise HTTPException(exc.codigo, str(exc)) from exc
