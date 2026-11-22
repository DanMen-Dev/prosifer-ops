"""Datos de demostración para la vitrina pública (sin PII real).

    docker compose exec api python -m app.demo sembrar
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from decimal import Decimal as D

from sqlalchemy import select

from app import modelos as m
from app.adaptadores.sql import usuarios
from app.config import config
from app.db import SesionLocal
from app.dependencias import unidad
from app.errores import ErrorNegocio
from app.esquemas import EntradaBobinaIn
from app.servicios import inventario

U = dict(usuario="demo", origen="demo")
HOY = dt.date.today()

# Credenciales públicas de la demo (portfolio). Cámbialas en el VPS si quieres.
DEMO_CORREO = "socio@demo.test"
DEMO_NOMBRE = "Socio Demo"
DEMO_CLAVE = "DemoProsifer1"

CLIENTES = [
    ("Aceros del Valle, C.A.", "J-10000001-0", True, False),
    ("Laminados Norte, C.A.", "J-10000002-0", True, False),
    ("Constructora Horizonte, C.A.", "J-10000003-0", True, False),
    ("Siderúrgica Demo Sur", "J-10000090-0", False, True),
]

BOBINAS = [
    ("DEMO-B001", "LAM FRIO", "0.90", "1200", "8235", "Aceros del Valle, C.A."),
    ("DEMO-B002", "LAM FRIO", "1.10", "1250", "6844", "Aceros del Valle, C.A."),
    ("DEMO-B003", "LAM CALI", "2.00", "1220", "9100", "Laminados Norte, C.A."),
    ("DEMO-B004", "LAM GALV", "0.70", "1000", "5520", "Constructora Horizonte, C.A."),
]


def _tercero(s, empresa_id: int, nombre: str, rif: str, es_cliente: bool, es_siderurgica: bool) -> m.Tercero:
    t = s.scalar(select(m.Tercero).where(m.Tercero.empresa_id == empresa_id, m.Tercero.nombre == nombre))
    if t is None:
        t = m.Tercero(
            empresa_id=empresa_id,
            nombre=nombre,
            rif=rif,
            es_cliente=es_cliente,
            es_siderurgica=es_siderurgica,
            activo=True,
        )
        s.add(t)
        s.flush()
    return t


def _usuario_demo(s, empresa_id: int) -> None:
    try:
        usuarios.crear(
            s,
            empresa_id,
            correo=DEMO_CORREO,
            nombre=DEMO_NOMBRE,
            rol="socio",
            clave=DEMO_CLAVE,
        )
        print(f"Usuario demo: {DEMO_CORREO} / {DEMO_CLAVE}")
    except ErrorNegocio as exc:
        if "ya existe" in str(exc).lower():
            print(f"Usuario demo ya existía: {DEMO_CORREO}")
        else:
            raise


def sembrar() -> int:
    with SesionLocal() as s:
        empresa_id = config.empresa_id
        if s.get(m.Empresa, empresa_id) is None:
            print(f"No hay empresa id={empresa_id}. ¿Corriste las migraciones?")
            return 1

        _usuario_demo(s, empresa_id)

        por_nombre: dict[str, m.Tercero] = {}
        for nombre, rif, cli, sid in CLIENTES:
            por_nombre[nombre] = _tercero(s, empresa_id, nombre, rif, cli, sid)

        uow = unidad(s, empresa_id)
        creadas = 0
        for codigo, tipo, espesor, ancho, peso, dueño in BOBINAS:
            if uow.piezas.id_por_codigo("bobina", codigo) is not None:
                continue
            inventario.registrar_entrada_bobina(
                uow,
                EntradaBobinaIn(
                    documento_numero=f"DEMO-{codigo}",
                    fecha=HOY,
                    codigo_bobina=codigo,
                    tipo_acero=tipo,
                    espesor_mm=D(espesor),
                    ancho_mm=D(ancho),
                    peso_kg=D(peso),
                    propietario_id=por_nombre[dueño].id,
                    siderurgica_id=por_nombre["Siderúrgica Demo Sur"].id,
                    buque="DEMO-VESSEL",
                    confirmar=True,
                ),
                **U,
            )
            creadas += 1
        s.commit()
    print(f"Demo lista: {len(CLIENTES)} terceros, {creadas} bobinas nuevas.")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m app.demo")
    sub = p.add_subparsers(dest="accion", required=True)
    sub.add_parser("sembrar", help="crea usuario demo, terceros y bobinas ficticios")
    a = p.parse_args(argv[1:])
    if a.accion == "sembrar":
        return sembrar()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
