"""Los documentos creados al cargar el libro de Slitter (bobinas y flejes) quedaron sin origen.

Las NE, OT y ajustes de esa carga se guardaron con origen y creado_por vacíos. La app siempre
los llena, así que todo documento sin origen viene de la importación: se marca "importacion".
Con eso el histórico de NE del Excel reconoce esas NE como las mismas y las completa con sus
renglones en vez de reportarlas como choque de numeración.

Revision ID: 0011
"""
from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE documento SET origen = 'importacion', creado_por = COALESCE(creado_por, 'importador') "
               "WHERE origen IS NULL")


def downgrade() -> None:
    pass
