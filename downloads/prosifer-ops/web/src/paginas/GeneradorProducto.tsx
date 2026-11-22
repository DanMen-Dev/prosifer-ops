import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { pedir, type Producto } from '../api'
import Modal from './Modal'

interface CampoFamilia {
  clave: 'subtipo' | 'espesor' | 'medida1' | 'medida2' | 'largo_mm'
  etiqueta: string
  tipo: 'mm' | 'pulgadas' | 'mm_o_pulgadas' | 'opcion' | 'numero'
  opciones: string[]
  obligatorio: boolean
}

interface FamiliaGen {
  clave: string
  nombre: string
  prefijo: string
  materiales: { codigo: string; nombre: string }[]
  campos: CampoFamilia[]
}

interface Generado { codigo: string; nombre: string; existente: Producto | null }

/** Lo que describió el cliente en su aviso de entrada: sirve para precargar familia, material y medidas. */
export interface ReferenciaProducto {
  descripcion: string
  tipo?: string                 // bobina | fleje | lamina | perfil | general
  tipo_acero?: string
  espesor_mm?: string
  ancho_mm?: string
  largo_mm?: string
  peso_unitario_kg?: string
}

const coma = (v?: string) => (v ? String(Number(v)).replace('.', ',') : '')

const AYUDA: Record<CampoFamilia['tipo'], string> = {
  mm: 'en mm, por ejemplo 2,50',
  pulgadas: "en pulgadas, por ejemplo 1 1/2''",
  mm_o_pulgadas: "100mm o 1 1/2''",
  opcion: '',
  numero: '',
}

/** Alta de un producto con la regla de la app: se elige la familia, se llenan las medidas y la app
 *  arma el código y el nombre. Los productos que no encajan en ninguna familia se cargan a mano. */
export default function GeneradorProducto({ onCerrar, onCreado, onAMano, referencia }: {
  onCerrar: () => void; onCreado: (p: Producto) => void
  onAMano?: () => void            // sin él, «cargar a mano» se hace aquí mismo (código, nombre y peso)
  referencia?: ReferenciaProducto | null   // con referencia (aunque sea null) se puede «Usar este producto» si ya existe
}) {
  const [familias, setFamilias] = useState<FamiliaGen[]>([])
  const [clave, setClave] = useState('')
  const [material, setMaterial] = useState('')
  const [valores, setValores] = useState<Record<string, string>>({})
  const [segunda, setSegunda] = useState('')
  const [peso, setPeso] = useState(referencia?.peso_unitario_kg ? coma(referencia.peso_unitario_kg) : '')
  const [aMano, setAMano] = useState(false)
  const [manual, setManual] = useState({ codigo: '', nombre: referencia?.descripcion ?? '' })
  const [generado, setGenerado] = useState<Generado | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    pedir<FamiliaGen[]>('/api/productos/familias').then((fs) => {
      setFamilias(fs)
      // lámina, bobina y fleje del aviso: su familia sale directa
      const t = referencia?.tipo
      if (t === 'lamina' || t === 'bobina' || t === 'fleje') {
        const f = fs.find((x) => x.clave === t)
        if (f) elegirFamilia(f.clave, f)
      }
    }).catch((e: Error) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const familia = useMemo(() => familias.find((f) => f.clave === clave) ?? null, [familias, clave])

  function elegirFamilia(c: string, dada?: FamiliaGen) {
    setClave(c)
    const f = dada ?? familias.find((x) => x.clave === c)
    const acero = referencia?.tipo_acero?.toUpperCase()
    setMaterial(f?.materiales.find((m) => m.codigo === acero)?.codigo ?? f?.materiales[0]?.codigo ?? '')
    // medidas que dio el cliente, en los campos que tenga la familia
    const v: Record<string, string> = {}
    const tiene = (k: string) => f?.campos.some((x) => x.clave === k && x.tipo !== 'opcion' && x.tipo !== 'pulgadas')
    if (referencia) {
      if (tiene('espesor') && referencia.espesor_mm) v.espesor = coma(referencia.espesor_mm)
      if (tiene('largo_mm') && referencia.largo_mm) v.largo_mm = coma(referencia.largo_mm)
      if (['lamina', 'bobina', 'fleje'].includes(c) && referencia.ancho_mm) v.medida1 = coma(referencia.ancho_mm)
    }
    setValores(v)
    setGenerado(null)
    setError(null)
  }

  async function crearAMano(e: FormEvent) {
    e.preventDefault()
    const pesoNum = peso.trim() === '' ? null : peso.trim().replace(',', '.')
    if (pesoNum !== null && Number.isNaN(Number(pesoNum))) { setError('El peso debe ser un número, por ejemplo 44,51'); return }
    setError(null)
    try {
      onCreado(await pedir<Producto>('/api/productos', {
        metodo: 'POST', cuerpo: { codigo: manual.codigo.trim().toUpperCase(), nombre: manual.nombre.trim(), peso_unitario_kg: pesoNum },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear')
    }
  }

  function poner(k: string, v: string) {
    setValores({ ...valores, [k]: v })
    setGenerado(null)
  }

  async function armar(e: FormEvent) {
    e.preventDefault()
    if (!familia) return
    setError(null)
    setOcupado(true)
    try {
      const largo = valores.largo_mm?.trim().replace(/\./g, '').replace(',', '.')
      setGenerado(await pedir<Generado>('/api/productos/generar', {
        metodo: 'POST',
        cuerpo: {
          familia: familia.clave, material, subtipo: valores.subtipo || null, espesor: valores.espesor || null,
          medida1: valores.medida1 || null, medida2: valores.medida2 || null,
          largo_mm: largo ? Number(largo) : null, segunda: segunda || null,
        },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo armar el código')
    } finally {
      setOcupado(false)
    }
  }

  async function crear() {
    if (!generado) return
    const pesoNum = peso.trim() === '' ? null : peso.trim().replace(',', '.')
    if (pesoNum !== null && Number.isNaN(Number(pesoNum))) { setError('El peso debe ser un número, por ejemplo 44,51'); return }
    setError(null)
    try {
      onCreado(await pedir<Producto>('/api/productos', {
        metodo: 'POST', cuerpo: { codigo: generado.codigo, nombre: generado.nombre, peso_unitario_kg: pesoNum },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear')
    }
  }

  const delCliente = referencia && (
    <div className="alerta">
      <strong>Lo describió el cliente:</strong> «{referencia.descripcion}»
      {[referencia.tipo_acero, referencia.espesor_mm && `${coma(referencia.espesor_mm)} mm`, referencia.ancho_mm && `${coma(referencia.ancho_mm)} mm`,
        referencia.largo_mm && `${coma(referencia.largo_mm)} mm`].filter(Boolean).length > 0 &&
        <span className="tenue"> · {[referencia.tipo_acero, referencia.espesor_mm && `${coma(referencia.espesor_mm)} mm`,
          referencia.ancho_mm && `${coma(referencia.ancho_mm)} mm`, referencia.largo_mm && `${coma(referencia.largo_mm)} mm`].filter(Boolean).join(' × ')}</span>}
      <br /><span className="pequeno">Revisa las medidas con el material que llegó: el código lo arma la regla de la familia.</span>
    </div>
  )

  if (aMano) {
    return (
      <Modal titulo="Nuevo producto (a mano)" onCerrar={onCerrar}>
        {delCliente}
        <form className="formulario sin-relleno" onSubmit={crearAMano}>
          <label>Código<input value={manual.codigo} required minLength={3} maxLength={40} autoFocus
            onChange={(e) => setManual({ ...manual, codigo: e.target.value })} placeholder="Con la convención de la empresa" /></label>
          <label>Nombre<input value={manual.nombre} required maxLength={200} onChange={(e) => setManual({ ...manual, nombre: e.target.value })} /></label>
          <label>Peso por unidad (kg)<input inputMode="decimal" value={peso} placeholder="44,51" onChange={(e) => setPeso(e.target.value)} /></label>
          {error && <p className="error">{error}</p>}
          <div className="acciones">
            <button className="primario">Crear producto</button>
            <button type="button" className="secundario" onClick={() => { setAMano(false); setError(null) }}>Volver al generador</button>
          </div>
        </form>
      </Modal>
    )
  }

  return (
    <Modal titulo="Nuevo producto" onCerrar={onCerrar}>
      {delCliente}
      <form className="formulario sin-relleno" onSubmit={armar}>
        <label>Familia
          <select value={clave} onChange={(e) => elegirFamilia(e.target.value)} required autoFocus>
            <option value="">Elige la familia…</option>
            {familias.map((f) => <option key={f.clave} value={f.clave}>{f.nombre} ({f.prefijo})</option>)}
          </select>
        </label>
        {familia && familia.materiales.length > 1 && (
          <label>Material
            <select value={material} onChange={(e) => { setMaterial(e.target.value); setGenerado(null) }}>
              {familia.materiales.map((m) => <option key={m.codigo} value={m.codigo}>{m.nombre} ({m.codigo})</option>)}
            </select>
          </label>
        )}
        {familia?.campos.map((c) => (
          <label key={c.clave}>{c.etiqueta}{!c.obligatorio && <span className="tenue pequeno"> (opcional)</span>}
            {c.tipo === 'opcion' ? (
              <select value={valores[c.clave] ?? ''} required={c.obligatorio} onChange={(e) => poner(c.clave, e.target.value)}>
                <option value="">Elige…</option>
                {c.opciones.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input value={valores[c.clave] ?? ''} required={c.obligatorio} placeholder={AYUDA[c.tipo]}
                inputMode={c.tipo === 'numero' ? 'decimal' : undefined} onChange={(e) => poner(c.clave, e.target.value)} />
            )}
          </label>
        ))}
        {familia && (
          <label>Calidad
            <select value={segunda} onChange={(e) => { setSegunda(e.target.value); setGenerado(null) }}>
              <option value="">Primera</option><option value="A">Segunda A</option>
              <option value="B">Segunda B</option><option value="C">Segunda C</option>
            </select>
          </label>
        )}
        {error && <p className="error">{error}</p>}
        {generado && (
          <div className={generado.existente ? 'alerta' : 'confirmacion'}>
            <p className="sin-margen"><span className="codigo fuerte">{generado.codigo}</span></p>
            <p className="sin-margen">{generado.nombre}</p>
            {generado.existente && <p className="sin-margen pequeno">Ya existe en el catálogo: «{generado.existente.nombre}». No hace falta crearlo.</p>}
            {generado.existente && referencia !== undefined && (
              <button type="button" className="primario" onClick={() => onCreado(generado.existente as Producto)}>Usar este producto</button>
            )}
          </div>
        )}
        {generado && !generado.existente && (
          <label>Peso por unidad (kg)<input inputMode="decimal" value={peso} placeholder="44,51" onChange={(e) => setPeso(e.target.value)} /></label>
        )}
        <div className="acciones">
          {familia && <button className={generado ? 'secundario' : 'primario'} disabled={ocupado}>{ocupado ? 'Armando…' : 'Armar código'}</button>}
          {generado && !generado.existente && <button type="button" className="primario" onClick={() => void crear()}>Crear producto</button>}
          <button type="button" className="enlace" onClick={() => (onAMano ? onAMano() : setAMano(true))}>No encaja en ninguna familia: cargar a mano</button>
        </div>
      </form>
    </Modal>
  )
}
