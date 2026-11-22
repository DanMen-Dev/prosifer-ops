import { useEffect, useState, type FormEvent } from 'react'
import { pedir, type Rol, type Tercero, type Usuario } from '../api'
import { NOMBRE_ROL } from '../formato'

interface Nuevo { correo: string; nombre: string; rol: Rol; tercero: string; clave: string }
const VACIO: Nuevo = { correo: '', nombre: '', rol: 'asistente', tercero: '', clave: '' }

export default function Usuarios({ usuario }: { usuario: Usuario }) {
  const [lista, setLista] = useState<Usuario[]>([])
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [nuevo, setNuevo] = useState<Nuevo>(VACIO)
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<string | null>(null)

  const cargar = () => pedir<Usuario[]>('/api/usuarios').then(setLista).catch((e: Error) => setError(e.message))

  useEffect(() => {
    void cargar()
    pedir<Tercero[]>('/api/terceros?rol=cliente').then(setTerceros).catch(() => {})
  }, [])

  const nombreTercero = (id: number | null) => terceros.find((t) => t.id === id)?.nombre ?? '—'

  async function crear(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setHecho(null)
    const tercero = terceros.find((t) => t.nombre.toLowerCase() === nuevo.tercero.trim().toLowerCase())
    if (nuevo.rol === 'cliente' && !tercero) {
      setError('Un usuario cliente necesita el tercero cuyos datos verá.')
      return
    }
    try {
      await pedir<Usuario>('/api/usuarios', {
        metodo: 'POST',
        cuerpo: { correo: nuevo.correo, nombre: nuevo.nombre, rol: nuevo.rol, clave: nuevo.clave,
          tercero_id: nuevo.rol === 'cliente' ? tercero?.id : null },
      })
      setHecho(`Usuario ${nuevo.correo} creado. Pásale su clave por un canal privado.`)
      setNuevo(VACIO)
      void cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear')
    }
  }

  async function alternar(u: Usuario) {
    setError(null)
    try {
      await pedir<Usuario>(`/api/usuarios/${u.id}`, { metodo: 'PATCH', cuerpo: { activo: !u.activo } })
      void cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar')
    }
  }

  return (
    <section>
      <div className="encabezado-seccion"><h1>Usuarios</h1></div>
      {error && <p className="error">{error}</p>}
      {hecho && <div className="exito">{hecho}</div>}

      <div className="tabla-envoltura tarjeta">
        <table className="tabla">
          <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Ve los datos de</th><th>Estado</th><th></th></tr></thead>
          <tbody>
            {lista.map((u) => (
              <tr key={u.id} className={u.activo ? '' : 'agotada'}>
                <td>{u.nombre}</td>
                <td>{u.correo}</td>
                <td>{NOMBRE_ROL[u.rol]}</td>
                <td>{u.rol === 'cliente' ? nombreTercero(u.tercero_id) : 'Todo'}</td>
                <td>{u.activo ? 'Activo' : 'Inactivo'}</td>
                <td>
                  {u.id !== usuario.id && (
                    <button className="enlace" onClick={() => void alternar(u)}>{u.activo ? 'Desactivar' : 'Activar'}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Nuevo usuario</h2>
      <form className="tarjeta formulario dos-columnas" onSubmit={crear}>
        <label>Nombre<input value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} required /></label>
        <label>Correo<input type="email" value={nuevo.correo} onChange={(e) => setNuevo({ ...nuevo, correo: e.target.value })} required /></label>
        <label>
          Rol
          <select value={nuevo.rol} onChange={(e) => setNuevo({ ...nuevo, rol: e.target.value as Rol })}>
            <option value="asistente">Asistente: registra y corrige, no anula</option>
            <option value="socio">Socio: todo, incluido anular y usuarios</option>
            <option value="cliente">Cliente: ve solo su inventario</option>
          </select>
        </label>
        {nuevo.rol === 'cliente' && (
          <label>
            Cliente
            <input list="lista-clientes" value={nuevo.tercero} placeholder="Escribe para buscar"
              onChange={(e) => setNuevo({ ...nuevo, tercero: e.target.value })} required />
            <datalist id="lista-clientes">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
          </label>
        )}
        <label>
          Clave inicial
          <input type="text" value={nuevo.clave} autoComplete="new-password" placeholder="Mínimo 10, letras y números"
            onChange={(e) => setNuevo({ ...nuevo, clave: e.target.value })} required />
        </label>
        <div className="acciones ancho-completo"><button className="primario">Crear usuario</button></div>
      </form>
    </section>
  )
}
