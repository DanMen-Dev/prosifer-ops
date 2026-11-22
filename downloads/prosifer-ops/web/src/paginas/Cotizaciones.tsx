import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  abrirPdf, consulta, pdfCotizacion, pedir, type BorradorCotizacion, type Cotizacion, type Producto, type RenglonCotizacion,
  type Tercero, type Usuario,
} from '../api'
import { fecha, hoyIso, usd } from '../formato'
import Modal from './Modal'

/* Cotizaciones en USD: la mayoría por servicios (corte, maquila, carga y manejo, almacenamiento) y
   algunas por venta de material. Siguen la numeración del Excel (D- 2943…); las del Excel son de consulta. */

/** Lee un archivo como base64 (sin el prefijo data:) para mandarlo como comprobante. */
function leerBase64(f: File): Promise<string> {
  return new Promise((ok, mal) => {
    const r = new FileReader()
    r.onload = () => ok(String(r.result).split(',', 2)[1] ?? '')
    r.onerror = () => mal(new Error('No se pudo leer el archivo'))
    r.readAsDataURL(f)
  })
}

const UNIDADES = ['Kg', 'Pza', 'Servicio', 'TM', 'Rollo', 'Bob']
const DESTINOS = ['Zelle', 'Binance (USDT)', 'Caja USD', 'Banesco Panamá', 'Chase Bank', 'Banesco Vzla']
/** "57.744,5" (con coma: el punto es de miles) o "0.04" (sin coma: el punto es decimal). */
const num = (v: string) => {
  const t = v.trim()
  return Number(t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t)
}
const totalRenglon = (r: { cantidad: string; precio: string }) => {
  const c = num(r.cantidad), p = num(r.precio)
  return Number.isFinite(c) && Number.isFinite(p) ? Math.round(c * p * 100) / 100 : 0
}
const coma = (v: string | number | null | undefined) => (v === null || v === undefined || v === '' ? '' : String(v).replace('.', ','))

interface RenglonForm { codigo: string; descripcion: string; cantidad: string; unidad: string; precio: string }
const VACIO: RenglonForm = { codigo: '', descripcion: '', cantidad: '', unidad: 'Kg', precio: '' }

export interface InicialCotizacion {
  tercero?: string | null
  orden_trabajo_id?: number | null
  orden?: string | null
  renglones?: RenglonCotizacion[]
  notas?: string | null
  avisos?: string[]
}

/** Formulario de cotización nueva. Desde una orden llega precargado (cliente, servicio y kg). */
export function NuevaCotizacion({ inicial, onHecho, onCerrar, enLinea = false }: {
  inicial?: InicialCotizacion | null; onHecho: (c: Cotizacion) => void; onCerrar?: () => void
  enLinea?: boolean   // en la pestaña Cotizaciones va desplegado en la página, no en una ventana
}) {
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [productos, setProductos] = useState<Producto[]>([])
  const [cliente, setCliente] = useState(inicial?.tercero ?? '')
  const [dia, setDia] = useState(hoyIso())
  const [renglones, setRenglones] = useState<RenglonForm[]>(inicial?.renglones?.length
    ? inicial.renglones.map((r) => ({ codigo: r.codigo ?? '', descripcion: r.descripcion, cantidad: coma(r.cantidad), unidad: r.unidad,
      precio: Number(r.precio_unitario) ? coma(r.precio_unitario) : '' }))
    : [{ ...VACIO }])
  const [vendedor, setVendedor] = useState('')
  const [condicion, setCondicion] = useState('')
  const [ne, setNe] = useState('')
  const [notas, setNotas] = useState(inicial?.notas ?? '')
  const [iva, setIva] = useState('')
  const [pago, setPago] = useState({ fecha: hoyIso(), destino: '', monto: '', referencia: '' })
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    pedir<Tercero[]>('/api/terceros').then((t) => setTerceros(t.filter((x) => x.activo))).catch(() => {})
    pedir<Producto[]>(`/api/productos${consulta({ limite: 2000 })}`).then(setProductos).catch(() => {})
  }, [])
  const elegido = terceros.find((t) => t.nombre.toLowerCase() === cliente.trim().toLowerCase()) ?? null
  useEffect(() => {   // vendedor y condición de pago de la ficha del cliente, si no se escribieron
    if (!elegido) return
    setVendedor((v) => v || elegido.vendedor || '')
    setCondicion((v) => v || elegido.forma_pago || '')
  }, [elegido])

  function cambiar(i: number, campo: keyof RenglonForm, v: string) {
    setRenglones(renglones.map((r, j) => {
      if (j !== i) return r
      const s = { ...r, [campo]: v }
      if (campo === 'descripcion' || campo === 'codigo') {   // del catálogo: código y nombre van juntos
        const p = productos.find((x) => (campo === 'codigo' ? x.codigo === v.trim().toUpperCase() : x.nombre === v.trim()))
        if (p) { s.codigo = p.codigo; s.descripcion = p.nombre; if (p.codigo.startsWith('SERV')) s.unidad = s.unidad || 'Kg' }
      }
      return s
    }))
  }

  const subtotal = renglones.reduce((t, r) => t + totalRenglon(r), 0)
  const ivaMonto = num(iva) > 0 ? Math.round(subtotal * num(iva)) / 100 : 0

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!elegido) { setError('Elige el cliente de la lista.'); return }
    const lista = renglones.filter((r) => r.descripcion.trim())
    if (lista.length === 0) { setError('Agrega al menos un renglón.'); return }
    for (const r of lista) {
      if (!(num(r.cantidad) > 0)) { setError(`${r.descripcion}: indica la cantidad.`); return }
      if (!(num(r.precio) >= 0) || r.precio.trim() === '') { setError(`${r.descripcion}: indica el precio unitario (USD).`); return }
    }
    const conPago = pago.destino.trim() !== '' || pago.monto.trim() !== ''
    if (conPago && (!pago.destino.trim() || !(num(pago.monto) > 0))) { setError('Pago recibido: indica el destino y el monto, o déjalo vacío.'); return }
    setOcupado(true)
    try {
      onHecho(await pedir<Cotizacion>('/api/cotizaciones', { metodo: 'POST', cuerpo: {
        abonos: conPago ? [{ fecha: pago.fecha || null, destino: pago.destino.trim(), monto: num(pago.monto),
          referencia: pago.referencia.trim() || null }] : [],
        tercero_id: elegido.id, fecha: dia, vendedor: vendedor.trim() || null, condicion_pago: condicion.trim() || null,
        nota_entrega: ne.trim() || null, notas: notas.trim() || null, iva_pct: iva.trim() ? num(iva) : null,
        orden_trabajo_id: inicial?.orden_trabajo_id ?? null,
        renglones: lista.map((r) => ({ codigo: r.codigo.trim() || null, descripcion: r.descripcion.trim(), cantidad: num(r.cantidad),
          unidad: r.unidad.trim() || 'Pza', precio_unitario: num(r.precio) })),
      } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo emitir')
    } finally {
      setOcupado(false)
    }
  }

  const titulo = inicial?.orden ? `Cotizar ${inicial.orden}` : 'Nueva cotización'
  const contenido = (
    <>
      {(inicial?.avisos ?? []).length > 0 && <div className="alerta"><ul>{inicial?.avisos?.map((a) => <li key={a}>{a}</li>)}</ul></div>}
      <form onSubmit={enviar}>
        <div className="formulario tres-columnas sin-relleno">
          <label className="doble">Cliente
            <input list="lista-terceros-cotizacion" value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Escribe para buscar" required />
            <datalist id="lista-terceros-cotizacion">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
          </label>
          <label>Fecha<input type="date" value={dia} onChange={(e) => setDia(e.target.value)} required /></label>
          <label>Vendedor<input value={vendedor} onChange={(e) => setVendedor(e.target.value)} placeholder="Gerencia, R.O., Oficina…" /></label>
          <label>Condición de pago<input value={condicion} onChange={(e) => setCondicion(e.target.value)} /></label>
          <label>Nota de entrega N.º<input value={ne} onChange={(e) => setNe(e.target.value)} placeholder="Si se relaciona con una" /></label>
        </div>
        <div className="tabla-envoltura">
          <table className="tabla compacta cortes">
            <thead><tr><th>Servicio o producto</th><th>Cantidad</th><th>Unidad</th><th>Precio unit. (USD)</th><th className="n">Total (USD)</th><th></th></tr></thead>
            <tbody>
              {renglones.map((r, i) => (
                <tr key={i}>
                  <td className="celda-articulo">
                    <input list="lista-productos-cotizacion" value={r.descripcion} aria-label="Servicio o producto"
                      placeholder="Escribe para buscar: «corte slitter», «carga y manejo»…" onChange={(e) => cambiar(i, 'descripcion', e.target.value)} />
                    {r.codigo && <div className="tenue pequeno codigo">{r.codigo}</div>}
                  </td>
                  <td><input inputMode="decimal" value={r.cantidad} size={9} aria-label="Cantidad" onChange={(e) => cambiar(i, 'cantidad', e.target.value)} /></td>
                  <td><input list="lista-unidades-cotizacion" value={r.unidad} size={7} aria-label="Unidad" onChange={(e) => cambiar(i, 'unidad', e.target.value)} /></td>
                  <td><input inputMode="decimal" value={r.precio} size={8} aria-label="Precio unitario en USD" placeholder="0,040"
                    onChange={(e) => cambiar(i, 'precio', e.target.value)} /></td>
                  <td className="n fuerte">{usd(totalRenglon(r), false)}</td>
                  <td>{renglones.length > 1 && <button type="button" className="enlace" onClick={() => setRenglones(renglones.filter((_, j) => j !== i))}>Quitar</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <datalist id="lista-productos-cotizacion">{productos.map((p) => <option key={p.id} value={p.nombre}>{p.codigo}</option>)}</datalist>
          <datalist id="lista-unidades-cotizacion">{UNIDADES.map((u) => <option key={u} value={u} />)}</datalist>
          <p className="pie-tabla">
            <button type="button" className="enlace" onClick={() => setRenglones([...renglones, { ...VACIO }])}>+ Otro renglón</button>
            {' · '}Subtotal <strong>{usd(subtotal)}</strong>{ivaMonto > 0 && <> · IVA {usd(ivaMonto)}</>} · Total <strong>{usd(subtotal + ivaMonto)}</strong>
          </p>
        </div>
        <div className="formulario dos-columnas sin-relleno">
          <label>Notas adicionales / comentarios (salen impresos)<textarea rows={2} value={notas} onChange={(e) => setNotas(e.target.value)}
            placeholder="Período de facturación, NS relacionada, bobina o perfil…" />
            {inicial?.notas && <span className="tenue pequeno">Precargado con el material de la orden; puedes agregarle lo que haga falta.</span>}</label>
          <label>IVA % (vacío = sin IVA)<input inputMode="decimal" value={iva} onChange={(e) => setIva(e.target.value)} /></label>
        </div>
        <fieldset className="pago-recibido">
          <legend>Pago ya recibido (opcional: si la cotización se emite después de cobrar)</legend>
          <div className="formulario cuatro-columnas sin-relleno">
            <label>Fecha<input type="date" value={pago.fecha} onChange={(e) => setPago({ ...pago, fecha: e.target.value })} /></label>
            <label>Forma de pago<input list="destinos-pago-nueva" value={pago.destino} onChange={(e) => setPago({ ...pago, destino: e.target.value })} placeholder="Zelle, Binance…" /></label>
            <label>Monto (USD)<input inputMode="decimal" value={pago.monto} onChange={(e) => setPago({ ...pago, monto: e.target.value })} /></label>
            <label>Referencia<input value={pago.referencia} onChange={(e) => setPago({ ...pago, referencia: e.target.value })} placeholder="Confirmación u orden" /></label>
            <datalist id="destinos-pago-nueva">{DESTINOS.map((x) => <option key={x} value={x} />)}</datalist>
          </div>
        </fieldset>
        {error && <p className="error">{error}</p>}
        <div className="acciones">
          <button className="primario" disabled={ocupado}>{ocupado ? 'Emitiendo…' : 'Emitir cotización'}</button>
          {onCerrar && <button type="button" className="secundario" onClick={onCerrar}>Cancelar</button>}
        </div>
      </form>
    </>
  )
  if (enLinea) return <section className="tarjeta bloque"><h2>{titulo}</h2>{contenido}</section>
  return <Modal titulo={titulo} onCerrar={onCerrar ?? (() => {})} ancho>{contenido}</Modal>
}

export function DetalleCotizacion({ id, onCerrar, onCambio, puedeEditar = true }: {
  id: number; onCerrar: () => void; onCambio: () => void; puedeEditar?: boolean
}) {
  const [c, setC] = useState<Cotizacion | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [accion, setAccion] = useState<'abono' | 'anular' | null>(null)
  const [abono, setAbono] = useState({ fecha: hoyIso(), destino: '', monto: '', referencia: '' })
  const [motivo, setMotivo] = useState('')
  const [archivo, setArchivo] = useState<File | null>(null)

  useEffect(() => { pedir<Cotizacion>(`/api/cotizaciones/${id}`).then(setC).catch((e: Error) => setError(e.message)) }, [id])
  const fallo = (e: unknown) => setError(e instanceof Error ? e.message : 'No se pudo')

  async function hacer() {
    setError(null)
    try {
      if (archivo && archivo.size > 6 * 1024 * 1024) throw new Error('El comprobante pasa de 6 MB')
      const comprobante = archivo
        ? { nombre: archivo.name, tipo_mime: archivo.type, base64: await leerBase64(archivo) } : null
      setC(accion === 'abono'
        ? await pedir<Cotizacion>(`/api/cotizaciones/${id}/abonos`, { metodo: 'POST', cuerpo: { fecha: abono.fecha || null, destino: abono.destino.trim(),
          monto: num(abono.monto), referencia: abono.referencia.trim() || null, comprobante } })
        : await pedir<Cotizacion>(`/api/cotizaciones/${id}/anular`, { metodo: 'POST', cuerpo: { motivo: motivo.trim() } }))
      setAccion(null)
      setAbono({ fecha: hoyIso(), destino: '', monto: '', referencia: '' })
      setArchivo(null)
      onCambio()
    } catch (e) { fallo(e) }
  }

  return (
    <Modal titulo={c ? `Cotización D-${c.numero} · ${c.tercero ?? ''}` : 'Cotización'} onCerrar={onCerrar} ancho>
      {error && <p className="error">{error}</p>}
      {!c && !error && <p className="tenue">Cargando…</p>}
      {c && (
        <>
          {c.anulada && <p className="error">Anulada{c.motivo_anulacion ? `: ${c.motivo_anulacion}` : ''}</p>}
          {c.historica && <p className="alerta">Emitida en el Excel: solo consulta.</p>}
          <dl className="datos-retiro">
            <div><dt>Fecha</dt><dd>{c.fecha ? fecha(c.fecha) : '—'}</dd></div>
            {c.vendedor && <div><dt>Vendedor</dt><dd>{c.vendedor}</dd></div>}
            {c.condicion_pago && <div><dt>Condición</dt><dd>{c.condicion_pago}</dd></div>}
            {c.nota_entrega && <div><dt>NE</dt><dd>{c.nota_entrega}</dd></div>}
            {c.orden && <div><dt>Orden</dt><dd>{c.orden}</dd></div>}
          </dl>
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Descripción</th><th className="n">Cantidad</th><th>Unidad</th><th className="n">Precio (USD)</th><th className="n">Total (USD)</th></tr></thead>
              <tbody>
                {c.renglones.map((r, i) => (
                  <tr key={i}>
                    <td><div>{r.descripcion}</div>{r.codigo && <div className="tenue pequeno codigo">{r.codigo}</div>}</td>
                    <td className="n">{r.cantidad !== undefined && r.cantidad !== null ? Number(r.cantidad).toLocaleString('es-VE') : '—'}</td>
                    <td>{r.unidad}</td>
                    <td className="n">{r.precio_unitario !== null && r.precio_unitario !== undefined
                      ? Number(r.precio_unitario).toLocaleString('es-VE', { minimumFractionDigits: 3, maximumFractionDigits: 4 }) : '—'}</td>
                    <td className="n fuerte">{usd(r.total ?? 0, false)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="pie-tabla">Subtotal {usd(c.subtotal)}{c.iva_pct && <> · IVA {Number(c.iva_pct)}% {usd(c.iva)}</>} · Total <strong>{usd(c.total)}</strong>
              {' · '}Abonado {usd(c.abonado)} · <strong className={Number(c.saldo) > 0 ? 'negativo' : ''}>Por cobrar {usd(c.saldo)}</strong></p>
          </div>
          {c.abonos.length > 0 && (
            <>
              <h3>Abonos</h3>
              <ul className="pequeno">{c.abonos.map((a, i) => <li key={i}>{a.fecha ? (a.fecha.length === 10 && a.fecha[4] === '-' ? fecha(a.fecha) : a.fecha) : '—'} · {a.destino} · <strong>{usd(a.monto)}</strong>{a.referencia && <span className="tenue"> · ref. {a.referencia}</span>}{a.comprobante_id && <> · <button className="enlace" onClick={() => void abrirPdf(`/api/cotizaciones/${id}/comprobantes/${a.comprobante_id}`, 'comprobante').catch(fallo)}>ver comprobante</button></>}</li>)}</ul>
            </>
          )}
          {c.notas && <p><span className="tenue">Notas:</span> {c.notas}</p>}
          {accion === 'abono' && (
            <div className="confirmacion">
              <div className="formulario cuatro-columnas sin-relleno">
                <label>Fecha<input type="date" value={abono.fecha} onChange={(e) => setAbono({ ...abono, fecha: e.target.value })} /></label>
                <label>Destino<input list="destinos-abono" value={abono.destino} onChange={(e) => setAbono({ ...abono, destino: e.target.value })} placeholder="Zelle, Caja USD…" /></label>
                <label>Monto (USD)<input inputMode="decimal" value={abono.monto} onChange={(e) => setAbono({ ...abono, monto: e.target.value })} /></label>
                <label>Referencia<input value={abono.referencia} onChange={(e) => setAbono({ ...abono, referencia: e.target.value })} placeholder="Confirmación u orden" /></label>
                <label>Comprobante<input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} /></label>
                <datalist id="destinos-abono">{DESTINOS.map((x) => <option key={x} value={x} />)}</datalist>
              </div>
              <div className="acciones">
                <button className="primario" disabled={!abono.destino.trim() || !(num(abono.monto) > 0)} onClick={() => void hacer()}>Anotar abono</button>
                <button className="secundario" onClick={() => setAccion(null)}>Volver</button>
              </div>
            </div>
          )}
          {accion === 'anular' && (
            <div className="confirmacion peligro-caja">
              <label>Motivo de la anulación<textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus /></label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void hacer()}>Anular cotización</button>
                <button className="secundario" onClick={() => setAccion(null)}>Volver</button>
              </div>
            </div>
          )}
          {!accion && (
            <div className="acciones">
              <button className="primario" onClick={() => { pdfCotizacion(c.id, c.numero, c.tercero).catch(fallo) }}>Ver PDF</button>
              <button className="secundario" onClick={() => { pdfCotizacion(c.id, c.numero, c.tercero, true).catch(fallo) }}>Guardar en carpeta</button>
              {puedeEditar && !c.anulada && Number(c.saldo) > 0 && <button className="secundario" onClick={() => setAccion('abono')}>Anotar abono</button>}
              {puedeEditar && !c.anulada && !c.historica && <button className="peligro" onClick={() => setAccion('anular')}>Anular</button>}
            </div>
          )}
        </>
      )}
    </Modal>
  )
}

export interface FiltrosCotizacion { numero: string; desde: string; hasta: string; incluir_anulados: boolean; tercero_id?: string }

/** Lista de cotizaciones (Salidas › Documentos, tipo Cotizaciones). El cliente ve solo las suyas. */
export function ListaCotizaciones({ usuario, filtros, version = 0 }: { usuario: Usuario; filtros: FiltrosCotizacion; version?: number }) {
  const esPersonal = usuario.rol !== 'cliente'
  const [lista, setLista] = useState<Cotizacion[] | null>(null)
  const [abierta, setAbierta] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(() => {
    pedir<Cotizacion[]>(`/api/cotizaciones${consulta({ q: filtros.numero.trim() || null, tercero_id: filtros.tercero_id || null, desde: filtros.desde || null,
      hasta: filtros.hasta || null, incluir_anuladas: filtros.incluir_anulados, limite: 300 })}`)
      .then(setLista).catch((e: Error) => setError(e.message))
  }, [filtros])
  useEffect(() => { cargar() }, [cargar, version])

  return (
    <>
      {error && <p className="error">{error}</p>}
      {lista && lista.length === 0 && <p className="vacio">No hay cotizaciones con esos filtros.</p>}
      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead><tr><th>Fecha</th><th>N.º</th>{esPersonal && <th>Cliente</th>}<th>Renglones</th><th className="n">Total (USD)</th><th className="n">Por cobrar</th></tr></thead>
            <tbody>
              {lista.map((c) => (
                <tr key={c.id} tabIndex={0} className={c.anulada ? 'anulado' : ''} onClick={() => setAbierta(c.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAbierta(c.id) }}>
                  <td>{c.fecha ? fecha(c.fecha) : '—'}</td>
                  <td className="fuerte">D-{c.numero}{c.historica && <span className="tenue pequeno"> · Excel</span>}
                    {c.anulada && <span className="etiqueta-anulada">ANULADA</span>}</td>
                  {esPersonal && <td>{c.tercero ?? '—'}</td>}
                  <td className="pequeno">{c.renglones.map((r) => r.descripcion).join(' · ')}{c.orden && <span className="tenue"> · {c.orden}</span>}</td>
                  <td className="n">{usd(c.total, false)}</td>
                  <td className="n">{c.anulada ? '—' : usd(c.saldo, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {abierta !== null && <DetalleCotizacion id={abierta} puedeEditar={esPersonal} onCerrar={() => setAbierta(null)} onCambio={cargar} />}
    </>
  )
}

/** Pestaña Salidas › Cotizaciones: el formulario ya desplegado para emitir. Las emitidas se ven en Documentos. */
export default function Cotizaciones({ onVerDocumentos }: { onVerDocumentos?: () => void }) {
  const [hecha, setHecha] = useState<Cotizacion | null>(null)
  const [abierta, setAbierta] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  return (
    <>
      {hecha && (
        <div className="exito">Cotización <strong>D-{hecha.numero}</strong> emitida para {hecha.tercero}: {usd(hecha.total)}.{' '}
          <button className="enlace" onClick={() => { pdfCotizacion(hecha.id, hecha.numero, hecha.tercero).catch((e: Error) => setError(e.message)) }}>Ver PDF</button>
          {' · '}<button className="enlace" onClick={() => { pdfCotizacion(hecha.id, hecha.numero, hecha.tercero, true).catch((e: Error) => setError(e.message)) }}>Guardar en carpeta</button>
          {' · '}<button className="enlace" onClick={() => setAbierta(hecha.id)}>Abrir</button>
          {onVerDocumentos && <>{' · '}<button className="enlace" onClick={onVerDocumentos}>Ver todas en Documentos</button></>}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {hecha
        ? <div className="acciones"><button className="primario" onClick={() => setHecha(null)}>Hacer otra cotización</button></div>
        : <NuevaCotizacion enLinea onHecho={setHecha} />}
      {abierta !== null && <DetalleCotizacion id={abierta} onCerrar={() => setAbierta(null)} onCambio={() => {}} />}
    </>
  )
}

/** Atajo desde una orden de corte o maquila: pide el borrador y abre el formulario precargado. */
export function CotizarOrden({ ordenId, onCerrar }: { ordenId: number; onCerrar: () => void }) {
  return <CotizarDesde url={`/api/cotizaciones/desde-orden/${ordenId}`} onCerrar={onCerrar} />
}

/** Cotización prellenada desde un borrador de la API (una orden, o el reporte mensual de salidas). */
export function CotizarDesde({ url, onCerrar }: { url: string; onCerrar: () => void }) {
  const [borrador, setBorrador] = useState<BorradorCotizacion | null>(null)
  const [hecho, setHecho] = useState<Cotizacion | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    pedir<BorradorCotizacion>(url).then(setBorrador).catch((e: Error) => setError(e.message))
  }, [url])
  if (error) return <Modal titulo="Cotizar" onCerrar={onCerrar}><p className="error">{error}</p></Modal>
  if (hecho) {
    return (
      <Modal titulo={`Cotización D-${hecho.numero}`} onCerrar={onCerrar}>
        <div className="exito">Cotización <strong>D-{hecho.numero}</strong> emitida para {hecho.tercero}: {usd(hecho.total)}.</div>
        <div className="acciones">
          <button className="primario" onClick={() => { pdfCotizacion(hecho.id, hecho.numero, hecho.tercero).catch((e: Error) => setError(e.message)) }}>Ver PDF</button>
          <button className="secundario" onClick={onCerrar}>Cerrar</button>
        </div>
      </Modal>
    )
  }
  if (!borrador) return <Modal titulo="Cotizar" onCerrar={onCerrar}><p className="tenue">Preparando la cotización…</p></Modal>
  return <NuevaCotizacion inicial={borrador} onCerrar={onCerrar} onHecho={setHecho} />
}
