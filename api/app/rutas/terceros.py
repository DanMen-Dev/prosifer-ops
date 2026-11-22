from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import modelos as m
from app.db import sesion
from app.esquemas import CambioTercero, TerceroIn, TerceroOut
from app.seguridad import Actor, editor
from app.adaptadores.sql import crud

ruta = APIRouter(prefix="/api/terceros", tags=["terceros"])


@ruta.get("", response_model=list[TerceroOut])
def listar(q: str | None = Query(default=None, description="Busca en el nombre, el RIF o la ciudad"),
           rol: str | None = Query(default=None, pattern="^(cliente|siderurgica)$"),
           s: Session = Depends(sesion), a: Actor = Depends(editor)):
    consulta = select(m.Tercero).where(m.Tercero.empresa_id == a.empresa_id)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(m.Tercero.nombre.ilike(patron), m.Tercero.rif.ilike(patron),
                                      m.Tercero.ciudad.ilike(patron)))
    if rol == "cliente":
        consulta = consulta.where(m.Tercero.es_cliente.is_(True))
    elif rol == "siderurgica":
        consulta = consulta.where(m.Tercero.es_siderurgica.is_(True))
    return s.scalars(consulta.order_by(m.Tercero.nombre).limit(2000)).all()


@ruta.post("", response_model=TerceroOut, status_code=201)
def crear(datos: TerceroIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    t = m.Tercero(empresa_id=a.empresa_id, **datos.model_dump())
    t.nombre = " ".join(t.nombre.split())
    s.add(t)
    try:
        s.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "ya existe un tercero con ese nombre") from exc
    return t


@ruta.patch("/{id_}", response_model=TerceroOut)
def editar(id_: int, datos: CambioTercero, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    t = s.get(m.Tercero, id_)
    if t is None or t.empresa_id != a.empresa_id:
        raise HTTPException(404, "no existe")
    crud.editar(s, a.empresa_id, t, datos.model_dump(exclude_unset=True), tabla="tercero",
                      usuario=a.usuario, origen=a.origen)
    return t
