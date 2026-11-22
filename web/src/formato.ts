const numero = new Intl.NumberFormat('es-VE', { maximumFractionDigits: 0 })
const decimal = new Intl.NumberFormat('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function kg(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  return `${numero.format(Number(v))} kg`
}

export function mm(v: string | number | null | undefined, decimales = false): string {
  if (v === null || v === undefined || v === '') return '—'
  return decimales ? decimal.format(Number(v)) : numero.format(Number(v))
}

export function fecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [a, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${a}`
}

export function hoyIso(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export const NOMBRE_MOVIMIENTO: Record<string, string> = {
  entrada: 'Entrada',
  consumo: 'Consumo por OT',
  produccion: 'Producción',
  salida: 'Nota de entrega',
  liberacion: 'Liberación',
  ajuste: 'Ajuste',
}

export const NOMBRE_ROL: Record<string, string> = {
  socio: 'Socio',
  asistente: 'Asistente',
  cliente: 'Cliente',
}

/** Montos de las cotizaciones: "2.309,76 USD" (sin la moneda si se pide así). */
export function usd(v: string | number | null | undefined, conMoneda = true): string {
  const n = Number(v ?? 0)
  const t = n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return conMoneda ? `${t} USD` : t
}
