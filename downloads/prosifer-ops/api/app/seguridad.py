"""Quién llama y qué puede hacer.

Dos formas de entrar:

- Personas: inician sesión con correo y clave (/api/auth/ingresar) y mandan
  "Authorization: Bearer <ficha>". Roles: socio, asistente, cliente.
- Integraciones (n8n, el agente, la futura app de NE): encabezado X-Api-Key.
  Actúan con permisos de asistente; se identifican con X-Usuario y X-Origen.

Reglas (doc de reglas, sección Usuarios, permisos e integraciones):
- socio: todo, incluido anular registros y gestionar usuarios.
- asistente e integración: registrar y editar, nunca anular.
- cliente: solo lee lo suyo (sus piezas y sus movimientos).
"""
from __future__ import annotations

import datetime as dt
import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import modelos as m
from app.config import config
from app.db import sesion
from app.dominio import claves

ROLES = ("socio", "asistente", "cliente")
ORIGENES_INTEGRACION = {"agente", "integracion", "interfaz"}
EDITORES = ("socio", "asistente", "integracion")


@dataclass(frozen=True)
class Actor:
    usuario: str          # nombre para la auditoría
    rol: str              # socio | asistente | cliente | integracion
    origen: str           # interfaz | portal | agente | integracion
    empresa_id: int
    usuario_id: int | None = None
    tercero_id: int | None = None   # solo clientes: el tercero cuyos datos puede ver

    @property
    def es_cliente(self) -> bool:
        return self.rol == "cliente"

    @property
    def cliente(self) -> int | None:
        """Tercero al que se limita lo que ve un usuario cliente; None para el personal."""
        return self.tercero_id if self.es_cliente else None


def _por_ficha(ficha: str, s: Session) -> Actor:
    try:
        datos = claves.leer_ficha(ficha, config.secreto_sesion)
    except claves.FichaInvalida as exc:
        raise HTTPException(401, f"sesión no válida: {exc}") from exc
    u = s.get(m.Usuario, datos.get("u"))
    # Se revisa en cada petición: desactivar a alguien o cambiarle el rol aplica al momento.
    if u is None or not u.activo or u.empresa_id != datos.get("e"):
        raise HTTPException(401, "usuario inactivo o inexistente")
    return Actor(usuario=u.correo, rol=u.rol, origen="portal" if u.rol == "cliente" else "interfaz",
                 empresa_id=u.empresa_id, usuario_id=u.id, tercero_id=u.tercero_id)


def actor(authorization: str = Header(default=""), x_api_key: str = Header(default=""),
          x_usuario: str = Header(default="integracion"), x_origen: str = Header(default="integracion"),
          s: Session = Depends(sesion)) -> Actor:
    if authorization.lower().startswith("bearer "):
        if not config.secreto_sesion:
            raise HTTPException(503, "falta configurar PROSIFER_SECRETO o PROSIFER_API_KEY")
        return _por_ficha(authorization[7:].strip(), s)
    if x_api_key and config.api_key and hmac.compare_digest(x_api_key, config.api_key):
        origen = x_origen if x_origen in ORIGENES_INTEGRACION else "integracion"
        return Actor(usuario=x_usuario[:80], rol="integracion", origen=origen, empresa_id=config.empresa_id)
    raise HTTPException(401, "inicia sesión o envía una clave de API válida")


def requiere(*roles: str):
    """Dependencia: deja pasar solo a los roles indicados."""
    def _verificar(a: Actor = Depends(actor)) -> Actor:
        if a.rol not in roles:
            raise HTTPException(403, "tu usuario no tiene permiso para esta acción")
        return a
    return _verificar


editor = requiere(*EDITORES)
socio = requiere("socio")
# Ajustes de inventario: un socio, o el agente (Prosi) después de que un aprobador lo confirmó en el grupo.
socio_o_agente = requiere("socio", "integracion")


def iniciar_sesion(s: Session, correo: str, clave: str) -> tuple[str, m.Usuario]:
    from sqlalchemy import select

    u = s.scalar(select(m.Usuario).where(m.Usuario.empresa_id == config.empresa_id,
                                         m.Usuario.correo == correo.strip().lower()))
    # Se calcula el hash aunque el usuario no exista, para no revelar qué correos existen por el tiempo.
    valido = claves.verificar_clave(clave, u.clave_hash if u else claves.hash_clave("x" * 12))
    if u is None or not valido or not u.activo:
        raise HTTPException(401, "correo o clave incorrectos")
    u.ultimo_acceso = dt.datetime.now(dt.timezone.utc)
    ficha = claves.crear_ficha({"u": u.id, "e": u.empresa_id}, config.secreto_sesion, config.horas_sesion)
    return ficha, u
