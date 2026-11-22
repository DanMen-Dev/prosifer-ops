import { useEffect, useState, type FormEvent } from 'react'
import { consulta, pedir, reciboEntrada, type Producto, type ResumenEntradaExistencia, type Tercero } from '../api'
import { hoyIso, kg } from '../formato'
import GeneradorProducto from './GeneradorProducto'
import Modal from './Modal'

interface Formulario {
  codigo: string
  descripcion: string
  propietario: string
  unidades: string
  peso: string
  calidad: string
  documento_tipo: string
  documento_numero: string
  fecha: string
  observacion: string
}

const INICIAL: Formulario = {
  codigo: '', descripcion: '', propietario: '', unidades: '', peso: '', calidad: '', documento_tipo: 'Nota de entrega',
  documento_numero: '', fecha: hoyIso(), observacion: '',
}

const DOCUMENTOS = ['Nota de entrega', 'Factura', 'Liberación', 'Devolución', 'Conteo físico']
const NOMBRE_TIPO: Record<string, string> = { lamina: 'Lámina', perfil: 'Perfil', general: 'Producto general' }
const piezas = new Intl.NumberFormat('es-VE')

/** Entrada por piezas de láminas, perfiles o productos generales que no salen de una OC de la planta. */
export type InicialExistencia = Partial<Formulario>

/** `inicial`: datos que vienen de un aviso de entrada del cliente (se revisan antes de guardar). */
export default function EntradaExistencia({ onVerInventario, inicial, aviso, onGuardada }: {
  onVerInventario: () => void; inicial?: InicialExistencia | null; aviso?: string | null
  onGuardada?: (piezaId: number, texto: string) => void
}) {
  const [f, setF] = useState<Formulario>({ ...INICIAL, ...(inicial ?? {}) })
  useEffect(() => { if (inicial) setF({ ...INICIAL, ...inicial }) }, [inicial])
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [sugeridos, setSugeridos] = useState<Producto[]>([])
  const [producto, setProducto] = useState<Producto | null>(null)
  const [resumen, setResumen] = useState<ResumenEntradaExistencia | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<string | null>(null)
  const [ultimaEntrada, setUltimaEntrada] = useState<{ id: number; cliente: string } | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [generador, setGenerador] = useState(false)

  useEffect(() => {
    pedir<Tercero[]>('/api/terceros').then((t) => setTerceros(t.filter((x) => x.activo))).catch(() => {})
  }, [])

  // Autocompletar del catálogo: busca por palabras en código y nombre.
  useEffect(() => {
    const q = f.codigo.trim()
    if (q.length < 2) { setSugeridos([]); return }
    const reloj = setTimeout(() => {
      pedir<Producto[]>(`/api/productos${consulta({ q, limite: 30 })}`).then(setSugeridos).catch(() => setSugeridos([]))
    }, 200)
    return () => clearTimeout(reloj)
  }, [f.codigo])

  // Al escribir un código exacto del catálogo se llenan descripción y peso.
  useEffect(() => {
    const p = sugeridos.find((x) => x.codigo === f.codigo.trim().toUpperCase()) ?? null
    setProducto(p)
    if (p) setF((v) => ({ ...v, descripcion: p.nombre, peso: v.peso || (p.peso_unitario_kg ?? '') }))
  }, [sugeridos, f.codigo])

  const campo = (k: keyof Formulario) => ({
    value: f[k], onChange: (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value }),
  })
  const dueno = terceros.find((t) => t.nombre.toLowerCase() === f.propietario.trim().toLowerCase())
  const formulario = f

  function cuerpo(confirmar: boolean, f: Formulario = formulario) {
    if (!dueno) throw new Error('Elige el dueño de la lista.')
    if (!/^\d+$/.test(f.unidades.trim()) || Number(f.unidades) <= 0) throw new Error('Las piezas van en números enteros mayores que cero.')
    return {
      codigo_producto: f.codigo.trim().toUpperCase(),
      descripcion: f.descripcion.trim() || null,
      propietario_id: dueno.id,
      unidades: Number(f.unidades),
      peso_unitario_kg: f.peso.trim() ? f.peso.trim().replace(',', '.') : null,
      calidad: f.calidad.trim() || null,
      documento_tipo: f.documento_tipo,
      documento_numero: f.documento_numero.trim(),
      fecha: f.fecha,
      observacion: f.observacion.trim() || null,
      confirmar,
      clave_idempotencia: confirmar ? clave : null,
    }
  }

  async function revisar(e: FormEvent) {
    e.preventDefault()
    await revisarCon(f)
  }

  // «Sumar a la existencia que ya tiene»: cambia el código por el de esa existencia y vuelve a revisar.
  async function sumarA(codigo: string, descripcion: string | null) {
    const nuevo = { ...f, codigo, descripcion: descripcion ?? f.descripcion }
    setF(nuevo)
    setResumen(null)
    await revisarCon(nuevo)
  }

  async function revisarCon(datos: Formulario) {
    setError(null)
    setHecho(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenEntradaExistencia>('/api/entradas/existencias', { metodo: 'POST', cuerpo: cuerpo(false, datos) })
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
      const r = await pedir<ResumenEntradaExistencia>('/api/entradas/existencias', { metodo: 'POST', cuerpo: cuerpo(true) })
      setUltimaEntrada(r.documento_id ? { id: r.documento_id, cliente: r.propietario } : null)
      if (r.pieza_id) onGuardada?.(r.pieza_id, `${piezas.format(r.unidades)} piezas de ${r.codigo_producto}`)
      setHecho(`Entraron ${piezas.format(r.unidades)} piezas de ${r.codigo_producto} (${r.propietario}). Ahora hay ${piezas.format(r.existencia_despues)}.`)
      setResumen(null)
      setF({ ...INICIAL, propietario: f.propietario, documento_tipo: f.documento_tipo, documento_numero: f.documento_numero, fecha: f.fecha })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>Entrada de láminas, perfiles y generales</h1>
      </div>
      <p className="tenue">
        Para compras, liberaciones recibidas, devoluciones o un conteo inicial. Lo que sale de una OC de la planta entra
        solo con la orden. Se suma a la existencia de ese código y ese dueño.
      </p>
      {hecho && (
        <div className="exito">
          {hecho} <button className="enlace" onClick={onVerInventario}>Ver inventario</button>
          {ultimaEntrada && (
            <div className="pequeno">
              Las entradas del mismo documento y fecha van en un solo recibo:{' '}
              <button className="enlace" onClick={() => { reciboEntrada(ultimaEntrada.id, ultimaEntrada.cliente, false).catch((e: Error) => setError(e.message)) }}>ver recibo</button>
              {' · '}
              <button className="enlace" onClick={() => { reciboEntrada(ultimaEntrada.id, ultimaEntrada.cliente, true).catch((e: Error) => setError(e.message)) }}>guardar en carpeta</button>
            </div>
          )}
        </div>
      )}

      {aviso && <div className="alerta">Precargado desde el {aviso}. Revisa los datos contra el material y el documento que llegó antes de guardar.</div>}
      <form className="tarjeta formulario dos-columnas" onSubmit={revisar}>
        <label className="ancho-completo">
          <span>Producto (código o nombre){' '}
            <button type="button" className="enlace pequeno" onClick={() => setGenerador(true)}>¿No está en el catálogo? Crear producto</button></span>
          <input list="lista-productos-entrada" {...campo('codigo')} placeholder="TUB000HPE090… o «tubo 1 x 1 0,90»" required />
          <datalist id="lista-productos-entrada">
            {sugeridos.map((p) => <option key={p.id} value={p.codigo}>{p.nombre}</option>)}
          </datalist>
          {f.codigo.trim().length >= 6 && !producto && /\d/.test(f.codigo) && (
            <span className="tenue pequeno">Este código no está en el catálogo: se puede registrar con su descripción y peso,
              o <button type="button" className="enlace pequeno" onClick={() => setGenerador(true)}>crear el producto</button> para que quede bien codificado.</span>
          )}
        </label>
        <label className="ancho-completo">
          Descripción {producto && <span className="tenue pequeno">(del catálogo)</span>}
          <input {...campo('descripcion')} placeholder="Se llena con el catálogo; escríbela si el código es nuevo" />
        </label>
        <label>
          Dueño
          <input list="lista-terceros-entrada" {...campo('propietario')} placeholder="Escribe para buscar" required />
          <datalist id="lista-terceros-entrada">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
        </label>
        <label>Piezas que entran<input inputMode="numeric" {...campo('unidades')} required /></label>
        <label>Peso por pieza (kg)<input inputMode="decimal" {...campo('peso')} placeholder="Del catálogo" /></label>
        <label>Calidad<input {...campo('calidad')} placeholder="1er, 1er-F, 2da-A…" /></label>
        <label>
          Documento
          <select value={f.documento_tipo} onChange={(e) => setF({ ...f, documento_tipo: e.target.value })}>
            {DOCUMENTOS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </label>
        <label>Número del documento<input {...campo('documento_numero')} required /></label>
        <label>Fecha<input type="date" {...campo('fecha')} required /></label>
        <label className="ancho-completo">Observación<textarea rows={2} {...campo('observacion')} /></label>
        {error && <p className="error ancho-completo">{error}</p>}
        <div className="acciones ancho-completo">
          <button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar entrada'}</button>
        </div>
      </form>

      {generador && (
        <GeneradorProducto onCerrar={() => setGenerador(false)}
          referencia={f.descripcion.trim() ? { descripcion: f.descripcion.trim(), peso_unitario_kg: f.peso.trim().replace(',', '.') || undefined } : null}
          onCreado={(p) => {
            // el producto nuevo (o el que ya existía con ese código) queda elegido en la entrada
            setGenerador(false)
            setSugeridos([p, ...sugeridos.filter((x) => x.id !== p.id)])
            setF({ ...f, codigo: p.codigo, descripcion: p.nombre, peso: p.peso_unitario_kg ? String(p.peso_unitario_kg).replace('.', ',') : f.peso })
          }} />
      )}
      {resumen && (
        <Modal titulo="Confirma la entrada" onCerrar={() => setResumen(null)}>
          <dl className="datos">
            <dt>Producto</dt><dd><div className="codigo">{resumen.codigo_producto}</div><div>{resumen.descripcion}</div></dd>
            <dt>Tipo</dt><dd>{NOMBRE_TIPO[resumen.tipo] ?? resumen.tipo}</dd>
            <dt>Dueño</dt><dd>{resumen.propietario}</dd>
            <dt>Entran</dt><dd className="fuerte">{piezas.format(resumen.unidades)} piezas · {kg(resumen.kg)}</dd>
            <dt>Peso por pieza</dt><dd>{resumen.peso_unitario_kg} kg</dd>
            <dt>Existencia</dt><dd>{piezas.format(resumen.existencia_antes)} → <strong>{piezas.format(resumen.existencia_despues)}</strong> piezas</dd>
          </dl>
          {(resumen.similares ?? []).length > 0 && (
            <div className="alerta">
              <strong>{resumen.propietario} ya tiene este material con otro código.</strong> Con {resumen.codigo_producto} las
              piezas quedarían en una línea aparte y no se sumarían.
              <ul className="lista-similares">
                {(resumen.similares ?? []).map((x) => (
                  <li key={x.pieza_id}>
                    <span className="codigo">{x.codigo}</span> · {x.descripcion} · <strong>{piezas.format(x.saldo_unidades ?? 0)} piezas</strong>{' '}
                    <button className="primario" disabled={ocupado} onClick={() => void sumarA(x.codigo, x.descripcion)}>Sumar a {x.codigo}</button>
                  </li>
                ))}
              </ul>
              <span className="tenue pequeno">Si de verdad es otro producto (otro acero u otra calidad), confirma con el código nuevo.</span>
            </div>
          )}
          {resumen.avisos.filter((a) => !a.includes('quedarían en una línea aparte')).length > 0 && <div className="alerta"><strong>Revisa:</strong><ul>
            {resumen.avisos.filter((a) => !a.includes('quedarían en una línea aparte')).map((a) => <li key={a}>{a}</li>)}</ul></div>}
          <div className="acciones">
            <button className={(resumen.similares ?? []).length ? 'secundario' : 'primario'} disabled={ocupado} onClick={() => void confirmar()}>
              {ocupado ? 'Guardando…' : (resumen.similares ?? []).length ? `Guardar con ${resumen.codigo_producto}` : 'Confirmar y guardar'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </Modal>
      )}
    </section>
  )
}
