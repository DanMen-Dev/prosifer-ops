"""Configuración por variables de entorno (ver .env.example). Nada secreto en el código."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    api_key: str
    secreto_sesion: str
    horas_sesion: float
    empresa_id: int
    cors_origenes: tuple[str, ...]


def cargar() -> Config:
    api_key = os.environ.get("PROSIFER_API_KEY", "")
    # Si no se define PROSIFER_SECRETO, se deriva de la clave de API para no romper instalaciones existentes.
    secreto = os.environ.get("PROSIFER_SECRETO") or (
        hashlib.sha256(f"sesion:{api_key}".encode()).hexdigest() if api_key else "")
    return Config(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://prosifer:prosifer@localhost:5432/prosifer"),
        api_key=api_key,
        secreto_sesion=secreto,
        horas_sesion=float(os.environ.get("PROSIFER_HORAS_SESION", "12")),
        empresa_id=int(os.environ.get("PROSIFER_EMPRESA_ID", "1")),
        cors_origenes=tuple(o for o in os.environ.get("PROSIFER_CORS", "").split(",") if o),
    )


config = cargar()
