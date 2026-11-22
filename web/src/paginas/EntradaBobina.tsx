import { useEffect, useState, type FormEvent } from 'react'
import { pedir, type Norma, type ResumenEntrada, type Tercero, type TipoAcero } from '../api'
import { hoyIso, kg } from '../formato'
import Modal from './Modal'

interface Formulario {
  documento_numero: string
  fecha: string
  codigo_bobina: string
  tipo_acero: string
  norma_id: string
  espesor_mm: string
  ancho_mm: string
  peso_kg: string
  propietario: string
  siderurgica: string
  buque: string
}

const INICIAL: Formulario = {
  documento_numero: '', fecha: hoyIso(), codigo_bobina: '', tipo_acero: '', norma_id: '', espesor_mm: '',
  ancho_mm: '', peso_kg: '', propietario: '', siderurgica: '', buque: '',
}

const num = (s: string) => s.trim().replace(',', '.')

export type InicialBobina = Partial<Formulario>

/** `inicial`: datos que vienen de un aviso de entrada del cliente (se revisan antes de guardar). */
export default function EntradaBobina({ onVerInventario, inicial, aviso, onGuardada }: {
  onVerInventario: () => void; inicial?: InicialBobina | null; aviso?: string | null
  onGuardada?: (piezaId: number, texto: string) => void
}) {
  const [f, setF] = useState<Formulario>({ ...INICIAL, ...(inicial ?? {}) })
  useEffect(() => { if (inicial) setF({ ...INICIAL, ...inicial }) }, [inicial])
  const [tipos, setTipos] = useState<TipoAcero[]>([])
  const [normas, setNormas] = useState<Norma[]>([])
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [resumen, setResumen] = useState<ResumenEntrada | null>(null)
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    pedir<TipoAcero[]>('/api/catalogos/tipos-acero').then((t) => setTipos(t.filter((x) => x.activo))).catch(() => {})
    pedir<Norma[]>('/api/catalogos/normas').then((n) => setNormas(n.filter((x) => x.activo))).catch(() => {})
    pedir<Tercero[]>('/api/terceros').then((t) => setTerceros(t.filter((x) => x.activo))).catch(() => {})
  }, [])

  const porNombre = (nombre: string) =>
    terceros.find((t) => t.nombre.toLowerCase() === nombre.trim().toLowerCase())

  function cuerpo(confirmar: boolean) {
    const dueno = porNombre(f.propietario)
    const sid = f.siderurgica.trim() ? porNombre(f.siderurgica) : undefined
    if (!dueno) throw new Error('Elige el dueño de la lista (escribe y selecciona un nombre existente).')
    if (f.siderurgica.trim() && !sid) throw new Error('La siderúrgica no está en la lista de terceros.')
    return {
      documento_numero: f.documento_numero.trim(),
      fecha: f.fecha,
      codigo_bobina: f.codigo_bobina.trim(),
      tipo_acero: f.tipo_acero,
      norma_id: f.norma_id ? Number(f.norma_id) : null,
      espesor_mm: num(f.espesor_mm),
      ancho_mm: num(f.ancho_mm),
      peso_kg: num(f.peso_kg),
      propietario_id: dueno.id,
      siderurgica_id: sid ? sid.id : null,
      buque: f.buque.trim() || null,
      confirmar,
      clave_idempotencia: confirmar ? clave : null,
    }
  }

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setHecho(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenEntrada>('/api/entradas/bobinas', { metodo: 'POST', cuerpo: cuerpo(false) })
      setClave(crypto.randomUUID())  // un mismo identificador por revisión: un doble clic no duplica
      setResumen(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo validar')
    } finally {
      setOcupado(false)
    }
  }

  async function confirmar() {
    setOcupado(true)
    setError(null)
    try {
      const r = await pedir<ResumenEntrada>('/api/entradas/bobinas', { metodo: 'POST', cuerpo: cuerpo(true) })
      setHecho(`Bobina ${f.codigo_bobina.trim().toUpperCase()} registrada como ${r.codigo_producto}.`)
      if (r.pieza_id) onGuardada?.(r.pieza_id, `Bobina ${f.codigo_bobina.trim().toUpperCase()}`)
      setResumen(null)
      // Se conservan documento, fecha, dueño y siderúrgica: suelen repetirse en la misma descarga.
      setF({ ...f, codigo_bobina: '', peso_kg: '' })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  const campo = (k: keyof Formulario) => ({
    value: f[k],
    onChange: (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value }),
  })

  return (
    <section>
      <div className="encabezado-seccion">
        <h1>Entrada de bobina</h1>
      </div>

      {hecho && (
        <div className="exito">
          {hecho} <button className="enlace" onClick={onVerInventario}>Ver inventario</button>
        </div>
      )}

      {aviso && <div className="alerta">Precargado desde el {aviso}. Revisa los datos contra el material y el documento que llegó antes de guardar.</div>}
      <form className="tarjeta formulario dos-columnas" onSubmit={revisar}>
        <label>
          Documento de entrada
          <input {...campo('documento_numero')} placeholder="Packing list o nota" required />
        </label>
        <label>
          Fecha de entrada
          <input type="date" {...campo('fecha')} required />
        </label>
        <label>
          Código de bobina
          <input {...campo('codigo_bobina')} placeholder="Como viene de la siderúrgica" required />
        </label>
        <label>
          Tipo de acero
          <select {...campo('tipo_acero')} required>
            <option value="">Elegir…</option>
            {tipos.map((t) => <option key={t.id} value={t.codigo}>{t.nombre} ({t.codigo})</option>)}
          </select>
        </label>
        <label>
          Espesor (mm)
          <input inputMode="decimal" {...campo('espesor_mm')} placeholder="0,90" required />
        </label>
        <label>
          Ancho (mm)
          <input inputMode="numeric" {...campo('ancho_mm')} placeholder="1220" required />
        </label>
        <label>
          Peso (kg)
          <input inputMode="decimal" {...campo('peso_kg')} placeholder="6250" required />
        </label>
        <label>
          Norma
          <select {...campo('norma_id')}>
            <option value="">Sin norma</option>
            {normas.map((n) => <option key={n.id} value={n.id}>{n.nombre}</option>)}
          </select>
        </label>
        <label>
          Dueño
          <input list="lista-terceros" {...campo('propietario')} placeholder="Escribe para buscar" required />
        </label>
        <label>
          Siderúrgica
          <input list="lista-terceros" {...campo('siderurgica')} placeholder="Opcional" />
        </label>
        <label>
          Buque
          <input {...campo('buque')} placeholder="Opcional" />
        </label>
        <datalist id="lista-terceros">
          {terceros.map((t) => <option key={t.id} value={t.nombre} />)}
        </datalist>
        {error && <p className="error ancho-completo">{error}</p>}
        <div className="acciones ancho-completo">
          <button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar entrada'}</button>
          <button type="button" className="secundario" onClick={() => { setF(INICIAL); setError(null) }}>Limpiar</button>
        </div>
      </form>

      {resumen && (
        <Modal titulo="Confirma la entrada" onCerrar={() => setResumen(null)}>
          <dl className="datos">
            <dt>Código de bobina</dt><dd className="codigo">{f.codigo_bobina.trim().toUpperCase()}</dd>
            <dt>Producto</dt><dd><strong>{resumen.codigo_producto}</strong></dd>
            <dt>Descripción</dt><dd>{resumen.descripcion}</dd>
            <dt>Peso</dt><dd>{kg(num(f.peso_kg))}</dd>
            <dt>Dueño</dt><dd>{resumen.propietario}</dd>
            <dt>Documento</dt><dd>{f.documento_numero} · {f.fecha.split('-').reverse().join('/')}</dd>
          </dl>
          {resumen.avisos.length > 0 && (
            <div className="alerta">
              <strong>Revisa antes de guardar:</strong>
              <ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void confirmar()}>
              {ocupado ? 'Guardando…' : 'Confirmar y guardar'}
            </button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </Modal>
      )}
    </section>
  )
}
