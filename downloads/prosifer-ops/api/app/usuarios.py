"""Crear usuarios desde la terminal (sirve para el primer socio).

    docker compose exec api python -m app.usuarios crear --correo socio@prosifer.com --nombre "Nombre" --rol socio
    docker compose exec api python -m app.usuarios clave --correo socio@prosifer.com

La clave se pide sin mostrarla en pantalla.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app import modelos as m
from app.config import config
from app.db import SesionLocal
from app.dominio import claves
from app.adaptadores.sql import usuarios
from app.errores import ErrorNegocio


def _pedir_clave() -> str:
    clave = getpass.getpass("Clave (mínimo 10 caracteres, letras y números): ")
    if clave != getpass.getpass("Repite la clave: "):
        raise SystemExit("Las claves no coinciden.")
    return clave


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m app.usuarios")
    sub = p.add_subparsers(dest="accion", required=True)
    c = sub.add_parser("crear")
    c.add_argument("--correo", required=True)
    c.add_argument("--nombre", required=True)
    c.add_argument("--rol", required=True, choices=("socio", "asistente", "cliente"))
    c.add_argument("--tercero-id", type=int)
    k = sub.add_parser("clave", help="cambiar la clave de un usuario")
    k.add_argument("--correo", required=True)
    a = p.parse_args(argv[1:])

    clave = _pedir_clave()
    with SesionLocal() as s:
        try:
            if a.accion == "crear":
                u = usuarios.crear(s, config.empresa_id, correo=a.correo, nombre=a.nombre, rol=a.rol,
                                   clave=clave, tercero_id=a.tercero_id)
            else:
                u = s.scalar(select(m.Usuario).where(m.Usuario.empresa_id == config.empresa_id,
                                                     m.Usuario.correo == a.correo.strip().lower()))
                if u is None:
                    raise ErrorNegocio("no existe ese usuario")
                motivo = claves.clave_valida(clave)
                if motivo:
                    raise ErrorNegocio(motivo)
                u.clave_hash = claves.hash_clave(clave)
            s.commit()
        except ErrorNegocio as exc:
            print(f"No se pudo: {exc}")
            return 1
    print(f"Listo: {u.correo} ({u.rol}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
