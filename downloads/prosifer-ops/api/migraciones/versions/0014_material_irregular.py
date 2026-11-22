"""Producto sin existencia: Material de Medidas Irregulares (MATERIALESIRREG).

Scrap, chatarra, recortes fuera de medida: sale en la nota de entrega solo para registrar su peso.
No exige stock de ningún cliente ni mueve inventario (sus renglones van en documento_linea).

Revision ID: 0014
"""
from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO producto (empresa_id, codigo, nombre, activo)
        SELECT e.id, 'MATERIALESIRREG', 'Material de Medidas Irregulares', true FROM empresa e
        WHERE NOT EXISTS (SELECT 1 FROM producto p WHERE p.empresa_id = e.id AND upper(p.codigo) = 'MATERIALESIRREG')
    """)
    op.execute("UPDATE producto SET activo = true WHERE upper(codigo) = 'MATERIALESIRREG'")


def downgrade() -> None:
    op.execute("""
        DELETE FROM producto WHERE upper(codigo) = 'MATERIALESIRREG'
        AND NOT EXISTS (SELECT 1 FROM documento_linea l WHERE upper(l.codigo) = 'MATERIALESIRREG')
    """)
