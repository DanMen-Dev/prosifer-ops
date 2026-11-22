"""Conteos físicos en patio (auditorías): cada conteo queda registrado, cuadre o no.

Así un descuadre futuro se explica desde el último conteo y no desde el inicio de los tiempos.

Revision ID: 0015
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

KG = sa.Numeric(12, 3)


def upgrade() -> None:
    op.create_table(
        "conteo",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("pieza_id", sa.BigInteger, sa.ForeignKey("pieza.id"), nullable=False),
        sa.Column("propietario_id", sa.Integer, sa.ForeignKey("tercero.id"), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("unidad", sa.String(4), nullable=False),
        sa.Column("sistema", KG, nullable=False),
        sa.Column("contado", KG, nullable=False),
        sa.Column("diferencia", KG, nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("ajuste_documento_id", sa.Integer, sa.ForeignKey("documento.id")),
        sa.Column("contado_por", sa.String(80)),
        sa.Column("observacion", sa.Text),
        sa.Column("resolucion", sa.Text),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("clave_idempotencia", sa.String(80)),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("creado_por", sa.String(80), nullable=False),
        sa.Column("resuelto_en", sa.DateTime(timezone=True)),
        sa.Column("resuelto_por", sa.String(80)),
    )
    op.create_index("conteo_pieza", "conteo", ["pieza_id", "fecha"])
    op.create_index("conteo_fecha", "conteo", ["empresa_id", "fecha"])
    op.create_index("conteo_idempotencia", "conteo", ["empresa_id", "clave_idempotencia"], unique=True,
                    postgresql_where=sa.text("clave_idempotencia IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("conteo")
