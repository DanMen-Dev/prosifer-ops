"""Modelo de datos (doc de reglas, sección Modelo de datos propuesto).

Idea central: una tabla de piezas y una de movimientos. La existencia de una
pieza (saldo_kg) se actualiza en la misma transacción que registra cada
movimiento; el libro de movimientos guarda la historia completa.
Todas las tablas llevan empresa_id para poder servir a más de un centro de servicio.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, LargeBinary, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

KG = Numeric(12, 3)


class Base(DeclarativeBase):
    pass


class Empresa(Base):
    __tablename__ = "empresa"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TipoAcero(Base):
    __tablename__ = "tipo_acero"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo"), UniqueConstraint("empresa_id", "nombre"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    codigo: Mapped[str] = mapped_column(String(3))
    nombre: Mapped[str] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Norma(Base):
    __tablename__ = "norma"
    __table_args__ = (UniqueConstraint("empresa_id", "nombre"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nombre: Mapped[str] = mapped_column(String(60))
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Tercero(Base):
    """Propietarios, clientes y siderúrgicas."""
    __tablename__ = "tercero"
    __table_args__ = (UniqueConstraint("empresa_id", "nombre"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nombre: Mapped[str] = mapped_column(String(160))
    rif: Mapped[str | None] = mapped_column(String(20))
    telefono: Mapped[str | None] = mapped_column(String(40))
    correo: Mapped[str | None] = mapped_column(String(120))
    es_cliente: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    es_siderurgica: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    dias_gracia_almacen: Mapped[int | None] = mapped_column(Integer)  # None = el valor general
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Ficha del cliente (Lista de Clientes del libro de formatos)
    direccion: Mapped[str | None] = mapped_column(String(300))
    estado_region: Mapped[str | None] = mapped_column(String(60))
    ciudad: Mapped[str | None] = mapped_column(String(80))
    forma_pago: Mapped[str | None] = mapped_column(String(40))
    vendedor: Mapped[str | None] = mapped_column(String(60))
    cliente_desde: Mapped[dt.date | None] = mapped_column(Date)


class Producto(Base):
    """Catálogo de lo que se cotiza y se despacha (Lista Productos del libro de formatos).

    El código sigue la convención de la empresa (tipo, acero, medidas); el peso unitario
    permite pasar de piezas a kg en notas de entrega y cotizaciones.
    """
    __tablename__ = "producto"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(200))
    peso_unitario_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Documento(Base):
    """Documento de entrada, OT, nota de entrega, liberación o ajuste."""
    __tablename__ = "documento"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    numero: Mapped[str | None] = mapped_column(String(80))
    fecha: Mapped[dt.date | None] = mapped_column(Date)
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    tercero_destino_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))  # nuevo dueño (liberación)
    observacion: Mapped[str | None] = mapped_column(Text)
    anulado: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    origen: Mapped[str | None] = mapped_column(String(12))
    creado_por: Mapped[str | None] = mapped_column(String(80))
    clave_idempotencia: Mapped[str | None] = mapped_column(String(80))
    documento_origen_id: Mapped[int | None] = mapped_column(ForeignKey("documento.id"))  # corrección -> NE
    encabezado: Mapped[dict | None] = mapped_column(JSON)  # NE impresa: chofer, placa, domicilio, cotización…
    estado: Mapped[str | None] = mapped_column(String(12))  # orden_despacho: pendiente | despachada
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tercero: Mapped[Tercero | None] = relationship(foreign_keys=[tercero_id], lazy="joined")
    tercero_destino: Mapped[Tercero | None] = relationship(foreign_keys=[tercero_destino_id], lazy="joined")


class DocumentoLinea(Base):
    """Líneas de un documento histórico del Excel, tal como se emitió. No mueven inventario."""
    __tablename__ = "documento_linea"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documento.id", ondelete="CASCADE"))
    posicion: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str | None] = mapped_column(String(60))
    descripcion: Mapped[str | None] = mapped_column(String(250))
    cantidad: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unidad: Mapped[str | None] = mapped_column(String(20))
    kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))


class Pieza(Base):
    """Bobina, fleje, paquete de láminas, lote de perfiles o producto general."""
    __tablename__ = "pieza"
    __table_args__ = (
        # Bobinas y flejes: un código físico por pieza. Láminas, perfiles y generales: una fila
        # por código de producto y dueño, con saldo en piezas (saldo_unidades no nulo).
        Index("pieza_codigo_unico", "empresa_id", "tipo", "codigo_fisico", unique=True,
              postgresql_where=text("NOT anulada AND saldo_unidades IS NULL")),
        Index("pieza_existencia_unica", "empresa_id", "tipo", "codigo_fisico", "propietario_id", unique=True,
              postgresql_where=text("NOT anulada AND saldo_unidades IS NOT NULL")),
        Index("pieza_disponibles", "empresa_id", "estado", "tipo"),
        Index("pieza_propietario", "propietario_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    tipo: Mapped[str] = mapped_column(String(10))
    codigo_fisico: Mapped[str] = mapped_column(String(200))
    codigo_producto: Mapped[str | None] = mapped_column(String(40))
    descripcion: Mapped[str | None] = mapped_column(String(200))
    tipo_acero_id: Mapped[int | None] = mapped_column(ForeignKey("tipo_acero.id"))
    norma_id: Mapped[int | None] = mapped_column(ForeignKey("norma.id"))
    espesor_mm: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    ancho_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 1))
    largo_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 1))
    calidad: Mapped[str | None] = mapped_column(String(10))
    propietario_id: Mapped[int] = mapped_column(ForeignKey("tercero.id"))
    siderurgica_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    buque: Mapped[str | None] = mapped_column(String(80))
    pieza_origen_id: Mapped[int | None] = mapped_column(ForeignKey("pieza.id"))
    orden_trabajo_id: Mapped[int | None] = mapped_column(ForeignKey("orden_trabajo.id"))
    fecha_entrada: Mapped[dt.date | None] = mapped_column(Date)
    peso_entrada_kg: Mapped[Decimal] = mapped_column(KG)
    saldo_kg: Mapped[Decimal] = mapped_column(KG)
    unidades_entrada: Mapped[int | None] = mapped_column(Integer)
    saldo_unidades: Mapped[int | None] = mapped_column(Integer)  # None = se lleva solo en kg
    estado: Mapped[str] = mapped_column(String(12))
    anulada: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creado_por: Mapped[str] = mapped_column(String(80))

    propietario: Mapped[Tercero] = relationship(foreign_keys=[propietario_id], lazy="joined")
    tipo_acero: Mapped[TipoAcero | None] = relationship(lazy="joined")
    norma: Mapped[Norma | None] = relationship(lazy="joined")


class Movimiento(Base):
    __tablename__ = "movimiento"
    __table_args__ = (
        Index("movimiento_pieza", "pieza_id", "id"),
        Index("movimiento_idempotencia", "empresa_id", "clave_idempotencia", unique=True,
              postgresql_where=text("clave_idempotencia IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    pieza_id: Mapped[int] = mapped_column(ForeignKey("pieza.id"))
    tipo: Mapped[str] = mapped_column(String(12))
    kg: Mapped[Decimal] = mapped_column(KG)
    saldo_despues_kg: Mapped[Decimal] = mapped_column(KG)
    unidades: Mapped[int | None] = mapped_column(Integer)
    saldo_despues_unidades: Mapped[int | None] = mapped_column(Integer)
    propietario_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    propietario_nuevo_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documento.id"))
    fecha: Mapped[dt.date | None] = mapped_column(Date)
    origen: Mapped[str] = mapped_column(String(12))  # interfaz | portal | agente | importacion
    clave_idempotencia: Mapped[str | None] = mapped_column(String(80))
    observacion: Mapped[str | None] = mapped_column(Text)
    revierte_id: Mapped[int | None] = mapped_column(ForeignKey("movimiento.id"))  # ajuste que deshace otro
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creado_por: Mapped[str] = mapped_column(String(80))

    documento: Mapped[Documento | None] = relationship(lazy="joined")


class Auditoria(Base):
    """Historial de ediciones: quién cambió qué campo, cuándo, y desde dónde."""
    __tablename__ = "auditoria"
    __table_args__ = (Index("auditoria_registro", "tabla", "registro_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    tabla: Mapped[str] = mapped_column(String(40))
    registro_id: Mapped[int] = mapped_column(BigInteger)
    campo: Mapped[str] = mapped_column(String(60))
    antes: Mapped[str | None] = mapped_column(Text)
    despues: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str] = mapped_column(String(80))
    origen: Mapped[str] = mapped_column(String(12))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Parametro(Base):
    """Variables del sistema con vigencia (tarifa de almacén, días de gracia, tolerancias)."""
    __tablename__ = "parametro"
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), primary_key=True)
    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    vigente_desde: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(String(200))


class Usuario(Base):
    """Personas que entran a la app: socio, asistente o cliente (un cliente queda atado a su tercero)."""
    __tablename__ = "usuario"
    __table_args__ = (UniqueConstraint("empresa_id", "correo"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    correo: Mapped[str] = mapped_column(String(120))  # siempre en minúsculas
    nombre: Mapped[str] = mapped_column(String(120))
    rol: Mapped[str] = mapped_column(String(12))
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    clave_hash: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_acceso: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class OrdenTrabajo(Base):
    """Orden de corte o de trabajo (slitter, lámina, CTF, maquila, Losacero).

    La pieza de entrada se consume con un movimiento "consumo" y cada pieza producida
    nace con un movimiento "produccion" y queda ligada a la orden (pieza.orden_trabajo_id).
    """
    __tablename__ = "orden_trabajo"
    __table_args__ = (
        Index("orden_trabajo_numero", "empresa_id", "tipo", "numero"),
        Index("orden_trabajo_idempotencia", "empresa_id", "clave_idempotencia", unique=True,
              postgresql_where=text("clave_idempotencia IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    tipo: Mapped[str] = mapped_column(String(12))            # slitter | lamina | ctf | maquila | losacero
    numero: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[dt.date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(12))          # cerrada | anulada (luego: solicitada, aprobada)
    pieza_id: Mapped[int | None] = mapped_column(ForeignKey("pieza.id", use_alter=True, name="ot_pieza_fk"))
    propietario_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    estatus_corte: Mapped[str | None] = mapped_column(String(8))  # total | parcial
    kg_consumido: Mapped[Decimal] = mapped_column(KG)
    kg_producido: Mapped[Decimal] = mapped_column(KG)
    kg_scrap: Mapped[Decimal] = mapped_column(KG)
    paradas: Mapped[int | None] = mapped_column(Integer)
    calidad: Mapped[str | None] = mapped_column(String(10))
    detalle: Mapped[dict | None] = mapped_column(JSON)       # cortes: ancho, rollos, kg; scrap
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("documento.id"))
    observacion: Mapped[str | None] = mapped_column(Text)
    origen: Mapped[str] = mapped_column(String(12))
    clave_idempotencia: Mapped[str | None] = mapped_column(String(80))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creado_por: Mapped[str] = mapped_column(String(80))

    pieza: Mapped[Pieza | None] = relationship(foreign_keys=[pieza_id], lazy="joined")
    propietario: Mapped[Tercero | None] = relationship(lazy="joined")


class Secuencia(Base):
    """Último número emitido por tipo de documento (nota de entrega, cotización)."""
    __tablename__ = "secuencia"
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30), primary_key=True)
    ultimo: Mapped[int] = mapped_column(Integer)


class Archivo(Base):
    """Copia de un documento generado (PDF de una OC, etiquetas, nota de entrega)."""
    __tablename__ = "archivo"
    __table_args__ = (Index("archivo_referencia", "empresa_id", "ref_tabla", "ref_id", "nombre"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    ref_tabla: Mapped[str] = mapped_column(String(40))
    ref_id: Mapped[int] = mapped_column(BigInteger)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo_mime: Mapped[str] = mapped_column(String(60))
    contenido: Mapped[bytes] = mapped_column(LargeBinary)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creado_por: Mapped[str] = mapped_column(String(80))


class Conteo(Base):
    """Conteo físico de una existencia en el patio (auditoría). Queda aunque cuadre: es el punto de partida
    para explicar descuadres futuros sin volver al inicio. Si no cuadra, se ajusta (o se descarta) aparte.

    estado: cuadra | pendiente (hay diferencia sin resolver) | ajustado (con su documento de ajuste) | descartado
    """
    __tablename__ = "conteo"
    __table_args__ = (
        Index("conteo_pieza", "pieza_id", "fecha"),
        Index("conteo_fecha", "empresa_id", "fecha"),
        Index("conteo_idempotencia", "empresa_id", "clave_idempotencia", unique=True,
              postgresql_where=text("clave_idempotencia IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    pieza_id: Mapped[int] = mapped_column(ForeignKey("pieza.id"))
    propietario_id: Mapped[int] = mapped_column(ForeignKey("tercero.id"))   # el dueño el día del conteo
    fecha: Mapped[dt.date] = mapped_column(Date)
    unidad: Mapped[str] = mapped_column(String(4))                          # pzas | kg
    sistema: Mapped[Decimal] = mapped_column(KG)                            # lo que decía el sistema al contar
    contado: Mapped[Decimal] = mapped_column(KG)
    diferencia: Mapped[Decimal] = mapped_column(KG)                         # contado - sistema
    estado: Mapped[str] = mapped_column(String(12))
    ajuste_documento_id: Mapped[int | None] = mapped_column(ForeignKey("documento.id"))
    contado_por: Mapped[str | None] = mapped_column(String(80))
    observacion: Mapped[str | None] = mapped_column(Text)
    resolucion: Mapped[str | None] = mapped_column(Text)
    origen: Mapped[str] = mapped_column(String(12))
    clave_idempotencia: Mapped[str | None] = mapped_column(String(80))
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creado_por: Mapped[str] = mapped_column(String(80))
    resuelto_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    resuelto_por: Mapped[str | None] = mapped_column(String(80))

    pieza: Mapped[Pieza] = relationship(lazy="joined")
    propietario: Mapped[Tercero] = relationship(lazy="joined")
    ajuste_documento: Mapped[Documento | None] = relationship(lazy="joined")
