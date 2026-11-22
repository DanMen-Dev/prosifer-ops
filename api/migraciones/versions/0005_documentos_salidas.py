"""Documentos de salida: nuevo dueño en liberaciones, anulación, quién y desde dónde.

Revision ID: 0005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documento", sa.Column("tercero_destino_id", sa.Integer, sa.ForeignKey("tercero.id")))
    op.add_column("documento", sa.Column("anulado", sa.Boolean, server_default=sa.text("false"), nullable=False))
    op.add_column("documento", sa.Column("origen", sa.String(12)))
    op.add_column("documento", sa.Column("creado_por", sa.String(80)))
    op.add_column("documento", sa.Column("clave_idempotencia", sa.String(80)))
    op.create_index("documento_tipo_fecha", "documento", ["empresa_id", "tipo", "fecha"])
    op.create_index("documento_idempotencia", "documento", ["empresa_id", "clave_idempotencia"], unique=True,
                    postgresql_where=sa.text("clave_idempotencia IS NOT NULL"))
    op.create_index("movimiento_documento", "movimiento", ["documento_id"])
    op.execute("""
        INSERT INTO parametro (empresa_id, clave, vigente_desde, valor, descripcion) VALUES
        (1, 'resto_aviso_kg', '2018-01-01', '50', 'Avisar si una nota de entrega deja un resto menor que esto')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("movimiento_documento", "movimiento")
    op.drop_index("documento_idempotencia", "documento")
    op.drop_index("documento_tipo_fecha", "documento")
    for c in ("clave_idempotencia", "creado_por", "origen", "anulado", "tercero_destino_id"):
        op.drop_column("documento", c)
