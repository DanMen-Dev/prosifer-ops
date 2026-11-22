"""Estado de los documentos que esperan algo: la orden de despacho del cliente.

orden_despacho: pendiente (material reservado, el patio la prepara) → despachada (salió con su
nota de salida). La anulada usa la marca "anulado" de siempre. Los demás documentos lo dejan vacío.

Revision ID: 0013
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documento", sa.Column("estado", sa.String(12)))
    op.create_index("documento_abiertos", "documento", ["empresa_id", "tipo", "estado"])


def downgrade() -> None:
    op.drop_index("documento_abiertos", table_name="documento")
    op.drop_column("documento", "estado")
