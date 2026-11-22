"""Puertos: lo que el núcleo de la aplicación necesita del exterior, sin saber cómo se hace.

Arquitectura hexagonal (puertos y adaptadores):

    dominio/       entidades y reglas puras (sin base de datos ni web)
    servicios/     casos de uso; hablan con el exterior solo por estos puertos
    puertos.py     contratos (este archivo)
    adaptadores/   implementaciones: sql/ (PostgreSQL), memoria.py (pruebas), pdf/ (ReportLab)
    rutas/         adaptador de entrada HTTP (FastAPI)
    importador/    adaptador de entrada por lotes desde los libros de Excel
    dependencias.py  raíz de composición: qué adaptador usa cada puerto

Los casos de uso reciben una UnidadDeTrabajo: todo lo que hacen ocurre en una sola
transacción, y quien la abre (la ruta HTTP) decide si se confirma o se deshace.
"""
from __future__ import annotations

import datetime as dt
from typing import Protocol

from app.dominio.entidades import (
    Documento, Movimiento, Norma, OrdenTrabajo, Pieza, ProductoCatalogo, Tercero, TipoAcero,
)
from app.dominio.impresion import (
    AtadoImpreso, HojaTrabajo, NotaEntregaImpresa, ReciboEntradaImpreso, ReporteInventario, DespachoImpreso, OrdenLaminaImpresa, OrdenMaquilaImpresa, OrdenSlitterImpresa, RolloImpreso,
)


class RepositorioPiezas(Protocol):
    def obtener(self, id_: int, *, bloquear: bool = False) -> Pieza | None: ...

    def obtener_varias(self, ids: list[int], *, bloquear: bool = False) -> dict[int, Pieza]: ...

    def id_por_codigo(self, tipo: str, codigo: str, *, excluir_id: int | None = None) -> int | None: ...

    def producidas_por(self, orden_id: int) -> list[Pieza]: ...

    def existencia(self, tipo: str, codigo: str, propietario_id: int, *, bloquear: bool = False) -> Pieza | None:
        """La fila de existencia de una lámina, perfil o general: un código de producto de un dueño."""
        ...

    def existencias_de(self, propietario_id: int, tipo: str) -> list[Pieza]:
        """Todas las existencias (por piezas, sin anular) de ese tipo que tiene un dueño."""
        ...

    def agregar(self, p: Pieza) -> Pieza: ...

    def guardar(self, p: Pieza) -> None: ...


class RepositorioMovimientos(Protocol):
    def agregar(self, mv: Movimiento) -> Movimiento: ...

    def por_clave(self, clave: str) -> Movimiento | None: ...

    def por_documento(self, documento_id: int) -> list[Movimiento]: ...

    def contar(self, pieza_id: int, *, excepto_tipo: str | None = None) -> int: ...

    def revertidos(self, ids: list[int]) -> set[int]:
        """De esos movimientos, los que ya fueron deshechos por otro (revierte_id)."""
        ...


class RepositorioDocumentos(Protocol):
    def agregar(self, d: Documento) -> Documento: ...

    def obtener(self, id_: int) -> Documento | None: ...

    def guardar(self, d: Documento) -> None: ...

    def por_clave(self, clave: str) -> Documento | None: ...

    def numero_en_uso(self, tipo: str, numero: str) -> bool: ...

    def correcciones(self, documento_id: int) -> list[Documento]:
        """Las correcciones hechas a una nota de entrega."""
        ...

    def abiertos(self, tipo: str) -> list[Documento]:
        """Documentos de ese tipo en estado pendiente y sin anular (órdenes de despacho por preparar)."""
        ...

    def agregar_lineas(self, documento_id: int, lineas: list[dict]) -> None:
        """Renglones que no mueven inventario (codigo, descripcion, cantidad, unidad, kg)."""
        ...

    def lineas(self, documento_id: int) -> list[dict]: ...

    def con_referencia_abono(self, tipo: str, referencia: str) -> Documento | None:
        """El documento de ese tipo que ya tiene un abono con esa referencia (pagos repetidos)."""
        ...


class RepositorioOrdenes(Protocol):
    def agregar(self, o: OrdenTrabajo) -> OrdenTrabajo: ...

    def obtener(self, id_: int) -> OrdenTrabajo | None: ...

    def guardar(self, o: OrdenTrabajo) -> None: ...

    def por_clave(self, clave: str) -> OrdenTrabajo | None: ...

    def ultimo_numero(self, tipo: str) -> int: ...

    def numero_en_uso(self, tipo: str, numero: int) -> bool: ...

    def planificadas(self) -> list[OrdenTrabajo]: ...


class RepositorioTerceros(Protocol):
    def obtener(self, id_: int) -> Tercero | None: ...


class RepositorioCatalogos(Protocol):
    def tipo_por_codigo(self, codigo: str) -> TipoAcero | None: ...

    def norma(self, id_: int) -> Norma | None: ...

    def producto(self, codigo: str) -> ProductoCatalogo | None:
        """Producto del catálogo (activo) por código, para nombre y peso por pieza."""
        ...


class RepositorioParametros(Protocol):
    def valor(self, clave: str, por_defecto: str, fecha: dt.date | None = None) -> str: ...


class RegistroAuditoria(Protocol):
    def registrar(self, tabla: str, registro_id: int, campo: str, antes: str | None, despues: str | None, *,
                  usuario: str, origen: str) -> None: ...


class GeneradorDocumentos(Protocol):
    def orden_slitter(self, orden: OrdenSlitterImpresa) -> bytes: ...

    def etiquetas_slitter(self, orden: OrdenSlitterImpresa, rollos: list[RolloImpreso] | None = None) -> bytes: ...

    def orden_lamina(self, orden: OrdenLaminaImpresa) -> bytes: ...

    def etiquetas_lamina(self, orden: OrdenLaminaImpresa, atados: list[AtadoImpreso] | None = None) -> bytes:
        """Una etiqueta por atado de primera y una por cada clase de segunda."""
        ...

    def orden_maquila(self, orden: OrdenMaquilaImpresa) -> bytes: ...

    def etiquetas_maquila(self, orden: OrdenMaquilaImpresa, paquetes: list[AtadoImpreso] | None = None) -> bytes: ...

    def nota_entrega(self, ne: NotaEntregaImpresa) -> bytes: ...

    def cotizacion(self, cotizacion) -> bytes:
        """Cotización en USD, formato de Prosifer."""
        ...

    def hoja_trabajo(self, hoja: HojaTrabajo) -> bytes: ...

    def despacho(self, documento: DespachoImpreso) -> bytes:
        """Orden de despacho del cliente o nota de salida."""
        ...

    def reporte_inventario(self, reporte: ReporteInventario) -> bytes:
        """Inventario disponible de un cliente, por categoría o total, para auditar en patio."""
        ...

    def recibo_entrada(self, recibo: ReciboEntradaImpreso, abajo: bool = False) -> bytes:
        """Media carta arriba (o abajo, para aprovechar una hoja ya usada)."""


class Numerador(Protocol):
    """Numeración correlativa sin huecos ni repetidos (notas de entrega, cotizaciones)."""

    def siguiente(self, tipo: str) -> int: ...

    def ver_siguiente(self, tipo: str) -> int: ...


class AlmacenArchivos(Protocol):
    """Copias de los documentos generados, para reimprimir exactamente lo que se entregó."""

    def guardar(self, ref_tabla: str, ref_id: int, nombre: str, contenido: bytes, *, tipo_mime: str,
                usuario: str) -> int: ...

    def buscar(self, ref_tabla: str, ref_id: int, nombre: str) -> bytes | None: ...


class UnidadDeTrabajo(Protocol):
    empresa_id: int
    piezas: RepositorioPiezas
    movimientos: RepositorioMovimientos
    documentos: RepositorioDocumentos
    ordenes: RepositorioOrdenes
    terceros: RepositorioTerceros
    catalogos: RepositorioCatalogos
    parametros: RepositorioParametros
    auditoria: RegistroAuditoria
    numerador: Numerador
    archivos: AlmacenArchivos
