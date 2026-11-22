"""Histórico de notas de entrega del Excel (solo consulta) y correcciones de NE de la app.

- documento_linea: las líneas tal como se emitieron en el Excel (código, cantidad, unidad,
  producto, kg). No mueven inventario: el saldo de apertura ya las descuenta.
- documento.documento_origen_id: una corrección apunta a la NE que corrige.
- movimiento.revierte_id: el ajuste que devuelve lo que salió mal apunta al movimiento que
  deshace; así se sabe qué líneas de una NE siguen vigentes.

Revision ID: 0010
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documento", sa.Column("documento_origen_id", sa.Integer, sa.ForeignKey("documento.id")))
    op.create_index("documento_origen", "documento", ["documento_origen_id"])
    op.add_column("movimiento", sa.Column("revierte_id", sa.BigInteger, sa.ForeignKey("movimiento.id")))
    op.create_index("movimiento_revierte", "movimiento", ["revierte_id"])
    op.create_index("documento_tipo_numero", "documento", ["empresa_id", "tipo", "numero"])
    op.create_table(
        "documento_linea",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey("documento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("posicion", sa.Integer, nullable=False),
        sa.Column("codigo", sa.String(60)),
        sa.Column("descripcion", sa.String(250)),
        sa.Column("cantidad", sa.Numeric(14, 3)),
        sa.Column("unidad", sa.String(20)),
        sa.Column("kg", sa.Numeric(14, 3)),
    )
    op.create_index("documento_linea_documento", "documento_linea", ["documento_id", "posicion"])


def downgrade() -> None:
    op.drop_table("documento_linea")
    op.drop_index("documento_tipo_numero", "documento")
    op.drop_index("movimiento_revierte", "movimiento")
    op.drop_column("movimiento", "revierte_id")
    op.drop_index("documento_origen", "documento")
    op.drop_column("documento", "documento_origen_id")
