"""Órdenes de trabajo (empieza por slitter) y enlace de cada pieza producida con su orden.

Revision ID: 0003
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

KG = sa.Numeric(12, 3)


def upgrade() -> None:
    op.create_table(
        "orden_trabajo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("fecha", sa.Date),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("pieza_id", sa.BigInteger, sa.ForeignKey("pieza.id", name="ot_pieza_fk")),
        sa.Column("propietario_id", sa.Integer, sa.ForeignKey("tercero.id")),
        sa.Column("estatus_corte", sa.String(8)),
        sa.Column("kg_consumido", KG, nullable=False),
        sa.Column("kg_producido", KG, nullable=False),
        sa.Column("kg_scrap", KG, nullable=False),
        sa.Column("paradas", sa.Integer),
        sa.Column("calidad", sa.String(10)),
        sa.Column("detalle", sa.JSON),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey("documento.id")),
        sa.Column("observacion", sa.Text),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("clave_idempotencia", sa.String(80)),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("creado_por", sa.String(80), nullable=False),
        sa.CheckConstraint("tipo IN ('slitter', 'lamina', 'ctf', 'maquila', 'losacero')", name="ot_tipo_valido"),
    )
    op.create_index("orden_trabajo_numero", "orden_trabajo", ["empresa_id", "tipo", "numero"])
    op.create_index("orden_trabajo_idempotencia", "orden_trabajo", ["empresa_id", "clave_idempotencia"],
                    unique=True, postgresql_where=sa.text("clave_idempotencia IS NOT NULL"))
    op.add_column("pieza", sa.Column("orden_trabajo_id", sa.Integer, sa.ForeignKey("orden_trabajo.id")))
    op.create_index("pieza_orden_trabajo", "pieza", ["orden_trabajo_id"])
    op.create_index("pieza_origen", "pieza", ["pieza_origen_id"])
    op.execute("""
        INSERT INTO parametro (empresa_id, clave, vigente_desde, valor, descripcion) VALUES
        (1, 'tolerancia_ancho_mm', '2018-01-01', '2', 'Exceso de ancho permitido al sumar los cortes del slitter')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("pieza_origen", "pieza")
    op.drop_index("pieza_orden_trabajo", "pieza")
    op.drop_column("pieza", "orden_trabajo_id")
    op.drop_table("orden_trabajo")
