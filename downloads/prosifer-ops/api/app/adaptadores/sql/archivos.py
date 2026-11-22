"""Adaptador PostgreSQL del puerto AlmacenArchivos (copias de PDF en la base)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import modelos as m


class AlmacenSql:
    def __init__(self, s: Session, empresa_id: int):
        self.s, self.e = s, empresa_id

    def guardar(self, ref_tabla: str, ref_id: int, nombre: str, contenido: bytes, *, tipo_mime: str,
                usuario: str) -> int:
        a = m.Archivo(empresa_id=self.e, ref_tabla=ref_tabla, ref_id=ref_id, nombre=nombre, tipo_mime=tipo_mime,
                      contenido=contenido, creado_por=usuario)
        self.s.add(a)
        self.s.flush()
        return a.id

    def buscar(self, ref_tabla: str, ref_id: int, nombre: str) -> bytes | None:
        return self.s.scalar(select(m.Archivo.contenido).where(
            m.Archivo.empresa_id == self.e, m.Archivo.ref_tabla == ref_tabla, m.Archivo.ref_id == ref_id,
            m.Archivo.nombre == nombre).order_by(m.Archivo.id.desc()).limit(1))
