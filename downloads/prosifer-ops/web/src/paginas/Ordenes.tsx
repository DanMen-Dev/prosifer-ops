import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { consulta, pdfOt, pedir, type DetalleOrden, type Orden, type Usuario } from '../api'
import { fecha, kg, mm } from '../formato'
import { CotizarOrden } from './Cotizaciones'
import Modal from './Modal'

interface Props { usuario: Usuario; abrir: number | null; onAbierta: () => void }

export const NOMBRE_OT: Record<string, string> = { slitter: 'Slitter', lamina: 'Laminadora', ctf: 'CTF', maquila: 'Maquila de perfiles' }
const NOMBRE_CLASE: Record<string, string> = { 1: 'Primera', A: 'Segunda A', B: 'Segunda B', C: 'Segunda C' }

export default function Ordenes({ usuario, abrir, onAbierta }: Props) {
  const [filtros, setFiltros] = useState({ tipo: 'slitter', numero: '', codigo: '', desde: '', hasta: '' })
  const [lista, setLista] = useState<Orden[]>([])
  const [error, setError] = useState<string | null>(null)
  const [seleccion, setSeleccion] = useState<number | null>(null)

  const cargar = useCallback(async (f: typeof filtros) => {
    setError(null)
    try {
      setLista(await pedir<Orden[]>(`/api/ot${consulta({ ...f, limite: 300 })}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar')
    }
  }, [])

  useEffect(() => { void cargar({ tipo: 'slitter', numero: '', codigo: '', desde: '', hasta: '' }) }, [cargar])
  useEffect(() => {
    if (abrir) { setSeleccion(abrir); onAbierta() }
  }, [abrir, onAbierta])

  function enviar(e: FormEvent) { e.preventDefault(); void cargar(filtros) }

  return (
    <section>
      <div className="encabezado-seccion"><h1>Órdenes de trabajo · {NOMBRE_OT[filtros.tipo] ?? 'Todas'}</h1></div>
      <form className="filtros tarjeta" onSubmit={enviar}>
        <label>
          Máquina
          <select value={filtros.tipo} onChange={(e) => { const f = { ...filtros, tipo: e.target.value }; setFiltros(f); void cargar(f) }}>
            {Object.entries(NOMBRE_OT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            <option value="">Todas</option>
          </select>
        </label>
        <label className="corto">Número<input inputMode="numeric" value={filtros.numero} onChange={(e) => setFiltros({ ...filtros, numero: e.target.value })} /></label>
        <label>Bobina<input value={filtros.codigo} onChange={(e) => setFiltros({ ...filtros, codigo: e.target.value })} placeholder="Código" /></label>
        <label>Desde<input type="date" value={filtros.desde} onChange={(e) => setFiltros({ ...filtros, desde: e.target.value })} /></label>
        <label>Hasta<input type="date" value={filtros.hasta} onChange={(e) => setFiltros({ ...filtros, hasta: e.target.value })} /></label>
        <div className="acciones-filtro"><button className="primario">Buscar</button></div>
      </form>
      {error && <p className="error">{error}</p>}
      {lista.length === 0 && !error && <p className="vacio">No hay órdenes con esos filtros.</p>}
      {lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead>
              <tr><th>OC</th><th>Fecha</th><th>Bobina</th>{usuario.rol !== 'cliente' && <th>Dueño</th>}<th>Corte</th>
                <th className="n">Consumido</th><th className="n">Producido</th><th className="n">Scrap</th>
                <th className="n">{filtros.tipo === 'slitter' ? 'Rollos' : 'Piezas'}</th></tr>
            </thead>
            <tbody>
              {lista.map((o) => (
                <tr key={o.id} onClick={() => setSeleccion(o.id)} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') setSeleccion(o.id) }}>
                  <td className="fuerte">{filtros.tipo ? o.numero : `${NOMBRE_OT[o.tipo] ?? o.tipo} ${o.numero}`}
                    {o.estado === 'planificada' && <div><span className="pedido-cliente">{usuario.rol === 'cliente' ? 'En proceso' : 'Planificada'}</span></div>}
                    {o.estado === 'anulada' && <div><span className="etiqueta-anulada">ANULADA</span></div>}</td>
                  <td>{fecha(o.fecha)}</td>
                  <td className="codigo">{o.codigo_pieza ?? '—'}</td>
                  {usuario.rol !== 'cliente' && <td>{o.propietario ?? '—'}</td>}
                  <td>{o.estatus_corte ?? '—'}</td>
                  <td className="n">{kg(o.kg_consumido)}</td>
                  <td className="n">{kg(o.kg_producido)}</td>
                  <td className="n">{kg(o.kg_scrap)}</td>
                  <td className="n">{o.piezas_producidas}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {seleccion !== null && (
        <DetalleOrdenModal id={seleccion} usuario={usuario} onCerrar={() => setSeleccion(null)} onCambio={() => void cargar(filtros)} />
      )}
    </section>
  )
}

function DetalleOrdenModal({ id, usuario, onCerrar, onCambio }: { id: number; usuario: Usuario; onCerrar: () => void; onCambio: () => void }) {
  const [d, setD] = useState<DetalleOrden | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [marcadas, setMarcadas] = useState<number[]>([])
  const [cotizando, setCotizando] = useState(false)

  useEffect(() => {
    pedir<DetalleOrden>(`/api/ot/${id}`).then(setD).catch((e: Error) => setError(e.message))
  }, [id])

  const porPiezas = d?.orden.tipo !== undefined && d.orden.tipo !== 'slitter'

  function pdf(doc: 'orden' | 'etiquetas', elegidos?: number[], guardar = false) {
    const q = elegidos && elegidos.length ? `?${porPiezas ? 'atados' : 'piezas'}=${elegidos.join(',')}` : ''
    pdfOt(`/api/ot/${id}/pdf/${doc}${q}`, d?.orden.tipo ?? 'slitter', d?.orden.numero ?? id, d?.orden.propietario, doc, guardar)
      .catch((e: Error) => setError(e.message))
  }

  async function anular() {
    setError(null)
    try {
      await pedir<Orden>(`/api/ot/${id}`, { metodo: 'DELETE', cuerpo: { motivo } })
      onCambio()
      onCerrar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo anular')
    }
  }

  const o = d?.orden
  return (
    <Modal titulo={o ? `OC ${o.numero} · ${NOMBRE_OT[o.tipo] ?? o.tipo}` : 'Orden'} onCerrar={onCerrar} ancho>
      {error && <p className="error">{error}</p>}
      {!d && !error && <p className="tenue">Cargando…</p>}
      {d && o && (
        <div className="imprimible">
          <div className="solo-impresion encabezado-impresion">
            <strong>Prosifer · Orden de trabajo {NOMBRE_OT[o.tipo] ?? o.tipo} N.º {o.numero}</strong>
          </div>
          {o.estado === 'anulada' && <p className="error">Orden anulada</p>}
          {o.estado === 'planificada' && (
            <p className="alerta">{usuario.rol === 'cliente'
              ? 'Orden autorizada por Prosifer: el material está apartado y se cortará en planta.'
              : 'Orden planificada: todavía sin resultados.'}</p>
          )}
          <dl className="datos">
            <dt>Fecha</dt><dd>{fecha(o.fecha)}</dd>
            <dt>Bobina</dt><dd className="codigo">{o.codigo_pieza ?? '—'}</dd>
            {d.pieza_entrada && <><dt>Material</dt><dd>{d.pieza_entrada.descripcion} · {mm(d.pieza_entrada.espesor_mm, true)} × {mm(d.pieza_entrada.ancho_mm)} mm</dd></>}
            <dt>Dueño</dt><dd>{o.propietario ?? '—'}</dd>
            <dt>Corte</dt><dd>{o.estatus_corte ?? '—'} · calidad {o.calidad ?? '—'} · paradas {o.paradas ?? 0}</dd>
            <dt>Registró</dt><dd>{o.creado_por} ({o.origen})</dd>
            {o.observacion && <><dt>Observación</dt><dd>{o.observacion}</dd></>}
          </dl>
          <div className="ficha-resumen">
            <div><span>Consumido</span><strong>{kg(o.kg_consumido)}</strong></div>
            <div><span>Producido</span><strong>{kg(o.kg_producido)}</strong></div>
            <div><span>Scrap</span><strong>{kg(o.kg_scrap)}</strong></div>
          </div>
          {d.detalle?.cortes && d.detalle.cortes.length > 0 && (
            <>
              <h3>Cortes</h3>
              <table className="tabla compacta">
                <thead><tr><th>#</th><th className="n">Ancho</th><th className="n">Rollos</th><th className="n">kg</th></tr></thead>
                <tbody>
                  {d.detalle.cortes.map((c) => (
                    <tr key={c.posicion}><td>{c.posicion}</td><td className="n">{mm(c.ancho_mm)} mm</td><td className="n">{c.rollos}</td><td className="n">{kg(c.kg)}</td></tr>
                  ))}
                  {d.detalle.scrap && Number(d.detalle.scrap.ancho_mm) > 0 && (
                    <tr><td>7</td><td className="n">{mm(d.detalle.scrap.ancho_mm)} mm</td><td className="n">scrap</td><td className="n">{kg(d.detalle.scrap.kg)}</td></tr>
                  )}
                </tbody>
              </table>
            </>
          )}
          {d.detalle?.grupos && d.detalle.grupos.length > 0 && (
            <>
              <h3>Producción{d.detalle.largo_mm ? ` · ${mm(d.detalle.ancho_mm)} × ${mm(d.detalle.largo_mm)} mm` : ''}</h3>
              <table className="tabla compacta">
                <thead><tr><th>Calidad</th><th>Producto</th><th className="n">Piezas</th><th className="n">kg</th></tr></thead>
                <tbody>
                  {d.detalle.grupos.map((g) => (
                    <tr key={g.codigo_producto}>
                      <td>{NOMBRE_CLASE[g.clase] ?? g.clase}</td>
                      <td><div className="codigo">{g.codigo_producto}</div><div className="tenue pequeno">{g.descripcion}</div></td>
                      <td className="n">{g.unidades}</td><td className="n">{kg(g.kg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {porPiezas && (d.detalle?.atados ?? d.detalle?.paquetes ?? []).length > 0 && (
            <>
              <h3>{d.detalle?.atados ? 'Atados' : 'Paquetes'} (etiquetas)</h3>
              <table className="tabla compacta">
                <thead><tr><th className="no-impresion"></th><th>#</th><th>Código</th><th className="n">Piezas</th><th className="n">kg</th></tr></thead>
                <tbody>
                  {(d.detalle?.atados?.map((a) => ({ n: a.atado, unidades: a.unidades, kg: a.kg, codigo: a.codigo }))
                    ?? d.detalle?.paquetes?.map((a) => ({ n: a.paquete, unidades: a.unidades, kg: a.kg, codigo: a.codigo })) ?? []).map((a) => (
                    <tr key={a.n}>
                      <td className="no-impresion">
                        <input type="checkbox" aria-label={`Reimprimir etiqueta ${a.n}`} checked={marcadas.includes(a.n)}
                          onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, a.n] : marcadas.filter((x) => x !== a.n))} />
                      </td>
                      <td>{a.n}</td><td className="codigo">{a.codigo}</td><td className="n">{a.unidades}</td><td className="n">{kg(a.kg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <h3>{porPiezas ? 'Existencias a las que sumó' : 'Rollos producidos'}</h3>
          {d.producidas.length === 0 && <p className="tenue pequeno">Sin piezas registradas.</p>}
          {porPiezas && d.producidas.length > 0 && (
            <table className="tabla compacta">
              <thead><tr><th>Código</th><th>Dueño</th><th className="n">Existencia hoy</th></tr></thead>
              <tbody>
                {d.producidas.map((p) => (
                  <tr key={p.id}><td className="codigo">{p.codigo_fisico}</td><td>{p.propietario_nombre}</td>
                    <td className="n">{p.saldo_unidades ?? '—'} pzas · {kg(p.saldo_kg)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {!porPiezas && d.producidas.length > 0 && (
            <table className="tabla compacta">
              <thead><tr><th className="no-impresion"></th><th>Código</th><th>Calidad</th><th className="n">Peso</th><th className="n">Saldo</th></tr></thead>
              <tbody>
                {d.producidas.map((p) => (
                  <tr key={p.id} className={p.estado === 'agotado' ? 'agotada' : ''}>
                    <td className="no-impresion">
                      <input type="checkbox" aria-label={`Reimprimir ${p.codigo_fisico}`} checked={marcadas.includes(p.id)}
                        onChange={(e) => setMarcadas(e.target.checked ? [...marcadas, p.id] : marcadas.filter((x) => x !== p.id))} />
                    </td>
                    <td className="codigo">{p.codigo_fisico}</td><td>{p.calidad ?? '—'}</td>
                    <td className="n">{kg(p.peso_entrada_kg)}</td><td className="n">{kg(p.saldo_kg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="acciones no-impresion">
            {['slitter', 'lamina', 'ctf', 'maquila'].includes(o.tipo) && !(usuario.rol === 'cliente' && o.estado !== 'ejecutada' && o.estado !== 'cerrada') && (
              <>
                {usuario.rol !== 'cliente' && o.estado !== 'anulada' && (
                  <button className="primario" onClick={() => setCotizando(true)}>Cotizar esta orden</button>
                )}
                <button className="primario" onClick={() => pdf('orden')}>Hoja de la orden (PDF)</button>
                <button className="secundario" onClick={() => pdf('orden', undefined, true)}>Guardar en carpeta</button>
                <button className="primario" onClick={() => pdf('etiquetas')}>Etiquetas (PDF)</button>
                {marcadas.length > 0 && (
                  <button className="secundario" onClick={() => pdf('etiquetas', marcadas)}>
                    Reimprimir {marcadas.length} etiqueta{marcadas.length === 1 ? '' : 's'}
                  </button>
                )}
              </>
            )}
            {usuario.rol === 'socio' && o.estado !== 'anulada' && !anulando && (
              <button className="peligro" onClick={() => setAnulando(true)}>Anular orden</button>
            )}
          </div>
          {anulando && (
            <div className="confirmacion peligro-caja no-impresion">
              <label>Motivo de la anulación (se devuelven los kg a la bobina{porPiezas ? ' y se descuentan las piezas producidas' : ''})<textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void anular()}>Anular definitivamente</button>
                <button className="secundario" onClick={() => setAnulando(false)}>Cancelar</button>
              </div>
            </div>
          )}
        </div>
      )}
      {cotizando && <CotizarOrden ordenId={id} onCerrar={() => setCotizando(false)} />}
    </Modal>
  )
}
