import { useEffect, useState, type FormEvent } from 'react'
import { pdfOt, pedir, type FichaPieza, type Orden, type Pieza, type ResumenOtSlitter } from '../api'
import { hoyIso, kg, mm } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import Modal from './Modal'
import { hojaTrabajo } from './Planificadas'

interface Corte { ancho_mm: string; rollos: string; kg: string; calidad: string }

const CORTE_VACIO: Corte = { ancho_mm: '', rollos: '1', kg: '', calidad: '' }
const CALIDADES = ['1er-F', '1er-C', '1er-G', '2da-A', '2da-B', '2da-C']
const num = (s: string) => Number(s.trim().replace(',', '.'))
const dec = (s: string) => s.trim().replace(',', '.')

export default function OrdenSlitter({ onVerOrden, plan = null, onPlanUsado }: {
  onVerOrden: (id: number) => void; plan?: Orden | null; onPlanUsado?: () => void
}) {
  const [bobina, setBobina] = useState<Pieza | null>(null)
  const [numero, setNumero] = useState('')
  const [fecha, setFecha] = useState(hoyIso())
  const [estatus, setEstatus] = useState<'total' | 'parcial'>('total')
  const [kgProcesado, setKgProcesado] = useState('')
  const [calidad, setCalidad] = useState('1er-F')
  const [paradas, setParadas] = useState('')
  const [observacion, setObservacion] = useState('')
  const [cortes, setCortes] = useState<Corte[]>([{ ...CORTE_VACIO }])
  const [scrapAncho, setScrapAncho] = useState('')
  const [scrapKg, setScrapKg] = useState('')
  const [resumen, setResumen] = useState<ResumenOtSlitter | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<{ texto: string; id: number; numero: number; propietario: string } | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cargarNumero = () =>
    pedir<{ numero: number }>('/api/ot/siguiente-numero?tipo=slitter').then((r) => setNumero(String(r.numero))).catch(() => {})

  useEffect(() => { if (!plan) void cargarNumero() }, [plan])
  // Resultados de una OC planificada: se precarga lo de la hoja
  useEffect(() => {
    if (!plan) return
    const p = (plan.plan ?? {}) as { cortes?: { ancho_mm: string; rollos: number }[]; scrap_ancho_mm?: string }
    setNumero(String(plan.numero))
    if (plan.calidad) setCalidad(plan.calidad)
    if (p.cortes?.length) setCortes(p.cortes.map((c) => ({ ...CORTE_VACIO, ancho_mm: String(Number(c.ancho_mm)), rollos: String(c.rollos) })))
    if (p.scrap_ancho_mm) setScrapAncho(String(Number(p.scrap_ancho_mm)))
    if (plan.pieza_id) pedir<FichaPieza>(`/api/piezas/${plan.pieza_id}`).then((f) => setBobina(f.pieza)).catch((e: Error) => setError(e.message))
  }, [plan?.id])

  function elegir(p: Pieza) {
    setBobina(p)
    setError(null)
    setHecho(null)
  }

  // Estimación en pantalla (la API recalcula y manda la cifra buena en la revisión)
  const anchoBobina = bobina?.ancho_mm ? Number(bobina.ancho_mm) : 0
  const consumido = estatus === 'total' ? Number(bobina?.saldo_kg ?? 0) : num(kgProcesado || '0')
  const anchoUsado = cortes.reduce((t, c) => t + (num(c.ancho_mm || '0') * num(c.rollos || '0')), 0) + num(scrapAncho || '0')
  const estimado = (c: Corte) =>
    c.kg ? num(c.kg) : anchoBobina ? (consumido * num(c.ancho_mm || '0') * num(c.rollos || '0')) / anchoBobina : 0
  const sobra = anchoBobina - anchoUsado

  function cambiarCorte(i: number, campo: keyof Corte, valor: string) {
    setCortes(cortes.map((c, j) => (j === i ? { ...c, [campo]: valor } : c)))
  }

  function cuerpo(confirmar: boolean) {
    if (!bobina) throw new Error('Elige la bobina que entra al slitter.')
    return {
      pieza_id: bobina.id,
      fecha,
      numero: numero ? Number(numero) : null,
      estatus_corte: estatus,
      kg_procesado: estatus === 'parcial' ? dec(kgProcesado) : null,
      calidad: calidad || null,
      paradas: paradas ? Number(paradas) : null,
      observacion: observacion.trim() || null,
      cortes: cortes.filter((c) => c.ancho_mm.trim()).map((c) => ({
        ancho_mm: dec(c.ancho_mm), rollos: Number(c.rollos || '1'), kg: c.kg ? dec(c.kg) : null, calidad: c.calidad || null,
      })),
      scrap_ancho_mm: scrapAncho ? dec(scrapAncho) : '0',
      scrap_kg: scrapKg ? dec(scrapKg) : null,
      orden_planificada_id: plan?.id ?? null,
      confirmar,
      clave_idempotencia: confirmar ? clave : null,
    }
  }

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenOtSlitter>('/api/ot/slitter', { metodo: 'POST', cuerpo: cuerpo(false) })
      setClave(crypto.randomUUID())
      setResumen(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo revisar')
    } finally {
      setOcupado(false)
    }
  }

  async function confirmar() {
    setOcupado(true)
    setError(null)
    try {
      const r = await pedir<ResumenOtSlitter>('/api/ot/slitter', { metodo: 'POST', cuerpo: cuerpo(true) })
      const rollos = r.cortes.reduce((t, c) => t + c.rollos, 0)
      setHecho({ texto: `OC ${r.numero} registrada: ${rollos} rollos de fleje, ${kg(r.kg_producido)}.`, id: r.orden_id ?? 0, numero: r.numero, propietario: r.propietario })
      setResumen(null)
      setBobina(null)
      setCortes([{ ...CORTE_VACIO }])
      setScrapAncho('')
      setScrapKg('')
      setKgProcesado('')
      setParadas('')
      setObservacion('')
      setEstatus('total')
      if (plan) onPlanUsado?.()
      void cargarNumero()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <section>
      <div className="encabezado-seccion"><h1>Orden de corte · Slitter</h1></div>

      {plan && (
        <div className="alerta no-impresion">
          Registrando los resultados de la <strong>OC {plan.numero} planificada</strong>: los datos de la hoja ya están cargados;
          {' '}completa lo que anotó el operador.{' '}
          <button type="button" className="enlace" onClick={() => hojaTrabajo(plan, setError)}>Ver la hoja</button>
        </div>
      )}
      {hecho && (
        <div className="exito">
          <div>{hecho.texto}</div>
          {hecho.id > 0 && (
            <div className="acciones">
              <button className="primario" onClick={() => void pdfOt(`/api/ot/${hecho.id}/pdf/orden`, 'slitter', hecho.numero, hecho.propietario, 'orden', false).catch((e: Error) => setError(e.message))}>
                Hoja de la orden (PDF)
              </button>
              <button className="secundario" onClick={() => void pdfOt(`/api/ot/${hecho.id}/pdf/orden`, 'slitter', hecho.numero, hecho.propietario, 'orden', true).catch((e: Error) => setError(e.message))}>
                Guardar la orden en carpeta
              </button>
              <button className="primario" onClick={() => void pdfOt(`/api/ot/${hecho.id}/pdf/etiquetas`, 'slitter', hecho.numero, hecho.propietario, 'etiquetas', false).catch((e: Error) => setError(e.message))}>
                Etiquetas (PDF)
              </button>
              <button className="secundario" onClick={() => onVerOrden(hecho.id)}>Ver la orden</button>
            </div>
          )}
        </div>
      )}

      <div className="tarjeta bloque">
        <h2 className="sin-margen">1. Bobina que entra</h2>
        {!bobina && (
          <BuscadorPiezas propietarioId={null} tipo="bobina" excluir={[]} onElegir={elegir} mostrarDueno autoFocus
            placeholder="Código, medida o dueño de la bobina · F4 para ver las disponibles" />
        )}
        {bobina && (
          <div className="bobina-elegida">
            <div>
              <div className="codigo fuerte">{bobina.codigo_fisico}</div>
              <div className="tenue pequeno">{bobina.codigo_producto} · {bobina.descripcion}</div>
            </div>
            <dl className="datos en-linea">
              <dt>Espesor</dt><dd>{mm(bobina.espesor_mm, true)} mm</dd>
              <dt>Ancho</dt><dd>{mm(bobina.ancho_mm)} mm</dd>
              <dt>Saldo</dt><dd className="fuerte">{kg(bobina.saldo_kg)}</dd>
              <dt>Dueño</dt><dd>{bobina.propietario_nombre}</dd>
            </dl>
            <button className="secundario" onClick={() => setBobina(null)}>Cambiar</button>
          </div>
        )}
      </div>

      {bobina && (
        <form className="tarjeta bloque" onSubmit={revisar}>
          <h2 className="sin-margen">2. Datos de la orden</h2>
          <div className="formulario cuatro-columnas sin-relleno">
            <label>Número de OC<input inputMode="numeric" value={numero} onChange={(e) => setNumero(e.target.value)} /></label>
            <label>Fecha de corte<input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required /></label>
            <label>
              Calidad
              <input list="calidades" value={calidad} onChange={(e) => setCalidad(e.target.value)} />
              <datalist id="calidades">{CALIDADES.map((c) => <option key={c} value={c} />)}</datalist>
            </label>
            <label>Paradas<input inputMode="numeric" value={paradas} onChange={(e) => setParadas(e.target.value)} placeholder="0" /></label>
          </div>

          <div className="selector">
            <label className="casilla"><input type="radio" checked={estatus === 'total'} onChange={() => setEstatus('total')} /> Corte total ({kg(bobina.saldo_kg)})</label>
            <label className="casilla"><input type="radio" checked={estatus === 'parcial'} onChange={() => setEstatus('parcial')} /> Corte parcial</label>
            {estatus === 'parcial' && (
              <label className="en-linea-label">
                kg a procesar
                <input inputMode="decimal" value={kgProcesado} onChange={(e) => setKgProcesado(e.target.value)} required />
              </label>
            )}
          </div>

          <h2>3. Cortes</h2>
          <div className="tabla-envoltura">
            <table className="tabla compacta cortes">
              <thead>
                <tr><th>#</th><th>Ancho (mm)</th><th>Rollos</th><th>kg del corte</th><th>Calidad</th><th className="n">Estimado</th><th></th></tr>
              </thead>
              <tbody>
                {cortes.map((c, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td><input inputMode="decimal" value={c.ancho_mm} onChange={(e) => cambiarCorte(i, 'ancho_mm', e.target.value)} required={i === 0} /></td>
                    <td><input inputMode="numeric" value={c.rollos} onChange={(e) => cambiarCorte(i, 'rollos', e.target.value)} /></td>
                    <td><input inputMode="decimal" value={c.kg} onChange={(e) => cambiarCorte(i, 'kg', e.target.value)} placeholder="auto" /></td>
                    <td><input list="calidades" value={c.calidad} onChange={(e) => cambiarCorte(i, 'calidad', e.target.value)} placeholder={calidad} /></td>
                    <td className="n">{kg(estimado(c))}</td>
                    <td>{cortes.length > 1 && <button type="button" className="enlace" onClick={() => setCortes(cortes.filter((_, j) => j !== i))}>Quitar</button>}</td>
                  </tr>
                ))}
                <tr>
                  <td>7</td>
                  <td><input inputMode="decimal" value={scrapAncho} onChange={(e) => setScrapAncho(e.target.value)} placeholder="Scrap" /></td>
                  <td className="tenue">scrap</td>
                  <td><input inputMode="decimal" value={scrapKg} onChange={(e) => setScrapKg(e.target.value)} placeholder="auto" /></td>
                  <td></td>
                  <td className="n">{kg(scrapKg ? num(scrapKg) : anchoBobina ? (consumido * num(scrapAncho || '0')) / anchoBobina : 0)}</td>
                  <td></td>
                </tr>
              </tbody>
            </table>
          </div>
          {cortes.length < 6 && (
            <button type="button" className="secundario" onClick={() => setCortes([...cortes, { ...CORTE_VACIO }])}>Agregar corte</button>
          )}
          <div className={`barra-ancho ${sobra < -2 ? 'excede' : ''}`}>
            <div className="relleno" style={{ width: `${Math.min(100, anchoBobina ? (anchoUsado / anchoBobina) * 100 : 0)}%` }} />
            <span>{mm(anchoUsado)} de {mm(anchoBobina)} mm {sobra > 2 ? `· sobran ${mm(sobra)} mm` : sobra < -2 ? `· se pasa ${mm(-sobra)} mm` : ''}</span>
          </div>

          <label className="ancho-completo">Observación<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} /></label>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar orden'}</button>
          </div>
        </form>
      )}
      {!bobina && error && <p className="error">{error}</p>}

      {resumen && (
        <Modal titulo={`Confirma la OC ${resumen.numero}`} onCerrar={() => setResumen(null)} ancho>
          <div className="ficha-resumen">
            <div><span>Consumido</span><strong>{kg(resumen.kg_consumido)}</strong></div>
            <div><span>Producido</span><strong>{kg(resumen.kg_producido)}</strong></div>
            <div><span>Scrap</span><strong>{kg(resumen.kg_scrap)}</strong></div>
          </div>
          <p className="pequeno">
            Bobina <span className="codigo">{resumen.bobina}</span> · {resumen.propietario} · corte {resumen.estatus_corte} ·
            diferencia {resumen.diferencia_pct} % · le quedan {kg(resumen.saldo_restante_kg)}
          </p>
          {resumen.avisos.length > 0 && (
            <div className="alerta"><strong>Revisa antes de guardar:</strong><ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>
          )}
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Rollo</th><th>Producto</th><th className="n">kg</th></tr></thead>
              <tbody>
                {resumen.cortes.flatMap((c) => c.detalle_rollos.map((r) => (
                  <tr key={r.codigo}><td className="codigo">{r.codigo.split(' / ').slice(-1)[0]}</td><td>{c.descripcion}</td><td className="n">{kg(r.kg)}</td></tr>
                )))}
              </tbody>
            </table>
          </div>
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void confirmar()}>{ocupado ? 'Guardando…' : 'Confirmar y guardar'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </Modal>
      )}
    </section>
  )
}
