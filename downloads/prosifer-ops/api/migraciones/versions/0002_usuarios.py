"""Usuarios con rol (socio, asistente, cliente).

Revision ID: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("correo", sa.String(120), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("rol", sa.String(12), nullable=False),
        sa.Column("tercero_id", sa.Integer, sa.ForeignKey("tercero.id")),
        sa.Column("clave_hash", sa.String(200), nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ultimo_acceso", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("empresa_id", "correo"),
        sa.CheckConstraint("rol IN ('socio', 'asistente', 'cliente')", name="usuario_rol_valido"),
        sa.CheckConstraint("rol <> 'cliente' OR tercero_id IS NOT NULL", name="usuario_cliente_con_tercero"),
    )


def downgrade() -> None:
    op.drop_table("usuario")
