import { useEffect, useState } from 'react'
import { salir, sesionGuardada, type Usuario } from './api'
import { NOMBRE_ROL } from './formato'
import Ingreso from './paginas/Ingreso'
import Inventario from './paginas/Inventario'
import Entradas from './paginas/Entradas'
import Usuarios from './paginas/Usuarios'
import Cortes from './paginas/Cortes'
import Salidas from './paginas/Salidas'
import Despachos from './paginas/Despachos'
import ClienteCortes from './paginas/ClienteCortes'
import AvisoDespachos from './paginas/AvisoDespachos'
import ClienteAvisos from './paginas/AvisosEntrada'
import Catalogos from './paginas/Catalogos'

type Vista = 'inventario' | 'entrada' | 'corte' | 'solicitudes' | 'ordenes' | 'despachos' | 'salidas' | 'catalogos' | 'usuarios' | 'avisos'
const VISTAS: Vista[] = ['inventario', 'entrada', 'corte', 'solicitudes', 'ordenes', 'despachos', 'salidas', 'catalogos', 'usuarios', 'avisos']

function vistaDelHash(): Vista {
  const h = window.location.hash.replace('#/', '') as Vista
  return VISTAS.includes(h) ? h : 'inventario'
}

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(() => sesionGuardada()?.usuario ?? null)
  const [vista, setVista] = useState<Vista>(vistaDelHash)
  const [aviso, setAviso] = useState<string | null>(null)
  const [pendientes, setPendientes] = useState(0)
  const [pedidosCorte, setPedidosCorte] = useState(0)
  const [avisosEntrada, setAvisosEntrada] = useState(0)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const alCambiar = () => setVista(vistaDelHash())
    const alVencer = () => {
      setUsuario(null)
      setAviso('Tu sesión venció. Vuelve a entrar.')
    }
    window.addEventListener('hashchange', alCambiar)
    window.addEventListener('prosifer:sesion-vencida', alVencer)
    return () => {
      window.removeEventListener('hashchange', alCambiar)
      window.removeEventListener('prosifer:sesion-vencida', alVencer)
    }
  }, [])

  if (!usuario) {
    return <Ingreso aviso={aviso} onEntrar={(u) => { setAviso(null); setUsuario(u) }} />
  }

  const esPersonal = usuario.rol !== 'cliente'
  const ir = (v: Vista) => { window.location.hash = `#/${v}` }
  // el personal ve las órdenes dentro de "Órdenes de corte" (subpestaña Documentos); el cliente, en "Mis órdenes"
  // el personal ve las órdenes de despacho en Salidas > Planificadas; el cliente, en "Despachos"
  const pedida: Vista = (vista === 'ordenes' || vista === 'solicitudes') && esPersonal ? 'corte'
    : vista === 'solicitudes' ? 'ordenes' : vista === 'despachos' && esPersonal ? 'salidas'
    : vista === 'avisos' && esPersonal ? 'entrada' : vista
  const actual: Vista =
    ((pedida === 'entrada' || pedida === 'corte' || pedida === 'catalogos') && !esPersonal) || (pedida === 'usuarios' && usuario.rol !== 'socio')
      ? 'inventario' : pedida

  return (
    <div className="app">
      <header className="barra">
        <div className="marca">
          <span className="logo-barra"><img src="/logo-prosifer.png" alt="Prosifer, C.A." width={112} height={34} /></span>
        </div>
        <nav className="pestanas" aria-label="Secciones">
          <button className={actual === 'inventario' ? 'activa' : ''} onClick={() => ir('inventario')}>
            {esPersonal ? 'Inventario' : 'Mi inventario'}
          </button>
          {esPersonal && (
            <button className={actual === 'entrada' ? 'activa' : ''} onClick={() => ir('entrada')}>
              Entradas
              {avisosEntrada > 0 && <span className="contador" title="Avisos de entrada de clientes por recibir">{avisosEntrada}</span>}
            </button>
          )}
          {!esPersonal && (
            <button className={actual === 'avisos' ? 'activa' : ''} onClick={() => ir('avisos')}>Entradas</button>
          )}
          {esPersonal && (
            <button className={actual === 'corte' ? 'activa' : ''} onClick={() => ir('corte')}>
              Órdenes de corte
              {pedidosCorte > 0 && <span className="contador" title="Solicitudes de corte de clientes por revisar">{pedidosCorte}</span>}
            </button>
          )}
          {!esPersonal && (
            <button className={actual === 'ordenes' ? 'activa' : ''} onClick={() => ir('ordenes')}>Órdenes de corte</button>
          )}
          {!esPersonal && (
            <button className={actual === 'despachos' ? 'activa' : ''} onClick={() => ir('despachos')}>Despachos</button>
          )}
          <button className={actual === 'salidas' ? 'activa' : ''} onClick={() => ir('salidas')}>
            {esPersonal ? 'Salidas' : 'Mis documentos'}
            {esPersonal && pendientes > 0 && <span className="contador" title="Órdenes de despacho pendientes">{pendientes}</span>}
          </button>
          {esPersonal && (
            <button className={actual === 'catalogos' ? 'activa' : ''} onClick={() => ir('catalogos')}>
              Clientes y productos
            </button>
          )}
          {usuario.rol === 'socio' && (
            <button className={actual === 'usuarios' ? 'activa' : ''} onClick={() => ir('usuarios')}>
              Usuarios
            </button>
          )}
        </nav>
        <div className="quien">
          <span className="empresa" title={usuario.empresa ?? undefined}>
            {usuario.empresa ?? (usuario.rol === 'cliente' ? '' : 'Prosifer')}
          </span>
          <span className="tenue-barra">–</span>
          <span className="nombre">{usuario.nombre}</span>
          <span className="rol">{NOMBRE_ROL[usuario.rol]}</span>
          <button className="enlace" onClick={() => { salir(); setUsuario(null) }}>Salir</button>
        </div>
      </header>
      <main className="contenido">
        {actual === 'inventario' && <Inventario usuario={usuario} />}
        {actual === 'entrada' && <Entradas usuario={usuario} onVerInventario={() => ir('inventario')}
          inicial={vista === 'avisos' ? 'avisos' : undefined} avisosPendientes={avisosEntrada} onCambioAvisos={() => setRevision(revision + 1)} />}
        {actual === 'avisos' && <ClienteAvisos usuario={usuario} />}
        {actual === 'corte' && <Cortes usuario={usuario}
          inicial={vista === 'ordenes' ? 'documentos' : vista === 'solicitudes' ? 'solicitudes' : 'planificadas'} />}
        {actual === 'ordenes' && <ClienteCortes usuario={usuario} />}
        {actual === 'despachos' && <Despachos usuario={usuario} />}
        {actual === 'salidas' && <Salidas usuario={usuario} pendientes={pendientes}
          inicial={vista === 'despachos' ? 'planificadas' : undefined} />}
        {actual === 'catalogos' && <Catalogos />}
        {actual === 'usuarios' && <Usuarios usuario={usuario} />}
      </main>
      {esPersonal && <AvisoDespachos onPendientes={setPendientes} onPedidosCorte={setPedidosCorte}
        onAvisosEntrada={setAvisosEntrada} onVerAvisos={() => ir('avisos')} revision={revision}
        onVer={() => ir('despachos')} onVerCortes={() => ir('solicitudes')} />}
    </div>
  )
}
