"""Encabezado de la nota de entrega impresa: domicilio de entrega, teléfonos, condición de pago,
vendedor, cotización, chofer, placa, nota de salida, ciudad y notas importantes.

Se guarda como JSON en documento.encabezado: son datos de la hoja, no mueven inventario, y se
pueden completar después de emitida la NE (el chofer y la placa suelen llegar al cargar).

Revision ID: 0012
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documento", sa.Column("encabezado", sa.JSON))


def downgrade() -> None:
    op.drop_column("documento", "encabezado")
