import { useCallback, useEffect, useState } from 'react'
import { consulta, pedir, type Orden, type Usuario } from '../api'
import Ordenes from './Ordenes'
import OrdenLamina from './OrdenLamina'
import OrdenMaquila from './OrdenMaquila'
import OrdenSlitter from './OrdenSlitter'
import Planificadas from './Planificadas'
import SolicitudesCorte from './SolicitudesCorte'

export type PestanaCortes = 'solicitudes' | 'planificadas' | 'slitter' | 'lamina' | 'maquila' | 'documentos'
type Pestana = PestanaCortes

/** Órdenes de la planta: planificadas (hoja de trabajo antes del corte), el registro de resultados por
 *  máquina y los documentos (el histórico de órdenes con sus PDF, etiquetas, anulación…). */
export default function Cortes({ usuario, inicial = 'planificadas' }: { usuario: Usuario; inicial?: Pestana }) {
  const [pestana, setPestana] = useState<Pestana>(inicial)
  const [abrir, setAbrir] = useState<number | null>(null)
  const abierta = useCallback(() => setAbrir(null), [])
  // al registrar una orden, se muestra en Documentos con su detalle abierto
  const onVerOrden = (id: number) => { setPlan(null); setAbrir(id); setPestana('documentos') }
  const [plan, setPlan] = useState<Orden | null>(null)
  const [pendientes, setPendientes] = useState<number | null>(null)
  const [solicitudes, setSolicitudes] = useState<number | null>(null)
  const [recargar, setRecargar] = useState(0)
  useEffect(() => { setPestana(inicial) }, [inicial])

  useEffect(() => {
    pedir<Orden[]>(`/api/ot${consulta({ estado: 'planificada', limite: 300 })}`).then((l) => setPendientes(l.length)).catch(() => {})
    pedir<unknown[]>('/api/solicitudes-corte?estado=pendiente').then((l) => setSolicitudes(l.length)).catch(() => {})
  }, [pestana, recargar])

  function registrar(o: Orden) {
    setPlan(o)
    setPestana(o.tipo === 'slitter' ? 'slitter' : o.tipo === 'maquila' ? 'maquila' : 'lamina')
  }
  function cambiar(p: Pestana) {
    setPlan(null)
    setPestana(p)
  }
  const usado = () => setPlan(null)

  return (
    <>
      <nav className="subpestanas" aria-label="Máquina">
        <button className={pestana === 'solicitudes' ? 'activa' : ''} onClick={() => cambiar('solicitudes')}>
          Solicitudes de clientes{solicitudes ? <span className="contador">{solicitudes}</span> : null}
        </button>
        <button className={pestana === 'planificadas' ? 'activa' : ''} onClick={() => cambiar('planificadas')}>
          Planificadas{pendientes ? ` (${pendientes})` : ''}
        </button>
        <button className={pestana === 'slitter' ? 'activa' : ''} onClick={() => cambiar('slitter')}>Slitter</button>
        <button className={pestana === 'lamina' ? 'activa' : ''} onClick={() => cambiar('lamina')}>Laminadora y CTF</button>
        <button className={pestana === 'maquila' ? 'activa' : ''} onClick={() => cambiar('maquila')}>Maquila de perfiles</button>
        <button className={pestana === 'documentos' ? 'activa' : ''} onClick={() => cambiar('documentos')}>Documentos</button>
      </nav>
      {pestana === 'solicitudes' && <SolicitudesCorte onCambio={() => setRecargar((n) => n + 1)} />}
      {pestana === 'planificadas' && <Planificadas onRegistrar={registrar} />}
      {pestana === 'slitter' && <OrdenSlitter onVerOrden={onVerOrden} plan={plan} onPlanUsado={usado} />}
      {pestana === 'lamina' && <OrdenLamina onVerOrden={onVerOrden} plan={plan} onPlanUsado={usado} />}
      {pestana === 'maquila' && <OrdenMaquila onVerOrden={onVerOrden} plan={plan} onPlanUsado={usado} />}
      {pestana === 'documentos' && <Ordenes usuario={usuario} abrir={abrir} onAbierta={abierta} />}
    </>
  )
}
