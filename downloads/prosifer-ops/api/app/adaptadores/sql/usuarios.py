"""Alta y cambios de usuarios (mantenimiento en el adaptador SQL). Lo usan la API (solo socio) y la línea de comandos."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import modelos as m
from app.dominio import claves
from app.adaptadores.sql.crud import editar
from app.errores import ErrorNegocio


def _validar(s: Session, empresa_id: int, rol: str, tercero_id: int | None) -> None:
    if rol == "cliente":
        if tercero_id is None:
            raise ErrorNegocio("un usuario cliente necesita el tercero cuyos datos podrá ver", 422)
        t = s.get(m.Tercero, tercero_id)
        if t is None or t.empresa_id != empresa_id:
            raise ErrorNegocio("tercero inexistente", 422)


def crear(s: Session, empresa_id: int, *, correo: str, nombre: str, rol: str, clave: str,
          tercero_id: int | None = None) -> m.Usuario:
    correo = correo.strip().lower()
    if "@" not in correo:
        raise ErrorNegocio("correo inválido", 422)
    motivo = claves.clave_valida(clave)
    if motivo:
        raise ErrorNegocio(motivo, 422)
    _validar(s, empresa_id, rol, tercero_id)
    if s.scalar(select(m.Usuario.id).where(m.Usuario.empresa_id == empresa_id, m.Usuario.correo == correo)):
        raise ErrorNegocio("ya existe un usuario con ese correo")
    u = m.Usuario(empresa_id=empresa_id, correo=correo, nombre=nombre.strip(), rol=rol,
                  tercero_id=tercero_id if rol == "cliente" else None, clave_hash=claves.hash_clave(clave))
    s.add(u)
    s.flush()
    return u


def cambiar(s: Session, empresa_id: int, u: m.Usuario, cambios: dict, *, usuario: str, origen: str,
            quien_id: int | None) -> m.Usuario:
    clave = cambios.pop("clave", None)
    rol = cambios.get("rol", u.rol)
    tercero_id = cambios.get("tercero_id", u.tercero_id)
    _validar(s, empresa_id, rol, tercero_id)
    if rol != "cliente":
        cambios["tercero_id"] = None
    quedaria_sin_socio = (u.rol == "socio" and (rol != "socio" or cambios.get("activo") is False))
    if quedaria_sin_socio:
        otros = s.scalar(select(func.count(m.Usuario.id)).where(
            m.Usuario.empresa_id == empresa_id, m.Usuario.rol == "socio", m.Usuario.activo.is_(True),
            m.Usuario.id != u.id))
        if not otros:
            raise ErrorNegocio("debe quedar al menos un socio activo")
    if quien_id == u.id and cambios.get("activo") is False:
        raise ErrorNegocio("no puedes desactivar tu propio usuario")
    editar(s, empresa_id, u, cambios, tabla="usuario", usuario=usuario, origen=origen)
    if clave:
        motivo = claves.clave_valida(clave)
        if motivo:
            raise ErrorNegocio(motivo, 422)
        u.clave_hash = claves.hash_clave(clave)
        s.add(m.Auditoria(empresa_id=empresa_id, tabla="usuario", registro_id=u.id, campo="clave",
                          antes=None, despues="(cambiada)", usuario=usuario, origen=origen))
    s.flush()
    return u
