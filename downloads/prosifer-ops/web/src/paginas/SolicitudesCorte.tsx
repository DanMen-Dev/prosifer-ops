import { useCallback, useEffect, useState } from 'react'
import { consulta, ESTADO_SOLICITUD, pedir, type SolicitudCorte } from '../api'
import { fecha, kg, mm } from '../formato'
import Modal from './Modal'
import { NOMBRE_TIPO, NuevaPlanificada } from './Planificadas'

/* Solicitudes de orden de corte que precargan los clientes. No son órdenes: Prosifer las revisa, y al
   autorizarlas abre el formulario de planificación precargado (lo que guarde es la OC definitiva) o las
   rechaza con un motivo que el cliente ve. Las planificadas siguen en su pestaña de siempre. */

export function EstadoSolicitudChip({ estado }: { estado: SolicitudCorte['estado'] }) {
  const clase = estado === 'pendiente' ? 'pendiente' : estado === 'aprobada' ? 'despachada' : estado === 'rechazada' ? 'anulada' : 'borrador'
  return <span className={`estado-despacho ${clase}`}>{ESTADO_SOLICITUD[estado]}</span>
}

export function DetallePedido({ s }: { s: SolicitudCorte }) {
  return (
    <>
      <p className="pedido-texto">{s.texto}</p>
      <div className="tabla-envoltura">
        <table className="tabla compacta">
          <thead><tr><th>{s.tipo === 'maquila' ? 'Fleje' : 'Bobina'}</th><th>Material</th><th className="n">Saldo hoy</th></tr></thead>
          <tbody>
            {s.piezas.map((p) => (
              <tr key={p.id}>
                <td className="codigo">{p.codigo_fisico}</td>
                <td>{p.descripcion} · {mm(p.espesor_mm, true)} × {mm(p.ancho_mm)} mm</td>
                <td className="n">{p.estado === 'disponible' ? kg(p.saldo_kg) : p.estado}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export default function SolicitudesCorte({ onCambio }: { onCambio?: () => void }) {
  const [estado, setEstado] = useState('pendiente')
  const [lista, setLista] = useState<SolicitudCorte[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [abierta, setAbierta] = useState<SolicitudCorte | null>(null)
  const [autorizando, setAutorizando] = useState<SolicitudCorte | null>(null)
  const [rechazando, setRechazando] = useState(false)
  const [motivo, setMotivo] = useState('')

  const cargar = useCallback(() => {
    setError(null)
    pedir<SolicitudCorte[]>(`/api/solicitudes-corte${consulta({ estado })}`).then(setLista).catch((e: Error) => setError(e.message))
  }, [estado])
  useEffect(cargar, [cargar])

  async function rechazar() {
    if (!abierta) return
    setError(null)
    try {
      await pedir(`/api/solicitudes-corte/${abierta.id}/rechazar`, { metodo: 'POST', cuerpo: { motivo: motivo.trim() } })
      setAbierta(null)
      setRechazando(false)
      setMotivo('')
      cargar()
      onCambio?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo rechazar')
    }
  }

  if (autorizando) {
    return (
      <NuevaPlanificada solicitud={autorizando} onCancelar={() => setAutorizando(null)}
        onHecha={() => { setAutorizando(null); cargar(); onCambio?.() }} />
    )
  }

  return (
    <section>
      <div className="encabezado-seccion">
        <h2>Solicitudes de clientes</h2>
        <label>Estado
          <select value={estado} onChange={(e) => setEstado(e.target.value)}>
            <option value="pendiente">Por revisar</option>
            <option value="aprobada">Autorizadas</option>
            <option value="rechazada">Rechazadas</option>
            <option value="cancelada">Canceladas por el cliente</option>
            <option value="">Todas</option>
          </select>
        </label>
      </div>
      <p className="tenue">Lo que los clientes piden desde su portal. Autorizar abre la planificación con el pedido cargado para
        revisarlo y ajustarlo; la orden definitiva pasa a Planificadas.</p>
      {error && <p className="error">{error}</p>}
      {lista && lista.length === 0 && <p className="vacio">{estado === 'pendiente' ? 'No hay solicitudes por revisar.' : 'No hay solicitudes.'}</p>}
      {lista && lista.length > 0 && (
        <div className="tabla-envoltura tarjeta">
          <table className="tabla">
            <thead><tr><th>N°</th><th>Fecha</th><th>Cliente</th><th>Máquina</th><th>Pieza</th><th>Pedido</th><th>Estado</th></tr></thead>
            <tbody>
              {lista.map((s) => (
                <tr key={s.id} onClick={() => { setAbierta(s); setRechazando(false) }} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') setAbierta(s) }}>
                  <td className="fuerte">{s.numero}</td>
                  <td>{fecha(s.fecha)}</td>
                  <td>{s.tercero}</td>
                  <td>{NOMBRE_TIPO[s.tipo] ?? s.tipo}</td>
                  <td className="codigo">{s.piezas.map((p) => p.codigo_fisico).join(', ')}</td>
                  <td className="pequeno">{s.texto.replace(/^Pedido del cliente: ?/, '')}</td>
                  <td><EstadoSolicitudChip estado={s.estado} />{s.orden_numero && <div className="tenue pequeno">OC {s.orden_numero}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {abierta && (
        <Modal titulo={`Solicitud ${abierta.numero} · ${NOMBRE_TIPO[abierta.tipo] ?? abierta.tipo}`} onCerrar={() => setAbierta(null)} ancho>
          <p><EstadoSolicitudChip estado={abierta.estado} /> · <strong>{abierta.tercero}</strong> · {fecha(abierta.fecha)}
            {abierta.creado_por && <span className="tenue pequeno"> · enviada por {abierta.creado_por}</span>}</p>
          <DetallePedido s={abierta} />
          {abierta.orden_numero && <p>Autorizada como <strong>OC {NOMBRE_TIPO[abierta.tipo]} {abierta.orden_numero}</strong>
            {abierta.revisado_por && <span className="tenue pequeno"> por {abierta.revisado_por}</span>}.</p>}
          {abierta.motivo && <p><span className="tenue">Motivo:</span> {abierta.motivo}</p>}
          {abierta.estado === 'pendiente' && !rechazando && (
            <div className="acciones">
              <button className="primario" onClick={() => { setAutorizando(abierta); setAbierta(null) }}>Revisar y autorizar</button>
              <button className="peligro" onClick={() => setRechazando(true)}>Rechazar</button>
            </div>
          )}
          {rechazando && (
            <div className="confirmacion peligro-caja">
              <label>Motivo del rechazo (el cliente lo verá)
                <textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus />
              </label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5} onClick={() => void rechazar()}>Rechazar solicitud</button>
                <button className="secundario" onClick={() => setRechazando(false)}>Volver</button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </section>
  )
}
