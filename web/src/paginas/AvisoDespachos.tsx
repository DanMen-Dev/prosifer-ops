import { useCallback, useEffect, useState } from 'react'
import { pedir, type AvisoEntrada, type OrdenDespacho, type SolicitudCorte } from '../api'
import { fecha, kg } from '../formato'
import Modal from './Modal'

const CLAVE = 'prosifer.despachos-vistos'
const CLAVE_CORTES = 'prosifer.pedidos-corte-vistos'
const CLAVE_AVISOS = 'prosifer.avisos-entrada-vistos'
const CADA_MS = 60_000
const avisadas = new Set<string>()   // ya notificadas al sistema en esta pestaña
const NOMBRE_OT: Record<string, string> = { slitter: 'Slitter', lamina: 'Láminas', maquila: 'Maquila' }

function vistos(clave: string): number[] {
  try { return JSON.parse(localStorage.getItem(clave) ?? '[]') as number[] } catch { return [] }
}

function marcar(clave: string, ids: number[]) {
  try { localStorage.setItem(clave, JSON.stringify([...new Set([...vistos(clave), ...ids])].slice(-500))) } catch { /* sin almacenamiento */ }
}

/** Para el personal: cada minuto revisa las órdenes de despacho pendientes y las órdenes de corte que
 *  solicitan los clientes. Si hay alguna nueva, avisa con una ventana (y con una notificación del
 *  sistema si la pestaña está en segundo plano y se dio permiso). Informa los conteos para los
 *  contadores de Salidas y de Órdenes de corte. También los avisos de entrada de material (contador de Entradas). */
export default function AvisoDespachos({ onPendientes, onPedidosCorte, onVer, onVerCortes, onAvisosEntrada, onVerAvisos, revision = 0 }: {
  onPendientes: (n: number) => void; onPedidosCorte: (n: number) => void; onVer: () => void; onVerCortes: () => void
  onAvisosEntrada: (n: number) => void; onVerAvisos: () => void; revision?: number
}) {
  const [nuevas, setNuevas] = useState<OrdenDespacho[]>([])
  const [cortes, setCortes] = useState<SolicitudCorte[]>([])
  const [llegadas, setLlegadas] = useState<AvisoEntrada[]>([])

  const revisar = useCallback(async () => {
    try {
      const [pend, plan, entra] = await Promise.all([
        pedir<OrdenDespacho[]>('/api/despachos?estado=pendiente&limite=200'),
        pedir<SolicitudCorte[]>('/api/solicitudes-corte?estado=pendiente&limite=200'),
        pedir<AvisoEntrada[]>('/api/avisos-entrada?estado=pendiente&limite=200'),
      ])
      const deClientes = plan
      onPendientes(pend.length)
      onPedidosCorte(deClientes.length)
      onAvisosEntrada(entra.length)
      const ya = new Set(vistos(CLAVE))
      const sin = pend.filter((o) => o.id !== null && !ya.has(o.id))
      const yaC = new Set(vistos(CLAVE_CORTES))
      const sinC = deClientes.filter((o) => !yaC.has(o.id))
      setNuevas(sin)
      setCortes(sinC)
      const yaA = new Set(vistos(CLAVE_AVISOS))
      const sinA = entra.filter((a) => !yaA.has(a.id))
      setLlegadas(sinA)
      const textos = [
        ...sin.filter((o) => !avisadas.has(`d${o.id}`)).map((o) => { avisadas.add(`d${o.id}`); return `Despacho N° ${o.numero} · ${o.tercero} · ${kg(o.total_kg)}` }),
        ...sinC.filter((o) => !avisadas.has(`c${o.id}`)).map((o) => { avisadas.add(`c${o.id}`); return `Solicitud de corte ${NOMBRE_OT[o.tipo] ?? o.tipo} N° ${o.numero} · ${o.tercero}` }),
        ...sinA.filter((a) => !avisadas.has(`a${a.id}`)).map((a) => { avisadas.add(`a${a.id}`); return `Aviso de entrada N° ${a.numero} · ${a.tercero} · ${kg(a.total_kg)}` }),
      ]
      if (textos.length && document.hidden && 'Notification' in window && Notification.permission === 'granted') {
        new Notification('Prosifer: pedidos nuevos de clientes', { body: textos.join('\n') })
      }
    } catch { /* sin conexión: se reintenta en el próximo ciclo */ }
  }, [onPendientes, onPedidosCorte, onAvisosEntrada])

  useEffect(() => {
    void revisar()
    const t = window.setInterval(() => void revisar(), CADA_MS)
    const alVolver = () => { if (!document.hidden) void revisar() }
    document.addEventListener('visibilitychange', alVolver)
    return () => { window.clearInterval(t); document.removeEventListener('visibilitychange', alVolver) }
  }, [revisar, revision])

  if (nuevas.length === 0 && cortes.length === 0 && llegadas.length === 0) return null
  const cerrar = () => {
    marcar(CLAVE, nuevas.map((o) => o.id as number))
    marcar(CLAVE_CORTES, cortes.map((o) => o.id))
    marcar(CLAVE_AVISOS, llegadas.map((a) => a.id))
    setLlegadas([])
    setNuevas([])
    setCortes([])
  }
  const pedirPermiso = 'Notification' in window && Notification.permission === 'default'
  const total = nuevas.length + cortes.length + llegadas.length

  return (
    <Modal titulo={total === 1 ? 'Pedido nuevo de un cliente' : `${total} pedidos nuevos de clientes`} onCerrar={cerrar}>
      {nuevas.length > 0 && (
        <>
          <p><strong>Órdenes de despacho:</strong> preparar el material en patio y emitir la nota de salida.</p>
          <ul className="lista-avisos">
            {nuevas.map((o) => (
              <li key={`d${o.id}`}>
                <strong>N° {o.numero}</strong> · {o.tercero}<br />
                <span className="tenue pequeno">{o.lineas.length} renglón{o.lineas.length === 1 ? '' : 'es'} · {kg(o.total_kg)}
                  {o.retiro?.fecha_retiro && <> · retira el {fecha(o.retiro.fecha_retiro)}</>}
                  {o.retiro?.placa && <> · placa {o.retiro.placa}</>}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {cortes.length > 0 && (
        <>
          <p><strong>Solicitudes de corte:</strong> revisarlas y autorizarlas (o rechazarlas) en Órdenes de corte › Solicitudes de clientes.</p>
          <ul className="lista-avisos">
            {cortes.map((o) => (
              <li key={`c${o.id}`}>
                <strong>{NOMBRE_OT[o.tipo] ?? o.tipo} · solicitud N° {o.numero}</strong> · {o.tercero}<br />
                <span className="tenue pequeno">{o.piezas.map((p) => p.codigo_fisico).join(', ')} · {o.texto.replace(/^Pedido del cliente: ?/, '')}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {llegadas.length > 0 && (
        <>
          <p><strong>Avisos de entrada:</strong> material que va a llegar al patio. Al recibirlo, regístralo desde Entradas › Avisos de clientes.</p>
          <ul className="lista-avisos">
            {llegadas.map((a) => (
              <li key={`a${a.id}`}>
                <strong>Aviso N° {a.numero}</strong> · {a.tercero}<br />
                <span className="tenue pequeno">llega el {a.fecha_estimada ? fecha(a.fecha_estimada) : '—'} · {a.renglones.length} renglón{a.renglones.length === 1 ? '' : 'es'} · {kg(a.total_kg)}
                  {a.transporte?.placa && <> · placa {a.transporte.placa}</>}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="acciones">
        {nuevas.length > 0 && <button className="primario" onClick={() => { cerrar(); onVer() }}>Ver despachos</button>}
        {cortes.length > 0 && <button className="primario" onClick={() => { cerrar(); onVerCortes() }}>Ver solicitudes de corte</button>}
        {llegadas.length > 0 && <button className="primario" onClick={() => { cerrar(); onVerAvisos() }}>Ver avisos de entrada</button>}
        <button className="secundario" onClick={cerrar}>Más tarde</button>
        {pedirPermiso && (
          <button className="enlace" onClick={() => { void Notification.requestPermission() }}>Avisarme también con el navegador minimizado</button>
        )}
      </div>
    </Modal>
  )
}
