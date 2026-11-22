"""Contraseñas y fichas de sesión, solo con la biblioteca estándar.

- Contraseñas: scrypt con sal aleatoria. Se guarda "scrypt$n$r$p$sal$hash".
- Ficha de sesión: datos en JSON + firma HMAC-SHA256, con vencimiento.
  Formato "<datos base64url>.<firma base64url>". No es un JWT, pero sigue la misma idea.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

N, R, P = 2 ** 14, 8, 1
LARGO_MINIMO = 10


class FichaInvalida(ValueError):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def clave_valida(clave: str) -> str | None:
    """Devuelve el motivo si la clave no sirve, o None si sirve."""
    if len(clave) < LARGO_MINIMO:
        return f"la clave debe tener al menos {LARGO_MINIMO} caracteres"
    if clave.isdigit() or clave.isalpha():
        return "la clave debe mezclar letras y números"
    return None


def hash_clave(clave: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(sal)}${_b64(h)}"


def verificar_clave(clave: str, guardado: str | None) -> bool:
    try:
        alg, n, r, p, sal, h = (guardado or "").split("$")
        if alg != "scrypt":
            return False
        calc = hashlib.scrypt(clave.encode(), salt=_unb64(sal), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, _unb64(h))
    except (ValueError, TypeError):
        return False


def crear_ficha(datos: dict, secreto: str, horas: float = 12, ahora: float | None = None) -> str:
    ahora = time.time() if ahora is None else ahora
    cuerpo = _b64(json.dumps({**datos, "exp": int(ahora + horas * 3600)}, separators=(",", ":")).encode())
    firma = _b64(hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def leer_ficha(ficha: str, secreto: str, ahora: float | None = None) -> dict:
    try:
        cuerpo, firma = ficha.split(".")
    except ValueError as exc:
        raise FichaInvalida("ficha mal formada") from exc
    esperada = _b64(hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(firma, esperada):
        raise FichaInvalida("firma inválida")
    try:
        datos = json.loads(_unb64(cuerpo))
    except ValueError as exc:
        raise FichaInvalida("ficha ilegible") from exc
    if (time.time() if ahora is None else ahora) >= datos.get("exp", 0):
        raise FichaInvalida("sesión vencida")
    return datos
