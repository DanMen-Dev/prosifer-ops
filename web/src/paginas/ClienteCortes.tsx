import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { pedir, type OpcionProducto, type Pieza, type SolicitudCorte, type Usuario } from '../api'
import { fecha, hoyIso, kg, mm } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import Modal from './Modal'
import Ordenes from './Ordenes'
import { DetallePedido, EstadoSolicitudChip } from './SolicitudesCorte'
import SugerenciasPerfil from './SugerenciasPerfil'

/* Órdenes de corte del portal del cliente: formularios simples para solicitar el corte (slitter,
   láminas, maquila), el seguimiento de esas solicitudes y el histórico de sus órdenes. La solicitud no es
   una orden: Prosifer la revisa y la autoriza como orden de corte definitiva, o la rechaza con un motivo. */

type Pestana = 'slitter' | 'lamina' | 'maquila' | 'solicitudes' | 'documentos'
const NOMBRE: Record<string, string> = { slitter: 'slitter', lamina: 'láminas', maquila: 'maquila' }
const NOMBRE_OC: Record<string, string> = { slitter: 'Slitter', lamina: 'Laminadora', maquila: 'Maquila' }

interface Enviada { numero: string; tipo: string }

function Bobina({ p }: { p: Pieza }) {
  return (
    <p className="ficha-corta">
      <span className="codigo">{p.codigo_fisico}</span> · {p.descripcion ?? ''} · {mm(p.espesor_mm, true)} × {mm(p.ancho_mm)} mm
      · <strong>{kg(p.saldo_kg)}</strong>
    </p>
  )
}

function useEnvio(onEnviada: (e: Enviada) => void) {
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  async function enviar(cuerpo: Record<string, unknown>) {
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<SolicitudCorte>('/api/solicitudes-corte', { metodo: 'POST', cuerpo: { fecha: hoyIso(), ...cuerpo } })
      onEnviada({ numero: r.numero, tipo: r.tipo })
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo enviar')
      return false
    } finally {
      setOcupado(false)
    }
  }
  return { error, setError, ocupado, enviar }
}

function Comentarios({ valor, onCambio }: { valor: string; onCambio: (v: string) => void }) {
  return (
    <label className="ancho-completo">Comentarios
      <textarea rows={2} value={valor} onChange={(e) => onCambio(e.target.value)}
        placeholder="Lo que Prosifer deba saber: urgencia, uso del material, cómo lo retiras…" />
    </label>
  )
}

const num = (v: string) => v.trim().replace(',', '.')

// --- Slitter ------------------------------------------------------------------

function PedidoSlitter({ usuario, onEnviada }: { usuario: Usuario; onEnviada: (e: Enviada) => void }) {
  const [bobina, setBobina] = useState<Pieza | null>(null)
  const [cortes, setCortes] = useState([{ ancho_mm: '', cortes: '' }])
  const [pesoRollo, setPesoRollo] = useState('')
  const [embalaje, setEmbalaje] = useState('')
  const [total, setTotal] = useState(true)
  const [pesoMax, setPesoMax] = useState('')
  const [comentarios, setComentarios] = useState('')
  const { error, setError, ocupado, enviar } = useEnvio(onEnviada)

  const usado = cortes.reduce((t, c) => t + (Number(num(c.ancho_mm)) || 0) * (Number(c.cortes) || 0), 0)
  const ancho = bobina?.ancho_mm ? Number(bobina.ancho_mm) : null

  async function enviarForm(e: FormEvent) {
    e.preventDefault()
    if (!bobina) { setError('Elige la bobina a cortar.'); return }
    const lista = cortes.filter((c) => c.ancho_mm.trim() && c.cortes.trim())
      .map((c) => ({ ancho_mm: num(c.ancho_mm), cortes: Number(c.cortes) }))
    if (lista.length === 0) { setError('Indica al menos un ancho y cuántos cortes.'); return }
    const ok = await enviar({
      tipo: 'slitter', pieza_id: bobina.id, cortes: lista, peso_max_rollo_kg: num(pesoRollo) || null,
      embalaje: embalaje || null, corte_total: total, peso_max_kg: total ? null : num(pesoMax) || null,
      comentarios: comentarios.trim() || null,
    })
    if (ok) { setBobina(null); setCortes([{ ancho_mm: '', cortes: '' }]); setComentarios(''); setPesoMax(''); setPesoRollo('') }
  }

  return (
    <form className="tarjeta bloque" onSubmit={enviarForm}>
      <h2>Orden de corte · Slitter</h2>
      <label className="ancho-completo">Bobina a cortar
        <BuscadorPiezas propietarioId={usuario.tercero_id} tipo="bobina" excluir={[]} placeholder="Código de la bobina"
          onElegir={setBobina} deshabilitado={usuario.tercero_id ? null : 'Tu usuario no está asociado a un cliente.'} />
      </label>
      {bobina && <Bobina p={bobina} />}
      <div className="tabla-envoltura">
        <table className="tabla compacta cortes">
          <thead><tr><th>Ancho del fleje (mm)</th><th>N.º de cortes</th><th></th></tr></thead>
          <tbody>
            {cortes.map((c, i) => (
              <tr key={i}>
                <td><input inputMode="decimal" value={c.ancho_mm} aria-label="Ancho del fleje en mm" placeholder="268"
                  onChange={(e) => setCortes(cortes.map((x, j) => (j === i ? { ...x, ancho_mm: e.target.value } : x)))} /></td>
                <td><input inputMode="numeric" value={c.cortes} aria-label="Número de cortes de ese ancho" placeholder="4"
                  onChange={(e) => setCortes(cortes.map((x, j) => (j === i ? { ...x, cortes: e.target.value } : x)))} /></td>
                <td>{cortes.length > 1 && <button type="button" className="enlace" onClick={() => setCortes(cortes.filter((_, j) => j !== i))}>Quitar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="pie-tabla">
          {cortes.length < 6 && <button type="button" className="enlace" onClick={() => setCortes([...cortes, { ancho_mm: '', cortes: '' }])}>+ Otro ancho</button>}
          {ancho !== null && usado > 0 && (
            <span className={usado > ancho ? 'error' : 'tenue'}> · Usas {mm(usado)} de {mm(ancho)} mm{usado <= ancho ? `; sobran ${mm(ancho - usado)} mm` : ' (te pasaste del ancho de la bobina)'}</span>
          )}
        </p>
      </div>
      <div className="formulario tres-columnas sin-relleno">
        <label>Peso máximo por rollo (kg) <span className="tenue pequeno">opcional</span>
          <input inputMode="decimal" value={pesoRollo} onChange={(e) => setPesoRollo(e.target.value)} placeholder="1500" />
        </label>
        <label>Embalaje del fleje <span className="tenue pequeno">opcional</span>
          <select value={embalaje} onChange={(e) => setEmbalaje(e.target.value)}>
            <option value="">Indiferente</option>
            <option value="ojo_al_cielo">Ojo al cielo</option>
            <option value="vertical">Vertical</option>
          </select>
        </label>
        <fieldset className="opciones-corte">
          <legend>¿Cuánto de la bobina?</legend>
          <label className="casilla"><input type="radio" checked={total} onChange={() => setTotal(true)} /> Toda (corte total)</label>
          <label className="casilla"><input type="radio" checked={!total} onChange={() => setTotal(false)} /> Una parte</label>
          {!total && (
            <input inputMode="decimal" value={pesoMax} onChange={(e) => setPesoMax(e.target.value)}
              aria-label="Peso máximo aproximado a cortar en kg" placeholder="kg aprox. a cortar" required />
          )}
        </fieldset>
      </div>
      <Comentarios valor={comentarios} onCambio={setComentarios} />
      {error && <p className="error">{error}</p>}
      <div className="acciones"><button className="primario" disabled={ocupado}>{ocupado ? 'Enviando…' : 'Enviar solicitud de slitter'}</button></div>
    </form>
  )
}

// --- Láminas --------------------------------------------------------------------

function PedidoLaminas({ usuario, onEnviada }: { usuario: Usuario; onEnviada: (e: Enviada) => void }) {
  const [bobina, setBobina] = useState<Pieza | null>(null)
  const [largo, setLargo] = useState('2400')
  const [total, setTotal] = useState(true)
  const [cantidad, setCantidad] = useState('')
  const [comentarios, setComentarios] = useState('')
  const { error, setError, ocupado, enviar } = useEnvio(onEnviada)

  // peso teórico de una lámina: espesor × ancho × largo × 7,85 kg/dm³
  const unaKg = bobina?.espesor_mm && bobina.ancho_mm && Number(num(largo))
    ? (Number(bobina.espesor_mm) * Number(bobina.ancho_mm) * Number(num(largo)) * 7.85) / 1e6 : null
  const salen = unaKg ? Math.floor(Number(bobina?.saldo_kg) / unaKg) : null

  async function enviarForm(e: FormEvent) {
    e.preventDefault()
    if (!bobina) { setError('Elige la bobina a cortar.'); return }
    const ok = await enviar({
      tipo: 'lamina', pieza_id: bobina.id, largo_mm: num(largo), corte_total: total,
      cantidad_laminas: total ? null : Number(cantidad) || null, comentarios: comentarios.trim() || null,
    })
    if (ok) { setBobina(null); setCantidad(''); setComentarios('') }
  }

  return (
    <form className="tarjeta bloque" onSubmit={enviarForm}>
      <h2>Orden de corte · Láminas</h2>
      <label className="ancho-completo">Bobina a cortar
        <BuscadorPiezas propietarioId={usuario.tercero_id} tipo="bobina" excluir={[]} placeholder="Código de la bobina"
          onElegir={setBobina} deshabilitado={usuario.tercero_id ? null : 'Tu usuario no está asociado a un cliente.'} />
      </label>
      {bobina && <Bobina p={bobina} />}
      <div className="formulario tres-columnas sin-relleno">
        <label>Largo de la lámina (mm)
          <input inputMode="decimal" value={largo} onChange={(e) => setLargo(e.target.value)} required />
        </label>
        <fieldset className="opciones-corte">
          <legend>¿Cuánto cortar?</legend>
          <label className="casilla"><input type="radio" checked={total} onChange={() => setTotal(true)} /> Toda la bobina</label>
          <label className="casilla"><input type="radio" checked={!total} onChange={() => setTotal(false)} /> Una cantidad de láminas</label>
          {!total && (
            <input inputMode="numeric" value={cantidad} onChange={(e) => setCantidad(e.target.value)}
              aria-label="Cantidad de láminas" placeholder="láminas" required />
          )}
        </fieldset>
        {unaKg !== null && (
          <p className="tenue pequeno">Cada lámina pesa unos {kg(unaKg.toFixed(2))}; de la bobina salen unas {salen?.toLocaleString('es-VE')}.</p>
        )}
      </div>
      <Comentarios valor={comentarios} onCambio={setComentarios} />
      {error && <p className="error">{error}</p>}
      <div className="acciones"><button className="primario" disabled={ocupado}>{ocupado ? 'Enviando…' : 'Enviar solicitud de láminas'}</button></div>
    </form>
  )
}

// --- Maquila --------------------------------------------------------------------

function PedidoMaquila({ usuario, onEnviada }: { usuario: Usuario; onEnviada: (e: Enviada) => void }) {
  const [flejes, setFlejes] = useState<Pieza[]>([])
  const [perfil, setPerfil] = useState<OpcionProducto | null>(null)
  const [comentarios, setComentarios] = useState('')
  const { error, setError, ocupado, enviar } = useEnvio(onEnviada)

  useEffect(() => { if (flejes.length === 0) setPerfil(null) }, [flejes.length])

  async function enviarForm(e: FormEvent) {
    e.preventDefault()
    if (flejes.length === 0) { setError('Elige el fleje a maquilar.'); return }
    if (!perfil) { setError('Elige el perfil a fabricar entre los sugeridos.'); return }
    const ok = await enviar({
      tipo: 'maquila', flejes: flejes.map((f) => f.id), codigo_producto: perfil.codigo, descripcion: perfil.nombre,
      comentarios: comentarios.trim() || null,
    })
    if (ok) { setFlejes([]); setPerfil(null); setComentarios('') }
  }

  const ancho = flejes[0]?.ancho_mm
  return (
    <form className="tarjeta bloque" onSubmit={enviarForm}>
      <h2>Orden de maquila · Perfiles</h2>
      <label className="ancho-completo">{flejes.length ? 'Agregar otro fleje del mismo ancho' : 'Fleje a maquilar'}
        <BuscadorPiezas propietarioId={usuario.tercero_id} tipo="fleje" excluir={flejes.map((f) => f.id)}
          placeholder="Código del fleje" deshabilitado={flejes.length >= 6 ? 'Máximo 6 flejes por orden.' : usuario.tercero_id ? null : 'Tu usuario no está asociado a un cliente.'}
          onElegir={(p) => {
            if (ancho && p.ancho_mm !== ancho) { setError(`Ese fleje es de ${mm(p.ancho_mm)} mm; en esta orden van de ${mm(ancho)} mm.`); return }
            setError(null)
            setFlejes([...flejes, p])
          }} />
      </label>
      {flejes.map((f) => (
        <div key={f.id} className="acciones" style={{ alignItems: 'center' }}>
          <Bobina p={f} />
          <button type="button" className="enlace" onClick={() => setFlejes(flejes.filter((x) => x.id !== f.id))}>Quitar</button>
        </div>
      ))}
      {flejes.length > 0 && (
        <SugerenciasPerfil fleje={flejes[0]} elegido={perfil?.codigo ?? ''} onElegir={setPerfil}
          ayuda="elige el perfil y el espesor; si necesitas otro, escríbelo en comentarios" />
      )}
      {perfil && <p>Perfil a fabricar: <strong>{perfil.nombre}</strong> <span className="codigo tenue">{perfil.codigo}</span></p>}
      <Comentarios valor={comentarios} onCambio={setComentarios} />
      {error && <p className="error">{error}</p>}
      <div className="acciones"><button className="primario" disabled={ocupado}>{ocupado ? 'Enviando…' : 'Enviar solicitud de maquila'}</button></div>
    </form>
  )
}

// --- Mis solicitudes ---------------------------------------------------------------

function MisSolicitudes({ onVerOrden }: { onVerOrden: (id: number) => void }) {
  const [lista, setLista] = useState<SolicitudCorte[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [abierta, setAbierta] = useState<SolicitudCorte | null>(null)
  const [cancelando, setCancelando] = useState(false)
  const [motivo, setMotivo] = useState('')

  const cargar = useCallback(() => {
    pedir<SolicitudCorte[]>('/api/solicitudes-corte').then(setLista).catch((e: Error) => setError(e.message))
  }, [])
  useEffect(cargar, [cargar])

  async function cancelar() {
    if (!abierta) return
    try {
      setAbierta(await pedir<SolicitudCorte>(`/api/solicitudes-corte/${abierta.id}/cancelar`, { metodo: 'POST', cuerpo: { motivo: motivo.trim() } }))
      setCancelando(false)
      cargar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cancelar')
    }
  }

  return (
    <>
      {error && <p className="error">{error}</p>}
      {lista && lista.length === 0 && <p className="vacio">Todavía no has enviado solicitudes de corte.</p>}
      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead><tr><th>N°</th><th>Fecha</th><th>Tipo</th><th>Pieza</th><th>Estado</th><th>Orden de corte</th></tr></thead>
            <tbody>
              {lista.map((s) => (
                <tr key={s.id} onClick={() => { setAbierta(s); setCancelando(false) }} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAbierta(s) }}>
                  <td className="fuerte">{s.numero}</td>
                  <td>{fecha(s.fecha)}</td>
                  <td>{NOMBRE_OC[s.tipo]}</td>
                  <td className="codigo">{s.piezas.map((p) => p.codigo_fisico).join(', ')}</td>
                  <td><EstadoSolicitudChip estado={s.estado} /></td>
                  <td>{s.orden_numero ? `OC ${s.orden_numero}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {abierta && (
        <Modal titulo={`Solicitud ${abierta.numero} · ${NOMBRE_OC[abierta.tipo]}`} onCerrar={() => setAbierta(null)} ancho>
          <p><EstadoSolicitudChip estado={abierta.estado} /> · {fecha(abierta.fecha)}</p>
          {abierta.estado === 'pendiente' && <p className="alerta">Prosifer la está revisando. Te confirmará la orden de corte o te dirá si hace falta un cambio.</p>}
          <DetallePedido s={abierta} />
          {abierta.orden_id && (
            <p>Autorizada como <strong>OC {NOMBRE_OC[abierta.tipo]} {abierta.orden_numero}</strong>.{' '}
              <button className="enlace" onClick={() => { setAbierta(null); onVerOrden(abierta.orden_id as number) }}>Ver la orden</button></p>
          )}
          {abierta.motivo && <p><span className="tenue">{abierta.estado === 'rechazada' ? 'Motivo del rechazo' : 'Motivo'}:</span> {abierta.motivo}</p>}
          {abierta.estado === 'pendiente' && !cancelando && (
            <div className="acciones"><button className="peligro" onClick={() => setCancelando(true)}>Cancelar solicitud</button></div>
          )}
          {cancelando && (
            <div className="confirmacion peligro-caja">
              <label>¿Por qué la cancelas?<input value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus /></label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void cancelar()}>Cancelar solicitud</button>
                <button className="secundario" onClick={() => setCancelando(false)}>Volver</button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </>
  )
}

// --- Módulo ---------------------------------------------------------------------

export default function ClienteCortes({ usuario }: { usuario: Usuario }) {
  const [pestana, setPestana] = useState<Pestana>('slitter')
  const [enviada, setEnviada] = useState<Enviada | null>(null)
  const [abrir, setAbrir] = useState<number | null>(null)
  const alEnviar = (e: Enviada) => setEnviada(e)

  return (
    <section>
      <div className="encabezado-seccion"><h1>Órdenes de corte</h1></div>
      <nav className="subpestanas" aria-label="Tipo de orden">
        <button className={pestana === 'slitter' ? 'activa' : ''} onClick={() => setPestana('slitter')}>Slitter</button>
        <button className={pestana === 'lamina' ? 'activa' : ''} onClick={() => setPestana('lamina')}>Láminas</button>
        <button className={pestana === 'maquila' ? 'activa' : ''} onClick={() => setPestana('maquila')}>Maquila</button>
        <button className={pestana === 'solicitudes' ? 'activa' : ''} onClick={() => setPestana('solicitudes')}>Mis solicitudes</button>
        <button className={pestana === 'documentos' ? 'activa' : ''} onClick={() => setPestana('documentos')}>Documentos</button>
      </nav>
      {['slitter', 'lamina', 'maquila'].includes(pestana) && (
        <p className="tenue">Solicita aquí tu corte. Prosifer revisa la solicitud y la convierte en la orden de corte definitiva
          (o te indica qué cambiar). Sigue su estado en «Mis solicitudes»; las órdenes cortadas quedan en «Documentos».</p>
      )}
      {enviada && (
        <div className="exito">
          Solicitud de {NOMBRE[enviada.tipo]} N° {enviada.numero} enviada a Prosifer para su revisión.{' '}
          <button className="enlace" onClick={() => { setEnviada(null); setPestana('solicitudes') }}>Ver mis solicitudes</button>
        </div>
      )}
      {pestana === 'slitter' && <PedidoSlitter usuario={usuario} onEnviada={alEnviar} />}
      {pestana === 'lamina' && <PedidoLaminas usuario={usuario} onEnviada={alEnviar} />}
      {pestana === 'maquila' && <PedidoMaquila usuario={usuario} onEnviada={alEnviar} />}
      {pestana === 'solicitudes' && <MisSolicitudes onVerOrden={(id) => { setAbrir(id); setPestana('documentos') }} />}
      {pestana === 'documentos' && <Ordenes usuario={usuario} abrir={abrir} onAbierta={() => setAbrir(null)} />}
    </section>
  )
}
