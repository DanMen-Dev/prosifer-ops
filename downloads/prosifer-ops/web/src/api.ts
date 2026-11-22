// Cliente de la API. La sesión (ficha + usuario) se guarda en este navegador.

export type Rol = 'socio' | 'asistente' | 'cliente'

export interface Usuario {
  id: number
  correo: string
  nombre: string
  rol: Rol
  tercero_id: number | null
  activo: boolean
  ultimo_acceso: string | null
  empresa?: string | null
}

export interface Pieza {
  id: number
  tipo: string
  codigo_fisico: string
  codigo_producto: string | null
  descripcion: string | null
  espesor_mm: string | null
  ancho_mm: string | null
  largo_mm: string | null
  calidad: string | null
  propietario_id: number
  propietario_nombre: string
  tipo_acero: string | null
  norma: string | null
  buque: string | null
  pieza_origen_id: number | null
  fecha_entrada: string | null
  peso_entrada_kg: string
  saldo_kg: string
  estado: string
  unidades_entrada?: number | null
  saldo_unidades?: number | null   // láminas, perfiles y generales: existencia en piezas
  en_proceso?: string | null            // OC planificada que la tiene
  reservada_en?: string | null          // orden(es) de despacho abiertas que la reservan
  unidades_reservadas?: number | null   // láminas, perfiles y generales: piezas reservadas
}

/** Etiqueta de ocupación de una pieza: «En proceso · OC slitter 125», «Reservada · orden de despacho 7»,
 *  «25 reservadas · órdenes de despacho 7, 9». Vacío si está libre. */
export function ocupacion(p: Pick<Pieza, 'en_proceso' | 'reservada_en' | 'unidades_reservadas' | 'saldo_unidades'>): string[] {
  const t: string[] = []
  if (p.en_proceso) t.push(`En proceso · ${p.en_proceso}`)
  if (p.reservada_en) {
    const enPiezas = p.saldo_unidades !== null && p.saldo_unidades !== undefined
    t.push(enPiezas && p.unidades_reservadas
      ? `${p.unidades_reservadas.toLocaleString('es-VE')} reservada${p.unidades_reservadas === 1 ? '' : 's'} · ${p.reservada_en}`
      : `Reservada · ${p.reservada_en}`)
  }
  return t
}

export interface Existencias {
  piezas: Pieza[]
  total_piezas: number
  total_kg: string
  total_unidades?: number | null
}

export interface Movimiento {
  id: number
  tipo: string
  kg: string
  saldo_despues_kg: string
  unidades?: number | null
  saldo_despues_unidades?: number | null
  fecha: string | null
  documento_tipo: string | null
  documento_numero: string | null
  propietario_anterior_id: number | null
  propietario_nuevo_id: number | null
  origen: string
  observacion: string | null
  creado_por: string
  creado_en: string
}

export interface FichaPieza {
  pieza: Pieza
  movimientos: Movimiento[]
  hijas: Pieza[]
  origen: OrigenPieza | null
  conteos?: Conteo[]
}

/** Conteo físico en patio (auditoría). estado: cuadra | pendiente | ajustado | descartado */
export interface Conteo {
  id: number | null
  guardado: boolean
  pieza_id: number
  codigo: string
  descripcion: string | null
  tipo: string
  propietario_id: number
  propietario: string | null
  fecha: string
  unidad: 'pzas' | 'kg'
  sistema: string
  contado: string
  diferencia: string
  estado: 'cuadra' | 'pendiente' | 'ajustado' | 'descartado'
  ajuste_documento_id: number | null
  ajuste_anulado: boolean
  contado_por: string | null
  observacion: string | null
  resolucion: string | null
  origen: string
  creado_por: string
  creado_en: string | null
  resuelto_por: string | null
}

export interface Tercero {
  id: number
  nombre: string
  rif: string | null
  telefono?: string | null
  correo?: string | null
  es_cliente: boolean
  es_siderurgica: boolean
  activo: boolean
  direccion?: string | null
  estado_region?: string | null
  ciudad?: string | null
  forma_pago?: string | null
  vendedor?: string | null
  cliente_desde?: string | null
  dias_gracia_almacen?: number | null
}

export interface Producto {
  id: number
  codigo: string
  nombre: string
  peso_unitario_kg: string | null
  activo: boolean
}

export interface TipoAcero { id: number; codigo: string; nombre: string; activo: boolean }
export interface Norma { id: number; nombre: string; activo: boolean }

export interface ResumenEntrada {
  guardada: boolean
  codigo_producto: string
  descripcion: string
  propietario: string
  avisos: string[]
  pieza_id: number | null
}

export interface ResumenEntradaExistencia {
  guardada: boolean
  tipo: string
  codigo_producto: string
  descripcion: string
  propietario: string
  unidades: number
  peso_unitario_kg: string
  kg: string
  existencia_antes: number
  existencia_despues: number
  avisos: string[]
  pieza_id: number | null
  documento_id?: number | null
  // el mismo material del mismo dueño con otro código (si se registra así, no se suma: queda otra línea)
  similares?: { pieza_id: number; codigo: string; descripcion: string | null; saldo_unidades: number | null }[]
}

const CLAVE = 'prosifer.sesion'

interface SesionGuardada { ficha: string; usuario: Usuario }

export function sesionGuardada(): SesionGuardada | null {
  try {
    const t = localStorage.getItem(CLAVE)
    return t ? (JSON.parse(t) as SesionGuardada) : null
  } catch {
    return null
  }
}

let memoria: SesionGuardada | null = sesionGuardada()

function guardar(s: SesionGuardada | null) {
  memoria = s
  try {
    if (s) localStorage.setItem(CLAVE, JSON.stringify(s))
    else localStorage.removeItem(CLAVE)
  } catch {
    /* navegador sin almacenamiento: la sesión vive solo en memoria */
  }
}

export class ErrorApi extends Error {
  constructor(message: string, public estado: number) {
    super(message)
  }
}

function mensajeDeError(cuerpo: unknown, estado: number): string {
  const detalle = (cuerpo as { detail?: unknown } | null)?.detail
  if (typeof detalle === 'string') return detalle
  if (Array.isArray(detalle)) {
    // Errores de validación de FastAPI: [{loc: [...], msg: '...'}]
    return detalle
      .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg ?? ''}`)
      .join(' · ')
  }
  return `error ${estado}`
}

export async function pedir<T>(ruta: string, opciones: { metodo?: string; cuerpo?: unknown } = {}): Promise<T> {
  const encabezados: Record<string, string> = {}
  if (memoria) encabezados.Authorization = `Bearer ${memoria.ficha}`
  if (opciones.cuerpo !== undefined) encabezados['Content-Type'] = 'application/json'
  const r = await fetch(ruta, {
    method: opciones.metodo ?? 'GET',
    headers: encabezados,
    body: opciones.cuerpo === undefined ? undefined : JSON.stringify(opciones.cuerpo),
  })
  const texto = await r.text()
  let cuerpo: unknown = null
  try {
    cuerpo = texto ? JSON.parse(texto) : null
  } catch {
    cuerpo = null
  }
  if (r.status === 401 && memoria) {
    guardar(null)
    window.dispatchEvent(new Event('prosifer:sesion-vencida'))
  }
  if (!r.ok) throw new ErrorApi(mensajeDeError(cuerpo, r.status), r.status)
  return cuerpo as T
}

/** Abre un PDF de la API en otra pestaña (la ficha de sesión no viaja en un enlace normal). */
export async function abrirPdf(ruta: string, nombre: string): Promise<void> {
  const ventana = window.open('', '_blank')
  const encabezados: Record<string, string> = {}
  if (memoria) encabezados.Authorization = `Bearer ${memoria.ficha}`
  const r = await fetch(ruta, { headers: encabezados })
  if (!r.ok) {
    ventana?.close()
    let detalle = `error ${r.status}`
    try { detalle = mensajeDeError(await r.json(), r.status) } catch { /* sin cuerpo */ }
    throw new ErrorApi(detalle, r.status)
  }
  const url = URL.createObjectURL(await r.blob())
  if (ventana) {
    ventana.location.href = url
  } else {
    const a = document.createElement('a')
    a.href = url
    a.download = nombre
    a.click()
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** Nombre de archivo válido en Windows: "Nota de Entrega 7237 Aceros del Valle, C.A..pdf". */
export function nombreArchivo(...partes: (string | number | null | undefined)[]): string {
  const base = partes.filter((p) => p !== null && p !== undefined && String(p).trim()).join(' ')
  return `${base.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim().slice(0, 150)}.pdf`
}

interface SelectorGuardar {
  showSaveFilePicker?: (o: {
    suggestedName: string; id?: string; startIn?: string
    types?: { description: string; accept: Record<string, string[]> }[]
  }) => Promise<{ createWritable: () => Promise<{ write: (b: Blob) => Promise<void>; close: () => Promise<void> }> }>
}

/** Guarda un PDF de la API con su nombre. En Chrome y Edge abre "Guardar como" y recuerda la última
 *  carpeta usada para ese tipo de documento (por ejemplo la de Dropbox de Ventas). En otros
 *  navegadores lo descarga con el nombre correcto en Descargas. Devuelve false si se canceló. */
export async function guardarPdf(ruta: string, nombre: string, carpeta = 'prosifer-documentos'): Promise<boolean> {
  const w = window as unknown as SelectorGuardar
  let destino: Awaited<ReturnType<NonNullable<SelectorGuardar['showSaveFilePicker']>>> | null = null
  if (w.showSaveFilePicker) {
    try {
      destino = await w.showSaveFilePicker({
        suggestedName: nombre, id: carpeta, startIn: 'documents',
        types: [{ description: 'Documento PDF', accept: { 'application/pdf': ['.pdf'] } }],
      })
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return false
      destino = null
    }
  }
  const encabezados: Record<string, string> = {}
  if (memoria) encabezados.Authorization = `Bearer ${memoria.ficha}`
  const r = await fetch(ruta, { headers: encabezados })
  if (!r.ok) {
    let detalle = `error ${r.status}`
    try { detalle = mensajeDeError(await r.json(), r.status) } catch { /* sin cuerpo */ }
    throw new ErrorApi(detalle, r.status)
  }
  const blob = await r.blob()
  if (destino) {
    const f = await destino.createWritable()
    await f.write(blob)
    await f.close()
    return true
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
  return true
}

/** Nombre de los documentos de las órdenes: "Orden de Maquila Nro 319 - Aceros del Valle, C.A..pdf". */
export const DOCUMENTO_OT: Record<string, string> = {
  slitter: 'Orden de Corte Slitter', lamina: 'Orden de Corte Laminadora', ctf: 'Orden de Corte CTF', maquila: 'Orden de Maquila',
}
export type PdfOt = 'orden' | 'etiquetas' | 'hoja'

export function nombreOt(tipo: string, numero: number | string, cliente: string | null | undefined, que: PdfOt = 'orden'): string {
  const base = DOCUMENTO_OT[tipo] ?? `Orden ${tipo}`
  const prefijo = que === 'etiquetas' ? `Etiquetas ${base}` : base
  const sufijo = que === 'hoja' ? ' (hoja de trabajo)' : ''
  return nombreArchivo(`${prefijo} Nro ${numero}${sufijo}`, cliente ? `- ${cliente}` : null)
}

/** Ver (otra pestaña) o guardar en la carpeta elegida (Chrome y Edge la recuerdan) un PDF de una orden. */
export function pdfOt(ruta: string, tipo: string, numero: number | string, cliente: string | null | undefined, que: PdfOt,
  guardar: boolean): Promise<unknown> {
  const nombre = nombreOt(tipo, numero, cliente, que)
  return guardar ? guardarPdf(ruta, nombre, 'prosifer-ordenes') : abrirPdf(ruta, nombre)
}

/** Recibo de entrada de material: agrupa las entradas del mismo cliente, documento y fecha.
 *  El número se asigna la primera vez que se imprime y se conserva. Sale en media carta: arriba, o
 *  abajo para aprovechar la otra mitad de una hoja ya usada. */
export async function reciboEntrada(documentoId: number, cliente: string | null | undefined, guardar: boolean,
  abajo = false): Promise<unknown> {
  const base = `/api/documentos/${documentoId}/recibo`
  const ruta = abajo ? `${base}?mitad=abajo` : base
  // ver: la pestaña se abre ya (si se espera, el navegador la bloquea); el PDF lleva el número adentro
  if (!guardar) return abrirPdf(ruta, nombreArchivo('Recibo de Entrada', cliente ? `- ${cliente}` : null))
  // guardar: primero el número, para que el archivo lo lleve en el nombre
  const n = await pedir<{ numero: number }>(`${base}/numero`, { metodo: 'POST' })
  return guardarPdf(ruta, nombreArchivo(`Recibo de Entrada Nro ${n.numero}`, cliente ? `- ${cliente}` : null), 'prosifer-recibos')
}

export async function ingresar(correo: string, clave: string): Promise<Usuario> {
  const s = await pedir<SesionGuardada>('/api/auth/ingresar', { metodo: 'POST', cuerpo: { correo, clave } })
  guardar(s)
  return s.usuario
}

export function salir() {
  guardar(null)
}

export function consulta(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

export interface OrigenPieza {
  pieza_id: number | null
  codigo: string | null
  orden_id: number | null
  orden_numero: number | null
  orden_tipo: string | null
}

export interface RolloPlan { codigo: string; kg: string }

export interface CortePlan {
  posicion: number
  ancho_mm: string
  rollos: number
  kg: string
  codigo_producto: string
  descripcion: string
  calidad: string | null
  detalle_rollos: RolloPlan[]
}

export interface ResumenOtSlitter {
  guardada: boolean
  orden_id: number | null
  numero: number
  bobina: string
  propietario: string
  estatus_corte: string
  kg_consumido: string
  kg_producido: string
  kg_scrap: string
  diferencia_pct: string
  saldo_restante_kg: string
  cortes: CortePlan[]
  avisos: string[]
}

export interface GrupoLamina {
  clase: string            // "1" primera; "A", "B", "C" segunda
  calidad: string
  codigo_producto: string
  descripcion: string
  unidades: number
  kg: string
  existencia_despues: number | null
}

export interface ResumenOtLamina {
  guardada: boolean
  orden_id: number | null
  maquina: string
  numero: number
  pieza: string
  propietario: string
  estatus_corte: string
  kg_consumido: string
  kg_producido: string
  kg_scrap: string
  saldo_restante_kg: string
  largo_mm: string
  ancho_mm: string
  total_laminas: number
  kg_por_lamina: string
  kg_teorico_por_lamina: string
  diferencia_teorico_pct: string
  espesor_real?: string | null
  espesor_comercial?: string | null
  grupos: GrupoLamina[]
  atados: { atado: number; unidades: number; kg: string; codigo: string }[]
  avisos: string[]
}

/** El mismo producto con el espesor real del material y con el comercial (redondeado). */
export interface OpcionProducto { codigo: string; nombre: string; existente: Producto | null }
export interface VariantesEspesor {
  espesor_real: string
  espesor_comercial: string | null
  real: OpcionProducto
  comercial: OpcionProducto | null
}

export interface ResumenOtMaquila {
  guardada: boolean
  orden_id: number | null
  numero: number
  propietario: string
  flejes: { pieza_id: number; codigo: string; kg: string; saldo_restante_kg: string }[]
  kg_consumido: string
  kg_producido: string
  kg_scrap: string
  total_perfiles: number
  kg_por_pieza: string
  kg_teorico: string | null
  diferencia_teorico_pct: string | null
  grupos: GrupoLamina[]
  paquetes: { paquete: number; unidades: number; kg: string; codigo: string }[]
  avisos: string[]
}

export interface Orden {
  id: number
  tipo: string
  numero: number
  fecha: string | null
  estado: string
  pieza_id: number | null
  codigo_pieza: string | null
  propietario: string | null
  estatus_corte: string | null
  kg_consumido: string
  kg_producido: string
  kg_scrap: string
  piezas_producidas: number
  calidad: string | null
  paradas: number | null
  observacion: string | null
  origen: string
  creado_por: string
  plan?: Record<string, unknown> | null   // OC planificada: lo pedido
}

export interface CorteDetalle { posicion: number; ancho_mm: string; rollos: number; kg: string; codigo_producto?: string; calidad?: string | null }

export interface DetalleOrden {
  orden: Orden
  detalle: {
    ancho_bobina_mm?: string | null; cortes?: CorteDetalle[]; scrap?: { ancho_mm: string; kg: string }; avisos?: string[]
    // láminas y perfiles
    largo_mm?: string; ancho_mm?: string; total_laminas?: number; total_unidades?: number; kg_por_lamina?: string
    kg_teorico_por_lamina?: string; kg_por_pieza?: string
    grupos?: { clase: string; calidad: string; codigo_producto: string; descripcion: string; unidades: number; kg: string }[]
    atados?: { atado: number; unidades: number; kg: string; codigo: string }[]
    paquetes?: { paquete: number; unidades: number; kg: string; codigo: string }[]
    flejes?: { pieza_id: number; codigo: string; kg: string }[]
  } | null
  pieza_entrada: Pieza | null
  producidas: Pieza[]
}

export interface LineaResumen {
  pieza_id: number
  codigo: string
  descripcion: string | null
  saldo_antes_kg: string
  kg: string
  saldo_despues_kg: string
  saldo_antes_unidades?: number | null
  unidades?: number | null
  saldo_despues_unidades?: number | null
}

export interface ResumenSalida {
  guardada: boolean
  documento_id: number | null
  tipo: string
  numero: string
  fecha: string
  tercero: string
  tercero_nuevo: string | null
  lineas: LineaResumen[]
  total_kg: string
  avisos: string[]
  libres?: { codigo: string; descripcion: string; kg: string }[]   // sin existencia (medidas irregulares)
}

/** Productos sin existencia: salen en la NE solo por su peso, sin stock de ningún cliente. */
export const MATERIAL_IRREGULAR = { codigo: 'MATERIALESIRREG', nombre: 'Material de Medidas Irregulares' }

export interface Documento {
  id: number
  tipo: string
  numero: string | null
  fecha: string | null
  tercero_id?: number | null
  tercero: string | null
  tercero_nuevo: string | null
  piezas: number
  total_kg: string
  anulado: boolean
  origen: string | null
  creado_por: string | null
  observacion: string | null
  encabezado?: EncabezadoNE | null
}

/** Datos de la NE impresa. Lo que quede vacío se toma de la ficha del cliente al imprimir. */
export interface EncabezadoNE {
  domicilio_entrega?: string | null
  telefonos?: string | null
  condicion_pago?: string | null
  vendedor?: string | null
  cotizacion?: string | null
  chofer?: string | null
  placa?: string | null
  nota_salida?: string | null
  ciudad?: string | null
  notas?: string | null
}

export interface LineaDocumento {
  movimiento_id: number | null     // null en el histórico del Excel
  pieza_id: number | null
  codigo: string
  descripcion: string | null
  tipo_movimiento: string
  kg: string
  saldo_despues_kg: string
  unidades?: number | null
  saldo_despues_unidades?: number | null
  cantidad?: string | null
  unidad?: string | null
}

export interface DetalleDocumento {
  documento: Documento
  lineas: LineaDocumento[]
  historico?: boolean
  descargas?: LineaDocumento[]   // NE histórica: lo ya descargado del inventario con ella
  corregible?: boolean
  correcciones?: Documento[]
}

export interface ResumenCorreccionNE {
  guardada: boolean
  numero: string | null
  tercero: string | null
  lineas: {
    antes_codigo: string; antes_descripcion: string | null; antes_kg: string; antes_unidades: number | null
    despues_codigo: string; despues_descripcion: string | null; despues_kg: string; despues_unidades: number | null
  }[]
  avisos: string[]
  documento_id: number | null
}

export const NOMBRE_DOCUMENTO: Record<string, string> = {
  nota_entrega: 'Nota de entrega',
  nota_salida: 'Nota de salida',
  entrada: 'Entrada',
  liberacion: 'Liberación',
  ajuste: 'Ajuste',
}


// --- Orden de despacho del cliente y nota de salida ---------------------------

export interface RetiroDespacho {
  fecha_retiro?: string | null
  retira?: string | null
  cedula?: string | null
  placa?: string | null
  transporte?: string | null
  telefono?: string | null
}

export interface LineaDespacho {
  pieza_id: number
  tipo: string
  codigo: string
  descripcion: string | null
  kg: string
  unidades: number | null
}

export type EstadoDespacho = 'borrador' | 'pendiente' | 'despachada' | 'anulada'

export interface OrdenDespacho {
  guardada: boolean
  id: number | null
  numero: string
  estado: EstadoDespacho
  fecha: string
  tercero_id: number
  tercero: string
  lineas: LineaDespacho[]
  total_kg: string
  total_unidades: number | null
  retiro: RetiroDespacho | null
  observacion: string | null
  origen: string | null
  creado_por: string | null
  creado_en: string | null
  nota_salida_id: number | null
  nota_salida_numero: string | null
  avisos: string[]
}

export const ESTADO_DESPACHO: Record<EstadoDespacho, string> = {
  borrador: 'Sin enviar', pendiente: 'Pendiente', despachada: 'Despachada', anulada: 'Anulada',
}

/** Orden de despacho en PDF: "Orden de Despacho Nro 12 - Cliente.pdf". */
export function pdfDespacho(id: number, numero: string, cliente: string, guardar = false): Promise<unknown> {
  const ruta = `/api/despachos/${id}/pdf`
  const nombre = nombreArchivo(`Orden de Despacho Nro ${numero}`, `- ${cliente}`)
  return guardar ? guardarPdf(ruta, nombre, 'prosifer-despachos') : abrirPdf(ruta, nombre)
}

/** Nota de salida en PDF (id del documento): "Nota de Salida Nro 3 - Cliente.pdf". */
export function pdfNotaSalida(id: number, numero: string | null, cliente: string | null | undefined,
  guardar = false): Promise<unknown> {
  const ruta = `/api/notas-salida/${id}/pdf`
  const nombre = nombreArchivo(`Nota de Salida Nro ${numero ?? ''}`, cliente ? `- ${cliente}` : null)
  return guardar ? guardarPdf(ruta, nombre, 'prosifer-despachos') : abrirPdf(ruta, nombre)
}

// --- Orden de corte que precarga el cliente -----------------------------------

export interface PlanOtOut { orden_id: number; tipo: string; numero: number; avisos: string[] }

export type EstadoSolicitud = 'pendiente' | 'aprobada' | 'rechazada' | 'cancelada'

/** Solicitud de orden de corte del cliente: Prosifer la autoriza (como OC planificada) o la rechaza. */
export interface SolicitudCorte {
  id: number
  numero: string
  estado: EstadoSolicitud
  tipo: 'slitter' | 'lamina' | 'maquila'
  fecha: string
  tercero_id: number
  tercero: string
  piezas: Pieza[]
  pedido: {
    cortes?: { ancho_mm: string; cortes: number }[]
    corte_total?: boolean
    peso_max_kg?: string
    peso_max_rollo_kg?: string
    embalaje?: string
    largo_mm?: string
    cantidad_laminas?: number
    codigo_producto?: string
    descripcion?: string | null
  }
  texto: string
  comentarios: string | null
  creado_por: string | null
  creado_en: string | null
  orden_id: number | null
  orden_numero: number | null
  motivo: string | null
  revisado_por: string | null
}

export const ESTADO_SOLICITUD: Record<EstadoSolicitud, string> = {
  pendiente: 'Por revisar', aprobada: 'Autorizada', rechazada: 'Rechazada', cancelada: 'Cancelada',
}


// --- Aviso de entrada: el cliente anuncia material que va a llegar -------------

export interface RenglonAviso {
  tipo: 'bobina' | 'fleje' | 'lamina' | 'perfil' | 'general'
  codigo?: string
  descripcion?: string
  tipo_acero?: string
  espesor_mm?: string
  ancho_mm?: string
  largo_mm?: string
  cantidad?: number
  peso_kg?: string
  entrada?: { pieza_id: number; codigo: string; texto?: string | null; por?: string }   // la entrada que se registró
}

export type EstadoAviso = 'pendiente' | 'recibido' | 'rechazado' | 'cancelado'

export interface AvisoEntrada {
  id: number
  numero: string
  estado: EstadoAviso
  fecha: string
  fecha_estimada: string | null
  tercero_id: number
  tercero: string
  documento_tipo: string | null
  documento_numero: string | null
  proveedor: string | null
  transporte: { chofer?: string; cedula?: string; placa?: string; transporte?: string; telefono?: string } | null
  renglones: RenglonAviso[]
  total_kg: string
  total_piezas: number
  comentarios: string | null
  creado_por: string | null
  creado_en: string | null
  nota: string | null
  revisado_por: string | null
}

export const ESTADO_AVISO: Record<EstadoAviso, string> = {
  pendiente: 'Por llegar', recibido: 'Recibido', rechazado: 'Rechazado', cancelado: 'Cancelado',
}
export const TIPO_RENGLON: Record<RenglonAviso['tipo'], string> = {
  bobina: 'Bobina', fleje: 'Fleje', lamina: 'Lámina', perfil: 'Perfil', general: 'Producto general',
}

// --- Cotizaciones (USD) ---------------------------------------------------------

export interface RenglonCotizacion {
  codigo?: string | null
  descripcion: string
  cantidad: string | number
  unidad: string
  precio_unitario: string | number | null
  total?: string
}

export interface Cotizacion {
  id: number
  guardada?: boolean
  numero: string
  fecha: string | null
  tercero_id: number | null
  tercero: string | null
  renglones: RenglonCotizacion[]
  subtotal: string
  iva_pct: string | null
  iva: string
  total: string
  abonos: { fecha: string | null; destino: string; monto: string; referencia?: string; por?: string; comprobante_id?: number }[]
  abonado: string
  saldo: string
  vendedor: string | null
  condicion_pago: string | null
  nota_entrega: string | null
  notas: string | null
  orden_trabajo_id: number | null
  orden: string | null
  anulada: boolean
  motivo_anulacion: string | null
  historica: boolean
  origen: string | null
  creado_por: string | null
  creado_en: string | null
}

export interface BorradorCotizacion {
  tercero_id: number | null
  tercero: string | null
  orden_trabajo_id?: number | null   // al cotizar una orden
  orden?: string | null
  renglones: RenglonCotizacion[]
  notas?: string | null     // bobina (slitter, laminadora) o perfil y primer fleje (maquila)
  avisos: string[]
}

export function pdfCotizacion(id: number, numero: string, cliente: string | null | undefined, guardar = false): Promise<unknown> {
  const ruta = `/api/cotizaciones/${id}/pdf`
  const nombre = nombreArchivo(`Cotizacion D-${numero}`, cliente ? `${cliente}` : null)
  return guardar ? guardarPdf(ruta, nombre, 'prosifer-cotizaciones') : abrirPdf(ruta, nombre)
}

/** Reporte mensual de salidas de un cliente ("Servicios de Descarga-Carga"). */
export interface FilaReporteSalidas {
  nota_salida: string | null
  fecha: string | null
  nota_entrega: string | null
  documento_id: number
  cantidad: string | null
  descripcion: string | null
  kg: string
  categoria: string
}
export interface ReporteSalidas {
  tercero_id: number
  tercero: string
  desde: string
  hasta: string
  filas: FilaReporteSalidas[]
  notas_entrega: number
  total_kg: string
  excluidas: { categoria: string; nombre: string; renglones: number; kg: string }[]
}

