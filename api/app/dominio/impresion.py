"""Datos de lo que se imprime (orden de corte, etiquetas). Sin dependencias: el adaptador
de PDF los recibe por el puerto GeneradorDocumentos y decide cómo dibujarlos."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class RolloImpreso:
    codigo: str
    posicion: str          # "1-A"
    kg: float
    corte: int             # posición del corte (1..6)
    calidad: str | None = None


@dataclass
class CorteImpreso:
    posicion: int
    ancho: float
    rollos: int
    kg: float
    codigo_producto: str
    descripcion: str


@dataclass
class OrdenSlitterImpresa:
    numero: int
    fecha: str
    bobina: str
    producto: str
    descripcion: str
    tipo_codigo: str
    tipo_nombre: str
    norma: str
    espesor: float
    ancho: float
    peso_entrada: float
    consumido: float
    dueno: str
    estatus: str
    calidad: str
    cortes: list[CorteImpreso]
    scrap_ancho: float
    scrap_kg: float
    rollos: list[RolloImpreso]
    registro: str
    paradas: int = 0
    observacion: str = ""
    anulada: bool = False
    extras: dict = field(default_factory=dict)


@dataclass
class GrupoImpreso:
    clase: str            # "1" primera; "A", "B", "C" segunda
    calidad: str
    codigo: str
    descripcion: str
    unidades: int
    kg: float


@dataclass
class AtadoImpreso:
    atado: int
    unidades: int
    kg: float
    codigo: str           # va en la etiqueta y en el QR


@dataclass
class OrdenLaminaImpresa:
    numero: int
    maquina: str          # "LAMINADORA" | "CTF"
    fecha: str
    pieza: str
    producto: str
    descripcion: str
    tipo_codigo: str
    tipo_nombre: str
    norma: str
    espesor: float
    ancho_pieza: float
    peso_entrada: float
    consumido: float
    dueno: str
    estatus: str
    largo: float
    ancho: float
    kg_por_lamina: float
    kg_teorico: float
    grupos: list[GrupoImpreso]
    atados: list[AtadoImpreso]
    scrap_kg: float
    registro: str
    paradas: int = 0
    observacion: str = ""
    anulada: bool = False

    @property
    def total_laminas(self) -> int:
        return sum(g.unidades for g in self.grupos)


@dataclass
class FlejeImpreso:
    codigo: str
    kg: float


@dataclass
class OrdenMaquilaImpresa:
    numero: int
    fecha: str
    dueno: str
    flejes: list[FlejeImpreso]
    tipo_codigo: str
    tipo_nombre: str
    norma: str
    espesor: float
    consumido: float
    scrap_kg: float
    kg_por_pieza: float
    kg_teorico: float | None
    grupos: list[GrupoImpreso]
    paquetes: list[AtadoImpreso]     # el número de paquete va en "atado"
    registro: str
    paradas: int = 0
    observacion: str = ""
    anulada: bool = False

    @property
    def total(self) -> int:
        return sum(g.unidades for g in self.grupos)


@dataclass
class RenglonNE:
    cantidad: Decimal
    unidad: str                      # Pza, Bob, Rollo
    descripcion: str
    codigo: str | None
    peso_unitario_kg: Decimal | None
    kg: Decimal


@dataclass
class NotaEntregaImpresa:
    """La NE como se imprime (formato de Prosifer, carta vertical)."""
    numero: str
    fecha: dt.date | None
    elaborada: dt.datetime | None
    cliente: str
    rif: str | None
    domicilio_entrega: str | None
    telefonos: str | None
    condicion_pago: str | None
    vendedor: str | None
    cotizacion: str | None
    chofer: str | None
    placa: str | None
    nota_salida: str | None
    ciudad: str
    notas: str | None
    renglones: list[RenglonNE]
    anulada: bool = False
    historica: bool = False          # del Excel: reimpresión de consulta

    @property
    def total_kg(self) -> Decimal:
        return sum((r.kg for r in self.renglones), Decimal("0"))


@dataclass
class PiezaHoja:
    codigo: str
    descripcion: str
    espesor_mm: Decimal | None
    ancho_mm: Decimal | None
    kg: Decimal
    norma: str | None = None
    tipo_acero: str | None = None


@dataclass
class HojaTrabajo:
    """OC planificada: la hoja que se imprime antes del corte, con casillas para anotar a mano."""
    orden_id: int
    tipo: str                        # slitter | lamina | ctf | maquila
    numero: int
    fecha: dt.date | None
    cliente: str
    piezas: list[PiezaHoja]
    plan: dict
    calidad: str | None = None
    observacion: str | None = None
    creado_por: str = ""
    anulada: bool = False

    @property
    def qr(self) -> str:
        """Lo que lee el teléfono (y, más adelante, el agente de WhatsApp) para cargar los resultados."""
        return f"PROSIFER OC {self.tipo.upper()} {self.numero} #{self.orden_id}"


@dataclass
class RenglonRecibo:
    cantidad: Decimal
    unidad: str
    descripcion: str
    codigo: str
    peso_unitario_kg: Decimal | None
    kg: Decimal


@dataclass
class ReciboEntradaImpreso:
    """Constancia de que Prosifer recibió material de un cliente (en custodia)."""
    numero: int
    fecha: dt.date | None
    cliente: str
    rif: str | None
    documento_cliente: str           # la carta, NE o guía con la que llegó el material
    renglones: list[RenglonRecibo]
    observacion: str | None
    registrado_por: str
    registrado: dt.datetime | None
    anulado: bool = False

    @property
    def total_kg(self) -> Decimal:
        return sum((r.kg for r in self.renglones), Decimal("0"))

    @property
    def total_piezas(self) -> Decimal:
        return sum((r.cantidad for r in self.renglones), Decimal("0"))


# --- Reporte de inventario (auditoría en patio) ------------------------------

@dataclass
class FilaInventario:
    codigo: str                     # código físico (bobina/fleje) o de producto
    descripcion: str
    tipo_acero: str | None          # código: HP, HN, GV…
    norma: str | None
    espesor_mm: Decimal | None
    ancho_mm: Decimal | None
    largo_mm: Decimal | None
    piezas: Decimal | None          # láminas, perfiles y generales; None en bobinas y flejes
    kg: Decimal
    fecha_entrada: dt.date | None = None

    @property
    def peso_unitario_kg(self) -> Decimal | None:
        return (self.kg / self.piezas) if self.piezas else None


@dataclass
class SeccionInventario:
    tipo: str                       # bobina | fleje | lamina | perfil | general
    filas: list[FilaInventario]

    @property
    def total_kg(self) -> Decimal:
        return sum((f.kg for f in self.filas), Decimal("0"))

    @property
    def total_piezas(self) -> Decimal:
        return sum((f.piezas if f.piezas is not None else Decimal("1") for f in self.filas), Decimal("0"))


@dataclass
class ReporteInventario:
    cliente: str
    rif: str | None
    generado: dt.datetime
    generado_por: str
    secciones: list[SeccionInventario]
    total: bool = False             # True: las cinco categorías, con resumen al inicio

    @property
    def total_kg(self) -> Decimal:
        return sum((s.total_kg for s in self.secciones), Decimal("0"))


# --- Orden de despacho y nota de salida ----------------------------------------

@dataclass
class DespachoImpreso:
    tipo: str                       # orden_despacho | nota_salida
    numero: str
    fecha: dt.date | None
    cliente: str
    rif: str | None
    estado: str                     # orden: pendiente | despachada | anulada; nota: emitida | anulada
    referencia: str | None          # "Nota de salida N° 3" en la orden; "Orden de despacho N° 5" en la nota
    renglones: list[RenglonRecibo]
    retiro: dict | None
    observacion: str | None
    creado_por: str
    creado_en: dt.datetime | None

    @property
    def anulado(self) -> bool:
        return self.estado == "anulada"

    @property
    def total_kg(self) -> Decimal:
        return sum((r.kg for r in self.renglones), Decimal("0"))

    @property
    def total_piezas(self) -> Decimal:
        return sum((r.cantidad for r in self.renglones), Decimal("0"))


@dataclass
class RenglonCotizacionImpreso:
    cantidad: Decimal
    unidad: str
    descripcion: str
    codigo: str | None
    precio_unitario: Decimal | None
    total: Decimal


@dataclass
class CotizacionImpresa:
    """La cotización como se imprime (formato de Prosifer, carta vertical, montos en USD)."""
    numero: str
    fecha: dt.date | None
    cliente: str
    rif: str | None
    domicilio: str | None
    telefonos: str | None
    condicion_pago: str | None
    vendedor: str | None
    nota_entrega: str | None
    ciudad: str
    notas: str | None
    renglones: list[RenglonCotizacionImpreso]
    subtotal: Decimal
    iva_pct: Decimal | None
    iva: Decimal
    total: Decimal
    abonos: list[str]                 # "13/11/2026 · Zelle · 100,00"
    anulada: bool = False
    historica: bool = False
