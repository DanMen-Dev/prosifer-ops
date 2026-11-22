"""Esquema inicial: catálogos, terceros, piezas, movimientos, auditoría y parámetros.

Revision ID: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

KG = sa.Numeric(12, 3)


def _ts():
    return sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _empresa():
    return sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "empresa",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False, unique=True),
        _ts(),
    )
    op.create_table(
        "tipo_acero",
        sa.Column("id", sa.Integer, primary_key=True),
        _empresa(),
        sa.Column("codigo", sa.String(3), nullable=False),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("empresa_id", "codigo"),
        sa.UniqueConstraint("empresa_id", "nombre"),
    )
    op.create_table(
        "norma",
        sa.Column("id", sa.Integer, primary_key=True),
        _empresa(),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("empresa_id", "nombre"),
    )
    op.create_table(
        "tercero",
        sa.Column("id", sa.Integer, primary_key=True),
        _empresa(),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("rif", sa.String(20)),
        sa.Column("telefono", sa.String(40)),
        sa.Column("correo", sa.String(120)),
        sa.Column("es_cliente", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("es_siderurgica", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("dias_gracia_almacen", sa.Integer),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("empresa_id", "nombre"),
    )
    op.create_table(
        "documento",
        sa.Column("id", sa.Integer, primary_key=True),
        _empresa(),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("numero", sa.String(80)),
        sa.Column("fecha", sa.Date),
        sa.Column("tercero_id", sa.Integer, sa.ForeignKey("tercero.id")),
        sa.Column("observacion", sa.Text),
        _ts(),
    )
    op.create_table(
        "pieza",
        sa.Column("id", sa.BigInteger, primary_key=True),
        _empresa(),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("codigo_fisico", sa.String(80), nullable=False),
        sa.Column("codigo_producto", sa.String(40)),
        sa.Column("descripcion", sa.String(200)),
        sa.Column("tipo_acero_id", sa.Integer, sa.ForeignKey("tipo_acero.id")),
        sa.Column("norma_id", sa.Integer, sa.ForeignKey("norma.id")),
        sa.Column("espesor_mm", sa.Numeric(6, 3)),
        sa.Column("ancho_mm", sa.Numeric(7, 1)),
        sa.Column("largo_mm", sa.Numeric(7, 1)),
        sa.Column("calidad", sa.String(10)),
        sa.Column("propietario_id", sa.Integer, sa.ForeignKey("tercero.id"), nullable=False),
        sa.Column("siderurgica_id", sa.Integer, sa.ForeignKey("tercero.id")),
        sa.Column("buque", sa.String(80)),
        sa.Column("pieza_origen_id", sa.BigInteger, sa.ForeignKey("pieza.id")),
        sa.Column("fecha_entrada", sa.Date),
        sa.Column("peso_entrada_kg", KG, nullable=False),
        sa.Column("saldo_kg", KG, nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("anulada", sa.Boolean, server_default=sa.text("false"), nullable=False),
        _ts(),
        sa.Column("creado_por", sa.String(80), nullable=False),
    )
    op.create_index("pieza_codigo_unico", "pieza", ["empresa_id", "tipo", "codigo_fisico"], unique=True,
                    postgresql_where=sa.text("NOT anulada"))
    op.create_index("pieza_disponibles", "pieza", ["empresa_id", "estado", "tipo"])
    op.create_index("pieza_propietario", "pieza", ["propietario_id"])
    op.create_table(
        "movimiento",
        sa.Column("id", sa.BigInteger, primary_key=True),
        _empresa(),
        sa.Column("pieza_id", sa.BigInteger, sa.ForeignKey("pieza.id"), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("kg", KG, nullable=False),
        sa.Column("saldo_despues_kg", KG, nullable=False),
        sa.Column("propietario_anterior_id", sa.Integer, sa.ForeignKey("tercero.id")),
        sa.Column("propietario_nuevo_id", sa.Integer, sa.ForeignKey("tercero.id")),
        sa.Column("documento_id", sa.Integer, sa.ForeignKey("documento.id")),
        sa.Column("fecha", sa.Date),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("clave_idempotencia", sa.String(80)),
        sa.Column("observacion", sa.Text),
        _ts(),
        sa.Column("creado_por", sa.String(80), nullable=False),
    )
    op.create_index("movimiento_pieza", "movimiento", ["pieza_id", "id"])
    op.create_index("movimiento_idempotencia", "movimiento", ["empresa_id", "clave_idempotencia"], unique=True,
                    postgresql_where=sa.text("clave_idempotencia IS NOT NULL"))
    op.create_table(
        "auditoria",
        sa.Column("id", sa.BigInteger, primary_key=True),
        _empresa(),
        sa.Column("tabla", sa.String(40), nullable=False),
        sa.Column("registro_id", sa.BigInteger, nullable=False),
        sa.Column("campo", sa.String(60), nullable=False),
        sa.Column("antes", sa.Text),
        sa.Column("despues", sa.Text),
        sa.Column("usuario", sa.String(80), nullable=False),
        sa.Column("origen", sa.String(12), nullable=False),
        _ts(),
    )
    op.create_index("auditoria_registro", "auditoria", ["tabla", "registro_id"])
    op.create_table(
        "parametro",
        sa.Column("empresa_id", sa.Integer, sa.ForeignKey("empresa.id"), primary_key=True),
        sa.Column("clave", sa.String(40), primary_key=True),
        sa.Column("vigente_desde", sa.Date, primary_key=True),
        sa.Column("valor", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.String(200)),
    )

    # Datos iniciales: Prosifer, tipos de acero y variables del sistema (decididas 8 nov 2026).
    op.execute("INSERT INTO empresa (id, nombre) VALUES (1, 'Prosifer')")
    op.execute("SELECT setval(pg_get_serial_sequence('empresa', 'id'), 1)")
    op.execute("""
        INSERT INTO tipo_acero (empresa_id, codigo, nombre) VALUES
        (1, 'HP', 'LAM FRIO'), (1, 'HN', 'LAM CALI'), (1, 'GV', 'LAM GALV'),
        (1, 'ES', 'LAM ESTR'), (1, 'PP', 'LAM PREP'), (1, 'AL', 'ALUMINIO')
    """)
    op.execute("""
        INSERT INTO parametro (empresa_id, clave, vigente_desde, valor, descripcion) VALUES
        (1, 'umbral_agotado_kg', '2018-01-01', '1', 'Por debajo de este saldo la pieza queda agotada'),
        (1, 'tolerancia_corte', '2018-01-01', '0.05', 'Aviso si consumido y producido + scrap difieren más que esto'),
        (1, 'tarifa_almacen_usd_ton_mes', '2018-01-01', '1.5', 'USD por tonelada al mes'),
        (1, 'dias_gracia_almacen', '2018-01-01', '30', 'Días sin movimiento antes de generar cargo (0, 15, 30 o 45)')
    """)


def downgrade() -> None:
    for tabla in ("parametro", "auditoria", "movimiento", "pieza", "documento", "tercero", "norma",
                  "tipo_acero", "empresa"):
        op.drop_table(tabla)
