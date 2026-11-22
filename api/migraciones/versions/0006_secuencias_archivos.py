"""Numeración correlativa (nota de entrega, cotización) y copias de documentos generados.

Revision ID: 0006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secuencia",
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), primary_key=True),
        sa.Column("tipo", sa.String(30), primary_key=True),
        sa.Column("ultimo", sa.Integer, nullable=False),
    )
    # Últimos números del Excel de formatos (8 nov 2026): la app sigue con el siguiente.
    op.execute("INSERT INTO secuencia (empresa_id, tipo, ultimo) VALUES (1, 'nota_entrega', 7224), (1, 'cotizacion', 2938)")
    op.create_table(
        "archivo",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("ref_tabla", sa.String(40), nullable=False),
        sa.Column("ref_id", sa.BigInteger, nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("tipo_mime", sa.String(60), nullable=False),
        sa.Column("contenido", sa.LargeBinary, nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("creado_por", sa.String(80), nullable=False),
    )
    op.create_index("archivo_referencia", "archivo", ["empresa_id", "ref_tabla", "ref_id", "nombre"])


def downgrade() -> None:
    op.drop_table("archivo")
    op.drop_table("secuencia")
