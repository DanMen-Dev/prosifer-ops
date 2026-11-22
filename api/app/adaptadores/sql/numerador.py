"""Adaptador PostgreSQL del puerto Numerador.

UPDATE … RETURNING bloquea la fila de la secuencia hasta que termina la transacción:
dos notas de entrega simultáneas nunca reciben el mismo número, y si la transacción
se deshace el número no se pierde.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class NumeradorSql:
    def __init__(self, s: Session, empresa_id: int):
        self.s, self.e = s, empresa_id

    def siguiente(self, tipo: str) -> int:
        n = self.s.execute(text(
            "UPDATE secuencia SET ultimo = ultimo + 1 WHERE empresa_id = :e AND tipo = :t RETURNING ultimo"),
            {"e": self.e, "t": tipo}).scalar()
        if n is None:
            self.s.execute(text("INSERT INTO secuencia (empresa_id, tipo, ultimo) VALUES (:e, :t, 1)"),
                           {"e": self.e, "t": tipo})
            n = 1
        return int(n)

    def ver_siguiente(self, tipo: str) -> int:
        n = self.s.execute(text("SELECT ultimo FROM secuencia WHERE empresa_id = :e AND tipo = :t"),
                           {"e": self.e, "t": tipo}).scalar()
        return int(n or 0) + 1

    def fijar(self, tipo: str, ultimo: int) -> None:
        """Ajuste administrativo: el próximo número será ultimo + 1."""
        self.s.execute(text(
            "INSERT INTO secuencia (empresa_id, tipo, ultimo) VALUES (:e, :t, :u) "
            "ON CONFLICT (empresa_id, tipo) DO UPDATE SET ultimo = EXCLUDED.ultimo"),
            {"e": self.e, "t": tipo, "u": ultimo})
