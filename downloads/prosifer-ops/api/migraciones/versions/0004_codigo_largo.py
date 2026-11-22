"""Código físico de pieza hasta 200 caracteres (hay rollos del Excel con códigos de 101).

Revision ID: 0004
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("pieza", "codigo_fisico", type_=sa.String(200), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("pieza", "codigo_fisico", type_=sa.String(80), existing_nullable=False)
