import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  abrirPdf, consulta, guardarPdf, NOMBRE_DOCUMENTO, reciboEntrada, nombreArchivo, pedir, type DetalleDocumento, type Documento, type EncabezadoNE, type Pieza, type ResumenCorreccionNE,
  type ReporteSalidas, type ResumenSalida,
  type Tercero, type Usuario,
  MATERIAL_IRREGULAR, pdfNotaSalida, type Existencias,
} from '../api'
import { fecha, hoyIso, kg } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import Cotizaciones, { CotizarDesde, ListaCotizaciones } from './Cotizaciones'
import Despachos from './Despachos'
import Modal from './Modal'

export type PestanaSalidas = 'planificadas' | 'nota' | 'liberacion' | 'reporte' | 'cotizaciones' | 'documentos'
type Pestana = PestanaSalidas

export default function Salidas({ usuario, inicial, pendientes = 0 }: {
  usuario: Usuario; inicial?: Pestana; pendientes?: number
}) {
  const esPersonal = usuario.rol !== 'cliente'
  const [pestana, setPestana] = useState<Pestana>(inicial ?? (esPersonal ? 'nota' : 'documentos'))
  useEffect(() => { if (inicial) setPestana(inicial) }, [inicial])
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [abrirDoc, setAbrirDoc] = useState<number | null>(null)
  const [tipoDocs, setTipoDocs] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (esPersonal) pedir<Tercero[]>('/api/terceros').then((t) => setTerceros(t.filter((x) => x.activo))).catch(() => {})
  }, [esPersonal])

  const verDocumento = (id: number) => { setAbrirDoc(id); setPestana('documentos') }

  return (
    <section>
      <div className="encabezado-seccion"><h1>{esPersonal ? 'Salidas' : 'Mis documentos'}</h1></div>
      {esPersonal && (
        <nav className="subpestanas" aria-label="Tipo de salida">
          <button className={pestana === 'planificadas' ? 'activa' : ''} onClick={() => setPestana('planificadas')}>
            Planificadas {pendientes > 0 && <span className="contador" aria-label={`${pendientes} pendientes`}>{pendientes}</span>}
          </button>
          <button className={pestana === 'nota' ? 'activa' : ''} onClick={() => setPestana('nota')}>Nota de entrega</button>
          <button className={pestana === 'liberacion' ? 'activa' : ''} onClick={() => setPestana('liberacion')}>Liberación</button>
          <button className={pestana === 'reporte' ? 'activa' : ''} onClick={() => setPestana('reporte')}>Reporte mensual</button>
          <button className={pestana === 'cotizaciones' ? 'activa' : ''} onClick={() => setPestana('cotizaciones')}>Cotizaciones</button>
          <button className={pestana === 'documentos' ? 'activa' : ''} onClick={() => setPestana('documentos')}>Documentos</button>
        </nav>
      )}
      <datalist id="lista-terceros-salidas">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
      {pestana === 'planificadas' && esPersonal && <Despachos usuario={usuario} onVerDocumento={verDocumento} />}
      {pestana === 'nota' && <NotaEntrega terceros={terceros} onVer={verDocumento} />}
      {pestana === 'liberacion' && <Liberacion terceros={terceros} onVer={verDocumento} />}
      {pestana === 'reporte' && esPersonal && <ReporteMensual terceros={terceros} onVer={verDocumento} />}
      {pestana === 'cotizaciones' && esPersonal && <Cotizaciones onVerDocumentos={() => { setTipoDocs('cotizacion'); setPestana('documentos') }} />}
      {pestana === 'documentos' && <Documentos usuario={usuario} abrir={abrirDoc} onAbierto={() => setAbrirDoc(null)} tipoInicial={tipoDocs} />}
    </section>
  )
}

/** "120 pzas · 2.500 kg" para láminas, perfiles y generales; solo kg para bobinas y flejes. */
function cantidad(unidades: number | null | undefined, kilos: string | number): string {
  return unidades === null || unidades === undefined ? kg(kilos) : `${Math.abs(unidades).toLocaleString('es-VE')} pzas · ${kg(Math.abs(Number(kilos)))}`
}

const porNombre = (terceros: Tercero[], nombre: string) =>
  terceros.find((t) => t.nombre.toLowerCase() === nombre.trim().toLowerCase()) ?? null

function Exito({ texto, id, onVer, pdf, guardar }: {
  texto: string; id: number | null; onVer: (id: number) => void; pdf?: () => void; guardar?: () => void
}) {
  return (
    <div className="exito">
      {texto} {id && <button className="enlace" onClick={() => onVer(id)}>Ver el documento</button>}
      {id && pdf && <> · <button className="enlace" onClick={pdf}>Ver la NE (PDF)</button></>}
      {id && guardar && <> · <button className="enlace" onClick={guardar}>Guardar la NE en carpeta</button></>}
    </div>
  )
}

/** "Nota de Entrega 7237 Aceros del Valle, C.A..pdf" */
const archivoNE = (numero: string | null, cliente: string | null | undefined) => nombreArchivo('Nota de Entrega', numero, cliente)

function imprimirNE(id: number, numero: string | null, cliente: string | null | undefined, onError: (m: string) => void) {
  abrirPdf(`/api/documentos/${id}/pdf`, archivoNE(numero, cliente)).catch((e: Error) => onError(e.message))
}

/** Guarda la NE con su nombre; la primera vez se elige la carpeta (la de Dropbox de Ventas) y el
 *  navegador la recuerda para las siguientes. */
function guardarNE(id: number, numero: string | null, cliente: string | null | undefined, onError: (m: string) => void) {
  guardarPdf(`/api/documentos/${id}/pdf`, archivoNE(numero, cliente), 'prosifer-notas-entrega')
    .catch((e: Error) => onError(e.message))
}

const CAMPOS_NE: { clave: keyof EncabezadoNE; titulo: string; ficha?: keyof Tercero; doble?: boolean }[] = [
  { clave: 'domicilio_entrega', titulo: 'Domicilio de entrega', ficha: 'direccion', doble: true },
  { clave: 'telefonos', titulo: 'Teléfonos', ficha: 'telefono' },
  { clave: 'condicion_pago', titulo: 'Condición de pago', ficha: 'forma_pago' },
  { clave: 'vendedor', titulo: 'Vendedor', ficha: 'vendedor' },
  { clave: 'cotizacion', titulo: 'Cotización N.º' },
  { clave: 'chofer', titulo: 'Chofer' },
  { clave: 'placa', titulo: 'Placa' },
  { clave: 'nota_salida', titulo: 'Nota de salida N.º' },
]

/** Datos que van en la NE impresa. Vacío = lo de la ficha del cliente (se ve como sugerencia). */
function CamposEncabezado({ valor, onCambio, ficha }: { valor: EncabezadoNE; onCambio: (v: EncabezadoNE) => void; ficha: Tercero | null }) {
  const poner = (k: keyof EncabezadoNE, v: string) => onCambio({ ...valor, [k]: v })
  return (
    <fieldset className="grupo-campos">
      <legend>Datos de la NE impresa <span className="tenue pequeno">(lo vacío se toma de la ficha del cliente)</span></legend>
      <div className="formulario cuatro-columnas sin-relleno">
        {CAMPOS_NE.map((c) => (
          <label key={c.clave} className={c.doble ? 'doble' : undefined}>{c.titulo}
            <input value={valor[c.clave] ?? ''} onChange={(e) => poner(c.clave, e.target.value)}
              placeholder={c.ficha && ficha ? String(ficha[c.ficha] ?? '') : ''} />
          </label>
        ))}
      </div>
      <label>Notas importantes (salen impresas en la NE)
        <textarea rows={2} value={valor.notas ?? ''} onChange={(e) => poner('notas', e.target.value)} />
      </label>
    </fieldset>
  )
}

const encabezadoLimpio = (v: EncabezadoNE): EncabezadoNE | null => {
  const d = Object.fromEntries(Object.entries(v).filter(([, x]) => typeof x === 'string' && x.trim()))
  return Object.keys(d).length ? d : null
}

function ConfirmarSalida({ r, ocupado, onConfirmar, onCerrar }: {
  r: ResumenSalida; ocupado: boolean; onConfirmar: () => void; onCerrar: () => void
}) {
  const esLib = r.tipo === 'liberacion'
  return (
    <Modal titulo={`Confirma la ${esLib ? 'liberación' : 'nota de entrega'} ${r.numero}`} onCerrar={onCerrar} ancho>
      <p>
        {esLib ? <>De <strong>{r.tercero}</strong> a <strong>{r.tercero_nuevo}</strong></> : <>Cliente <strong>{r.tercero}</strong></>}
        {' · '}{fecha(r.fecha)} · {r.lineas.length} pieza{r.lineas.length === 1 ? '' : 's'} · <strong>{kg(r.total_kg)}</strong>
      </p>
      {r.avisos.length > 0 && <div className="alerta"><strong>Revisa antes de guardar:</strong><ul>{r.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>}
      <div className="tabla-envoltura">
        <table className="tabla compacta">
          <thead><tr><th>Pieza</th><th className="n">Saldo</th><th className="n">{esLib ? 'Pasa al nuevo dueño' : 'Sale'}</th>{!esLib && <th className="n">Queda</th>}</tr></thead>
          <tbody>
            {r.lineas.map((l) => (
              <tr key={l.pieza_id}>
                <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                <td className="n">{cantidad(l.saldo_antes_unidades, l.saldo_antes_kg)}</td>
                <td className="n fuerte">{cantidad(l.unidades, l.kg)}</td>
                {!esLib && <td className="n">{cantidad(l.saldo_despues_unidades, l.saldo_despues_kg)}</td>}
              </tr>
            ))}
            {(r.libres ?? []).map((l, i) => (
              <tr key={`libre${i}`}>
                <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                <td className="n tenue">sin existencia</td>
                <td className="n fuerte">{kg(l.kg)}</td>
                <td className="n tenue">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="acciones">
        <button className="primario" disabled={ocupado} onClick={onConfirmar}>{ocupado ? 'Guardando…' : 'Confirmar y guardar'}</button>
        <button className="secundario" onClick={onCerrar}>Corregir</button>
      </div>
    </Modal>
  )
}

interface LineaNota { pieza: Pieza; kg: string }   // en láminas, perfiles y generales "kg" lleva las piezas
interface LineaIrregular { kg: string; detalle: string }

const enPiezas = (p: Pieza) => p.saldo_unidades !== null && p.saldo_unidades !== undefined

function NotaEntrega({ terceros, onVer }: { terceros: Tercero[]; onVer: (id: number) => void }) {
  const [dia, setDia] = useState(hoyIso())
  const [cliente, setCliente] = useState('')
  const [lineas, setLineas] = useState<LineaNota[]>([])
  const [irregulares, setIrregulares] = useState<LineaIrregular[]>([])
  const [observacion, setObservacion] = useState('')
  const [encabezado, setEncabezado] = useState<EncabezadoNE>({})
  const [resumen, setResumen] = useState<ResumenSalida | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<{ texto: string; id: number | null; numero: string; cliente: string } | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const elegido = porNombre(terceros, cliente)

  useEffect(() => { setLineas([]) }, [elegido?.id])

  function cuerpo(confirmar: boolean) {
    if (!elegido) throw new Error('Elige el cliente de la lista.')
    if (lineas.length === 0 && irregulares.length === 0) throw new Error('Agrega al menos una pieza o material de medidas irregulares.')
    const libres = irregulares.map((x) => {
      const v = x.kg.trim().replace(',', '.')
      if (!v || !(Number(v) > 0)) throw new Error(`${MATERIAL_IRREGULAR.nombre}: indica los kg que salen.`)
      return { codigo: MATERIAL_IRREGULAR.codigo, kg: v, detalle: x.detalle.trim() || null }
    })
    return {
      fecha: dia, tercero_id: elegido.id, observacion: observacion.trim() || null, confirmar, libres,
      clave_idempotencia: confirmar ? clave : null, encabezado: encabezadoLimpio(encabezado),
      lineas: lineas.map((l) => {
        const v = l.kg.trim().replace(',', '.')
        if (enPiezas(l.pieza)) {
          if (v && !/^\d+$/.test(v)) throw new Error(`${l.pieza.codigo_fisico}: las piezas van en números enteros.`)
          return { pieza_id: l.pieza.id, unidades: v ? Number(v) : null }
        }
        return { pieza_id: l.pieza.id, kg: v || null }
      }),
    }
  }

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenSalida>('/api/salidas/nota-entrega', { metodo: 'POST', cuerpo: cuerpo(false) })
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
    try {
      const r = await pedir<ResumenSalida>('/api/salidas/nota-entrega', { metodo: 'POST', cuerpo: cuerpo(true) })
      setHecho({ texto: `Nota de entrega ${r.numero} registrada: ${kg(r.total_kg)}.`, id: r.documento_id, numero: r.numero, cliente: elegido?.nombre ?? '' })
      setResumen(null)
      setLineas([])
      setIrregulares([])
      setObservacion('')
      setEncabezado({})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  // Estimado: en piezas, al peso medio de la existencia (el definitivo lo calcula el sistema al revisar).
  const total = lineas.reduce((t, l) => {
    if (!l.kg.trim()) return t + Number(l.pieza.saldo_kg)
    const v = Number(l.kg.replace(',', '.'))
    return t + (enPiezas(l.pieza) && l.pieza.saldo_unidades ? (Number(l.pieza.saldo_kg) / l.pieza.saldo_unidades) * v : v)
  }, 0) + irregulares.reduce((t, x) => t + (Number(x.kg.replace(',', '.')) || 0), 0)

  return (
    <>
      {hecho && <Exito texto={hecho.texto} id={hecho.id} onVer={onVer}
        pdf={hecho.id ? () => imprimirNE(hecho.id as number, hecho.numero, hecho.cliente, setError) : undefined}
        guardar={hecho.id ? () => guardarNE(hecho.id as number, hecho.numero, hecho.cliente, setError) : undefined} />}
      <form className="tarjeta bloque" onSubmit={revisar}>
        <div className="formulario cuatro-columnas sin-relleno">
          <label>Número de NE<input value="Se asigna al guardar" disabled /></label>
          <label>Fecha<input type="date" value={dia} onChange={(e) => setDia(e.target.value)} required /></label>
          <label className="doble">Cliente (dueño del material)
            <input list="lista-terceros-salidas" value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Escribe para buscar" required />
          </label>
        </div>
        <BuscadorPiezas propietarioId={elegido?.id ?? null} excluir={lineas.map((l) => l.pieza.id)}
          deshabilitado={elegido ? null : 'Primero elige el cliente.'}
          onElegir={(p) => setLineas([...lineas, { pieza: p, kg: '' }])} />
        {lineas.length > 0 && (
          <div className="tabla-envoltura">
            <table className="tabla compacta cortes">
              <thead><tr><th>Pieza</th><th className="n">Saldo</th><th>Salen (kg o piezas)</th><th></th></tr></thead>
              <tbody>
                {lineas.map((l, i) => (
                  <tr key={l.pieza.id}>
                    <td><div className="codigo">{l.pieza.codigo_fisico}</div><div className="tenue pequeno">{l.pieza.descripcion}</div></td>
                    <td className="n">{cantidad(l.pieza.saldo_unidades, l.pieza.saldo_kg)}</td>
                    <td><input inputMode={enPiezas(l.pieza) ? 'numeric' : 'decimal'} value={l.kg}
                      aria-label={enPiezas(l.pieza) ? 'Piezas que salen' : 'kg que salen'}
                      placeholder={enPiezas(l.pieza) ? `piezas (todas: ${l.pieza.saldo_unidades})` : 'kg (toda la pieza)'}
                      onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, kg: e.target.value } : x)))} /></td>
                    <td><button type="button" className="enlace" onClick={() => setLineas(lineas.filter((_, j) => j !== i))}>Quitar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {irregulares.length === 0 && <p className="pie-tabla">Total estimado: <strong>{kg(total)}</strong></p>}
          </div>
        )}
        <div className="bloque-irregular">
          {irregulares.length > 0 && (
            <div className="tabla-envoltura">
              <table className="tabla compacta cortes">
                <thead><tr><th>{MATERIAL_IRREGULAR.nombre}</th><th>Detalle (sale impreso)</th><th>Kg que salen</th><th></th></tr></thead>
                <tbody>
                  {irregulares.map((x, i) => (
                    <tr key={i}>
                      <td><div className="codigo">{MATERIAL_IRREGULAR.codigo}</div><div className="tenue pequeno">sin existencia: no descuenta inventario</div></td>
                      <td><input value={x.detalle} aria-label="Detalle" maxLength={150} placeholder="Scrap, chatarra, recortes fuera de medida…"
                        onChange={(e) => setIrregulares(irregulares.map((y, j) => (j === i ? { ...y, detalle: e.target.value } : y)))} /></td>
                      <td><input inputMode="decimal" value={x.kg} aria-label="Kg que salen" placeholder="kg" required
                        onChange={(e) => setIrregulares(irregulares.map((y, j) => (j === i ? { ...y, kg: e.target.value } : y)))} /></td>
                      <td><button type="button" className="enlace" onClick={() => setIrregulares(irregulares.filter((_, j) => j !== i))}>Quitar</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="pie-tabla">Total estimado: <strong>{kg(total)}</strong></p>
            </div>
          )}
          <button type="button" className="secundario" disabled={!elegido}
            onClick={() => setIrregulares([...irregulares, { kg: '', detalle: '' }])}>
            + {MATERIAL_IRREGULAR.nombre}
          </button>
          <span className="tenue pequeno"> Scrap, chatarra o cortes fuera de medida: sale solo por su peso, sin stock del cliente.</span>
        </div>
        <CamposEncabezado valor={encabezado} onCambio={setEncabezado} ficha={elegido} />
        <label>Observación interna (no sale impresa)<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <div className="acciones"><button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar nota'}</button></div>
      </form>
      {resumen && <ConfirmarSalida r={resumen} ocupado={ocupado} onConfirmar={() => void confirmar()} onCerrar={() => setResumen(null)} />}
    </>
  )
}

function Liberacion({ terceros, onVer }: { terceros: Tercero[]; onVer: (id: number) => void }) {
  const [numero, setNumero] = useState('')
  const [dia, setDia] = useState(hoyIso())
  const [actual, setActual] = useState('')
  const [nuevo, setNuevo] = useState('')
  const [piezas, setPiezas] = useState<Pieza[]>([])
  const [observacion, setObservacion] = useState('')
  const [resumen, setResumen] = useState<ResumenSalida | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<{ texto: string; id: number | null } | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const dueno = porNombre(terceros, actual)
  const destino = porNombre(terceros, nuevo)

  useEffect(() => { setPiezas([]) }, [dueno?.id])

  function cuerpo(confirmar: boolean) {
    if (!dueno || !destino) throw new Error('Elige el dueño actual y el nuevo dueño de la lista.')
    if (piezas.length === 0) throw new Error('Agrega al menos una pieza.')
    return {
      numero, fecha: dia, propietario_actual_id: dueno.id, propietario_nuevo_id: destino.id,
      piezas: piezas.map((p) => p.id), observacion: observacion.trim() || null, confirmar,
      clave_idempotencia: confirmar ? clave : null,
    }
  }

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenSalida>('/api/salidas/liberacion', { metodo: 'POST', cuerpo: cuerpo(false) })
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
    try {
      const r = await pedir<ResumenSalida>('/api/salidas/liberacion', { metodo: 'POST', cuerpo: cuerpo(true) })
      setHecho({ texto: `Liberación ${r.numero} registrada: ${r.lineas.length} piezas pasan a ${r.tercero_nuevo}.`, id: r.documento_id })
      setResumen(null)
      setPiezas([])
      setNumero('')
      setObservacion('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <>
      {hecho && <Exito {...hecho} onVer={onVer} />}
      <form className="tarjeta bloque" onSubmit={revisar}>
        <p className="tenue pequeno sin-margen">La liberación traspasa piezas completas: todo su saldo pasa al nuevo dueño y nada sale del patio.</p>
        <div className="formulario cuatro-columnas sin-relleno">
          <label>Número<input value={numero} onChange={(e) => setNumero(e.target.value)} required /></label>
          <label>Fecha<input type="date" value={dia} onChange={(e) => setDia(e.target.value)} required /></label>
          <label>Dueño actual<input list="lista-terceros-salidas" value={actual} onChange={(e) => setActual(e.target.value)} required /></label>
          <label>Nuevo dueño<input list="lista-terceros-salidas" value={nuevo} onChange={(e) => setNuevo(e.target.value)} required /></label>
        </div>
        <BuscadorPiezas propietarioId={dueno?.id ?? null} excluir={piezas.map((p) => p.id)}
          deshabilitado={dueno ? null : 'Primero elige el dueño actual.'} onElegir={(p) => setPiezas([...piezas, p])} />
        {piezas.length > 0 && (
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Pieza</th><th className="n">Saldo que pasa</th><th></th></tr></thead>
              <tbody>
                {piezas.map((p) => (
                  <tr key={p.id}>
                    <td><div className="codigo">{p.codigo_fisico}</div><div className="tenue pequeno">{p.descripcion}</div></td>
                    <td className="n">{kg(p.saldo_kg)}</td>
                    <td><button type="button" className="enlace" onClick={() => setPiezas(piezas.filter((x) => x.id !== p.id))}>Quitar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <label>Observación<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <div className="acciones"><button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar liberación'}</button></div>
      </form>
      {resumen && <ConfirmarSalida r={resumen} ocupado={ocupado} onConfirmar={() => void confirmar()} onCerrar={() => setResumen(null)} />}
    </>
  )
}

/** Lista de documentos. Con `tipoFijo` muestra solo ese tipo (las entradas de material en la pestaña Entradas). */
export function Documentos({ usuario, abrir = null, onAbierto = () => {}, tipoFijo, tipoInicial, opcionesTipo }: {
  usuario: Usuario; abrir?: number | null; onAbierto?: () => void; tipoFijo?: string; tipoInicial?: string
  /** Lista corta de tipos para elegir (Entradas: entradas o ajustes), en lugar de la lista completa de Salidas */
  opcionesTipo?: { valor: string; nombre: string }[]
}) {
  const inicial = { tipo: tipoFijo ?? tipoInicial ?? '', numero: '', desde: '', hasta: '', incluir_anulados: true, tercero_id: '' }
  const [filtros, setFiltros] = useState(inicial)
  // Filtro por cliente (solo el personal: un cliente ya ve únicamente lo suyo)
  const esPersonal = usuario.rol !== 'cliente'
  const [clientes, setClientes] = useState<Tercero[]>([])
  useEffect(() => {
    if (esPersonal) pedir<Tercero[]>('/api/terceros?rol=cliente').then((t) => setClientes(t.filter((x) => x.activo))).catch(() => {})
  }, [esPersonal])
  // las cotizaciones tienen su propia lista (montos en USD); se buscan con los mismos filtros
  const [filtrosCot, setFiltrosCot] = useState(inicial)
  const [versionCot, setVersionCot] = useState(0)
  const esCotizacion = filtros.tipo === 'cotizacion'
  const [lista, setLista] = useState<Documento[]>([])
  const [error, setError] = useState<string | null>(null)
  const [seleccion, setSeleccion] = useState<number | null>(null)

  const cargar = useCallback(async (f: typeof filtros) => {
    setError(null)
    if (f.tipo === 'cotizacion') { setFiltrosCot(f); setVersionCot((v) => v + 1); return }
    try {
      setLista(await pedir<Documento[]>(`/api/documentos${consulta({ ...f, tercero_id: f.tercero_id || null, limite: 300 })}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar')
    }
  }, [])

  useEffect(() => { void cargar({ tipo: tipoFijo ?? tipoInicial ?? '', numero: '', desde: '', hasta: '', incluir_anulados: true, tercero_id: '' }) }, [cargar, tipoFijo, tipoInicial])
  useEffect(() => { if (abrir) { setSeleccion(abrir); onAbierto() } }, [abrir, onAbierto])

  return (
    <>
      <form className="filtros tarjeta" onSubmit={(e) => { e.preventDefault(); void cargar(filtros) }}>
        {opcionesTipo && (
          <label>Tipo
            <select value={filtros.tipo} onChange={(e) => { const f = { ...filtros, tipo: e.target.value }; setFiltros(f); void cargar(f) }}>
              {opcionesTipo.map((o) => <option key={o.valor} value={o.valor}>{o.nombre}</option>)}
            </select>
          </label>
        )}
        {!tipoFijo && !opcionesTipo && (
          <label>Tipo
            <select value={filtros.tipo} onChange={(e) => { const f = { ...filtros, tipo: e.target.value }; setFiltros(f); void cargar(f) }}>
              <option value="">Todos</option><option value="nota_entrega">Notas de entrega</option><option value="nota_salida">Notas de salida</option>
              <option value="liberacion">Liberaciones</option><option value="ajuste">Ajustes</option>
              <option value="cotizacion">Cotizaciones</option>
            </select>
          </label>
        )}
        {esPersonal && (
          <label>Cliente
            <select value={filtros.tercero_id} onChange={(e) => { const f = { ...filtros, tercero_id: e.target.value }; setFiltros(f); void cargar(f) }}>
              <option value="">Todos</option>
              {clientes.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
            </select>
          </label>
        )}
        <label className="corto">{(tipoFijo ?? filtros.tipo) === 'entrada' ? 'Documento del cliente' : 'Número'}<input value={filtros.numero} onChange={(e) => setFiltros({ ...filtros, numero: e.target.value })} /></label>
        <label>Desde<input type="date" value={filtros.desde} onChange={(e) => setFiltros({ ...filtros, desde: e.target.value })} /></label>
        <label>Hasta<input type="date" value={filtros.hasta} onChange={(e) => setFiltros({ ...filtros, hasta: e.target.value })} /></label>
        <label className="casilla">
          <input type="checkbox" checked={filtros.incluir_anulados}
            onChange={(e) => { const f = { ...filtros, incluir_anulados: e.target.checked }; setFiltros(f); void cargar(f) }} />
          Mostrar anuladas
        </label>
        <div className="acciones-filtro"><button className="primario">Buscar</button></div>
      </form>
      {error && <p className="error">{error}</p>}
      {esCotizacion && <ListaCotizaciones usuario={usuario} filtros={filtrosCot} version={versionCot} />}
      {!esCotizacion && lista.length === 0 && !error && <p className="vacio">No hay documentos con esos filtros.</p>}
      {!esCotizacion && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead><tr><th>Fecha</th><th>Tipo</th><th>Número</th><th>Dueño / cliente</th><th className="n">Piezas</th><th className="n">kg</th></tr></thead>
            <tbody>
              {lista.map((d) => (
                <tr key={d.id} className={d.anulado ? 'anulado' : undefined} onClick={() => setSeleccion(d.id)} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') setSeleccion(d.id) }}>
                  <td>{fecha(d.fecha)}</td>
                  <td>{NOMBRE_DOCUMENTO[d.tipo] ?? d.tipo}</td>
                  <td className="fuerte">{d.numero ?? '—'}{d.origen === 'excel' && <span className="tenue pequeno"> · Excel</span>}
                    {d.anulado && <span className="etiqueta-anulada">ANULADA</span>}</td>
                  <td>{d.tercero ?? '—'}{d.tercero_nuevo ? ` → ${d.tercero_nuevo}` : ''}</td>
                  <td className="n">{d.piezas}</td>
                  <td className="n">{kg(d.total_kg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {seleccion !== null && <DetalleDocumentoModal id={seleccion} usuario={usuario} onCerrar={() => setSeleccion(null)} onCambio={() => void cargar(filtros)} />}
    </>
  )
}

/** NE histórica (Excel o libro de Slitter): descarga del inventario el material que salió con ella y en su
 *  momento se descargó a mano. Viene precargado con las piezas de la NE que se encuentran en el inventario
 *  del cliente; la salida queda con la fecha de la NE y enlazada a ella. Solo socio. */
function DescargaHistorica({ d, onHecho, onCancelar }: { d: DetalleDocumento; onHecho: () => void; onCancelar: () => void }) {
  const doc = d.documento
  const [lineas, setLineas] = useState<LineaNota[]>([])
  const [buscando, setBuscando] = useState(true)
  const [resumen, setResumen] = useState<ResumenSalida | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    let vivo = true
    const yaDescargadas = new Set((d.descargas ?? []).map((x) => x.pieza_id))
    async function precargar() {
      const halladas: LineaNota[] = []
      for (const l of d.lineas) {
        if (!l.codigo || l.codigo === '—' || !doc.tercero_id) continue
        try {
          const r = await pedir<Existencias>(`/api/existencias${consulta({ codigo: l.codigo, propietario_id: doc.tercero_id, limite: 20 })}`)
          const p = r.piezas.find((x) => (x.codigo_fisico === l.codigo || x.codigo_producto === l.codigo) && !yaDescargadas.has(x.id))
          if (!p || halladas.some((h) => h.pieza.id === p.id)) continue
          const kgLinea = Math.abs(Number(l.kg))
          const valor = enPiezas(p)
            ? (l.cantidad ? String(Math.round(Number(l.cantidad))) : '')
            : (kgLinea && kgLinea < Number(p.saldo_kg) ? String(kgLinea) : '')
          halladas.push({ pieza: p, kg: valor })
        } catch { /* sin coincidencia: se agrega a mano */ }
      }
      if (vivo) { setLineas(halladas); setBuscando(false) }
    }
    void precargar()
    return () => { vivo = false }
  }, [d, doc.tercero_id])

  function cuerpo(confirmar: boolean) {
    if (lineas.length === 0) throw new Error('Agrega al menos una pieza.')
    return {
      confirmar,
      lineas: lineas.map((l) => {
        const v = l.kg.trim().replace(',', '.')
        if (enPiezas(l.pieza)) {
          if (v && !/^\d+$/.test(v)) throw new Error(`${l.pieza.codigo_fisico}: las piezas van en números enteros.`)
          return { pieza_id: l.pieza.id, unidades: v ? Number(v) : null }
        }
        return { pieza_id: l.pieza.id, kg: v || null }
      }),
    }
  }

  async function llamar(confirmar: boolean) {
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenSalida>(`/api/documentos/${doc.id}/descargar`, { metodo: 'POST', cuerpo: cuerpo(confirmar) })
      if (confirmar) onHecho()
      else setResumen(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="confirmacion no-impresion">
      <h3>Descargar del inventario</h3>
      {resumen ? (
        <>
          <p>Sale con la NE <strong>{resumen.numero}</strong> del {fecha(resumen.fecha)} · <strong>{kg(resumen.total_kg)}</strong></p>
          {resumen.avisos.length > 0 && <div className="alerta"><ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>}
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Pieza</th><th className="n">Saldo</th><th className="n">Sale</th><th className="n">Queda</th></tr></thead>
              <tbody>
                {resumen.lineas.map((l) => (
                  <tr key={l.pieza_id}>
                    <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                    <td className="n">{cantidad(l.saldo_antes_unidades, l.saldo_antes_kg)}</td>
                    <td className="n fuerte">{cantidad(l.unidades, l.kg)}</td>
                    <td className="n">{cantidad(l.saldo_despues_unidades, l.saldo_despues_kg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void llamar(true)}>{ocupado ? 'Guardando…' : 'Confirmar la descarga'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </>
      ) : (
        <>
          <p className="tenue pequeno">Para material que salió con esta NE y en su momento se descargó a mano. La salida queda con la
            fecha de la NE y enlazada a ella (no gasta un número de NE). {buscando ? 'Buscando las piezas de la NE en el inventario…' : ''}</p>
          <BuscadorPiezas propietarioId={doc.tercero_id ?? null} excluir={lineas.map((l) => l.pieza.id)}
            deshabilitado={doc.tercero_id ? null : 'La NE no tiene cliente.'}
            onElegir={(p) => setLineas([...lineas, { pieza: p, kg: '' }])} />
          {lineas.length > 0 && (
            <div className="tabla-envoltura">
              <table className="tabla compacta cortes">
                <thead><tr><th>Pieza</th><th className="n">Saldo</th><th>Sale (kg o piezas)</th><th></th></tr></thead>
                <tbody>
                  {lineas.map((l, i) => (
                    <tr key={l.pieza.id}>
                      <td><div className="codigo">{l.pieza.codigo_fisico}</div><div className="tenue pequeno">{l.pieza.descripcion}</div></td>
                      <td className="n">{cantidad(l.pieza.saldo_unidades, l.pieza.saldo_kg)}</td>
                      <td><input inputMode={enPiezas(l.pieza) ? 'numeric' : 'decimal'} value={l.kg}
                        aria-label={enPiezas(l.pieza) ? 'Piezas que salen' : 'kg que salen'}
                        placeholder={enPiezas(l.pieza) ? `piezas (todas: ${l.pieza.saldo_unidades})` : 'kg (toda la pieza)'}
                        onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, kg: e.target.value } : x)))} /></td>
                      <td><button type="button" className="enlace" onClick={() => setLineas(lineas.filter((_, j) => j !== i))}>Quitar</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado || buscando} onClick={() => void llamar(false)}>{ocupado ? 'Revisando…' : 'Revisar descarga'}</button>
            <button className="secundario" onClick={onCancelar}>Cancelar</button>
          </div>
        </>
      )}
    </div>
  )
}

function DetalleDocumentoModal({ id, usuario, onCerrar, onCambio }: { id: number; usuario: Usuario; onCerrar: () => void; onCambio: () => void }) {
  const [d, setD] = useState<DetalleDocumento | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [anulando, setAnulando] = useState(false)
  const [descargando, setDescargando] = useState(false)
  const [descargado, setDescargado] = useState(false)
  const [corrigiendo, setCorrigiendo] = useState(false)
  const [editandoHoja, setEditandoHoja] = useState<EncabezadoNE | null>(null)
  const [reciboAbajo, setReciboAbajo] = useState(false)
  const [motivo, setMotivo] = useState('')

  useEffect(() => { pedir<DetalleDocumento>(`/api/documentos/${id}`).then(setD).catch((e: Error) => setError(e.message)) }, [id])

  async function guardarHoja() {
    if (!editandoHoja) return
    setError(null)
    try {
      await pedir<Documento>(`/api/documentos/${id}/encabezado`, { metodo: 'PUT', cuerpo: encabezadoLimpio(editandoHoja) ?? {} })
      setEditandoHoja(null)
      setD(await pedir<DetalleDocumento>(`/api/documentos/${id}`))
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron guardar los datos')
    }
  }

  async function anular() {
    setError(null)
    try {
      await pedir<Documento>(`/api/documentos/${id}`, { metodo: 'DELETE', cuerpo: { motivo } })
      onCambio()
      onCerrar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo anular')
    }
  }

  const doc = d?.documento
  const nombre = doc ? NOMBRE_DOCUMENTO[doc.tipo] ?? doc.tipo : 'Documento'
  return (
    <Modal titulo={doc ? `${nombre} ${doc.numero ?? ''}` : nombre} onCerrar={onCerrar} ancho>
      {error && <p className="error">{error}</p>}
      {!d && !error && <p className="tenue">Cargando…</p>}
      {d && doc && (
        <div className="imprimible">
          <div className="solo-impresion encabezado-impresion"><strong>Prosifer · {nombre} N.º {doc.numero}</strong></div>
          {doc.anulado && <p className="error">Documento anulado</p>}
          {d.historico && doc.tipo === 'entrada' && <p className="alerta">Entrada histórica del Excel: solo consulta. Su material
            ya está en el inventario importado; no se registra de nuevo.</p>}
          {d.historico && doc.tipo !== 'entrada' && <p className="alerta">Histórico del Excel: solo consulta. No movió inventario y no se corrige
            {usuario.rol === 'socio' ? '; si su material sigue en el inventario, usa «Descargar del inventario».' : '.'}</p>}
          {descargado && <div className="exito">Material descargado del inventario con esta NE.</div>}
          <dl className="datos">
            <dt>Fecha</dt><dd>{fecha(doc.fecha)}</dd>
            <dt>{doc.tipo === 'liberacion' ? 'De' : 'Cliente'}</dt><dd>{doc.tercero ?? '—'}</dd>
            {doc.tercero_nuevo && <><dt>A</dt><dd>{doc.tercero_nuevo}</dd></>}
            {doc.creado_por && <><dt>Registró</dt><dd>{doc.creado_por} ({doc.origen})</dd></>}
            {doc.observacion && <><dt>Observación</dt><dd>{doc.observacion}</dd></>}
            {CAMPOS_NE.filter((c) => doc.encabezado?.[c.clave]).map((c) => (
              <span key={c.clave} style={{ display: 'contents' }}><dt>{c.titulo}</dt><dd>{doc.encabezado?.[c.clave]}</dd></span>
            ))}
            {doc.encabezado?.notas && <><dt>Notas importantes</dt><dd>{doc.encabezado.notas}</dd></>}
          </dl>
          <table className="tabla compacta">
            <thead><tr><th>Pieza</th><th className="n">Cantidad</th></tr></thead>
            <tbody>
              {d.lineas.map((l, i) => (
                <tr key={l.movimiento_id ?? `h${i}`}>
                  <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                  <td className="n">{d.historico
                    ? `${l.cantidad === null || l.cantidad === undefined ? '—' : Number(l.cantidad).toLocaleString('es-VE')} ${l.unidad ?? ''} · ${kg(Math.abs(Number(l.kg)))}`
                    : cantidad(l.unidades, l.kg)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="pie-tabla">Total: <strong>{kg(doc.total_kg)}</strong></p>
          {(d.correcciones ?? []).length > 0 && (
            <div className="no-impresion">
              <h3>Correcciones</h3>
              <ul className="pequeno">
                {(d.correcciones ?? []).map((c) => (
                  <li key={c.id}>{fecha(c.fecha)} · {c.creado_por}: {c.observacion}{c.anulado ? ' (anulada con la NE)' : ''}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="acciones no-impresion">
            {doc.tipo === 'nota_entrega' && (
              <>
                <button className="primario" onClick={() => imprimirNE(doc.id, doc.numero, doc.tercero, setError)}>Ver NE (PDF)</button>
                <button className="primario" onClick={() => guardarNE(doc.id, doc.numero, doc.tercero, setError)}>Guardar NE en carpeta</button>
              </>
            )}
            {doc.tipo === 'nota_salida' && (
              <>
                <button className="primario" onClick={() => { pdfNotaSalida(doc.id, doc.numero, doc.tercero).catch((e: Error) => setError(e.message)) }}>Ver nota de salida (PDF)</button>
                <button className="primario" onClick={() => { pdfNotaSalida(doc.id, doc.numero, doc.tercero, true).catch((e: Error) => setError(e.message)) }}>Guardar en carpeta</button>
              </>
            )}
            {doc.tipo === 'entrada' && !d.historico && (
              <>
                <button className="primario" onClick={() => { reciboEntrada(doc.id, doc.tercero, false, reciboAbajo).catch((e: Error) => setError(e.message)) }}>Recibo de entrada (PDF)</button>
                <button className="primario" onClick={() => { reciboEntrada(doc.id, doc.tercero, true, reciboAbajo).catch((e: Error) => setError(e.message)) }}>Guardar recibo en carpeta</button>
                <label className="pequeno" title="Para imprimir en la otra mitad de una hoja ya usada">
                  <input type="checkbox" checked={reciboAbajo} onChange={(e) => setReciboAbajo(e.target.checked)} /> en la mitad de abajo
                </label>
              </>
            )}
            <button className="secundario" onClick={() => window.print()}>Imprimir resumen</button>
            {doc.tipo === 'nota_entrega' && !d.historico && !doc.anulado && usuario.rol !== 'cliente' && !editandoHoja && !corrigiendo && !anulando && (
              <button className="secundario" onClick={() => setEditandoHoja({ ...(doc.encabezado ?? {}) })}>Chofer, placa y datos de la hoja</button>
            )}
            {d.corregible && usuario.rol !== 'cliente' && !corrigiendo && !anulando && (
              <button className="secundario" onClick={() => setCorrigiendo(true)}>Corregir NE</button>
            )}
            {usuario.rol === 'socio' && doc.tipo === 'nota_entrega' && d.historico && !doc.anulado && !descargando && (
              <button className="secundario" onClick={() => { setDescargado(false); setDescargando(true) }}>Descargar del inventario</button>
            )}
            {usuario.rol === 'socio' && !doc.anulado && !d.historico && !anulando && !corrigiendo && (
              <button className="peligro" onClick={() => setAnulando(true)}>Anular</button>
            )}
          </div>
          {editandoHoja && (
            <div className="confirmacion no-impresion">
              <CamposEncabezado valor={editandoHoja} onCambio={setEditandoHoja} ficha={null} />
              <div className="acciones">
                <button className="primario" onClick={() => void guardarHoja()}>Guardar datos de la hoja</button>
                <button className="secundario" onClick={() => setEditandoHoja(null)}>Cancelar</button>
              </div>
            </div>
          )}
          {descargando && (
            <DescargaHistorica d={d} onCancelar={() => setDescargando(false)}
              onHecho={() => {
                setDescargando(false); setDescargado(true); onCambio()
                pedir<DetalleDocumento>(`/api/documentos/${id}`).then(setD).catch(() => {})
              }} />
          )}
          {(d.descargas ?? []).length > 0 && (
            <div>
              <h3>Descargado del inventario con esta NE</h3>
              <table className="tabla compacta">
                <thead><tr><th>Pieza</th><th className="n">Salió</th><th className="n">Quedó</th></tr></thead>
                <tbody>
                  {(d.descargas ?? []).map((x) => (
                    <tr key={x.movimiento_id ?? x.codigo}>
                      <td><div className="codigo">{x.codigo}</div><div className="tenue pequeno">{x.descripcion}</div></td>
                      <td className="n">{cantidad(x.unidades, x.kg)}</td>
                      <td className="n">{cantidad(x.saldo_despues_unidades, x.saldo_despues_kg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {corrigiendo && (
            <CorregirNE detalle={d} onCancelar={() => setCorrigiendo(false)}
              onHecho={() => { setCorrigiendo(false); onCambio(); pedir<DetalleDocumento>(`/api/documentos/${id}`).then(setD).catch(() => {}) }} />
          )}
          {anulando && (
            <div className="confirmacion peligro-caja no-impresion">
              <label>Motivo de la anulación (las piezas recuperan sus kg o su dueño anterior)
                <textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              </label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void anular()}>Anular definitivamente</button>
                <button className="secundario" onClick={() => setAnulando(false)}>Cancelar</button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

interface CambioLinea { cantidad: string; nueva: Pieza | null; buscando: boolean }

/** Corrige cantidades o productos de una NE de la app. La NE conserva su número; lo que salió mal se
 *  devuelve al inventario y sale lo correcto, todo con motivo y quién lo hizo. */
function CorregirNE({ detalle, onCancelar, onHecho }: { detalle: DetalleDocumento; onCancelar: () => void; onHecho: () => void }) {
  const doc = detalle.documento
  const [cambios, setCambios] = useState<Record<number, CambioLinea>>({})
  const [motivo, setMotivo] = useState('')
  const [resumen, setResumen] = useState<ResumenCorreccionNE | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cambio = (id: number): CambioLinea => cambios[id] ?? { cantidad: '', nueva: null, buscando: false }
  const poner = (id: number, c: Partial<CambioLinea>) => setCambios({ ...cambios, [id]: { ...cambio(id), ...c } })

  function cuerpo(confirmar: boolean) {
    const lista = detalle.lineas.filter((l) => l.movimiento_id !== null).flatMap((l) => {
      const c = cambio(l.movimiento_id as number)
      const v = c.cantidad.trim().replace(',', '.')
      if (!v && !c.nueva) return []
      const enPiezasDestino = c.nueva ? c.nueva.saldo_unidades !== null && c.nueva.saldo_unidades !== undefined
        : l.unidades !== null && l.unidades !== undefined
      if (v && enPiezasDestino && !/^\d+$/.test(v)) throw new Error(`${l.codigo}: las piezas van en números enteros.`)
      return [{ movimiento_id: l.movimiento_id, pieza_id: c.nueva?.id ?? null,
        unidades: v && enPiezasDestino ? Number(v) : null, kg: v && !enPiezasDestino ? v : null }]
    })
    if (lista.length === 0) throw new Error('Indica la cantidad correcta o el producto correcto en al menos una línea.')
    return { cambios: lista, motivo: motivo.trim(), confirmar, clave_idempotencia: confirmar ? clave : null }
  }

  async function revisar() {
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenCorreccionNE>(`/api/documentos/${doc.id}/correccion`, { metodo: 'POST', cuerpo: cuerpo(false) })
      setClave(crypto.randomUUID())
      setResumen(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo revisar')
    } finally {
      setOcupado(false)
    }
  }

  async function confirmar() {
    setOcupado(true)
    setError(null)
    try {
      await pedir<ResumenCorreccionNE>(`/api/documentos/${doc.id}/correccion`, { metodo: 'POST', cuerpo: cuerpo(true) })
      onHecho()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="confirmacion no-impresion">
      <p className="pequeno sin-margen">
        Escribe solo lo que cambia: la cantidad que salió de verdad o el producto correcto (del mismo cliente).
        La NE {doc.numero} conserva su número.
      </p>
      <table className="tabla compacta">
        <thead><tr><th>Línea actual</th><th className="n">Salió</th><th>Cantidad correcta</th><th>Producto correcto</th></tr></thead>
        <tbody>
          {detalle.lineas.filter((l) => l.movimiento_id !== null).map((l) => {
            const id = l.movimiento_id as number
            const c = cambio(id)
            const enPiezas = c.nueva ? c.nueva.saldo_unidades !== null && c.nueva.saldo_unidades !== undefined
              : l.unidades !== null && l.unidades !== undefined
            return (
              <tr key={id}>
                <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                <td className="n">{cantidad(l.unidades, l.kg)}</td>
                <td><input inputMode={enPiezas ? 'numeric' : 'decimal'} value={c.cantidad} placeholder={enPiezas ? 'piezas' : 'kg'}
                  aria-label={`Cantidad correcta de ${l.codigo}`} onChange={(e) => poner(id, { cantidad: e.target.value })} /></td>
                <td>
                  {c.nueva ? (
                    <span><span className="codigo">{c.nueva.codigo_fisico}</span>{' '}
                      <button type="button" className="enlace" onClick={() => poner(id, { nueva: null })}>quitar</button></span>
                  ) : c.buscando ? (
                    <BuscadorPiezas propietarioId={doc.tercero_id ?? null} excluir={[]} autoFocus
                      deshabilitado={doc.tercero_id ? null : 'La NE no tiene cliente.'}
                      onElegir={(p) => poner(id, { nueva: p, buscando: false })} placeholder="Producto correcto · F4" />
                  ) : (
                    <button type="button" className="enlace" onClick={() => poner(id, { buscando: true })}>Cambiar producto</button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <label>Motivo de la corrección (queda registrado)<textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></label>
      {error && <p className="error">{error}</p>}
      {resumen && (
        <div className="alerta">
          <strong>Así queda la NE {resumen.numero}:</strong>
          <ul>
            {resumen.lineas.map((x, i) => (
              <li key={i}>
                {x.antes_codigo} · {cantidad(x.antes_unidades, x.antes_kg)} → <strong>{x.despues_codigo} · {cantidad(x.despues_unidades, x.despues_kg)}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="acciones">
        {!resumen && <button className="primario" disabled={motivo.trim().length < 5 || ocupado} onClick={() => void revisar()}>{ocupado ? 'Revisando…' : 'Revisar corrección'}</button>}
        {resumen && <button className="primario" disabled={ocupado} onClick={() => void confirmar()}>{ocupado ? 'Guardando…' : 'Confirmar corrección'}</button>}
        {resumen && <button className="secundario" onClick={() => setResumen(null)}>Volver a editar</button>}
        <button className="secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </div>
  )
}

/** Primer y último día del mes (AAAA-MM). */
function limitesMes(mes: string): { desde: string; hasta: string } {
  const [a, m] = mes.split('-').map(Number)
  const ultimo = new Date(a, m, 0).getDate()
  return { desde: `${mes}-01`, hasta: `${mes}-${String(ultimo).padStart(2, '0')}` }
}

// Categorías del reporte: bobinas y flejes fuera por omisión (ya pagaron su servicio o tienen su propio
// servicio de carga y descarga). Las láminas sí cuentan: HYMS las retira por partes a lo largo del mes.
const CATEGORIAS_REPORTE: [string, string][] = [['bobina', 'Bobinas'], ['fleje', 'Flejes'], ['lamina', 'Láminas'],
  ['perfil', 'Perfiles'], ['general', 'Productos generales'], ['irregular', 'Medidas irregulares']]

/** Reporte "Servicios de Descarga-Carga": salidas del cliente en el mes (o el período que se elija), con la
 *  masa despachada, en PDF y con el atajo para cotizar el servicio de descarga, almacén y carga. */
function ReporteMensual({ terceros, onVer }: { terceros: Tercero[]; onVer: (id: number) => void }) {
  const clientes = terceros.filter((t) => t.es_cliente)
  const hoy = hoyIso()
  const [clienteId, setClienteId] = useState('')
  const [mes, setMes] = useState(hoy.slice(0, 7))
  const [periodo, setPeriodo] = useState(limitesMes(hoy.slice(0, 7)))
  const [rep, setRep] = useState<ReporteSalidas | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(false)
  const [cotizar, setCotizar] = useState(false)
  const [excluir, setExcluir] = useState<string[]>(['bobina', 'fleje'])
  const params = () => consulta({ tercero_id: clienteId, desde: periodo.desde, hasta: periodo.hasta, excluir: excluir.join(',') })

  const ver = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!clienteId) { setError('Elige el cliente'); return }
    setError(null); setCargando(true)
    try { setRep(await pedir<ReporteSalidas>(`/api/reportes/salidas${params()}`)) } catch (x) { setError((x as Error).message); setRep(null) }
    setCargando(false)
  }
  const nombre = () => nombreArchivo('Reporte Descarga-Carga', rep?.tercero, periodo.desde, 'al', periodo.hasta)

  return (
    <div className="panel">
      <p className="tenue">Salidas del cliente en el período (notas de entrega no anuladas, renglón por renglón) con la masa
        despachada: la base del cobro de descarga, almacén y carga.</p>
      <form className="filtros" onSubmit={ver}>
        <label>Cliente
          <select value={clienteId} onChange={(e) => { setClienteId(e.target.value); setRep(null) }}>
            <option value="">— elige —</option>
            {clientes.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}
          </select>
        </label>
        <label>Mes
          <input type="month" value={mes} onChange={(e) => { setMes(e.target.value); if (e.target.value) setPeriodo(limitesMes(e.target.value)); setRep(null) }} />
        </label>
        <label>Desde<input type="date" value={periodo.desde} onChange={(e) => { setPeriodo({ ...periodo, desde: e.target.value }); setRep(null) }} /></label>
        <label>Hasta<input type="date" value={periodo.hasta} onChange={(e) => { setPeriodo({ ...periodo, hasta: e.target.value }); setRep(null) }} /></label>
        <button className="primario" disabled={cargando}>{cargando ? 'Consultando…' : 'Ver reporte'}</button>
      </form>
      <fieldset className="filtros">
        <legend>No incluir</legend>
        {CATEGORIAS_REPORTE.map(([c, nombre]) => (
          <label key={c} className="pequeno">
            <input type="checkbox" checked={excluir.includes(c)}
              onChange={(e) => { setExcluir(e.target.checked ? [...excluir, c] : excluir.filter((x) => x !== c)); setRep(null) }} /> {nombre}
          </label>
        ))}
      </fieldset>
      {error && <p className="error">{error}</p>}
      {rep && (
        <>
          <div className="acciones">
            <button className="primario" onClick={() => { abrirPdf(`/api/reportes/salidas/pdf${params()}`, nombre()).catch((x: Error) => setError(x.message)) }}>Ver PDF</button>
            <button className="secundario" onClick={() => { guardarPdf(`/api/reportes/salidas/pdf${params()}`, nombre()).catch((x: Error) => setError(x.message)) }}>Guardar PDF en carpeta</button>
            <button className="primario" disabled={!rep.filas.length} onClick={() => setCotizar(true)}>Cotizar este reporte</button>
          </div>
          <p><strong>{rep.notas_entrega}</strong> notas de entrega · masa total despachada <strong>{kg(rep.total_kg)}</strong></p>
          {rep.excluidas.length > 0 && <p className="tenue pequeno">No incluye: {rep.excluidas.map((e) => `${e.nombre.toLowerCase()} (${e.renglones} renglones, ${kg(e.kg)})`).join('; ')}.</p>}
          <table className="tabla compacta">
            <thead><tr><th>Nota de salida</th><th>Fecha</th><th>NE</th><th className="n">Cantidad</th><th>Descripción</th><th className="n">Masa</th></tr></thead>
            <tbody>
              {rep.filas.map((f, i) => (
                <tr key={`${f.documento_id}-${i}`}>
                  <td>{f.nota_salida ?? '—'}</td><td>{fecha(f.fecha)}</td>
                  <td><button className="enlace" onClick={() => onVer(f.documento_id)}>{f.nota_entrega}</button></td>
                  <td className="n">{f.cantidad === null ? '—' : Number(f.cantidad).toLocaleString('es-VE')}</td>
                  <td>{f.descripcion}</td><td className="n">{kg(f.kg)}</td>
                </tr>
              ))}
              {!rep.filas.length && <tr><td colSpan={6} className="tenue">Sin salidas en el período.</td></tr>}
            </tbody>
          </table>
        </>
      )}
      {cotizar && rep && (
        <CotizarDesde url={`/api/reportes/salidas/cotizar${params()}`} onCerrar={() => setCotizar(false)} />
      )}
    </div>
  )
}

