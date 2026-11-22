"""La maquila de perfiles sigue en la OC 318 del Excel (la 1036 de la hoja es de 2023, fuera de serie).

Revision ID: 0009
"""
from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE parametro SET valor = '318',
               descripcion = 'Última OC de maquila de perfiles del Excel (hoja ProductoFlejes, oct 2026)'
         WHERE clave = 'ultima_oc_maquila' AND valor = '1036'
    """)


def downgrade() -> None:
    op.execute("UPDATE parametro SET valor = '1036' WHERE clave = 'ultima_oc_maquila' AND valor = '318'")
