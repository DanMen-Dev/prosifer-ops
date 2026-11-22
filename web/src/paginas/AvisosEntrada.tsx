import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  consulta, ESTADO_AVISO, pedir, TIPO_RENGLON, type AvisoEntrada, type Producto, type RenglonAviso, type TipoAcero, type Usuario,
} from '../api'
import { fecha, hoyIso, kg } from '../formato'
import GeneradorProducto from './GeneradorProducto'
import Modal from './Modal'

/* Aviso de entrada: el cliente anuncia material que va a llegar al patio. No mueve inventario; Prosifer
   lo usa para preparar la recepción y registra la entrada con sus formularios de siempre (precargados). */

const nuevos = (a: AvisoEntrada) => a.renglones.filter((r) => !r.codigo && r.tipo !== 'bobina' && r.tipo !== 'fleje').length
const CLASE: Record<AvisoEntrada['estado'], string> = { pendiente: 'pendiente', recibido: 'despachada', rechazado: 'anulada', cancelado: 'borrador' }

export function EstadoAvisoChip({ estado }: { estado: AvisoEntrada['estado'] }) {
  return <span className={`estado-despacho ${CLASE[estado]}`}>{ESTADO_AVISO[estado]}</span>
}

const medida = (r: RenglonAviso) => [r.espesor_mm && `${r.espesor_mm} mm`, r.ancho_mm && `${r.ancho_mm} mm`, r.largo_mm && `${r.largo_mm} mm`]
  .filter(Boolean).join(' × ')

export function DetalleAviso({ a, onRegistrar, onAlta }: {
  a: AvisoEntrada; onRegistrar?: (r: RenglonAviso, indice: number) => void; onAlta?: (r: RenglonAviso, indice: number) => void
}) {
  const t = a.transporte ?? {}
  return (
    <>
      <dl className="datos-retiro">
        <div><dt>Llega</dt><dd>{a.fecha_estimada ? fecha(a.fecha_estimada) : '—'}</dd></div>
        {(a.documento_tipo || a.documento_numero) && <div><dt>Documento</dt><dd>{[a.documento_tipo, a.documento_numero].filter(Boolean).join(' ')}</dd></div>}
        {a.proveedor && <div><dt>Proveedor</dt><dd>{a.proveedor}</dd></div>}
        {t.chofer && <div><dt>Chofer</dt><dd>{t.chofer}{t.cedula ? ` · ${t.cedula}` : ''}</dd></div>}
        {t.placa && <div><dt>Placa</dt><dd>{t.placa}</dd></div>}
        {t.transporte && <div><dt>Transporte</dt><dd>{t.transporte}</dd></div>}
        {t.telefono && <div><dt>Teléfono</dt><dd>{t.telefono}</dd></div>}
      </dl>
      <div className="tabla-envoltura">
        <table className="tabla compacta">
          <thead><tr><th>Tipo</th><th>Material</th><th>Medidas</th><th className="n">Piezas</th><th className="n">Kg</th>{onRegistrar && <th></th>}</tr></thead>
          <tbody>
            {a.renglones.map((r, i) => (
              <tr key={i}>
                <td>{TIPO_RENGLON[r.tipo]}{r.tipo_acero ? ` ${r.tipo_acero}` : ''}</td>
                <td>{r.codigo && <div className="codigo">{r.codigo}</div>}<div className={r.codigo ? 'tenue pequeno' : ''}>{r.descripcion}</div>
                  {!r.codigo && PRODUCTO.has(r.tipo) && <span className="estado-despacho pendiente" title="El cliente lo escribió a mano">Fuera del catálogo: dar de alta</span>}</td>
                <td>{medida(r)}</td>
                <td className="n">{r.cantidad ?? ''}</td>
                <td className="n">{r.peso_kg ? kg(r.peso_kg) : ''}</td>
                {onRegistrar && <td>{r.entrada
                  ? <span className="estado-despacho despachada" title={r.entrada.texto ?? undefined}>Registrada · {r.entrada.codigo}</span>
                  : r.tipo !== 'fleje'
                    ? !r.codigo && PRODUCTO.has(r.tipo) && onAlta
                      ? <button className="enlace" onClick={() => onAlta(r, i)}>Dar de alta y registrar</button>
                      : <button className="enlace" onClick={() => onRegistrar(r, i)}>Registrar entrada</button>
                    : <span className="tenue pequeno">regístralo a mano</span>}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="pie-tabla">Total anunciado: <strong>{kg(a.total_kg)}</strong>{a.total_piezas ? ` · ${a.total_piezas} piezas` : ''}</p>
      </div>
      {a.comentarios && <p><span className="tenue">Comentarios:</span> {a.comentarios}</p>}
      {a.nota && <p><span className="tenue">{a.estado === 'recibido' ? 'Nota de Prosifer' : 'Motivo'}:</span> {a.nota}</p>}
    </>
  )
}

// --- Lista del personal (Entradas > Avisos de clientes) --------------------------

const faltan = (a: AvisoEntrada) => a.renglones.filter((r) => r.tipo !== 'fleje' && !r.entrada).length

export function AvisosPersonal({ onRegistrar, onCambio }: {
  onRegistrar: (r: RenglonAviso, a: AvisoEntrada, indice: number) => void; onCambio?: () => void
}) {
  const [estado, setEstado] = useState('pendiente')
  const [lista, setLista] = useState<AvisoEntrada[] | null>(null)
  const [abierto, setAbierto] = useState<AvisoEntrada | null>(null)
  const [accion, setAccion] = useState<'recibir' | 'rechazar' | null>(null)
  const [texto, setTexto] = useState('')
  const [forzar, setForzar] = useState(false)
  const [alta, setAlta] = useState<{ r: RenglonAviso; i: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(() => {
    pedir<AvisoEntrada[]>(`/api/avisos-entrada${consulta({ estado })}`).then(setLista).catch((e: Error) => setError(e.message))
  }, [estado])
  useEffect(cargar, [cargar])

  async function cerrar() {
    if (!abierto || !accion) return
    setError(null)
    try {
      const cuerpo = accion === 'recibir' ? { nota: texto.trim() || null, forzar } : { motivo: texto.trim() }
      setAbierto(await pedir<AvisoEntrada>(`/api/avisos-entrada/${abierto.id}/${accion}`, { metodo: 'POST', cuerpo }))
      setAccion(null)
      setTexto('')
      setForzar(false)
      cargar()
      onCambio?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo')
    }
  }

  return (
    <section>
      <div className="encabezado-seccion">
        <h2>Avisos de clientes</h2>
        <label>Estado
          <select value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="pendiente">Por llegar</option>
            <option value="recibido">Recibidos</option>
            <option value="rechazado">Rechazados</option>
            <option value="cancelado">Cancelados por el cliente</option>
            <option value="">Todos</option>
          </select>
        </label>
      </div>
      <p className="tenue">Material que los clientes anunciaron. Cuando llegue, abre el aviso, registra cada renglón con «Registrar
        entrada» (el formulario sale precargado) y márcalo como recibido.</p>
      {error && !abierto && <p className="error">{error}</p>}
      {lista && lista.length === 0 && <p className="vacio">{estado === 'pendiente' ? 'No hay material por llegar.' : 'No hay avisos.'}</p>}
      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead><tr><th>N°</th><th>Llega</th><th>Cliente</th><th>Documento</th><th>Transporte</th><th className="n">Kg</th><th>Estado</th></tr></thead>
            <tbody>
              {lista.map((a) => (
                <tr key={a.id} tabIndex={0} onClick={() => { setAbierto(a); setAccion(null); setError(null) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAbierto(a) }}>
                  <td className="fuerte">{a.numero}</td>
                  <td>{a.fecha_estimada ? fecha(a.fecha_estimada) : '—'}</td>
                  <td>{a.tercero}</td>
                  <td>{[a.documento_tipo, a.documento_numero].filter(Boolean).join(' ') || '—'}</td>
                  <td>{a.transporte?.placa ?? '—'}{a.transporte?.chofer && <span className="tenue pequeno"> · {a.transporte.chofer}</span>}</td>
                  <td className="n">{kg(a.total_kg)}</td>
                  <td><EstadoAvisoChip estado={a.estado} />
                    {a.estado === 'recibido' && faltan(a) > 0 && <span className="error pequeno"> · {faltan(a)} sin entrada</span>}
                    {nuevos(a) > 0 && <span className="tenue pequeno"> · {nuevos(a)} fuera del catálogo</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {abierto && (
        <Modal titulo={`Aviso de entrada ${abierto.numero} · ${abierto.tercero}`} onCerrar={() => setAbierto(null)} ancho>
          <p><EstadoAvisoChip estado={abierto.estado} /> · anunciado el {fecha(abierto.fecha)}
            {abierto.creado_por && <span className="tenue pequeno"> por {abierto.creado_por}</span>}</p>
          {nuevos(abierto) > 0 && abierto.estado === 'pendiente' && <div className="alerta">
            {nuevos(abierto) === 1 ? 'Un artículo no está' : `${nuevos(abierto)} artículos no están`} en el catálogo: el cliente lo escribió a mano.
            Usa «Dar de alta y registrar»: abre el generador de códigos con lo que describió el cliente y, al crear el producto,
            pasa a la entrada ya precargada con el código nuevo.</div>}
          {abierto.estado === 'recibido' && faltan(abierto) > 0 && <div className="alerta">
            Se marcó como recibido pero {faltan(abierto) === 1 ? 'un renglón no tiene' : `${faltan(abierto)} renglones no tienen`} su
            entrada registrada: <strong>el inventario del cliente no se sumó</strong>. Si no se hizo a mano, usa «Registrar entrada».</div>}
          <DetalleAviso a={abierto} onRegistrar={abierto.estado === 'pendiente' || abierto.estado === 'recibido'
            ? (r, i) => onRegistrar(r, abierto, i) : undefined} onAlta={(r, i) => setAlta({ r, i })} />
          {alta && (
            <GeneradorProducto onCerrar={() => setAlta(null)}
              referencia={{ descripcion: alta.r.descripcion ?? '', tipo: alta.r.tipo, tipo_acero: alta.r.tipo_acero,
                espesor_mm: alta.r.espesor_mm, ancho_mm: alta.r.ancho_mm, largo_mm: alta.r.largo_mm,
                peso_unitario_kg: alta.r.peso_kg && alta.r.cantidad ? String(Number(alta.r.peso_kg) / alta.r.cantidad) : undefined }}
              onCreado={(p) => {
                // con el producto ya en el catálogo, se abre la entrada precargada con su código
                const { r, i } = alta
                setAlta(null)
                onRegistrar({ ...r, codigo: p.codigo, descripcion: p.nombre }, abierto, i)
              }} />
          )}
          {error && <p className="error">{error}</p>}
          {abierto.estado === 'pendiente' && !accion && (
            <div className="acciones">
              <button className="primario" onClick={() => setAccion('recibir')}>Marcar como recibido</button>
              <button className="peligro" onClick={() => setAccion('rechazar')}>No llegó / rechazar</button>
            </div>
          )}
          {accion && (
            <div className={`confirmacion ${accion === 'rechazar' ? 'peligro-caja' : ''}`}>
              {accion === 'recibir' && faltan(abierto) > 0 && (
                <div className="alerta">
                  <strong>Marcar como recibido no suma inventario.</strong> {faltan(abierto) === 1 ? 'Un renglón no tiene' : `${faltan(abierto)} renglones no tienen`} su
                  entrada registrada: primero usa «Registrar entrada» en cada uno.
                  <label className="casilla"><input type="checkbox" checked={forzar} onChange={(e) => setForzar(e.target.checked)} />
                    Las entradas ya se registraron a mano (o parte no llegó): cerrar igual</label>
                </div>
              )}
              <label>{accion === 'recibir' ? 'Nota para el cliente (opcional): por ejemplo, diferencias con lo anunciado' : 'Motivo (el cliente lo verá)'}
                <textarea rows={2} value={texto} onChange={(e) => setTexto(e.target.value)} autoFocus />
              </label>
              <div className="acciones">
                <button className={accion === 'recibir' ? 'primario' : 'peligro'}
                  disabled={(accion === 'rechazar' && texto.trim().length < 5) || (accion === 'recibir' && faltan(abierto) > 0 && !forzar)}
                  onClick={() => void cerrar()}>{accion === 'recibir' ? 'Confirmar recibido' : 'Rechazar aviso'}</button>
                <button className="secundario" onClick={() => setAccion(null)}>Volver</button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </section>
  )
}

// --- Portal del cliente: anunciar y seguir ---------------------------------------

interface RenglonForm { tipo: RenglonAviso['tipo']; codigo: string; descripcion: string; tipo_acero: string; espesor_mm: string; ancho_mm: string; largo_mm: string; cantidad: string; peso_kg: string }
const VACIO: RenglonForm = { tipo: 'bobina', codigo: '', descripcion: '', tipo_acero: '', espesor_mm: '', ancho_mm: '', largo_mm: '', cantidad: '', peso_kg: '' }
const n = (s: string) => s.trim().replace(',', '.')
const unicos = (xs: (string | null | undefined)[]) => [...new Set(xs.map((x) => (x ?? '').trim()).filter(Boolean))].sort()
const PRODUCTO = new Set<RenglonAviso['tipo']>(['lamina', 'perfil', 'general'])
/** Tipo de renglón según el código del catálogo (misma regla que el inventario: LAM…, PER…, FLE…, BOB…). */
const tipoPorCodigo = (c: string): RenglonAviso['tipo'] => {
  const x = c.toUpperCase()
  return x.startsWith('LAM') ? 'lamina' : x.startsWith('PER') ? 'perfil' : x.startsWith('FLE') ? 'fleje'
    : x.startsWith('BOB') ? 'bobina' : 'general'
}
const pesoTotal = (pu: string | null | undefined, piezas: string) =>
  pu && Number(piezas) > 0 ? (Number(pu) * Number(piezas)).toFixed(2).replace(/\.00$/, '') : ''
const sinAcentos = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

/** Campo con lista desplegable propia (no depende del datalist del navegador): se abre al entrar al campo
 *  y filtra mientras se escribe; cada palabra escrita debe aparecer («lamina 3,00 2400»). */
function Combo({ valor, opciones, onCambio, onElegir, placeholder, etiqueta, vacio = 'Sin coincidencias' }: {
  valor: string; opciones: { valor: string; detalle?: string }[]; onCambio: (v: string) => void
  onElegir?: (v: string) => void; placeholder?: string; etiqueta: string; vacio?: string
}) {
  const ref = useRef<HTMLInputElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number; w: number } | null>(null)
  const [marca, setMarca] = useState(0)
  const palabras = sinAcentos(valor).split(/\s+/).filter(Boolean)
  const filtradas = opciones.filter((o) => {
    const txt = sinAcentos(`${o.valor} ${o.detalle ?? ''}`)
    return palabras.every((w) => txt.includes(w))
  }).slice(0, 40)
  const abrir = () => {
    const r = ref.current?.getBoundingClientRect()
    if (r) setPos({ x: r.left, y: r.bottom + 2, w: Math.max(r.width, 320) })
    setMarca(0)
  }
  const elegir = (v: string) => { onCambio(v); onElegir?.(v); setPos(null) }
  useEffect(() => {   // la lista va fija en pantalla: si algo se desplaza, se cierra
    if (!pos) return
    const cerrar = (e: Event) => { if (!(e.target instanceof HTMLElement && e.target.closest('.combo-lista'))) setPos(null) }
    window.addEventListener('scroll', cerrar, true)
    window.addEventListener('resize', cerrar)
    return () => { window.removeEventListener('scroll', cerrar, true); window.removeEventListener('resize', cerrar) }
  }, [pos])
  return (
    <>
      <input ref={ref} value={valor} aria-label={etiqueta} placeholder={placeholder} autoComplete="off"
        onFocus={abrir} onBlur={() => setPos(null)}
        onChange={(e) => { onCambio(e.target.value); if (!pos) abrir() }}
        onKeyDown={(e) => {
          if (!pos || filtradas.length === 0) return
          if (e.key === 'ArrowDown') { e.preventDefault(); setMarca(Math.min(marca + 1, filtradas.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setMarca(Math.max(marca - 1, 0)) }
          if (e.key === 'Enter') { e.preventDefault(); elegir(filtradas[marca].valor) }
          if (e.key === 'Escape') { e.stopPropagation(); setPos(null) }
        }} />
      {pos && opciones.length > 0 && (
        <ul className="combo-lista" role="listbox" style={{ left: pos.x, top: pos.y, width: pos.w }}>
          {filtradas.length === 0 && <li className="tenue">{vacio}</li>}
          {filtradas.map((o, k) => (
            <li key={o.valor} role="option" aria-selected={k === marca} className={k === marca ? 'marcada' : ''}
              onMouseDown={(e) => { e.preventDefault(); elegir(o.valor) }} onMouseEnter={() => setMarca(k)}>
              {o.valor}{o.detalle && <span className="tenue pequeno"> · {o.detalle}</span>}
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function NuevoAviso({ anteriores, onHecho, onCerrar }: { anteriores: AvisoEntrada[]; onHecho: (a: AvisoEntrada) => void; onCerrar: () => void }) {
  const [llega, setLlega] = useState(hoyIso())
  const [docTipo, setDocTipo] = useState('Nota de entrega')
  const [docNumero, setDocNumero] = useState('')
  const [proveedor, setProveedor] = useState('')
  const [transporte, setTransporte] = useState({ chofer: '', cedula: '', placa: '', transporte: '', telefono: '' })
  const [renglones, setRenglones] = useState<RenglonForm[]>([{ ...VACIO }])
  const [comentarios, setComentarios] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [tipos, setTipos] = useState<TipoAcero[]>([])
  const [productos, setProductos] = useState<Producto[]>([])
  const [catalogoError, setCatalogoError] = useState(false)

  useEffect(() => {
    pedir<TipoAcero[]>('/api/catalogos/tipos-acero').then((t) => setTipos(t.filter((x) => x.activo))).catch(() => {})
    // el catálogo completo se carga una vez: la lista desplegable filtra sola mientras se escribe
    pedir<Producto[]>(`/api/productos${consulta({ limite: 2000 })}`).then(setProductos).catch(() => setCatalogoError(true))
  }, [])
  const porNombre = (c: string) => productos.find((p) => p.nombre.trim().toUpperCase() === c.trim().toUpperCase())
  const opcionesProducto = productos.map((p) => ({ valor: p.nombre,
    detalle: [TIPO_RENGLON[tipoPorCodigo(p.codigo)], p.peso_unitario_kg ? `${kg(p.peso_unitario_kg)} c/u` : ''].filter(Boolean).join(' · ') }))

  // memoria de avisos anteriores: proveedores, documentos y transportes que ya usó el cliente
  const proveedores = unicos(anteriores.map((a) => a.proveedor))
  const transportes = anteriores.map((a) => a.transporte).filter((x): x is NonNullable<AvisoEntrada['transporte']> => !!x)
  const placas = unicos(transportes.map((x) => x.placa))
  const choferes = unicos(transportes.map((x) => x.chofer))
  const empresas = unicos(transportes.map((x) => x.transporte))
  const OPC_T: Record<string, string[] | undefined> = { placa: placas, chofer: choferes, transporte: empresas }

  function cambiarTransporte(k: keyof typeof transporte, v: string) {
    const nuevo = { ...transporte, [k]: v }
    // al elegir una placa o un chofer conocido, completa el resto con su último aviso
    const previo = (k === 'placa' || k === 'chofer') && v.trim()
      ? transportes.find((x) => (x[k] ?? '').trim().toUpperCase() === v.trim().toUpperCase()) : undefined
    if (previo) {
      for (const c of ['chofer', 'cedula', 'placa', 'transporte', 'telefono'] as const) {
        if (!nuevo[c].trim() && previo[c]) nuevo[c] = previo[c] as string
      }
    }
    setTransporte(nuevo)
  }

  const cambiar = (i: number, campo: keyof RenglonForm, v: string) => {
    setRenglones(renglones.map((r, j) => {
      if (j !== i) return r
      const s = { ...r, [campo]: v }
      // el cliente elige el nombre del artículo en cualquier tipo de renglón; el código lo pone el catálogo
      // (no lo escribe el cliente) y el tipo se ajusta solo al del artículo elegido
      const elegido = porNombre(s.descripcion)
      if (campo === 'descripcion') {
        s.codigo = elegido?.codigo ?? ''
        if (elegido) {
          s.tipo = tipoPorCodigo(elegido.codigo)
          s.peso_kg = pesoTotal(elegido.peso_unitario_kg, s.cantidad) || s.peso_kg
        }
      }
      if (campo === 'cantidad' && elegido) s.peso_kg = pesoTotal(elegido.peso_unitario_kg, v) || s.peso_kg
      return s
    }))
  }

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const lista = renglones.filter((r) => r.descripcion.trim()).map((r) => ({
      tipo: r.tipo, codigo: r.codigo.trim() || null, descripcion: r.descripcion.trim() || null,
      tipo_acero: r.tipo_acero.trim().toUpperCase() || null, espesor_mm: n(r.espesor_mm) || null, ancho_mm: n(r.ancho_mm) || null,
      largo_mm: n(r.largo_mm) || null, cantidad: r.cantidad.trim() ? Number(r.cantidad) : null, peso_kg: n(r.peso_kg) || null,
    }))
    if (lista.length === 0) { setError('Agrega al menos un renglón con la descripción del material.'); return }
    setOcupado(true)
    try {
      const t = Object.fromEntries(Object.entries(transporte).filter(([, v]) => v.trim()))
      onHecho(await pedir<AvisoEntrada>('/api/avisos-entrada', { metodo: 'POST', cuerpo: {
        fecha_estimada: llega, documento_tipo: docTipo, documento_numero: docNumero.trim() || null,
        proveedor: proveedor.trim() || null, transporte: Object.keys(t).length ? t : null, renglones: lista,
        comentarios: comentarios.trim() || null,
      } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo enviar')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Modal titulo="Anunciar entrada de material" onCerrar={onCerrar} ancho>
      <form onSubmit={enviar}>
        <div className="formulario tres-columnas sin-relleno">
          <label>¿Cuándo llega?<input type="date" value={llega} min={hoyIso()} onChange={(e) => setLlega(e.target.value)} required /></label>
          <label>Documento
            <select value={docTipo} onChange={(e) => setDocTipo(e.target.value)}>
              <option>Nota de entrega</option><option>Factura</option><option>Guía de despacho</option><option>Otro</option>
            </select>
          </label>
          <label>N.º del documento<input value={docNumero} onChange={(e) => setDocNumero(e.target.value)} /></label>
          <label className="ancho-completo">Proveedor o siderúrgica de origen
            <Combo etiqueta="Proveedor" valor={proveedor} onCambio={setProveedor} opciones={proveedores.map((v) => ({ valor: v }))}
              placeholder="Escribe o elige uno que ya usaste" />
          </label>
        </div>
        <h3>Material</h3>
        <div className="tabla-envoltura">
          <table className="tabla compacta cortes">
            <thead><tr><th>Tipo</th><th>Descripción del artículo</th><th>Acero</th><th>Esp. mm</th><th>Ancho mm</th><th>Largo mm</th><th>Piezas</th><th>Kg</th><th></th></tr></thead>
            <tbody>
              {renglones.map((r, i) => (
                <tr key={i}>
                  <td><select value={r.tipo} aria-label="Tipo" onChange={(e) => cambiar(i, 'tipo', e.target.value)}>
                    {Object.entries(TIPO_RENGLON).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                  <td className="celda-articulo">
                    <Combo etiqueta="Descripción del artículo" valor={r.descripcion} onCambio={(v) => cambiar(i, 'descripcion', v)}
                      opciones={opcionesProducto} placeholder="Escribe para buscar: «lamina 2,00», «tubo 1 x 1», «bobina»…"
                      vacio="No está en el catálogo: déjalo escrito y Prosifer lo revisa" />
                    {r.descripcion.trim() && !r.codigo && productos.length > 0 && PRODUCTO.has(r.tipo) &&
                      <span className="tenue pequeno">fuera del catálogo</span>}</td>
                  <td><select value={r.tipo_acero} aria-label="Tipo de acero" onChange={(e) => cambiar(i, 'tipo_acero', e.target.value)}>
                    <option value="">—</option>
                    {tipos.map((x) => <option key={x.id} value={x.codigo}>{x.codigo}</option>)}
                  </select></td>
                  <td><input inputMode="decimal" value={r.espesor_mm} aria-label="Espesor en mm" size={5} onChange={(e) => cambiar(i, 'espesor_mm', e.target.value)} /></td>
                  <td><input inputMode="decimal" value={r.ancho_mm} aria-label="Ancho en mm" size={6} onChange={(e) => cambiar(i, 'ancho_mm', e.target.value)} /></td>
                  <td><input inputMode="decimal" value={r.largo_mm} aria-label="Largo en mm" size={6} onChange={(e) => cambiar(i, 'largo_mm', e.target.value)} /></td>
                  <td><input inputMode="numeric" value={r.cantidad} aria-label="Piezas" size={5} onChange={(e) => cambiar(i, 'cantidad', e.target.value)} /></td>
                  <td><input inputMode="decimal" value={r.peso_kg} aria-label="Peso en kg" size={7} onChange={(e) => cambiar(i, 'peso_kg', e.target.value)} /></td>
                  <td>{renglones.length > 1 && <button type="button" className="enlace" onClick={() => setRenglones(renglones.filter((_, j) => j !== i))}>Quitar</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="pie-tabla"><button type="button" className="enlace" onClick={() => setRenglones([...renglones, { ...VACIO, tipo: renglones.at(-1)?.tipo ?? 'bobina' }])}>+ Otro renglón</button>
            {catalogoError && <span className="error pequeno"> No se pudo cargar el catálogo de productos; escribe la descripción del artículo.</span>}
            <span className="tenue pequeno"> · Escribe en Descripción y elige el artículo de la lista: el tipo se ajusta solo y, si el catálogo tiene el peso por pieza, los kg se calculan con las piezas. Bobinas: una por renglón.</span></p>
        </div>
        <h3>Transporte</h3>
        <div className="formulario tres-columnas sin-relleno">
          {([['chofer', 'Chofer'], ['cedula', 'Cédula'], ['placa', 'Placa'], ['transporte', 'Empresa de transporte'], ['telefono', 'Teléfono']] as const).map(([k, t]) => (
            <label key={k}>{t}{OPC_T[k]
              ? <Combo etiqueta={t} valor={transporte[k]} onCambio={(v) => cambiarTransporte(k, v)} opciones={OPC_T[k].map((v) => ({ valor: v }))} />
              : <input value={transporte[k]} onChange={(e) => cambiarTransporte(k, e.target.value)} />}</label>
          ))}
        </div>
        {transportes.length > 0 && <p className="tenue pequeno">Elige una placa o un chofer que ya usaste y se completan los demás datos.</p>}
        <label>Comentarios<textarea rows={2} value={comentarios} onChange={(e) => setComentarios(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <div className="acciones">
          <button className="primario" disabled={ocupado}>{ocupado ? 'Enviando…' : 'Enviar aviso'}</button>
          <button type="button" className="secundario" onClick={onCerrar}>Cancelar</button>
        </div>
      </form>
    </Modal>
  )
}

export default function ClienteAvisos(_: { usuario: Usuario }) {
  const [lista, setLista] = useState<AvisoEntrada[] | null>(null)
  const [nuevo, setNuevo] = useState(false)
  const [abierto, setAbierto] = useState<AvisoEntrada | null>(null)
  const [cancelando, setCancelando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [aviso, setAviso] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(() => {
    pedir<AvisoEntrada[]>('/api/avisos-entrada').then(setLista).catch((e: Error) => setError(e.message))
  }, [])
  useEffect(cargar, [cargar])

  async function cancelar() {
    if (!abierto) return
    try {
      setAbierto(await pedir<AvisoEntrada>(`/api/avisos-entrada/${abierto.id}/cancelar`, { metodo: 'POST', cuerpo: { motivo: motivo.trim() } }))
      setCancelando(false)
      cargar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cancelar')
    }
  }

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>Entradas de material</h1>
        <button className="primario" onClick={() => { setAviso(null); setNuevo(true) }}>Anunciar entrada</button>
      </div>
      <p className="tenue">Avísanos qué material va a llegar a nuestro patio, cuándo y en qué transporte, para tener todo listo al
        recibirlo. Cuando llegue y lo registremos, lo verás en Mi inventario.</p>
      {aviso && <div className="exito">{aviso}</div>}
      {error && <p className="error">{error}</p>}
      {lista && lista.length === 0 && <p className="vacio">Todavía no has anunciado entradas.</p>}
      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead><tr><th>N°</th><th>Llega</th><th>Documento</th><th className="n">Renglones</th><th className="n">Kg</th><th>Estado</th></tr></thead>
            <tbody>
              {lista.map((a) => (
                <tr key={a.id} tabIndex={0} onClick={() => { setAbierto(a); setCancelando(false) }}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAbierto(a) }}>
                  <td className="fuerte">{a.numero}</td>
                  <td>{a.fecha_estimada ? fecha(a.fecha_estimada) : '—'}</td>
                  <td>{[a.documento_tipo, a.documento_numero].filter(Boolean).join(' ') || '—'}</td>
                  <td className="n">{a.renglones.length}</td>
                  <td className="n">{kg(a.total_kg)}</td>
                  <td><EstadoAvisoChip estado={a.estado} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {nuevo && <NuevoAviso anteriores={lista ?? []} onCerrar={() => setNuevo(false)}
        onHecho={(a) => { setNuevo(false); setAviso(`Aviso ${a.numero} enviado. Prosifer lo tendrá en cuenta para recibir el material.`); cargar() }} />}
      {abierto && (
        <Modal titulo={`Aviso de entrada ${abierto.numero}`} onCerrar={() => setAbierto(null)} ancho>
          <p><EstadoAvisoChip estado={abierto.estado} /> · enviado el {fecha(abierto.fecha)}</p>
          <DetalleAviso a={abierto} />
          {abierto.estado === 'pendiente' && !cancelando && (
            <div className="acciones"><button className="peligro" onClick={() => setCancelando(true)}>Cancelar aviso</button></div>
          )}
          {cancelando && (
            <div className="confirmacion peligro-caja">
              <label>¿Por qué lo cancelas?<input value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus /></label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void cancelar()}>Cancelar aviso</button>
                <button className="secundario" onClick={() => setCancelando(false)}>Volver</button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </section>
  )
}
