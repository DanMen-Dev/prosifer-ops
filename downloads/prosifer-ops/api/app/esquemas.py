from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Catálogos -------------------------------------------------------------

class TipoAceroIn(BaseModel):
    codigo: str = Field(min_length=2, max_length=3)
    nombre: str = Field(min_length=1, max_length=40)


class TipoAceroOut(Orm):
    id: int
    codigo: str
    nombre: str
    activo: bool


class NormaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)


class NormaOut(Orm):
    id: int
    nombre: str
    activo: bool


class CambioCatalogo(BaseModel):
    nombre: str | None = None
    codigo: str | None = None
    activo: bool | None = None


# --- Terceros --------------------------------------------------------------

class TerceroIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    rif: str | None = None
    telefono: str | None = None
    correo: str | None = None
    es_cliente: bool = True
    es_siderurgica: bool = False
    dias_gracia_almacen: int | None = Field(default=None, ge=0, le=365)
    direccion: str | None = Field(default=None, max_length=300)
    estado_region: str | None = Field(default=None, max_length=60)
    ciudad: str | None = Field(default=None, max_length=80)
    forma_pago: str | None = Field(default=None, max_length=40)
    vendedor: str | None = Field(default=None, max_length=60)


class CambioTercero(BaseModel):
    nombre: str | None = None
    rif: str | None = None
    telefono: str | None = None
    correo: str | None = None
    es_cliente: bool | None = None
    es_siderurgica: bool | None = None
    dias_gracia_almacen: int | None = Field(default=None, ge=0, le=365)
    activo: bool | None = None
    direccion: str | None = Field(default=None, max_length=300)
    estado_region: str | None = Field(default=None, max_length=60)
    ciudad: str | None = Field(default=None, max_length=80)
    forma_pago: str | None = Field(default=None, max_length=40)
    vendedor: str | None = Field(default=None, max_length=60)


class TerceroOut(Orm):
    id: int
    nombre: str
    rif: str | None
    telefono: str | None
    correo: str | None
    es_cliente: bool
    es_siderurgica: bool
    dias_gracia_almacen: int | None
    activo: bool
    direccion: str | None = None
    estado_region: str | None = None
    ciudad: str | None = None
    forma_pago: str | None = None
    vendedor: str | None = None
    cliente_desde: dt.date | None = None


# --- Productos -------------------------------------------------------------

class ProductoOut(Orm):
    id: int
    codigo: str
    nombre: str
    peso_unitario_kg: Decimal | None
    activo: bool


class CambioProducto(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    peso_unitario_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    activo: bool | None = None


class GenerarProductoIn(BaseModel):
    """Datos para que la app arme código y nombre (ver GET /api/productos/familias)."""
    familia: str = Field(max_length=40)
    material: str = Field(default="HN", max_length=4)
    subtipo: str | None = Field(default=None, max_length=20)
    espesor: str | None = Field(default=None, max_length=20, description="2,50 (mm) o 3/16'' (pulgadas)")
    medida1: str | None = Field(default=None, max_length=20)
    medida2: str | None = Field(default=None, max_length=20)
    largo_mm: Decimal | None = Field(default=None, gt=0, lt=100000)
    segunda: str | None = Field(default=None, pattern="^[ABC]$")


class ProductoGenerado(BaseModel):
    codigo: str
    nombre: str
    existente: ProductoOut | None = None


class VariantesEspesorIn(BaseModel):
    codigo: str = Field(max_length=60, description="Producto del catálogo que se va a fabricar (por ejemplo un perfil)")
    espesor_mm: Decimal = Field(gt=0, lt=100, description="Espesor real del material que entra")


class VariantesEspesor(BaseModel):
    """El mismo producto con el espesor real y, si difiere, con el comercial (redondeado)."""
    espesor_real: Decimal
    espesor_comercial: Decimal | None
    real: ProductoGenerado
    comercial: ProductoGenerado | None


class PerfilSugerido(BaseModel):
    """Un perfil que suele salir del fleje, con el espesor real y (si difiere) el comercial."""
    nombre: str
    espesor_real: Decimal
    espesor_comercial: Decimal | None
    real: ProductoGenerado
    comercial: ProductoGenerado | None


class ProductoIn(BaseModel):
    codigo: str | None = Field(default=None, max_length=40,
                               description="Vacío: la app lo asigna con el prefijo del nombre (PUE0001, PUE0002…)")
    nombre: str = Field(min_length=2, max_length=200)
    peso_unitario_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)


# --- Entradas --------------------------------------------------------------

class EntradaBobinaIn(BaseModel):
    documento_numero: str = Field(min_length=1, max_length=80)
    fecha: dt.date
    codigo_bobina: str = Field(min_length=2, max_length=80)
    tipo_acero: str = Field(description="Código (HP, HN, GV, ES, PP, AL) o nombre (LAM FRIO...)")
    norma_id: int | None = None
    espesor_mm: Decimal = Field(gt=0, lt=100)
    ancho_mm: Decimal = Field(gt=0, lt=10000)
    peso_kg: Decimal = Field(gt=0)
    propietario_id: int
    siderurgica_id: int | None = None
    buque: str | None = Field(default=None, max_length=80)
    confirmar: bool = Field(
        default=False,
        description="false = solo valida y devuelve el resumen para la ventana de confirmación; true = guarda")
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class ResumenEntrada(BaseModel):
    guardada: bool
    codigo_producto: str
    descripcion: str
    propietario: str
    avisos: list[str]
    pieza_id: int | None = None


class EntradaExistenciaIn(BaseModel):
    """Entrada de láminas, perfiles o productos generales por piezas (compra, recepción, devolución)."""
    tipo: str | None = Field(default=None, pattern="^(lamina|perfil|general)$",
                             description="Vacío = por el código: LAM… lámina, PER… perfil, el resto general")
    codigo_producto: str = Field(min_length=3, max_length=40)
    descripcion: str | None = Field(default=None, max_length=200, description="Vacío = la del catálogo")
    propietario_id: int
    unidades: int = Field(gt=0, le=1_000_000)
    peso_unitario_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4,
                                             description="Vacío = el del catálogo")
    calidad: str | None = Field(default=None, max_length=10)
    documento_tipo: str = Field(default="Nota de entrega", max_length=40)
    documento_numero: str = Field(min_length=1, max_length=80)
    fecha: dt.date
    observacion: str | None = Field(default=None, max_length=1000)
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class ResumenEntradaExistencia(BaseModel):
    guardada: bool
    tipo: str
    codigo_producto: str
    descripcion: str
    propietario: str
    unidades: int
    peso_unitario_kg: Decimal
    kg: Decimal
    existencia_antes: int
    existencia_despues: int
    avisos: list[str]
    pieza_id: int | None = None
    documento_id: int | None = None       # para imprimir el recibo de entrada
    # Existencias del mismo dueño con las mismas medidas (o descripción) bajo OTRO código: si se registra
    # con el código nuevo quedan dos líneas del mismo material en vez de sumarse.
    similares: list["ExistenciaSimilar"] = []


class ExistenciaSimilar(BaseModel):
    pieza_id: int
    codigo: str
    descripcion: str | None
    saldo_unidades: int | None


# --- Existencias y piezas --------------------------------------------------

class PiezaOut(Orm):
    id: int
    tipo: str
    codigo_fisico: str
    codigo_producto: str | None
    descripcion: str | None
    espesor_mm: Decimal | None
    ancho_mm: Decimal | None
    largo_mm: Decimal | None
    calidad: str | None
    propietario_id: int
    propietario_nombre: str
    tipo_acero: str | None
    norma: str | None
    buque: str | None
    pieza_origen_id: int | None
    fecha_entrada: dt.date | None
    peso_entrada_kg: Decimal
    saldo_kg: Decimal
    estado: str
    unidades_entrada: int | None = None
    saldo_unidades: int | None = None
    # Ocupación (no cambia el saldo): bobina o fleje en una OC planificada o reservada en una orden de
    # despacho abierta; en láminas, perfiles y generales, las piezas reservadas en despachos abiertos.
    en_proceso: str | None = None            # "OC slitter 125"
    reservada_en: str | None = None          # "orden de despacho 7, 9"
    unidades_reservadas: int | None = None


class Existencias(BaseModel):
    piezas: list[PiezaOut]
    total_piezas: int
    total_kg: Decimal
    total_unidades: int | None = None   # solo si todas las filas se llevan en piezas


class MovimientoOut(Orm):
    id: int
    tipo: str
    kg: Decimal
    saldo_despues_kg: Decimal
    unidades: int | None = None
    saldo_despues_unidades: int | None = None
    fecha: dt.date | None
    documento_tipo: str | None
    documento_numero: str | None
    propietario_anterior_id: int | None
    propietario_nuevo_id: int | None
    origen: str
    observacion: str | None
    creado_por: str
    creado_en: dt.datetime


class FichaPieza(BaseModel):
    pieza: PiezaOut
    movimientos: list[MovimientoOut]
    hijas: list[PiezaOut]
    origen: "OrigenPieza | None" = None
    conteos: list["ConteoOut"] = Field(default_factory=list, description="Conteos físicos en patio, el último primero")


class UnionExistencias(BaseModel):
    destino_id: int = Field(description="La existencia que se queda con las piezas (la del código correcto)")
    motivo: str = Field(min_length=5, max_length=300)


class CambioPieza(BaseModel):
    """Datos descriptivos que la asistente puede corregir sin pasar por el socio."""
    codigo_fisico: str | None = Field(default=None, min_length=2, max_length=200)
    descripcion: str | None = None
    norma_id: int | None = None
    buque: str | None = None
    calidad: str | None = None
    fecha_entrada: dt.date | None = None


# --- Usuarios y sesión -----------------------------------------------------

class Ingreso(BaseModel):
    correo: str = Field(min_length=3, max_length=120)
    clave: str = Field(min_length=1, max_length=200)


class UsuarioOut(Orm):
    id: int
    correo: str
    nombre: str
    rol: str
    tercero_id: int | None
    activo: bool
    ultimo_acceso: dt.datetime | None
    empresa: str | None = None     # la del cliente, o Prosifer para el personal: se muestra arriba a la derecha


class Sesion(BaseModel):
    ficha: str
    usuario: UsuarioOut


class UsuarioIn(BaseModel):
    correo: str = Field(min_length=3, max_length=120)
    nombre: str = Field(min_length=2, max_length=120)
    rol: str = Field(pattern="^(socio|asistente|cliente)$")
    tercero_id: int | None = None
    clave: str = Field(min_length=1, max_length=200)


class CambioUsuario(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    rol: str | None = Field(default=None, pattern="^(socio|asistente|cliente)$")
    tercero_id: int | None = None
    activo: bool | None = None
    clave: str | None = Field(default=None, min_length=1, max_length=200)


class Anulacion(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


# --- Órdenes de trabajo ----------------------------------------------------

class CortePlanIn(BaseModel):
    ancho_mm: Decimal = Field(gt=0, lt=3000)
    rollos: int = Field(ge=1, le=15)


class PlanOtIn(BaseModel):
    """OC planificada: se crea antes del corte, se imprime la hoja de trabajo y los resultados se cargan después.
    La pieza (o los flejes) quedan "en proceso": no se pueden vender ni planificar en otra orden."""
    tipo: str = Field(pattern="^(slitter|lamina|ctf|maquila)$")
    fecha: dt.date
    numero: int | None = Field(default=None, ge=1, description="Vacío = el siguiente número")
    pieza_id: int | None = Field(default=None, description="Bobina (o fleje) que entra: slitter, laminadora y CTF")
    flejes: list[int] = Field(default_factory=list, max_length=6, description="Maquila: flejes que entran")
    cortes: list[CortePlanIn] = Field(default_factory=list, max_length=6, description="Slitter: anchos y rollos")
    largo_mm: Decimal | None = Field(default=None, gt=0, le=20000, description="Lámina o perfil")
    ancho_mm: Decimal | None = Field(default=None, gt=0, description="Lámina: vacío = el de la bobina")
    redondear_espesor: bool = False
    codigo_producto: str | None = Field(default=None, max_length=60, description="Maquila: perfil a fabricar")
    descripcion: str | None = Field(default=None, max_length=250)
    peso_teorico_kg: Decimal | None = Field(default=None, gt=0)
    calidad: str | None = Field(default=None, max_length=10)
    observacion: str | None = Field(default=None, max_length=1000)
    confirmar: bool = Field(default=True, description="false = vista previa: valida y devuelve el plan sin guardar")
    clave_idempotencia: str | None = Field(default=None, max_length=80,
                                           description="La misma clave no crea dos órdenes (agente, reintentos)")


class CorteSolicitudIn(BaseModel):
    ancho_mm: Decimal = Field(gt=0, lt=3000, description="Desarrollo o ancho del fleje")
    cortes: int = Field(ge=1, le=15, description="Cuántos flejes de ese ancho")


class SolicitudCorteIn(BaseModel):
    """Solicitud de orden de corte que el cliente precarga desde su portal (formato simple).

    No es todavía una orden: Prosifer la revisa en Órdenes de corte > Solicitudes de clientes y la
    autoriza (pasándola, con los cambios que haga falta, a una OC planificada) o la rechaza con un motivo.
    """
    tipo: str = Field(pattern="^(slitter|lamina|maquila)$")
    fecha: dt.date
    pieza_id: int | None = Field(default=None, description="Slitter y láminas: la bobina a cortar")
    flejes: list[int] = Field(default_factory=list, max_length=6, description="Maquila: los flejes a maquilar")
    # slitter
    cortes: list[CorteSolicitudIn] = Field(default_factory=list, max_length=6)
    peso_max_rollo_kg: Decimal | None = Field(default=None, gt=0, description="Slitter: peso máximo por rollo")
    embalaje: str | None = Field(default=None, pattern="^(ojo_al_cielo|vertical)$")
    corte_total: bool = Field(default=True, description="Slitter y láminas: toda la bobina o solo una parte")
    peso_max_kg: Decimal | None = Field(default=None, gt=0, description="Slitter parcial: kg aproximados a cortar")
    # láminas
    largo_mm: Decimal | None = Field(default=None, gt=0, le=20000)
    cantidad_laminas: int | None = Field(default=None, ge=1, description="Láminas parcial: cuántas")
    # maquila
    codigo_producto: str | None = Field(default=None, max_length=60, description="Perfil a fabricar (sugerido)")
    descripcion: str | None = Field(default=None, max_length=250)
    comentarios: str | None = Field(default=None, max_length=800)


class SolicitudCorteOut(BaseModel):
    id: int
    numero: str
    estado: str = Field(description="pendiente (por revisar) | aprobada | rechazada | cancelada")
    tipo: str
    fecha: dt.date
    tercero_id: int
    tercero: str
    piezas: list[PiezaOut]
    pedido: dict = Field(description="Lo que pidió: cortes, largo, perfil, corte total o parcial, embalaje…")
    texto: str = Field(description="El pedido en palabras, como irá a la observación de la orden")
    comentarios: str | None = None
    creado_por: str | None = None
    creado_en: dt.datetime | None = None
    orden_id: int | None = None
    orden_numero: int | None = None
    motivo: str | None = Field(default=None, description="Por qué se rechazó o se canceló")
    revisado_por: str | None = None


class AprobacionSolicitudIn(PlanOtIn):
    """La OC planificada que sale de la solicitud, tal como Prosifer la autoriza (puede cambiar lo pedido)."""


class PlanOtOut(BaseModel):
    orden_id: int | None          # None en la vista previa
    tipo: str
    numero: int
    avisos: list[str] = []
    guardada: bool = True
    propietario: str | None = None
    piezas: list[dict] = []        # lo que entra: id, codigo, descripcion, kg (para mostrar antes de confirmar)
    plan: dict | None = None


class CorteSlitterIn(BaseModel):
    ancho_mm: Decimal = Field(gt=0, lt=3000)
    rollos: int = Field(ge=1, le=15)
    kg: Decimal | None = Field(default=None, gt=0, description="Vacío = se reparte según el ancho")
    calidad: str | None = Field(default=None, max_length=10)


class OtSlitterIn(BaseModel):
    pieza_id: int = Field(description="Bobina (o fleje) que entra al slitter")
    fecha: dt.date
    numero: int | None = Field(default=None, ge=1, description="Vacío = el siguiente número")
    estatus_corte: str = Field(pattern="^(total|parcial)$")
    kg_procesado: Decimal | None = Field(default=None, gt=0, description="Obligatorio si el corte es parcial")
    cortes: list[CorteSlitterIn] = Field(min_length=1, max_length=6)
    scrap_ancho_mm: Decimal = Field(default=Decimal("0"), ge=0)
    scrap_kg: Decimal | None = Field(default=None, ge=0)
    calidad: str | None = Field(default=None, max_length=10)
    paradas: int | None = Field(default=None, ge=0)
    observacion: str | None = Field(default=None, max_length=1000)
    orden_planificada_id: int | None = Field(default=None, description="La OC planificada cuyos resultados se cargan")
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class RolloPlan(BaseModel):
    codigo: str
    kg: Decimal


class CortePlanOut(BaseModel):
    posicion: int
    ancho_mm: Decimal
    rollos: int
    kg: Decimal
    codigo_producto: str
    descripcion: str
    calidad: str | None
    detalle_rollos: list[RolloPlan]


class ResumenOtSlitter(BaseModel):
    guardada: bool
    orden_id: int | None = None
    numero: int
    bobina: str
    propietario: str
    estatus_corte: str
    kg_consumido: Decimal
    kg_producido: Decimal
    kg_scrap: Decimal
    diferencia_pct: Decimal
    saldo_restante_kg: Decimal
    cortes: list[CortePlanOut]
    avisos: list[str]


class OtLaminaIn(BaseModel):
    """Orden de corte a lámina: laminadora (maquina="lamina") o CTF (maquina="ctf")."""
    maquina: str = Field(default="lamina", pattern="^(lamina|ctf)$")
    pieza_id: int = Field(description="Bobina (o fleje, en la CTF) que entra")
    fecha: dt.date
    numero: int | None = Field(default=None, ge=1, description="Vacío = el siguiente número")
    estatus_corte: str = Field(pattern="^(total|parcial)$")
    kg_procesado: Decimal | None = Field(default=None, gt=0, description="Obligatorio si el corte es parcial")
    largo_mm: Decimal = Field(gt=0, le=20000)
    ancho_mm: Decimal | None = Field(default=None, gt=0, description="Vacío = el ancho de la pieza")
    atados: list[int] = Field(default_factory=list, max_length=8, description="Láminas de primera en cada atado")
    segunda_a: int = Field(default=0, ge=0)
    segunda_b: int = Field(default=0, ge=0)
    segunda_c: int = Field(default=0, ge=0)
    scrap_kg: Decimal = Field(default=Decimal("0"), ge=0, description="Puntas, recortes y lo que no es lámina")
    calidad: str | None = Field(default=None, max_length=10, description="Calidad de la primera: 1er-F, 1er-G…")
    redondear_espesor: bool = Field(default=False, description="Lámina con el espesor comercial (0,58 -> 0,60) en el "
                                    "nombre y en el código; si no, el espesor real de la bobina")
    paradas: int | None = Field(default=None, ge=0)
    observacion: str | None = Field(default=None, max_length=1000)
    orden_planificada_id: int | None = Field(default=None, description="La OC planificada cuyos resultados se cargan")
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class GrupoLaminaOut(BaseModel):
    clase: str                  # "1" primera; "A", "B", "C" segunda
    calidad: str
    codigo_producto: str
    descripcion: str
    unidades: int
    kg: Decimal
    existencia_despues: int | None = None


class AtadoOut(BaseModel):
    atado: int
    unidades: int
    kg: Decimal
    codigo: str


class ResumenOtLamina(BaseModel):
    guardada: bool
    orden_id: int | None = None
    maquina: str
    numero: int
    pieza: str
    propietario: str
    estatus_corte: str
    kg_consumido: Decimal
    kg_producido: Decimal
    kg_scrap: Decimal
    saldo_restante_kg: Decimal
    largo_mm: Decimal
    ancho_mm: Decimal
    total_laminas: int
    kg_por_lamina: Decimal
    kg_teorico_por_lamina: Decimal
    diferencia_teorico_pct: Decimal
    espesor_real: Decimal | None = None
    espesor_comercial: Decimal | None = None   # distinto del real: la pantalla pregunta si se redondea
    grupos: list[GrupoLaminaOut]
    atados: list[AtadoOut]
    avisos: list[str]


class FlejeMaquilaIn(BaseModel):
    pieza_id: int
    kg: Decimal | None = Field(default=None, gt=0, description="Vacío = todo el fleje")


class OtMaquilaIn(BaseModel):
    """Maquila de perfiles: flejes de un cliente → perfiles del catálogo."""
    fecha: dt.date
    numero: int | None = Field(default=None, ge=1, description="Vacío = el siguiente número")
    flejes: list[FlejeMaquilaIn] = Field(min_length=1, max_length=6)
    codigo_producto: str = Field(min_length=3, max_length=40, description="Perfil de primera (PER…)")
    descripcion: str | None = Field(default=None, max_length=200, description="Vacío = la del catálogo")
    peso_teorico_kg: Decimal | None = Field(default=None, gt=0, description="Vacío = el del catálogo")
    paquetes: list[int] = Field(default_factory=list, max_length=12, description="Perfiles de primera en cada paquete")
    segunda_a: int = Field(default=0, ge=0)
    segunda_b: int = Field(default=0, ge=0)
    segunda_c: int = Field(default=0, ge=0)
    scrap_kg: Decimal = Field(default=Decimal("0"), ge=0)
    calidad: str | None = Field(default=None, max_length=10)
    paradas: int | None = Field(default=None, ge=0)
    observacion: str | None = Field(default=None, max_length=1000)
    orden_planificada_id: int | None = Field(default=None, description="La OC planificada cuyos resultados se cargan")
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class FlejeConsumidoOut(BaseModel):
    pieza_id: int
    codigo: str
    kg: Decimal
    saldo_restante_kg: Decimal


class PaqueteOut(BaseModel):
    paquete: int
    unidades: int
    kg: Decimal
    codigo: str


class ResumenOtMaquila(BaseModel):
    guardada: bool
    orden_id: int | None = None
    numero: int
    propietario: str
    flejes: list[FlejeConsumidoOut]
    kg_consumido: Decimal
    kg_producido: Decimal
    kg_scrap: Decimal
    total_perfiles: int
    kg_por_pieza: Decimal
    kg_teorico: Decimal | None
    diferencia_teorico_pct: Decimal | None
    grupos: list[GrupoLaminaOut]
    paquetes: list[PaqueteOut]
    avisos: list[str]


class OrdenOut(BaseModel):
    id: int
    tipo: str
    numero: int
    fecha: dt.date | None
    estado: str
    pieza_id: int | None
    codigo_pieza: str | None
    propietario: str | None
    estatus_corte: str | None
    kg_consumido: Decimal
    kg_producido: Decimal
    kg_scrap: Decimal
    piezas_producidas: int
    calidad: str | None
    paradas: int | None
    observacion: str | None
    origen: str
    creado_por: str
    plan: dict | None = None        # OC planificada: lo pedido (cortes, largo, perfil, flejes…)


class DetalleOrden(BaseModel):
    orden: OrdenOut
    detalle: dict | None
    pieza_entrada: "PiezaOut | None"
    producidas: list["PiezaOut"]


class OrigenPieza(BaseModel):
    pieza_id: int | None
    codigo: str | None
    orden_id: int | None
    orden_numero: int | None
    orden_tipo: str | None


# --- Salidas: notas de entrega, liberaciones y ajustes ---------------------

class LineaSalidaIn(BaseModel):
    pieza_id: int
    kg: Decimal | None = Field(default=None, gt=0, description="Bobinas y flejes. Vacío = toda la pieza")
    unidades: int | None = Field(default=None, gt=0, description="Láminas, perfiles y generales: piezas. Vacío = todas")


class EncabezadoNE(BaseModel):
    """Datos de la NE impresa. Lo que falte se toma de la ficha del cliente al imprimir."""
    domicilio_entrega: str | None = Field(default=None, max_length=300)
    telefonos: str | None = Field(default=None, max_length=80)
    condicion_pago: str | None = Field(default=None, max_length=60)
    vendedor: str | None = Field(default=None, max_length=60)
    cotizacion: str | None = Field(default=None, max_length=40)
    chofer: str | None = Field(default=None, max_length=80)
    placa: str | None = Field(default=None, max_length=20)
    nota_salida: str | None = Field(default=None, max_length=40)
    ciudad: str | None = Field(default=None, max_length=60)
    notas: str | None = Field(default=None, max_length=600, description="NOTAS IMPORTANTES de la hoja")

    def limpio(self) -> dict | None:
        d = {k: v.strip() for k, v in self.model_dump().items() if v and v.strip()}
        return d or None


class LineaLibreIn(BaseModel):
    """Renglón de un producto sin existencia (MATERIALESIRREG): solo registra el peso que sale."""
    codigo: str = Field(min_length=1, max_length=40)
    kg: Decimal = Field(gt=0)
    detalle: str | None = Field(default=None, max_length=150, description="Scrap, chatarra, recortes…")


class NotaEntregaIn(BaseModel):
    # El número lo asigna el sistema al guardar (correlativo); el usuario no lo escoge.
    fecha: dt.date
    tercero_id: int = Field(description="Cliente dueño del material que sale")
    lineas: list[LineaSalidaIn] = Field(default=[], max_length=200)
    libres: list[LineaLibreIn] = Field(default=[], max_length=20,
                                       description="Productos sin existencia (material de medidas irregulares)")

    @model_validator(mode="after")
    def _algo_sale(self):
        if not self.lineas and not self.libres:
            raise ValueError("agrega al menos una pieza o un renglón de material de medidas irregulares")
        return self
    observacion: str | None = Field(default=None, max_length=1000)
    encabezado: EncabezadoNE | None = None
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class DescargaHistoricaIn(BaseModel):
    """Material rezagado: lo que salió con una NE del histórico del Excel y nunca se descargó en la app.

    Primero con confirmar=false para revisar. La salida queda con la fecha de la NE y enlazada a ella.
    """
    lineas: list[LineaSalidaIn] = Field(min_length=1, max_length=200)
    confirmar: bool = False


class LiberacionIn(BaseModel):
    numero: str = Field(min_length=1, max_length=80)
    fecha: dt.date
    propietario_actual_id: int
    propietario_nuevo_id: int
    piezas: list[int] = Field(min_length=1, max_length=500)
    observacion: str | None = Field(default=None, max_length=1000)
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class CambioLineaNE(BaseModel):
    movimiento_id: int = Field(description="La línea de la NE que se corrige (su movimiento de salida)")
    pieza_id: int | None = Field(default=None, description="Producto correcto; vacío = el mismo")
    kg: Decimal | None = Field(default=None, gt=0, description="Bobinas y flejes: kg correctos")
    unidades: int | None = Field(default=None, gt=0, description="Láminas, perfiles y generales: piezas correctas")


class CorreccionNEIn(BaseModel):
    """Corrige cantidades o productos de una NE emitida en la app; el número de la NE no cambia."""
    cambios: list[CambioLineaNE] = Field(min_length=1, max_length=200)
    motivo: str = Field(min_length=5, max_length=500)
    fecha: dt.date | None = None
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class LineaCorreccionOut(BaseModel):
    antes_codigo: str
    antes_descripcion: str | None
    antes_kg: Decimal
    antes_unidades: int | None
    despues_codigo: str
    despues_descripcion: str | None
    despues_kg: Decimal
    despues_unidades: int | None


class ResumenCorreccionNE(BaseModel):
    guardada: bool
    numero: str | None
    tercero: str | None
    lineas: list[LineaCorreccionOut]
    avisos: list[str]
    documento_id: int | None = None


class AjusteIn(BaseModel):
    saldo_nuevo_kg: Decimal = Field(ge=0, description="En láminas, perfiles y generales manda saldo_nuevo_unidades")
    saldo_nuevo_unidades: int | None = Field(default=None, ge=0)
    motivo: str = Field(min_length=5, max_length=500)
    fecha: dt.date | None = None


class ConteoIn(BaseModel):
    """Lo que se contó en el patio. En láminas, perfiles y generales, piezas; en bobinas y flejes, kg."""
    contado: Decimal = Field(ge=0)
    fecha: dt.date | None = None
    contado_por: str | None = Field(default=None, max_length=80, description="Quién contó en el patio")
    observacion: str | None = Field(default=None, max_length=500)
    ajustar: bool = Field(default=False, description="Si no cuadra, ajustar el saldo al conteo (solo socio o agente)")
    confirmar: bool = Field(default=True, description="false: solo dice si cuadra, sin guardar")
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class ResolverConteoIn(BaseModel):
    accion: str = Field(pattern="^(ajustar|descartar)$")
    motivo: str | None = Field(default=None, max_length=500)


class ConteoOut(BaseModel):
    id: int | None
    guardado: bool = True
    pieza_id: int
    codigo: str
    descripcion: str | None
    tipo: str
    propietario_id: int
    propietario: str | None
    fecha: dt.date
    unidad: str
    sistema: Decimal
    contado: Decimal
    diferencia: Decimal
    estado: str
    ajuste_documento_id: int | None = None
    ajuste_anulado: bool = False
    contado_por: str | None = None
    observacion: str | None = None
    resolucion: str | None = None
    origen: str
    creado_por: str
    creado_en: dt.datetime | None = None
    resuelto_por: str | None = None


class LineaResumen(BaseModel):
    pieza_id: int
    codigo: str
    descripcion: str | None
    saldo_antes_kg: Decimal
    kg: Decimal
    saldo_despues_kg: Decimal
    saldo_antes_unidades: int | None = None
    unidades: int | None = None
    saldo_despues_unidades: int | None = None


class LineaLibre(BaseModel):
    codigo: str
    descripcion: str
    kg: Decimal


class ResumenSalida(BaseModel):
    guardada: bool
    documento_id: int | None = None
    tipo: str
    numero: str
    fecha: dt.date
    tercero: str
    tercero_nuevo: str | None = None
    lineas: list[LineaResumen]
    total_kg: Decimal
    avisos: list[str]
    libres: list[LineaLibre] = []   # sin existencia: no mueven inventario


class DocumentoOut(BaseModel):
    id: int
    tipo: str
    numero: str | None
    fecha: dt.date | None
    tercero_id: int | None = None
    tercero: str | None
    tercero_nuevo: str | None
    piezas: int
    total_kg: Decimal
    anulado: bool
    origen: str | None
    creado_por: str | None
    observacion: str | None
    encabezado: dict | None = None


class LineaDocumento(BaseModel):
    movimiento_id: int | None        # None en el histórico del Excel (no mueve inventario)
    pieza_id: int | None
    codigo: str
    descripcion: str | None
    tipo_movimiento: str
    kg: Decimal
    saldo_despues_kg: Decimal
    unidades: int | None = None
    saldo_despues_unidades: int | None = None
    cantidad: Decimal | None = None   # histórico: cantidad y unidad tal como se emitieron
    unidad: str | None = None


class DetalleDocumento(BaseModel):
    documento: DocumentoOut
    lineas: list[LineaDocumento]
    historico: bool = False            # NE cargada del Excel: solo consulta
    descargas: list[LineaDocumento] = []   # NE histórica: lo que ya se descargó del inventario con ella
    corregible: bool = False           # NE de la app, no anulada
    correcciones: list[DocumentoOut] = []


FichaPieza.model_rebuild()
ResumenEntradaExistencia.model_rebuild()
DetalleOrden.model_rebuild()


# --- Orden de despacho del cliente y nota de salida ---------------------------

class LineaDespachoIn(BaseModel):
    pieza_id: int
    kg: Decimal | None = Field(default=None, gt=0, description="Bobinas y flejes. Vacío = toda la pieza")
    unidades: int | None = Field(default=None, gt=0, description="Láminas, perfiles y generales: piezas. Vacío = todas")


class RetiroDespacho(BaseModel):
    """Quién y cuándo retira el material. El cliente lo indica; el patio lo confirma en la nota de salida."""
    fecha_retiro: dt.date | None = None
    retira: str | None = Field(default=None, max_length=80, description="Chofer o persona que retira")
    cedula: str | None = Field(default=None, max_length=20)
    placa: str | None = Field(default=None, max_length=20)
    transporte: str | None = Field(default=None, max_length=80, description="Empresa de transporte, si aplica")
    telefono: str | None = Field(default=None, max_length=40)

    def limpio(self) -> dict | None:
        d = {k: (v.isoformat() if isinstance(v, dt.date) else v.strip())
             for k, v in self.model_dump().items() if v and (not isinstance(v, str) or v.strip())}
        return d or None


class OrdenDespachoIn(BaseModel):
    """Orden de despacho: el cliente pide retirar material de su inventario en patio.

    Primero con confirmar=false para revisar (devuelve renglones y avisos sin guardar); luego con
    confirmar=true. Un usuario cliente no manda tercero_id (se usa el suyo); el personal y el
    agente lo indican.
    """
    tercero_id: int | None = Field(default=None, description="Cliente dueño del material (personal y agente)")
    fecha: dt.date = Field(description="Fecha de la orden")
    lineas: list[LineaDespachoIn] = Field(min_length=1, max_length=200)
    retiro: RetiroDespacho | None = None
    observacion: str | None = Field(default=None, max_length=1000)
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


class LineaDespachoOut(BaseModel):
    pieza_id: int
    tipo: str
    codigo: str
    descripcion: str | None
    kg: Decimal
    unidades: int | None = None
    saldo_kg: Decimal | None = None
    saldo_unidades: int | None = None


class OrdenDespachoOut(BaseModel):
    guardada: bool = True
    id: int | None = None
    numero: str
    estado: str = Field(description="borrador (sin guardar) | pendiente | despachada | anulada")
    fecha: dt.date
    tercero_id: int
    tercero: str
    lineas: list[LineaDespachoOut]
    total_kg: Decimal
    total_unidades: int | None = None
    retiro: dict | None = None
    observacion: str | None = None
    origen: str | None = None
    creado_por: str | None = None
    creado_en: dt.datetime | None = None
    nota_salida_id: int | None = None
    nota_salida_numero: str | None = None
    avisos: list[str] = []


class NotaSalidaIn(BaseModel):
    """Nota de salida de una orden de despacho: lo que realmente sale del patio.

    Sin `lineas` sale lo que pidió la orden; con `lineas` se ajusta (lo que no salga se libera).
    """
    fecha: dt.date
    lineas: list[LineaDespachoIn] | None = Field(default=None, max_length=200)
    libres: list[LineaLibreIn] = Field(default=[], max_length=20,
                                       description="Productos sin existencia (material de medidas irregulares)")
    retiro: RetiroDespacho | None = Field(default=None, description="Vacío = el de la orden")
    observacion: str | None = Field(default=None, max_length=1000)
    confirmar: bool = False
    clave_idempotencia: str | None = Field(default=None, max_length=80)


# --- Aviso de entrada: el cliente anuncia material que va a llegar ---------------

class TransporteAviso(BaseModel):
    chofer: str | None = Field(default=None, max_length=80)
    cedula: str | None = Field(default=None, max_length=20)
    placa: str | None = Field(default=None, max_length=20)
    transporte: str | None = Field(default=None, max_length=80, description="Empresa de transporte")
    telefono: str | None = Field(default=None, max_length=40)

    def limpio(self) -> dict | None:
        d = {k: v.strip() for k, v in self.model_dump().items() if v and v.strip()}
        return d or None


class RenglonAvisoIn(BaseModel):
    tipo: str = Field(pattern="^(bobina|fleje|lamina|perfil|general)$")
    codigo: str | None = Field(default=None, max_length=60, description="Código de la bobina o del producto, si se sabe")
    descripcion: str | None = Field(default=None, max_length=250)
    tipo_acero: str | None = Field(default=None, max_length=10, description="HP, HN, GV…")
    espesor_mm: Decimal | None = Field(default=None, gt=0, lt=100)
    ancho_mm: Decimal | None = Field(default=None, gt=0, lt=5000)
    largo_mm: Decimal | None = Field(default=None, gt=0, le=20000)
    cantidad: int | None = Field(default=None, ge=1, description="Piezas (bobinas, láminas, perfiles…)")
    peso_kg: Decimal | None = Field(default=None, gt=0, description="Peso total del renglón")


class AvisoEntradaIn(BaseModel):
    """El cliente anuncia material que va a llegar al patio. No mueve inventario: Prosifer lo usa para
    preparar la recepción y registrar la entrada cuando el material llega."""
    tercero_id: int | None = Field(default=None, description="Cliente dueño (personal y agente; el cliente no lo indica)")
    fecha_estimada: dt.date = Field(description="Cuándo llega el material")
    documento_tipo: str | None = Field(default=None, max_length=40, description="Nota de entrega, factura…")
    documento_numero: str | None = Field(default=None, max_length=80)
    proveedor: str | None = Field(default=None, max_length=120, description="Siderúrgica o proveedor de origen")
    transporte: TransporteAviso | None = None
    renglones: list[RenglonAvisoIn] = Field(min_length=1, max_length=100)
    comentarios: str | None = Field(default=None, max_length=800)


class AvisoEntradaOut(BaseModel):
    id: int
    numero: str
    estado: str = Field(description="pendiente (por llegar) | recibido | rechazado | cancelado")
    fecha: dt.date
    fecha_estimada: dt.date | None
    tercero_id: int
    tercero: str
    documento_tipo: str | None = None
    documento_numero: str | None = None
    proveedor: str | None = None
    transporte: dict | None = None
    renglones: list[dict]
    total_kg: Decimal
    total_piezas: int
    comentarios: str | None = None
    creado_por: str | None = None
    creado_en: dt.datetime | None = None
    nota: str | None = Field(default=None, description="Lo que anotó Prosifer al recibirlo o rechazarlo")
    revisado_por: str | None = None


class NotaAviso(BaseModel):
    nota: str | None = Field(default=None, max_length=500)
    forzar: bool = Field(default=False, description="Cerrar aunque haya renglones sin entrada enlazada "
                                                    "(se registraron a mano o no llegaron)")


class EnlaceEntradaAviso(BaseModel):
    """La entrada que se registró para un renglón del aviso (la pieza o existencia que sumó)."""
    pieza_id: int
    texto: str | None = Field(default=None, max_length=200, description="Lo que se registró, para mostrarlo")


# --- Cotizaciones (servicios y venta de material) ---------------------------------

class RenglonCotizacionIn(BaseModel):
    codigo: str | None = Field(default=None, max_length=60, description="Código del catálogo (servicio o producto)")
    descripcion: str = Field(min_length=1, max_length=250)
    cantidad: Decimal = Field(gt=0)
    unidad: str = Field(default="Pza", max_length=20, description="Kg, Pza, Servicio, TM…")
    precio_unitario: Decimal = Field(ge=0, description="USD por unidad")


class AbonoCotizacion(BaseModel):
    fecha: dt.date | None = None
    destino: str = Field(min_length=1, max_length=80, description="Caja USD, Banesco Panamá, Zelle, Binance…")
    monto: Decimal = Field(gt=0, description="USD")
    referencia: str | None = Field(default=None, max_length=80,
                                   description="Confirmación o id de la operación: la misma no se registra dos veces")
    comprobante: "ComprobanteIn | None" = Field(default=None, description="Captura del pago (solo al anotar un abono)")


class ComprobanteIn(BaseModel):
    """Imagen o PDF del pago, en base64 (como la entrega Evolution o un campo de archivo)."""
    nombre: str = Field(default="comprobante", max_length=100)
    tipo_mime: str = Field(pattern="^(image/(jpeg|png|webp)|application/pdf)$")
    base64: str = Field(min_length=10, max_length=8_000_000, description="Hasta unos 6 MB")


class CotizacionIn(BaseModel):
    """Cotización en USD. El número lo asigna la app (sigue la numeración del Excel)."""
    tercero_id: int
    fecha: dt.date
    renglones: list[RenglonCotizacionIn] = Field(min_length=1, max_length=30)
    vendedor: str | None = Field(default=None, max_length=60)
    condicion_pago: str | None = Field(default=None, max_length=60)
    nota_entrega: str | None = Field(default=None, max_length=40, description="N° de la NE relacionada, si hay")
    notas: str | None = Field(default=None, max_length=500, description="Notas adicionales (salen impresas)")
    iva_pct: Decimal | None = Field(default=None, ge=0, le=100)
    orden_trabajo_id: int | None = Field(default=None, description="La orden de corte o maquila que se cotiza")
    abonos: list[AbonoCotizacion] = Field(default=[], max_length=6, description="Pagos ya recibidos al emitirla")
    confirmar: bool = Field(default=True, description="false = vista previa: número y totales sin guardar")
    clave_idempotencia: str | None = Field(default=None, max_length=80,
                                           description="La misma clave no emite dos cotizaciones")


class CotizacionOut(BaseModel):
    id: int | None                   # None en la vista previa (confirmar=false)
    guardada: bool = True
    numero: str
    fecha: dt.date | None
    tercero_id: int | None
    tercero: str | None
    renglones: list[dict]            # codigo, descripcion, cantidad, unidad, precio_unitario, total
    subtotal: Decimal
    iva_pct: Decimal | None = None
    iva: Decimal
    total: Decimal
    abonos: list[dict] = []          # fecha, destino, monto
    abonado: Decimal
    saldo: Decimal
    vendedor: str | None = None
    condicion_pago: str | None = None
    nota_entrega: str | None = None
    notas: str | None = None
    orden_trabajo_id: int | None = None
    orden: str | None = None         # "OC slitter 125"
    anulada: bool = False
    motivo_anulacion: str | None = None
    historica: bool = False          # del Excel: solo consulta
    origen: str | None = None
    creado_por: str | None = None
    creado_en: dt.datetime | None = None


class BorradorCotizacion(BaseModel):
    """Lo que la app propone para cotizar una orden (servicio según máquina y acero, y los kg) o el reporte
    mensual de salidas (servicio de descarga, almacén y carga por la masa despachada)."""
    tercero_id: int | None
    tercero: str | None
    orden_trabajo_id: int | None = None
    orden: str | None = None
    renglones: list[RenglonCotizacionIn]
    notas: str | None = None         # comentarios que relacionan el servicio con el material (bobina, perfil, fleje)
    avisos: list[str] = []

AbonoCotizacion.model_rebuild()


class FilaReporteSalidas(BaseModel):
    nota_salida: str | None
    fecha: dt.date | None
    nota_entrega: str | None
    documento_id: int
    cantidad: Decimal | None
    descripcion: str | None
    kg: Decimal
    categoria: str = "general"       # bobina | fleje | lamina | perfil | general | irregular


class ExcluidoReporte(BaseModel):
    categoria: str
    nombre: str
    renglones: int
    kg: Decimal


class ReporteSalidas(BaseModel):
    """Salidas de material de un cliente en un período (NE emitidas, no anuladas): base del cobro de
    descarga, almacén y carga por la masa despachada."""
    tercero_id: int
    tercero: str
    desde: dt.date
    hasta: dt.date
    filas: list[FilaReporteSalidas]
    notas_entrega: int
    total_kg: Decimal
    excluidas: list[ExcluidoReporte] = []   # lo que no se cuenta (p. ej. bobinas y flejes: ya pagaron su servicio)

