import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { abrirPdf, consulta, nombreArchivo, pedir, type Conteo, type Tercero, type Usuario } from '../api'
import { fecha, kg } from '../formato'
import FichaPieza from './FichaPieza'

export const NOMBRE_ESTADO_CONTEO: Record<Conteo['estado'], string> = {
  cuadra: 'Cuadra', pendiente: 'Diferencia pendiente', ajustado: 'Ajustado', descartado: 'Descartado',
}

/** "47 pzas" o "1.250 kg" */
export function cantidadConteo(v: string | number, unidad: Conteo['unidad']): string {
  return unidad === 'pzas' ? `${Number(v).toLocaleString('es-VE')} pzas` : kg(v)
}

export function DiferenciaConteo({ c }: { c: Conteo }) {
  const d = Number(c.diferencia)
  if (d === 0) return <span className="tenue">—</span>
  return <span className={d < 0 ? 'negativo' : 'diferencia-mas'}>{d > 0 ? '+' : ''}{cantidadConteo(d, c.unidad)}</span>
}

export function EstadoConteo({ c }: { c: Conteo }) {
  return (
    <span className={`estado-despacho ${c.estado}`} title={c.resolucion ?? undefined}>
      {NOMBRE_ESTADO_CONTEO[c.estado]}{c.estado === 'ajustado' && c.ajuste_anulado ? ' (ajuste anulado)' : ''}
    </span>
  )
}

interface Filtros { tercero_id: string; desde: string; hasta: string; estado: string; texto: string }
const VACIOS: Filtros = { tercero_id: '', desde: '', hasta: '', estado: '', texto: '' }

/** Inventario › Conteos físicos: el historial de auditorías en patio, cuadren o no. Es el punto de partida
 *  para explicar un descuadre: lo que pasó después del último conteo. */
export default function Conteos({ usuario }: { usuario: Usuario }) {
  const [filtros, setFiltros] = useState<Filtros>(VACIOS)
  const [lista, setLista] = useState<Conteo[] | null>(null)
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [seleccion, setSeleccion] = useState<number | null>(null)

  const buscar = useCallback(async (f: Filtros) => {
    setCargando(true)
    setError(null)
    try {
      setLista(await pedir<Conteo[]>(`/api/conteos${consulta({ ...f, limite: 2000 })}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void buscar(VACIOS)
    pedir<Tercero[]>('/api/terceros?rol=cliente').then(setTerceros).catch(() => setTerceros([]))
  }, [buscar])

  function cambiar<K extends keyof Filtros>(campo: K, valor: Filtros[K], buscarYa = false) {
    const nuevos = { ...filtros, [campo]: valor }
    setFiltros(nuevos)
    if (buscarYa) void buscar(nuevos)
  }

  function enviar(e: FormEvent) {
    e.preventDefault()
    void buscar(filtros)
  }

  function resumenPdf() {
    const dueno = terceros.find((t) => String(t.id) === filtros.tercero_id)
    const rango = [filtros.desde && fecha(filtros.desde).replace(/\//g, '-'), filtros.hasta && `al ${fecha(filtros.hasta).replace(/\//g, '-')}`]
    abrirPdf(`/api/conteos/pdf${consulta({ ...filtros })}`, nombreArchivo('Conteos en patio', dueno?.nombre, ...rango))
      .catch((e: Error) => setError(e.message))
  }

  const cuenta = (estado: Conteo['estado']) => (lista ?? []).filter((c) => c.estado === estado).length

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>Conteos físicos</h1>
        {lista && (
          <div className="totales" aria-live="polite">
            <div><strong>{lista.length.toLocaleString('es-VE')}</strong><span>conteos</span></div>
            <div><strong>{cuenta('cuadra').toLocaleString('es-VE')}</strong><span>cuadran</span></div>
            <div><strong>{cuenta('pendiente').toLocaleString('es-VE')}</strong><span>pendientes</span></div>
            <div><strong>{cuenta('ajustado').toLocaleString('es-VE')}</strong><span>ajustados</span></div>
          </div>
        )}
      </div>
      <p className="tenue">
        Cada auditoría en patio queda aquí, cuadre o no. Si mañana algo no cuadra, se revisa desde el último conteo
        (en la ficha de la existencia, sus movimientos después de esa fecha). Para registrar un conteo, abre la existencia
        en Inventario › Existencias y usa <strong>Registrar conteo</strong>.
      </p>

      <form className="filtros tarjeta" onSubmit={enviar}>
        <label>
          Dueño
          <select value={filtros.tercero_id} onChange={(e) => cambiar('tercero_id', e.target.value, true)}>
            <option value="">Todos</option>
            {terceros.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        </label>
        <label>
          Estado
          <select value={filtros.estado} onChange={(e) => cambiar('estado', e.target.value, true)}>
            <option value="">Todos</option>
            <option value="pendiente">Diferencia pendiente</option>
            <option value="cuadra">Cuadra</option>
            <option value="ajustado">Ajustado</option>
            <option value="descartado">Descartado</option>
          </select>
        </label>
        <label className="corto">Desde<input type="date" value={filtros.desde} onChange={(e) => cambiar('desde', e.target.value, true)} /></label>
        <label className="corto">Hasta<input type="date" value={filtros.hasta} onChange={(e) => cambiar('hasta', e.target.value, true)} /></label>
        <label>
          Producto
          <input value={filtros.texto} placeholder="Código o descripción" onChange={(e) => cambiar('texto', e.target.value)} />
        </label>
        <div className="acciones-filtro">
          <button className="primario" disabled={cargando}>{cargando ? 'Buscando…' : 'Buscar'}</button>
          <button type="button" className="secundario" onClick={() => { setFiltros(VACIOS); void buscar(VACIOS) }}>Limpiar</button>
        </div>
      </form>

      <div className="barra-reporte">
        <span className="tenue">Resumen para el grupo o para archivar (con los filtros de arriba):</span>
        <button type="button" className="secundario" disabled={!lista || lista.length === 0} onClick={resumenPdf}>
          Resumen de conteos (PDF)
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {lista && lista.length === 0 && !cargando && <p className="vacio">No hay conteos con esos filtros.</p>}

      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead>
              <tr>
                <th>Fecha</th><th>Producto</th><th>Dueño</th>
                <th className="n">Sistema</th><th className="n">Contado</th><th className="n">Diferencia</th>
                <th>Estado</th><th>Contó</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((c) => (
                <tr key={c.id ?? 0} onClick={() => setSeleccion(c.pieza_id)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') setSeleccion(c.pieza_id) }}
                  title={[c.observacion, c.resolucion].filter(Boolean).join(' · ') || undefined}>
                  <td>{fecha(c.fecha)}</td>
                  <td>
                    <div className="codigo">{c.codigo}</div>
                    <div className="tenue pequeno">{c.descripcion}</div>
                  </td>
                  <td>{c.propietario}</td>
                  <td className="n">{cantidadConteo(c.sistema, c.unidad)}</td>
                  <td className="n fuerte">{cantidadConteo(c.contado, c.unidad)}</td>
                  <td className="n"><DiferenciaConteo c={c} /></td>
                  <td><EstadoConteo c={c} /></td>
                  <td>
                    <div>{c.contado_por ?? '—'}</div>
                    <div className="tenue pequeno">{c.origen === 'agente' ? 'vía Prosi' : c.creado_por}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {seleccion !== null && (
        <FichaPieza id={seleccion} usuario={usuario} onCerrar={() => setSeleccion(null)} onCambio={() => void buscar(filtros)} />
      )}
    </section>
  )
}
