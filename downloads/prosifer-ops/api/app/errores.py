"""Errores del núcleo. La API los traduce a respuestas HTTP."""
from __future__ import annotations


class ErrorNegocio(ValueError):
    """Regla de negocio incumplida: la API la devuelve con su código (409, 422, 404)."""

    def __init__(self, mensaje: str, codigo: int = 409):
        super().__init__(mensaje)
        self.codigo = codigo
