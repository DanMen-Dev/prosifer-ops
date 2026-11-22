"""Ficha completa de clientes y catálogo de productos (del libro de formatos de NE y cotizaciones).

Revision ID: 0007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tercero", sa.Column("direccion", sa.String(300)))
    op.add_column("tercero", sa.Column("estado_region", sa.String(60)))
    op.add_column("tercero", sa.Column("ciudad", sa.String(80)))
    op.add_column("tercero", sa.Column("forma_pago", sa.String(40)))
    op.add_column("tercero", sa.Column("vendedor", sa.String(60)))
    op.add_column("tercero", sa.Column("cliente_desde", sa.Date))
    op.create_index("tercero_rif", "tercero", ["empresa_id", "rif"])

    op.create_table(
        "producto",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("peso_unitario_kg", sa.Numeric(12, 4)),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("empresa_id", "codigo"),
    )


def downgrade() -> None:
    op.drop_table("producto")
    op.drop_index("tercero_rif", "tercero")
    for col in ("cliente_desde", "vendedor", "forma_pago", "ciudad", "estado_region", "direccion"):
        op.drop_column("tercero", col)
