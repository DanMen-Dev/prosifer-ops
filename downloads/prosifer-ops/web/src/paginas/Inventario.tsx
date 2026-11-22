import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { abrirPdf, consulta, nombreArchivo, ocupacion, pedir, type Existencias, type Tercero, type TipoAcero, type Usuario } from '../api'
import { fecha, kg, mm } from '../formato'
import Conteos from './Conteos'
import FichaPieza from './FichaPieza'

interface Filtros {
  tipo: string
  tipo_acero: string
  espesor_mm: string
  ancho_mm: string
  codigo: string
  propietario_id: string
  incluir_agotadas: boolean
}

const VACIOS: Filtros = {
  tipo: 'bobina', tipo_acero: '', espesor_mm: '', ancho_mm: '', codigo: '', propietario_id: '',
  incluir_agotadas: false,
}

const CLAVE_FILTROS = 'prosifer.filtros-inventario'

function filtrosGuardados(): Filtros {
  try {
    const t = localStorage.getItem(CLAVE_FILTROS)
    return t ? { ...VACIOS, ...(JSON.parse(t) as Partial<Filtros>) } : VACIOS
  } catch {
    return VACIOS
  }
}

function guardarFiltros(f: Filtros) {
  try { localStorage.setItem(CLAVE_FILTROS, JSON.stringify(f)) } catch { /* sin almacenamiento */ }
}

/** Inventario: las existencias y, para el personal, el historial de conteos físicos en patio. */
export default function Inventario({ usuario }: { usuario: Usuario }) {
  const [pestana, setPestana] = useState<'existencias' | 'conteos'>('existencias')
  if (usuario.rol === 'cliente') return <ListaExistencias usuario={usuario} />
  return (
    <>
      <nav className="subpestanas" aria-label="Inventario">
        <button className={pestana === 'existencias' ? 'activa' : ''} onClick={() => setPestana('existencias')}>Existencias</button>
        <button className={pestana === 'conteos' ? 'activa' : ''} onClick={() => setPestana('conteos')}>Conteos físicos</button>
      </nav>
      {pestana === 'existencias' ? <ListaExistencias usuario={usuario} /> : <Conteos usuario={usuario} />}
    </>
  )
}

function ListaExistencias({ usuario }: { usuario: Usuario }) {
  const esPersonal = usuario.rol !== 'cliente'
  const [filtros, setFiltros] = useState<Filtros>(filtrosGuardados)
  const [datos, setDatos] = useState<Existencias | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tipos, setTipos] = useState<TipoAcero[]>([])
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [seleccion, setSeleccion] = useState<number | null>(null)

  const buscar = useCallback(async (f: Filtros) => {
    guardarFiltros(f)
    setCargando(true)
    setError(null)
    try {
      setDatos(await pedir<Existencias>(`/api/existencias${consulta({ ...f, limite: 2000 })}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void buscar(filtrosGuardados())
    pedir<TipoAcero[]>('/api/catalogos/tipos-acero').then(setTipos).catch(() => setTipos([]))
    if (esPersonal) pedir<Tercero[]>('/api/terceros?rol=cliente').then(setTerceros).catch(() => setTerceros([]))
  }, [buscar, esPersonal])

  function cambiar<K extends keyof Filtros>(campo: K, valor: Filtros[K], buscarYa = false) {
    const nuevos = { ...filtros, [campo]: valor }
    setFiltros(nuevos)
    if (buscarYa) void buscar(nuevos)
  }

  const CATEGORIA: Record<string, string> = {
    bobina: 'Bobinas', fleje: 'Flejes', lamina: 'Láminas', perfil: 'Perfiles', general: 'Productos generales',
  }
  const dueno = esPersonal ? terceros.find((t) => String(t.id) === filtros.propietario_id) : null
  const puedeReporte = !esPersonal || !!dueno

  function reporte(categoria: string) {
    const ruta = `/api/reportes/inventario${consulta({ categoria, propietario_id: esPersonal ? filtros.propietario_id : null })}`
    const titulo = categoria === 'todas' ? 'Inventario Total' : `Inventario de ${CATEGORIA[categoria]}`
    abrirPdf(ruta, nombreArchivo(titulo, dueno ? `- ${dueno.nombre}` : null)).catch((e: Error) => setError(e.message))
  }

  function enviar(e: FormEvent) {
    e.preventDefault()
    void buscar(filtros)
  }

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>{esPersonal ? 'Inventario' : 'Mi inventario'}</h1>
        {datos && (
          <div className="totales" aria-live="polite">
            {datos.total_unidades !== null && datos.total_unidades !== undefined ? (
              <>
                <div><strong>{datos.total_unidades.toLocaleString('es-VE')}</strong><span>piezas</span></div>
                <div><strong>{datos.total_piezas.toLocaleString('es-VE')}</strong><span>códigos por dueño</span></div>
              </>
            ) : (
              <div><strong>{datos.total_piezas.toLocaleString('es-VE')}</strong><span>piezas</span></div>
            )}
            <div><strong>{kg(datos.total_kg)}</strong><span>{filtros.incluir_agotadas ? 'saldo' : 'disponible'}</span></div>
          </div>
        )}
      </div>

      <form className="filtros tarjeta" onSubmit={enviar}>
        <label>
          Tipo de pieza
          <select value={filtros.tipo} onChange={(e) => cambiar('tipo', e.target.value, true)}>
            <option value="">Todas</option>
            <option value="bobina">Bobinas</option>
            <option value="fleje">Flejes</option>
            <option value="lamina">Láminas</option>
            <option value="perfil">Perfiles</option>
            <option value="general">Productos generales</option>
          </select>
        </label>
        <label>
          Acero
          <select value={filtros.tipo_acero} onChange={(e) => cambiar('tipo_acero', e.target.value, true)}>
            <option value="">Todos</option>
            {tipos.map((t) => <option key={t.id} value={t.codigo}>{t.nombre} ({t.codigo})</option>)}
          </select>
        </label>
        <label className="corto">
          Espesor (mm)
          <input inputMode="decimal" value={filtros.espesor_mm} placeholder="0.90"
            onChange={(e) => cambiar('espesor_mm', e.target.value.replace(',', '.'))} />
        </label>
        <label className="corto">
          Ancho (mm)
          <input inputMode="numeric" value={filtros.ancho_mm} placeholder="1220"
            onChange={(e) => cambiar('ancho_mm', e.target.value)} />
        </label>
        <label>
          Código
          <input value={filtros.codigo} placeholder="Bobina o producto"
            onChange={(e) => cambiar('codigo', e.target.value)} />
        </label>
        {esPersonal && (
          <label>
            Dueño
            <select value={filtros.propietario_id} onChange={(e) => cambiar('propietario_id', e.target.value, true)}>
              <option value="">Todos</option>
              {terceros.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
            </select>
          </label>
        )}
        <label className="casilla">
          <input type="checkbox" checked={filtros.incluir_agotadas}
            onChange={(e) => cambiar('incluir_agotadas', e.target.checked, true)} />
          Incluir agotadas
        </label>
        <div className="acciones-filtro">
          <button className="primario" disabled={cargando}>{cargando ? 'Buscando…' : 'Buscar'}</button>
          <button type="button" className="secundario" onClick={() => { setFiltros(VACIOS); void buscar(VACIOS) }}>
            Limpiar
          </button>
        </div>
      </form>

      <div className="barra-reporte">
        <span className="tenue">Reporte para auditar en patio:</span>
        <button type="button" className="secundario" disabled={!puedeReporte || !filtros.tipo}
          title={!puedeReporte ? 'Elige primero el dueño' : !filtros.tipo ? 'Elige una categoría en "Tipo de pieza"' : ''}
          onClick={() => reporte(filtros.tipo)}>
          {filtros.tipo ? `${CATEGORIA[filtros.tipo]} (PDF)` : 'Categoría (PDF)'}
        </button>
        <button type="button" className="secundario" disabled={!puedeReporte}
          title={!puedeReporte ? 'Elige primero el dueño' : ''} onClick={() => reporte('todas')}>
          Total del cliente (PDF)
        </button>
        {!puedeReporte && <span className="tenue pequeno">Elige el dueño en los filtros para sacar su reporte.</span>}
      </div>

      {error && <p className="error">{error}</p>}

      {datos && datos.piezas.length === 0 && !cargando && (
        <p className="vacio">No hay piezas con esos filtros.</p>
      )}

      {datos && datos.piezas.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead>
              <tr>
                <th>Código</th>
                <th>Producto</th>
                <th className="n">Espesor</th>
                <th className="n">Ancho</th>
                {esPersonal && <th>Dueño</th>}
                <th>Entrada</th>
                <th className="n">Piezas</th>
                <th className="n">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {datos.piezas.map((p) => (
                <tr key={p.id} onClick={() => setSeleccion(p.id)} className={p.estado === 'agotado' ? 'agotada' : ''}
                  tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') setSeleccion(p.id) }}>
                  <td className="codigo">{p.codigo_fisico}
                    {ocupacion(p).map((t) => <div key={t} className="chip-ocupada">{t}</div>)}</td>
                  <td>
                    <div>{p.codigo_producto ?? '—'}</div>
                    <div className="tenue pequeno">{p.descripcion}</div>
                  </td>
                  <td className="n">{mm(p.espesor_mm, true)}</td>
                  <td className="n">{mm(p.ancho_mm)}</td>
                  {esPersonal && <td>{p.propietario_nombre}</td>}
                  <td>{fecha(p.fecha_entrada)}</td>
                  <td className="n fuerte">{p.saldo_unidades === null || p.saldo_unidades === undefined ? '1' : p.saldo_unidades.toLocaleString('es-VE')}</td>
                  <td className="n">{kg(p.saldo_kg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {datos.total_piezas > datos.piezas.length && (
            <p className="tenue pequeno pie-tabla">
              Mostrando {datos.piezas.length} de {datos.total_piezas}. Usa los filtros para acotar.
            </p>
          )}
        </div>
      )}

      {seleccion !== null && (
        <FichaPieza id={seleccion} usuario={usuario} onCerrar={() => setSeleccion(null)}
          onCambio={() => void buscar(filtros)} />
      )}
    </section>
  )
}
