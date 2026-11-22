import { useEffect, useState, type FormEvent } from 'react'
import { pdfOt, pedir, type FichaPieza, type Orden, type Pieza, type ResumenOtLamina } from '../api'
import { hoyIso, kg, mm } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import Modal from './Modal'
import { hojaTrabajo } from './Planificadas'

type Maquina = 'lamina' | 'ctf'

const NOMBRE: Record<Maquina, string> = { lamina: 'Laminadora', ctf: 'CTF' }
const CALIDADES = ['1er-F', '1er-C', '1er-G', '1er']
const MAX_ATADOS = 8
const NOMBRE_CLASE: Record<string, string> = { 1: 'Primera', A: 'Segunda A', B: 'Segunda B', C: 'Segunda C' }
const dec = (s: string) => s.trim().replace(',', '.')
const num = (s: string) => Number(dec(s) || '0')
const entero = (s: string) => (s.trim() ? Math.max(0, Math.floor(Number(s))) : 0)
const piezas = new Intl.NumberFormat('es-VE')

/** Orden de corte a lámina: de una bobina (o fleje, en la CTF) salen láminas por atados y segundas. */
export default function OrdenLamina({ onVerOrden, plan = null, onPlanUsado }: {
  onVerOrden: (id: number) => void; plan?: Orden | null; onPlanUsado?: () => void
}) {
  const [maquina, setMaquina] = useState<Maquina>('lamina')
  const [pieza, setPieza] = useState<Pieza | null>(null)
  const [numero, setNumero] = useState('')
  const [fecha, setFecha] = useState(hoyIso())
  const [estatus, setEstatus] = useState<'total' | 'parcial'>('total')
  const [kgProcesado, setKgProcesado] = useState('')
  const [largo, setLargo] = useState('2400')
  const [ancho, setAncho] = useState('')
  const [calidad, setCalidad] = useState('1er-F')
  const [atados, setAtados] = useState<string[]>([''])
  const [segundas, setSegundas] = useState({ a: '', b: '', c: '' })
  const [scrap, setScrap] = useState('')
  const [paradas, setParadas] = useState('')
  const [observacion, setObservacion] = useState('')
  const [resumen, setResumen] = useState<ResumenOtLamina | null>(null)
  // Bobina con espesor no comercial (0,58): se pregunta si las láminas llevan 0,58 o 0,60 (nombre y código)
  const [redondear, setRedondear] = useState<boolean | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<{ texto: string; id: number; numero: number; propietario: string } | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cargarNumero = (m: Maquina) =>
    pedir<{ numero: number }>(`/api/ot/siguiente-numero?tipo=${m}`).then((r) => setNumero(String(r.numero))).catch(() => {})

  useEffect(() => { if (!plan) void cargarNumero(maquina) }, [maquina, plan])
  useEffect(() => { if (!plan) setRedondear(null) }, [pieza?.id, plan])
  // Resultados de una OC planificada: se precarga lo de la hoja
  useEffect(() => {
    if (!plan) return
    const p = (plan.plan ?? {}) as Record<string, string | boolean | null>
    setMaquina(plan.tipo === 'ctf' ? 'ctf' : 'lamina')
    setNumero(String(plan.numero))
    if (p.largo_mm) setLargo(String(Number(p.largo_mm)))
    if (p.ancho_mm) setAncho(String(Number(p.ancho_mm)))
    if (plan.calidad) setCalidad(plan.calidad)
    setRedondear(p.redondear_espesor === true)
    if (plan.pieza_id) pedir<FichaPieza>(`/api/piezas/${plan.pieza_id}`).then((f) => setPieza(f.pieza)).catch((e: Error) => setError(e.message))
  }, [plan?.id])

  function elegir(p: Pieza) {
    setPieza(p)
    setAncho(p.ancho_mm ? String(Number(p.ancho_mm)) : '')
    if (p.tipo_acero === 'GV') setCalidad('1er-G')
    else if (p.tipo_acero === 'HN') setCalidad('1er-C')
    else setCalidad('1er-F')
    setError(null)
    setHecho(null)
  }

  // Estimado en pantalla; la cifra buena la da la revisión.
  const consumido = estatus === 'total' ? Number(pieza?.saldo_kg ?? 0) : num(kgProcesado)
  const primera = atados.reduce((t, a) => t + entero(a), 0)
  const total = primera + entero(segundas.a) + entero(segundas.b) + entero(segundas.c)
  const porLamina = total ? (consumido - num(scrap)) / total : 0
  const teorico = pieza?.espesor_mm ? Number(pieza.espesor_mm) * num(ancho || pieza.ancho_mm || '0') * num(largo) * 7.85 / 1e6 : 0

  function cuerpo(confirmar: boolean) {
    if (!pieza) throw new Error('Elige la bobina que entra.')
    return {
      maquina,
      pieza_id: pieza.id,
      fecha,
      numero: numero ? Number(numero) : null,
      estatus_corte: estatus,
      kg_procesado: estatus === 'parcial' ? dec(kgProcesado) : null,
      largo_mm: dec(largo),
      ancho_mm: ancho.trim() ? dec(ancho) : null,
      atados: atados.map(entero).filter((n) => n > 0),
      segunda_a: entero(segundas.a),
      segunda_b: entero(segundas.b),
      segunda_c: entero(segundas.c),
      scrap_kg: scrap.trim() ? dec(scrap) : '0',
      calidad: calidad || null,
      paradas: paradas ? Number(paradas) : null,
      observacion: observacion.trim() || null,
      redondear_espesor: redondear === true,
      orden_planificada_id: plan?.id ?? null,
      confirmar,
      clave_idempotencia: confirmar ? clave : null,
    }
  }

  async function elegirEspesor(valor: boolean) {
    setRedondear(valor)
    setOcupado(true)
    try {
      const c = { ...cuerpo(false), redondear_espesor: valor }
      setResumen(await pedir<ResumenOtLamina>('/api/ot/lamina', { metodo: 'POST', cuerpo: c }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo revisar')
    } finally {
      setOcupado(false)
    }
  }

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenOtLamina>('/api/ot/lamina', { metodo: 'POST', cuerpo: cuerpo(false) })
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
      const r = await pedir<ResumenOtLamina>('/api/ot/lamina', { metodo: 'POST', cuerpo: cuerpo(true) })
      setHecho({ texto: `OC ${r.numero} de ${NOMBRE[maquina].toLowerCase()} registrada: ${piezas.format(r.total_laminas)} láminas, ${kg(r.kg_producido)}.`,
        id: r.orden_id ?? 0, numero: r.numero, propietario: r.propietario })
      setResumen(null)
      setPieza(null)
      setAtados([''])
      setSegundas({ a: '', b: '', c: '' })
      setScrap('')
      setKgProcesado('')
      setParadas('')
      setObservacion('')
      setEstatus('total')
      if (plan) onPlanUsado?.()
      void cargarNumero(maquina)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  const pdf = (doc: 'orden' | 'etiquetas', guardar = false) => {
    if (!hecho) return
    void pdfOt(`/api/ot/${hecho.id}/pdf/${doc}`, maquina, hecho.numero, hecho.propietario, doc, guardar)
      .catch((e: Error) => setError(e.message))
  }

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>Orden de corte · {NOMBRE[maquina]}</h1>
        <div className="selector">
          <label className="casilla"><input type="radio" checked={maquina === 'lamina'} onChange={() => setMaquina('lamina')} /> Laminadora</label>
          <label className="casilla"><input type="radio" checked={maquina === 'ctf'} onChange={() => setMaquina('ctf')} /> CTF</label>
        </div>
      </div>

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
              <button className="primario" onClick={() => pdf('orden')}>Hoja de la orden (PDF)</button>
              <button className="secundario" onClick={() => pdf('orden', true)}>Guardar la orden en carpeta</button>
              <button className="primario" onClick={() => pdf('etiquetas')}>Etiquetas de atados (PDF)</button>
              <button className="secundario" onClick={() => onVerOrden(hecho.id)}>Ver la orden</button>
            </div>
          )}
        </div>
      )}

      <div className="tarjeta bloque">
        <h2 className="sin-margen">1. Pieza que entra</h2>
        {!pieza && (
          <BuscadorPiezas propietarioId={null} tipo={maquina === 'ctf' ? '' : 'bobina'} excluir={[]} onElegir={elegir}
            mostrarDueno autoFocus placeholder="Código, medida o dueño de la bobina · F4 para ver las disponibles" />
        )}
        {pieza && (
          <div className="bobina-elegida">
            <div>
              <div className="codigo fuerte">{pieza.codigo_fisico}</div>
              <div className="tenue pequeno">{pieza.codigo_producto} · {pieza.descripcion}</div>
            </div>
            <dl className="datos en-linea">
              <dt>Espesor</dt><dd>{mm(pieza.espesor_mm, true)} mm</dd>
              <dt>Ancho</dt><dd>{mm(pieza.ancho_mm)} mm</dd>
              <dt>Saldo</dt><dd className="fuerte">{kg(pieza.saldo_kg)}</dd>
              <dt>Dueño</dt><dd>{pieza.propietario_nombre}</dd>
            </dl>
            <button className="secundario" onClick={() => setPieza(null)}>Cambiar</button>
          </div>
        )}
      </div>

      {pieza && (
        <form className="tarjeta bloque" onSubmit={revisar}>
          <h2 className="sin-margen">2. Datos de la orden</h2>
          <div className="formulario cuatro-columnas sin-relleno">
            <label>Número de OC<input inputMode="numeric" value={numero} onChange={(e) => setNumero(e.target.value)} /></label>
            <label>Fecha de corte<input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required /></label>
            <label>Largo de la lámina (mm)<input inputMode="decimal" value={largo} onChange={(e) => setLargo(e.target.value)} required /></label>
            <label>Ancho (mm)<input inputMode="decimal" value={ancho} onChange={(e) => setAncho(e.target.value)} placeholder="El de la bobina" /></label>
            <label>
              Calidad de primera
              <input list="calidades-lamina" value={calidad} onChange={(e) => setCalidad(e.target.value)} />
              <datalist id="calidades-lamina">{CALIDADES.map((c) => <option key={c} value={c} />)}</datalist>
            </label>
            <label>Paradas<input inputMode="numeric" value={paradas} onChange={(e) => setParadas(e.target.value)} placeholder="0" /></label>
            <label>Scrap (kg)<input inputMode="decimal" value={scrap} onChange={(e) => setScrap(e.target.value)} placeholder="Puntas y recortes" /></label>
          </div>

          <div className="selector">
            <label className="casilla"><input type="radio" checked={estatus === 'total'} onChange={() => setEstatus('total')} /> Corte total ({kg(pieza.saldo_kg)})</label>
            <label className="casilla"><input type="radio" checked={estatus === 'parcial'} onChange={() => setEstatus('parcial')} /> Corte parcial</label>
            {estatus === 'parcial' && (
              <label className="en-linea-label">
                kg a procesar
                <input inputMode="decimal" value={kgProcesado} onChange={(e) => setKgProcesado(e.target.value)} required />
              </label>
            )}
          </div>

          <h2>3. Láminas producidas</h2>
          <p className="tenue pequeno sin-margen">Primera por atados (cada atado lleva su etiqueta). Segunda en A, B y C.</p>
          <div className="tabla-envoltura">
            <table className="tabla compacta cortes">
              <thead><tr><th>Atado</th><th>Láminas de primera</th><th className="n">kg estimado</th><th></th></tr></thead>
              <tbody>
                {atados.map((a, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td><input inputMode="numeric" value={a} required={i === 0 && total === 0}
                      onChange={(e) => setAtados(atados.map((x, j) => (j === i ? e.target.value : x)))} /></td>
                    <td className="n">{kg(entero(a) * porLamina)}</td>
                    <td>{atados.length > 1 && <button type="button" className="enlace" onClick={() => setAtados(atados.filter((_, j) => j !== i))}>Quitar</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {atados.length < MAX_ATADOS && (
            <button type="button" className="secundario" onClick={() => setAtados([...atados, ''])}>Agregar atado</button>
          )}
          <div className="formulario cuatro-columnas sin-relleno">
            <label>Segunda A<input inputMode="numeric" value={segundas.a} onChange={(e) => setSegundas({ ...segundas, a: e.target.value })} placeholder="0" /></label>
            <label>Segunda B<input inputMode="numeric" value={segundas.b} onChange={(e) => setSegundas({ ...segundas, b: e.target.value })} placeholder="0" /></label>
            <label>Segunda C<input inputMode="numeric" value={segundas.c} onChange={(e) => setSegundas({ ...segundas, c: e.target.value })} placeholder="0" /></label>
          </div>
          <div className="ficha-resumen">
            <div><span>Láminas</span><strong>{piezas.format(total)}</strong></div>
            <div><span>Peso por lámina</span><strong>{total ? `${porLamina.toFixed(2).replace('.', ',')} kg` : '—'}</strong></div>
            <div><span>Teórico</span><strong>{teorico ? `${teorico.toFixed(2).replace('.', ',')} kg` : '—'}</strong></div>
          </div>

          <label className="ancho-completo">Observación<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} /></label>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar orden'}</button>
          </div>
        </form>
      )}
      {!pieza && error && <p className="error">{error}</p>}

      {resumen && (
        <Modal titulo={`Confirma la OC ${resumen.numero} de ${NOMBRE[maquina].toLowerCase()}`} onCerrar={() => setResumen(null)} ancho>
          <div className="ficha-resumen">
            <div><span>Procesado</span><strong>{kg(resumen.kg_consumido)}</strong></div>
            <div><span>Láminas</span><strong>{piezas.format(resumen.total_laminas)} · {kg(resumen.kg_producido)}</strong></div>
            <div><span>Por lámina</span><strong>{resumen.kg_por_lamina} kg</strong></div>
          </div>
          <p className="pequeno">
            Bobina <span className="codigo">{resumen.pieza}</span> · {resumen.propietario} · corte {resumen.estatus_corte} ·
            {' '}{mm(resumen.ancho_mm)} × {mm(resumen.largo_mm)} mm · teórico {resumen.kg_teorico_por_lamina} kg
            ({resumen.diferencia_teorico_pct} %) · scrap {kg(resumen.kg_scrap)} · a la bobina le quedan {kg(resumen.saldo_restante_kg)}
          </p>
          {resumen.espesor_comercial && (
            <div className="alerta">
              <strong>La bobina es de {resumen.espesor_real} mm.</strong> ¿Las láminas llevan ese espesor o se redondean a
              {' '}{resumen.espesor_comercial} mm? Si se redondea, cambian el nombre y el código.
              <div className="acciones">
                <button type="button" className={redondear === false ? 'primario' : 'secundario'} disabled={ocupado}
                  onClick={() => void elegirEspesor(false)}>Mantener {resumen.espesor_real} mm</button>
                <button type="button" className={redondear === true ? 'primario' : 'secundario'} disabled={ocupado}
                  onClick={() => void elegirEspesor(true)}>Redondear a {resumen.espesor_comercial} mm</button>
              </div>
            </div>
          )}
          {resumen.avisos.length > 0 && (
            <div className="alerta"><strong>Revisa antes de guardar:</strong><ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>
          )}
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Calidad</th><th>Producto</th><th className="n">Láminas</th><th className="n">kg</th><th className="n">Quedarán</th></tr></thead>
              <tbody>
                {resumen.grupos.map((g) => (
                  <tr key={g.codigo_producto}>
                    <td>{NOMBRE_CLASE[g.clase] ?? g.clase}</td>
                    <td><div className="codigo">{g.codigo_producto}</div><div className="tenue pequeno">{g.descripcion}</div></td>
                    <td className="n">{piezas.format(g.unidades)}</td>
                    <td className="n">{kg(g.kg)}</td>
                    <td className="n">{g.existencia_despues === null ? '—' : piezas.format(g.existencia_despues)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tenue pequeno">{resumen.atados.length} etiquetas de atado{resumen.grupos.some((g) => g.clase !== '1') ? ' más una por cada segunda' : ''}.</p>
          <div className="acciones">
            <button className="primario" disabled={ocupado || (!!resumen.espesor_comercial && redondear === null)}
              title={resumen.espesor_comercial && redondear === null ? 'Elige primero si se redondea el espesor' : undefined}
              onClick={() => void confirmar()}>{ocupado ? 'Guardando…' : 'Confirmar y guardar'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </Modal>
      )}
    </section>
  )
}
