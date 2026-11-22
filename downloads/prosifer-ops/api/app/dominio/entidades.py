"""Entidades del dominio. Clases simples, sin base de datos ni web.

Los repositorios (puertos) las devuelven y las guardan; el adaptador SQL las traduce
a las tablas. Los campos marcados "lectura" los completa el repositorio al cargar
(nombres para mostrar) y no se guardan.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Tercero:
    id: int
    nombre: str


@dataclass
class TipoAcero:
    id: int
    codigo: str
    nombre: str


@dataclass
class Norma:
    id: int
    nombre: str


@dataclass
class ProductoCatalogo:
    id: int
    codigo: str
    nombre: str
    peso_unitario_kg: Decimal | None = None


@dataclass
class Pieza:
    id: int | None
    tipo: str                         # bobina | fleje | lamina | perfil | general
    codigo_fisico: str
    propietario_id: int
    peso_entrada_kg: Decimal
    saldo_kg: Decimal
    estado: str                       # disponible | agotado
    creado_por: str
    codigo_producto: str | None = None
    descripcion: str | None = None
    tipo_acero_id: int | None = None
    norma_id: int | None = None
    espesor_mm: Decimal | None = None
    ancho_mm: Decimal | None = None
    largo_mm: Decimal | None = None
    calidad: str | None = None
    siderurgica_id: int | None = None
    buque: str | None = None
    pieza_origen_id: int | None = None
    orden_trabajo_id: int | None = None
    fecha_entrada: dt.date | None = None
    anulada: bool = False
    # Láminas, perfiles y generales: existencia por código y dueño, en piezas además de kg.
    unidades_entrada: int | None = None
    saldo_unidades: int | None = None
    # lectura
    propietario_nombre: str = ""
    tipo_acero_codigo: str | None = None
    tipo_acero_nombre: str | None = None
    norma_nombre: str | None = None


TIPOS_POR_UNIDADES = ("lamina", "perfil", "general")


@dataclass
class Movimiento:
    id: int | None
    pieza_id: int
    tipo: str                         # entrada | consumo | produccion | salida | liberacion | ajuste
    kg: Decimal
    saldo_despues_kg: Decimal
    origen: str
    creado_por: str
    fecha: dt.date | None = None
    unidades: int | None = None
    saldo_despues_unidades: int | None = None
    documento_id: int | None = None
    propietario_anterior_id: int | None = None
    propietario_nuevo_id: int | None = None
    clave_idempotencia: str | None = None
    observacion: str | None = None
    revierte_id: int | None = None    # el ajuste que deshace otro movimiento (anulación, corrección)
    creado_en: dt.datetime | None = None


@dataclass
class Documento:
    id: int | None
    tipo: str                         # entrada | ot_slitter | nota_entrega | liberacion | ajuste | …
    numero: str | None = None
    fecha: dt.date | None = None
    tercero_id: int | None = None
    tercero_destino_id: int | None = None
    observacion: str | None = None
    anulado: bool = False
    origen: str | None = None
    creado_por: str | None = None
    clave_idempotencia: str | None = None
    documento_origen_id: int | None = None   # una corrección apunta a la NE que corrige
    encabezado: dict | None = None           # NE impresa: chofer, placa, domicilio, cotización…
    estado: str | None = None                # orden_despacho: pendiente | despachada


@dataclass
class OrdenTrabajo:
    id: int | None
    tipo: str                         # slitter | lamina | ctf | maquila | losacero
    numero: int
    estado: str                       # planificada | ejecutada | cerrada | anulada
    kg_consumido: Decimal
    kg_producido: Decimal
    kg_scrap: Decimal
    origen: str
    creado_por: str
    fecha: dt.date | None = None
    pieza_id: int | None = None
    propietario_id: int | None = None
    estatus_corte: str | None = None
    paradas: int | None = None
    calidad: str | None = None
    detalle: dict | None = field(default=None)
    documento_id: int | None = None
    observacion: str | None = None
    clave_idempotencia: str | None = None
    # lectura
    propietario_nombre: str = ""
