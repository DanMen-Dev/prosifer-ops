import { useEffect, useState, type FormEvent } from 'react'
import { consulta, pedir, type Producto, type Tercero } from '../api'
import { fecha } from '../formato'
import GeneradorProducto from './GeneradorProducto'
import Modal from './Modal'

type Pestana = 'clientes' | 'productos'

/** Clientes y productos: la ficha que usan las notas de entrega y las cotizaciones. */
export default function Catalogos() {
  const [pestana, setPestana] = useState<Pestana>('clientes')
  return (
    <section>
      <div className="encabezado-seccion">
        <h1>Clientes y productos</h1>
        <nav className="subpestanas" aria-label="Catálogo">
          <button className={pestana === 'clientes' ? 'activa' : ''} onClick={() => setPestana('clientes')}>Clientes</button>
          <button className={pestana === 'productos' ? 'activa' : ''} onClick={() => setPestana('productos')}>Productos</button>
        </nav>
      </div>
      {pestana === 'clientes' ? <Clientes /> : <Productos />}
    </section>
  )
}

/** Busca al escribir, con una pausa corta para no pedir en cada tecla. */
function useBusqueda<T>(ruta: (q: string) => string, recarga: string): [string, (q: string) => void, T[] | null, string | null] {
  const [q, setQ] = useState('')
  const [lista, setLista] = useState<T[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const reloj = setTimeout(() => {
      pedir<T[]>(ruta(q.trim())).then((r) => { setLista(r); setError(null) })
        .catch((e: Error) => setError(e.message))
    }, 250)
    return () => clearTimeout(reloj)
  }, [q, recarga]) // ruta cambia en cada render; lo que cambia la búsqueda es q y recarga
  return [q, setQ, lista, error]
}

// ---------------------------------------------------------------- clientes

const CAMPOS_CLIENTE: [keyof Tercero, string, string?][] = [
  ['nombre', 'Nombre o razón social'],
  ['rif', 'RIF', 'J-12345678-9'],
  ['telefono', 'Teléfono'],
  ['correo', 'Correo'],
  ['direccion', 'Dirección'],
  ['ciudad', 'Ciudad'],
  ['estado_region', 'Estado'],
  ['forma_pago', 'Forma de pago', 'Contado'],
  ['vendedor', 'Vendedor'],
]

function Clientes() {
  const [recarga, setRecarga] = useState(0)
  const [q, setQ, lista, error] = useBusqueda<Tercero>(
    (texto) => `/api/terceros${consulta({ q: texto || null, rol: 'cliente' })}`, String(recarga))
  const [abierto, setAbierto] = useState<Tercero | 'nuevo' | null>(null)

  return (
    <>
      <div className="filtros">
        <label className="ancho-completo">Buscar
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre, RIF o ciudad" autoFocus />
        </label>
        <div className="acciones-filtro"><button className="primario" onClick={() => setAbierto('nuevo')}>Nuevo cliente</button></div>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="tabla-envoltura tarjeta">
        <table className="tabla">
          <thead><tr><th>Cliente</th><th>RIF</th><th>Ciudad</th><th>Teléfono</th><th>Vendedor</th><th>Pago</th></tr></thead>
          <tbody>
            {(lista ?? []).map((t) => (
              <tr key={t.id} className={`${t.activo ? '' : 'agotada'}`} onClick={() => setAbierto(t)}>
                <td className="fuerte">{t.nombre}</td>
                <td className="codigo">{t.rif ?? '—'}</td>
                <td>{[t.ciudad, t.estado_region].filter(Boolean).join(', ') || '—'}</td>
                <td>{t.telefono ?? '—'}</td>
                <td>{t.vendedor ?? '—'}</td>
                <td>{t.forma_pago ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista !== null && lista.length === 0 && <p className="vacio">Ningún cliente coincide.</p>}
        {lista !== null && lista.length > 0 && <p className="pie-tabla tenue pequeno">{lista.length} clientes</p>}
      </div>
      {abierto && (
        <FichaCliente cliente={abierto === 'nuevo' ? null : abierto} onCerrar={() => setAbierto(null)}
          onGuardado={() => { setAbierto(null); setRecarga((n) => n + 1) }} />
      )}
    </>
  )
}

function FichaCliente({ cliente, onCerrar, onGuardado }: { cliente: Tercero | null; onCerrar: () => void; onGuardado: () => void }) {
  const [datos, setDatos] = useState<Record<string, string>>(() =>
    Object.fromEntries(CAMPOS_CLIENTE.map(([k]) => [k, String((cliente?.[k] as string | null | undefined) ?? '')])))
  const [activo, setActivo] = useState(cliente?.activo ?? true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setGuardando(true)
    // Vacío = sin dato; solo se envía lo que cambió, así la auditoría registra cambios reales.
    const valor = (k: string) => datos[k].trim() || null
    const cuerpo: Record<string, unknown> = {}
    for (const [k] of CAMPOS_CLIENTE) {
      if (!cliente || valor(k) !== ((cliente[k] as string | null | undefined) ?? null)) cuerpo[k] = valor(k)
    }
    if (cliente && activo !== cliente.activo) cuerpo.activo = activo
    try {
      if (cliente) {
        if (Object.keys(cuerpo).length) await pedir(`/api/terceros/${cliente.id}`, { metodo: 'PATCH', cuerpo })
      } else {
        await pedir('/api/terceros', { metodo: 'POST', cuerpo: { ...cuerpo, es_cliente: true } })
      }
      onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal titulo={cliente ? cliente.nombre : 'Nuevo cliente'} onCerrar={onCerrar} ancho>
      <form className="formulario dos-columnas sin-relleno" onSubmit={guardar}>
        {CAMPOS_CLIENTE.map(([k, etiqueta, ejemplo]) => (
          <label key={k} className={k === 'nombre' || k === 'direccion' ? 'ancho-completo' : ''}>
            {etiqueta}
            <input value={datos[k]} placeholder={ejemplo} required={k === 'nombre'}
              type={k === 'correo' ? 'email' : 'text'} onChange={(e) => setDatos({ ...datos, [k]: e.target.value })} />
          </label>
        ))}
        {cliente && (
          <label className="en-linea-label">
            <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo
          </label>
        )}
        {cliente?.cliente_desde && <p className="tenue pequeno">Cliente desde {fecha(cliente.cliente_desde)}</p>}
        {error && <p className="error ancho-completo">{error}</p>}
        <div className="acciones ancho-completo">
          <button className="primario" disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>
          <button type="button" className="secundario" onClick={onCerrar}>Cancelar</button>
        </div>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------- productos

const kgUnidad = new Intl.NumberFormat('es-VE', { maximumFractionDigits: 4 })

function Productos() {
  const [recarga, setRecarga] = useState(0)
  const [inactivos, setInactivos] = useState(false)
  const [q, setQ, lista, error] = useBusqueda<Producto>(
    (texto) => `/api/productos${consulta({ q: texto || null, limite: 1000, incluir_inactivos: inactivos || null })}`,
    `${recarga}-${inactivos}`)
  const [abierto, setAbierto] = useState<Producto | 'nuevo' | 'generador' | null>(null)

  return (
    <>
      <div className="filtros">
        <label className="ancho-completo">Buscar
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Código o nombre: lamina 3,00 2400" autoFocus />
        </label>
        <label className="en-linea-label">
          <input type="checkbox" checked={inactivos} onChange={(e) => setInactivos(e.target.checked)} /> Ver inactivos
        </label>
        <div className="acciones-filtro"><button className="primario" onClick={() => setAbierto('generador')}>Nuevo producto</button></div>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="tabla-envoltura tarjeta">
        <table className="tabla">
          <thead><tr><th>Producto</th><th>Código</th><th className="n">Peso por unidad</th></tr></thead>
          <tbody>
            {(lista ?? []).map((p) => (
              <tr key={p.id} className={`${p.activo ? '' : 'agotada'}`} onClick={() => setAbierto(p)}>
                <td>{p.nombre}</td>
                <td className="codigo">{p.codigo}</td>
                <td className="n">{p.peso_unitario_kg === null ? '—' : `${kgUnidad.format(Number(p.peso_unitario_kg))} kg`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista !== null && lista.length === 0 && <p className="vacio">Ningún producto coincide.</p>}
        {lista !== null && lista.length > 0 && (
          <p className="pie-tabla tenue pequeno">{lista.length === 1000 ? 'Primeros 1.000: escribe para acotar' : `${lista.length} productos`}</p>
        )}
      </div>
      {abierto === 'generador' && (
        <GeneradorProducto onCerrar={() => setAbierto(null)} onAMano={() => setAbierto('nuevo')}
          onCreado={() => { setAbierto(null); setRecarga((n) => n + 1) }} />
      )}
      {abierto && abierto !== 'generador' && (
        <FichaProducto producto={abierto === 'nuevo' ? null : abierto} onCerrar={() => setAbierto(null)}
          onGuardado={() => { setAbierto(null); setRecarga((n) => n + 1) }} />
      )}
    </>
  )
}

function FichaProducto({ producto, onCerrar, onGuardado }: { producto: Producto | null; onCerrar: () => void; onGuardado: () => void }) {
  const [codigo, setCodigo] = useState(producto?.codigo ?? '')
  const [nombre, setNombre] = useState(producto?.nombre ?? '')
  const [peso, setPeso] = useState(producto?.peso_unitario_kg ?? '')
  const [activo, setActivo] = useState(producto?.activo ?? true)
  const [error, setError] = useState<string | null>(null)

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const pesoNum = peso.trim() === '' ? null : peso.trim().replace(',', '.')
    if (pesoNum !== null && Number.isNaN(Number(pesoNum))) { setError('El peso debe ser un número, por ejemplo 44,51'); return }
    try {
      if (producto) {
        await pedir(`/api/productos/${producto.id}`, { metodo: 'PATCH', cuerpo: { nombre, peso_unitario_kg: pesoNum, activo } })
      } else {
        await pedir('/api/productos', { metodo: 'POST', cuerpo: { codigo: codigo.trim() || null, nombre, peso_unitario_kg: pesoNum } })
      }
      onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
    }
  }

  return (
    <Modal titulo={producto ? 'Producto' : 'Nuevo producto'} onCerrar={onCerrar}>
      <form className="formulario sin-relleno" onSubmit={guardar}>
        <label>Código
          <input className="codigo" value={codigo} disabled={!!producto}
            placeholder={producto ? undefined : 'Vacío: lo asigna la app'}
            onChange={(e) => setCodigo(e.target.value.toUpperCase())} />
        </label>
        {!producto && (
          <p className="tenue pequeno sin-margen">
            Para lo que no está en el generador (puertas, accesorios…) deja el código vacío: la app lo arma con las tres
            primeras letras del nombre y un correlativo (Puerta… → PUE0001). El nombre lleva el detalle.
          </p>
        )}
        {producto && <p className="tenue pequeno sin-margen">El código no se cambia porque ya está en documentos emitidos. Si está mal, desactiva este producto y crea otro.</p>}
        <label>Nombre<input value={nombre} required onChange={(e) => setNombre(e.target.value)} /></label>
        <label>Peso por unidad (kg)<input inputMode="decimal" value={peso} placeholder="44,51" onChange={(e) => setPeso(e.target.value)} /></label>
        {producto && (
          <label className="en-linea-label">
            <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo
          </label>
        )}
        {error && <p className="error">{error}</p>}
        <div className="acciones">
          <button className="primario">Guardar</button>
          <button type="button" className="secundario" onClick={onCerrar}>Cancelar</button>
        </div>
      </form>
    </Modal>
  )
}
