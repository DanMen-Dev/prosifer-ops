import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  consulta, ESTADO_DESPACHO, MATERIAL_IRREGULAR, pdfDespacho, pdfNotaSalida, pedir, type EstadoDespacho, type OrdenDespacho, type Pieza,
  type ResumenSalida, type RetiroDespacho, type Tercero, type Usuario,
} from '../api'
import { fecha, hoyIso, kg } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import Modal from './Modal'

/* Orden de despacho del cliente: el cliente (o el personal en su nombre) pide retirar material de su
   inventario; queda pendiente con el material reservado y el patio la despacha con una nota de salida. */

const enPiezas = (p: Pieza) => p.saldo_unidades !== null && p.saldo_unidades !== undefined

function cantidad(unidades: number | null | undefined, kilos: string | number): string {
  return unidades === null || unidades === undefined
    ? kg(kilos) : `${Math.abs(unidades).toLocaleString('es-VE')} pzas · ${kg(Math.abs(Number(kilos)))}`
}

function Estado({ estado }: { estado: EstadoDespacho }) {
  return <span className={`estado-despacho ${estado}`}>{ESTADO_DESPACHO[estado]}</span>
}

const CAMPOS_RETIRO: { clave: keyof RetiroDespacho; titulo: string; tipo?: string }[] = [
  { clave: 'fecha_retiro', titulo: 'Fecha de retiro', tipo: 'date' },
  { clave: 'retira', titulo: 'Chofer o persona que retira' },
  { clave: 'cedula', titulo: 'Cédula' },
  { clave: 'placa', titulo: 'Placa' },
  { clave: 'transporte', titulo: 'Transporte (empresa)' },
  { clave: 'telefono', titulo: 'Teléfono' },
]

function CamposRetiro({ valor, onCambio, titulo }: { valor: RetiroDespacho; onCambio: (v: RetiroDespacho) => void; titulo: string }) {
  return (
    <fieldset className="grupo-campos">
      <legend>{titulo}</legend>
      <div className="formulario tres-columnas sin-relleno">
        {CAMPOS_RETIRO.map((c) => (
          <label key={c.clave}>{c.titulo}
            <input type={c.tipo ?? 'text'} value={valor[c.clave] ?? ''}
              onChange={(e) => onCambio({ ...valor, [c.clave]: e.target.value })} />
          </label>
        ))}
      </div>
    </fieldset>
  )
}

const retiroLimpio = (v: RetiroDespacho): RetiroDespacho | null => {
  const d = Object.fromEntries(Object.entries(v).filter(([, x]) => typeof x === 'string' && x.trim()))
  return Object.keys(d).length ? d : null
}

function DatosRetiro({ r }: { r: RetiroDespacho | null }) {
  if (!r || !Object.keys(r).length) return <p className="tenue pequeno">Sin datos de retiro.</p>
  return (
    <dl className="datos-retiro">
      {CAMPOS_RETIRO.filter((c) => r[c.clave]).map((c) => (
        <div key={c.clave}><dt>{c.titulo}</dt><dd>{c.clave === 'fecha_retiro' ? fecha(r[c.clave]) : r[c.clave]}</dd></div>
      ))}
    </dl>
  )
}

function TablaLineas({ o }: { o: OrdenDespacho }) {
  return (
    <div className="tabla-envoltura">
      <table className="tabla compacta">
        <thead><tr><th>Pieza</th><th className="n">Sale</th></tr></thead>
        <tbody>
          {o.lineas.map((l) => (
            <tr key={l.pieza_id}>
              <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
              <td className="n fuerte">{cantidad(l.unidades, l.kg)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="pie-tabla">Total: <strong>{kg(o.total_kg)}</strong>
        {o.total_unidades ? <> · {o.total_unidades.toLocaleString('es-VE')} pzas</> : null}</p>
    </div>
  )
}

// --- Nueva orden ------------------------------------------------------------------

interface LineaForm { pieza: Pieza; valor: string }

export function NuevaOrdenDespacho({ usuario, terceros = [], onHecho, onCerrar }: {
  usuario: Usuario; terceros?: Tercero[]; onHecho: (o: OrdenDespacho) => void; onCerrar: () => void
}) {
  const esCliente = usuario.rol === 'cliente'
  const [dia, setDia] = useState(hoyIso())
  const [cliente, setCliente] = useState('')
  const [lineas, setLineas] = useState<LineaForm[]>([])
  const [retiro, setRetiro] = useState<RetiroDespacho>({})
  const [observacion, setObservacion] = useState('')
  const [resumen, setResumen] = useState<OrdenDespacho | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const elegido = esCliente ? null : terceros.find((t) => t.nombre.toLowerCase() === cliente.trim().toLowerCase()) ?? null
  const dueno = esCliente ? usuario.tercero_id : elegido?.id ?? null

  useEffect(() => { if (!esCliente) setLineas([]) }, [elegido?.id, esCliente])

  function cuerpo(confirmar: boolean) {
    if (!dueno) throw new Error('Elige el cliente de la lista.')
    if (lineas.length === 0) throw new Error('Agrega al menos un producto o bobina.')
    return {
      tercero_id: esCliente ? null : dueno, fecha: dia, retiro: retiroLimpio(retiro),
      observacion: observacion.trim() || null, confirmar, clave_idempotencia: confirmar ? clave : null,
      lineas: lineas.map((l) => {
        const v = l.valor.trim().replace(',', '.')
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
      setResumen(await pedir<OrdenDespacho>('/api/despachos', { metodo: 'POST', cuerpo: cuerpo(false) }))
      setClave(crypto.randomUUID())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo revisar')
    } finally {
      setOcupado(false)
    }
  }

  async function enviar() {
    setOcupado(true)
    setError(null)
    try {
      onHecho(await pedir<OrdenDespacho>('/api/despachos', { metodo: 'POST', cuerpo: cuerpo(true) }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo enviar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Modal titulo="Nueva orden de despacho" onCerrar={onCerrar} ancho>
      {resumen ? (
        <>
          <p>Cliente <strong>{resumen.tercero}</strong> · {fecha(resumen.fecha)} · {resumen.lineas.length} renglón
            {resumen.lineas.length === 1 ? '' : 'es'} · <strong>{kg(resumen.total_kg)}</strong></p>
          {resumen.avisos.length > 0 && <div className="alerta"><strong>Revisa antes de enviar:</strong>
            <ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>}
          <TablaLineas o={resumen} />
          <DatosRetiro r={resumen.retiro} />
          <p className="tenue pequeno">Al enviarla, el material queda reservado para este despacho hasta que el patio emita
            la nota de salida o anules la orden.</p>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void enviar()}>{ocupado ? 'Enviando…' : 'Enviar orden'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </>
      ) : (
        <form onSubmit={revisar}>
          <div className="formulario cuatro-columnas sin-relleno">
            <label>Número<input value="Se asigna al enviar" disabled /></label>
            <label>Fecha<input type="date" value={dia} onChange={(e) => setDia(e.target.value)} required /></label>
            {!esCliente && (
              <label className="doble">Cliente (dueño del material)
                <input list="lista-terceros-despacho" value={cliente} onChange={(e) => setCliente(e.target.value)}
                  placeholder="Escribe para buscar" required />
                <datalist id="lista-terceros-despacho">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
              </label>
            )}
          </div>
          <BuscadorPiezas propietarioId={dueno} excluir={lineas.map((l) => l.pieza.id)}
            deshabilitado={dueno ? null : 'Primero elige el cliente.'}
            placeholder="Busca en tu inventario por código o descripción"
            onElegir={(p) => setLineas([...lineas, { pieza: p, valor: '' }])} />
          {lineas.length > 0 && (
            <div className="tabla-envoltura">
              <table className="tabla compacta cortes">
                <thead><tr><th>Producto o bobina</th><th className="n">En patio</th><th>Retirar</th><th></th></tr></thead>
                <tbody>
                  {lineas.map((l, i) => (
                    <tr key={l.pieza.id}>
                      <td><div className="codigo">{l.pieza.codigo_fisico}</div><div className="tenue pequeno">{l.pieza.descripcion}</div></td>
                      <td className="n">{cantidad(l.pieza.saldo_unidades, l.pieza.saldo_kg)}</td>
                      <td><input inputMode={enPiezas(l.pieza) ? 'numeric' : 'decimal'} value={l.valor}
                        aria-label={enPiezas(l.pieza) ? 'Piezas a retirar' : 'kg a retirar'}
                        placeholder={enPiezas(l.pieza) ? `piezas (todas: ${l.pieza.saldo_unidades})` : 'kg (toda la pieza)'}
                        onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, valor: e.target.value } : x)))} /></td>
                      <td><button type="button" className="enlace" onClick={() => setLineas(lineas.filter((_, j) => j !== i))}>Quitar</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <CamposRetiro valor={retiro} onCambio={setRetiro} titulo="Quién y cuándo retira" />
          <label>Observación<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)}
            placeholder="Por ejemplo: retiran en la mañana; cargar primero las láminas" /></label>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar orden'}</button>
            <button type="button" className="secundario" onClick={onCerrar}>Cancelar</button>
          </div>
        </form>
      )}
    </Modal>
  )
}

// --- Nota de salida (patio) ---------------------------------------------------

function EmitirNotaSalida({ o, onHecho, onCancelar }: { o: OrdenDespacho; onHecho: (r: ResumenSalida) => void; onCancelar: () => void }) {
  const [dia, setDia] = useState(hoyIso())
  const [valores, setValores] = useState<Record<number, string>>(
    () => Object.fromEntries(o.lineas.map((l) => [l.pieza_id, String(l.unidades ?? l.kg)])))
  const [retiro, setRetiro] = useState<RetiroDespacho>({ ...(o.retiro ?? {}) })
  const [observacion, setObservacion] = useState('')
  const [irregulares, setIrregulares] = useState<{ kg: string; detalle: string }[]>([])
  const [resumen, setResumen] = useState<ResumenSalida | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  function cuerpo(confirmar: boolean) {
    const libres = irregulares.map((x) => {
      const v = x.kg.trim().replace(',', '.')
      if (!v || !(Number(v) > 0)) throw new Error(`${MATERIAL_IRREGULAR.nombre}: indica los kg que salen.`)
      return { codigo: MATERIAL_IRREGULAR.codigo, kg: v, detalle: x.detalle.trim() || null }
    })
    const lineas = o.lineas.filter((l) => (valores[l.pieza_id] ?? '').trim() !== '' && Number(valores[l.pieza_id]) > 0)
      .map((l) => {
        const v = valores[l.pieza_id].trim().replace(',', '.')
        return l.unidades !== null ? { pieza_id: l.pieza_id, unidades: Number(v) } : { pieza_id: l.pieza_id, kg: v }
      })
    if (lineas.length === 0) throw new Error('Indica al menos un renglón que sale.')
    return { fecha: dia, lineas, libres, retiro: retiroLimpio(retiro), observacion: observacion.trim() || null, confirmar,
      clave_idempotencia: confirmar ? clave : null }
  }

  async function llamar(confirmar: boolean) {
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenSalida>(`/api/despachos/${o.id}/nota-salida`, { metodo: 'POST', cuerpo: cuerpo(confirmar) })
      if (confirmar) onHecho(r)
      else { setResumen(r); setClave(crypto.randomUUID()) }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="confirmacion no-impresion">
      <h3>Nota de salida</h3>
      {resumen ? (
        <>
          <p>Nota de salida <strong>{resumen.numero}</strong> · {fecha(resumen.fecha)} · <strong>{kg(resumen.total_kg)}</strong></p>
          {resumen.avisos.length > 0 && <div className="alerta"><ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>}
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Pieza</th><th className="n">En patio</th><th className="n">Sale</th><th className="n">Queda</th></tr></thead>
              <tbody>
                {resumen.lineas.map((l) => (
                  <tr key={l.pieza_id}>
                    <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                    <td className="n">{cantidad(l.saldo_antes_unidades, l.saldo_antes_kg)}</td>
                    <td className="n fuerte">{cantidad(l.unidades, l.kg)}</td>
                    <td className="n">{cantidad(l.saldo_despues_unidades, l.saldo_despues_kg)}</td>
                  </tr>
                ))}
                {(resumen.libres ?? []).map((l, i) => (
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
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void llamar(true)}>{ocupado ? 'Guardando…' : 'Confirmar salida del patio'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </>
      ) : (
        <>
          <p className="tenue pequeno">Viene cargada con lo que pidió el cliente. Si sale menos, cámbialo; lo que no salga queda
            libre en su inventario. Deja vacío un renglón que no sale.</p>
          <label className="corto">Fecha de salida<input type="date" value={dia} onChange={(e) => setDia(e.target.value)} /></label>
          <div className="tabla-envoltura">
            <table className="tabla compacta cortes">
              <thead><tr><th>Pieza</th><th className="n">Pedido</th><th>Sale</th></tr></thead>
              <tbody>
                {o.lineas.map((l) => (
                  <tr key={l.pieza_id}>
                    <td><div className="codigo">{l.codigo}</div><div className="tenue pequeno">{l.descripcion}</div></td>
                    <td className="n">{cantidad(l.unidades, l.kg)}</td>
                    <td><input inputMode={l.unidades !== null ? 'numeric' : 'decimal'} value={valores[l.pieza_id] ?? ''}
                      aria-label={l.unidades !== null ? 'Piezas que salen' : 'kg que salen'}
                      onChange={(e) => setValores({ ...valores, [l.pieza_id]: e.target.value })} />
                      <span className="tenue pequeno"> {l.unidades !== null ? 'pzas' : 'kg'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
                        <td><input inputMode="decimal" value={x.kg} aria-label="Kg que salen" placeholder="kg"
                          onChange={(e) => setIrregulares(irregulares.map((y, j) => (j === i ? { ...y, kg: e.target.value } : y)))} /></td>
                        <td><button type="button" className="enlace" onClick={() => setIrregulares(irregulares.filter((_, j) => j !== i))}>Quitar</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <button type="button" className="secundario" onClick={() => setIrregulares([...irregulares, { kg: '', detalle: '' }])}>
              + {MATERIAL_IRREGULAR.nombre}</button>
            <span className="tenue pequeno"> Scrap, chatarra o cortes fuera de medida que salen con este despacho: solo su peso.</span>
          </div>
          <CamposRetiro valor={retiro} onCambio={setRetiro} titulo="Quién retira (confirma con la cédula y la placa)" />
          <label>Observación<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} /></label>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void llamar(false)}>{ocupado ? 'Revisando…' : 'Revisar nota de salida'}</button>
            <button className="secundario" onClick={onCancelar}>Cancelar</button>
          </div>
        </>
      )}
    </div>
  )
}

// --- Detalle --------------------------------------------------------------------

function DetalleDespacho({ id, usuario, onCerrar, onCambio, onVerDocumento }: {
  id: number; usuario: Usuario; onCerrar: () => void; onCambio: () => void; onVerDocumento?: (id: number) => void
}) {
  const esPersonal = usuario.rol !== 'cliente'
  const [o, setO] = useState<OrdenDespacho | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [emitiendo, setEmitiendo] = useState(false)
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [hecho, setHecho] = useState<ResumenSalida | null>(null)

  const cargar = useCallback(() => {
    pedir<OrdenDespacho>(`/api/despachos/${id}`).then(setO).catch((e: Error) => setError(e.message))
  }, [id])
  useEffect(cargar, [cargar])

  async function anular() {
    setError(null)
    try {
      setO(await pedir<OrdenDespacho>(`/api/despachos/${id}/anular`, { metodo: 'POST', cuerpo: { motivo } }))
      setAnulando(false)
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo anular')
    }
  }

  const fallo = (e: Error) => setError(e.message)

  return (
    <Modal titulo={o ? `Orden de despacho ${o.numero}` : 'Orden de despacho'} onCerrar={onCerrar} ancho>
      {!o && !error && <p className="tenue">Cargando…</p>}
      {o && (
        <>
          <p>
            <Estado estado={o.estado} /> · <strong>{o.tercero}</strong> · {fecha(o.fecha)}
            {o.creado_por && <span className="tenue pequeno"> · pedida por {o.creado_por}{o.origen === 'agente' ? ' (agente)' : ''}</span>}
          </p>
          {hecho && (
            <div className="exito">
              Nota de salida {hecho.numero} registrada: {kg(hecho.total_kg)} salieron del patio.{' '}
              {hecho.documento_id && <>
                <button className="enlace" onClick={() => { pdfNotaSalida(hecho.documento_id as number, hecho.numero, o.tercero).catch(fallo) }}>Ver (PDF)</button>
                {' · '}<button className="enlace" onClick={() => { pdfNotaSalida(hecho.documento_id as number, hecho.numero, o.tercero, true).catch(fallo) }}>Guardar en carpeta</button>
              </>}
            </div>
          )}
          <TablaLineas o={o} />
          <h3>Retiro</h3>
          <DatosRetiro r={o.retiro} />
          {o.observacion && <p><span className="tenue">Observación:</span> {o.observacion}</p>}
          {o.nota_salida_id && (
            <p>Despachada con la <strong>nota de salida {o.nota_salida_numero}</strong>.{' '}
              <button className="enlace" onClick={() => { pdfNotaSalida(o.nota_salida_id as number, o.nota_salida_numero, o.tercero).catch(fallo) }}>Ver (PDF)</button>
              {onVerDocumento && <> · <button className="enlace" onClick={() => onVerDocumento(o.nota_salida_id as number)}>Ver el documento</button></>}
            </p>
          )}
          {error && <p className="error">{error}</p>}
          {!emitiendo && !anulando && (
            <div className="acciones no-impresion">
              {esPersonal && o.estado === 'pendiente' && (
                <button className="primario" onClick={() => setEmitiendo(true)}>Emitir nota de salida</button>
              )}
              <button className="secundario" onClick={() => { pdfDespacho(o.id as number, o.numero, o.tercero).catch(fallo) }}>Orden (PDF)</button>
              <button className="secundario" onClick={() => { pdfDespacho(o.id as number, o.numero, o.tercero, true).catch(fallo) }}>Guardar orden en carpeta</button>
              {o.estado === 'pendiente' && <button className="peligro" onClick={() => setAnulando(true)}>Anular orden</button>}
            </div>
          )}
          {emitiendo && (
            <EmitirNotaSalida o={o} onCancelar={() => setEmitiendo(false)}
              onHecho={(r) => { setHecho(r); setEmitiendo(false); cargar(); onCambio() }} />
          )}
          {anulando && (
            <div className="confirmacion peligro-caja no-impresion">
              <label>Motivo de la anulación (el material queda libre otra vez)
                <input value={motivo} onChange={(e) => setMotivo(e.target.value)} minLength={5} autoFocus />
              </label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void anular()}>Anular orden</button>
                <button className="secundario" onClick={() => setAnulando(false)}>Volver</button>
              </div>
            </div>
          )}
        </>
      )}
      {!o && error && <p className="error">{error}</p>}
    </Modal>
  )
}

// --- Lista --------------------------------------------------------------------

/** Lista de órdenes de despacho con su detalle. El cliente ve las suyas; el personal, todas
 *  (por defecto las pendientes: lo que el patio tiene por preparar). */
export default function Despachos({ usuario, onVerDocumento, abrir = null, onAbierto }: {
  usuario: Usuario; onVerDocumento?: (id: number) => void; abrir?: number | null; onAbierto?: () => void
}) {
  const esPersonal = usuario.rol !== 'cliente'
  const [estado, setEstado] = useState<string>(esPersonal ? 'pendiente' : '')
  const [lista, setLista] = useState<OrdenDespacho[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nueva, setNueva] = useState(false)
  const [abierta, setAbierta] = useState<number | null>(abrir)
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [aviso, setAviso] = useState<string | null>(null)

  const cargar = useCallback(() => {
    setError(null)
    pedir<OrdenDespacho[]>(`/api/despachos${consulta({ estado })}`).then(setLista).catch((e: Error) => setError(e.message))
  }, [estado])
  useEffect(cargar, [cargar])
  useEffect(() => { if (abrir) { setAbierta(abrir); onAbierto?.() } }, [abrir, onAbierto])
  useEffect(() => {
    if (esPersonal) pedir<Tercero[]>('/api/terceros?rol=cliente').then(setTerceros).catch(() => setTerceros([]))
  }, [esPersonal])

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>{esPersonal ? 'Órdenes de despacho' : 'Mis órdenes de despacho'}</h1>
        <button className="primario" onClick={() => { setAviso(null); setNueva(true) }}>Nueva orden de despacho</button>
      </div>
      {!esPersonal && (
        <p className="tenue">Pide aquí el retiro de material de tu inventario en Prosifer. Al enviarla, el material queda
          reservado y el patio la prepara; recibirás la nota de salida cuando salga.</p>
      )}
      {aviso && <div className="exito">{aviso}</div>}
      <div className="filtros tarjeta">
        <label>Estado
          <select value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="">Todas</option>
            <option value="pendiente">Pendientes</option>
            <option value="despachada">Despachadas</option>
            <option value="anulada">Anuladas</option>
          </select>
        </label>
        <div className="acciones-filtro"><button className="secundario" onClick={cargar}>Actualizar</button></div>
      </div>
      {error && <p className="error">{error}</p>}
      {lista && lista.length === 0 && (
        <p className="vacio">{estado === 'pendiente' ? 'No hay órdenes de despacho pendientes.' : 'No hay órdenes de despacho.'}</p>
      )}
      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead>
              <tr><th>N°</th><th>Fecha</th>{esPersonal && <th>Cliente</th>}<th>Retiro</th><th className="n">Renglones</th>
                <th className="n">Kg</th><th>Estado</th><th>Nota de salida</th></tr>
            </thead>
            <tbody>
              {lista.map((o) => (
                <tr key={o.id} onClick={() => setAbierta(o.id)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAbierta(o.id) }}>
                  <td className="fuerte">{o.numero}</td>
                  <td>{fecha(o.fecha)}</td>
                  {esPersonal && <td>{o.tercero}</td>}
                  <td>{o.retiro?.fecha_retiro ? fecha(o.retiro.fecha_retiro) : '—'}
                    {o.retiro?.placa && <span className="tenue pequeno"> · {o.retiro.placa}</span>}</td>
                  <td className="n">{o.lineas.length}</td>
                  <td className="n">{kg(o.total_kg)}</td>
                  <td><Estado estado={o.estado} /></td>
                  <td>{o.nota_salida_numero ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {nueva && (
        <NuevaOrdenDespacho usuario={usuario} terceros={terceros} onCerrar={() => setNueva(false)}
          onHecho={(o) => { setNueva(false); setAviso(`Orden de despacho ${o.numero} enviada: ${kg(o.total_kg)} reservados.`); cargar(); setAbierta(o.id) }} />
      )}
      {abierta !== null && (
        <DetalleDespacho id={abierta} usuario={usuario} onCerrar={() => setAbierta(null)} onCambio={cargar}
          onVerDocumento={onVerDocumento ? (d) => { setAbierta(null); onVerDocumento(d) } : undefined} />
      )}
    </section>
  )
}
