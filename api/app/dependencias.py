"""Raíz de composición: qué adaptador implementa cada puerto.

Las rutas piden aquí la unidad de trabajo y el generador de documentos; los casos de
uso no saben qué hay detrás. Para pruebas sin base de datos se usa
app.adaptadores.memoria.UnidadMemoria con los mismos casos de uso.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.adaptadores.sql.repositorios import UnidadSql
from app.db import sesion
from app.puertos import GeneradorDocumentos, UnidadDeTrabajo
from app.seguridad import Actor, actor

_generador = GeneradorReportlab()


def generador_documentos() -> GeneradorDocumentos:
    return _generador


def unidad(s: Session, empresa_id: int) -> UnidadDeTrabajo:
    return UnidadSql(s, empresa_id)


def unidad_actual(s: Session = Depends(sesion), a: Actor = Depends(actor)) -> UnidadDeTrabajo:
    """Dependencia de FastAPI: la unidad de trabajo de la petición (misma sesión y transacción)."""
    return UnidadSql(s, a.empresa_id)
