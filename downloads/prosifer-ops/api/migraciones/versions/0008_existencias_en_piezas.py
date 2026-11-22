"""Láminas, perfiles y productos generales: existencia en piezas por código y dueño.

Una bobina o un fleje es una pieza física con su código. Una lámina, un perfil o un
producto general se lleva como el Excel: una fila por código de producto y dueño, con
su saldo en piezas y en kg (saldo_unidades NO nulo). Por eso hay dos índices únicos.

Revision ID: 0008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pieza", sa.Column("unidades_entrada", sa.Integer))
    op.add_column("pieza", sa.Column("saldo_unidades", sa.Integer))
    op.add_column("movimiento", sa.Column("unidades", sa.Integer))
    op.add_column("movimiento", sa.Column("saldo_despues_unidades", sa.Integer))

    op.drop_index("pieza_codigo_unico", "pieza")
    op.create_index("pieza_codigo_unico", "pieza", ["empresa_id", "tipo", "codigo_fisico"], unique=True,
                    postgresql_where=sa.text("NOT anulada AND saldo_unidades IS NULL"))
    op.create_index("pieza_existencia_unica", "pieza", ["empresa_id", "tipo", "codigo_fisico", "propietario_id"],
                    unique=True, postgresql_where=sa.text("NOT anulada AND saldo_unidades IS NOT NULL"))

    # Últimas órdenes del libro de bobinas, para que la numeración siga donde quedó.
    op.execute("""
        INSERT INTO parametro (empresa_id, clave, vigente_desde, valor, descripcion) VALUES
        (1, 'ultima_oc_lamina', '2018-01-01', '1085', 'Última OC de laminadora del Excel (hoja Producto)'),
        (1, 'ultima_oc_ctf', '2018-01-01', '429', 'Última OC de CTF del Excel (hoja ProductoCTF)'),
        (1, 'ultima_oc_maquila', '2018-01-01', '1036', 'Última OC de maquila de perfiles del Excel (hoja ProductoFlejes)')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM parametro WHERE clave IN ('ultima_oc_lamina', 'ultima_oc_ctf', 'ultima_oc_maquila')")
    op.drop_index("pieza_existencia_unica", "pieza")
    op.drop_index("pieza_codigo_unico", "pieza")
    op.create_index("pieza_codigo_unico", "pieza", ["empresa_id", "tipo", "codigo_fisico"], unique=True,
                    postgresql_where=sa.text("NOT anulada"))
    for t, c in (("movimiento", "saldo_despues_unidades"), ("movimiento", "unidades"),
                 ("pieza", "saldo_unidades"), ("pieza", "unidades_entrada")):
        op.drop_column(t, c)
