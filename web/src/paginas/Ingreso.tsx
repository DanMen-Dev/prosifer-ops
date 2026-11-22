import { useState, type FormEvent } from 'react'
import { ingresar, type Usuario } from '../api'

export default function Ingreso({ aviso, onEntrar }: { aviso: string | null; onEntrar: (u: Usuario) => void }) {
  const [correo, setCorreo] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    try {
      onEntrar(await ingresar(correo, clave))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo entrar')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="ingreso">
      <form className="tarjeta ingreso-caja" onSubmit={enviar}>
        <div className="logo-ingreso">
          <img src="/logo-prosifer.png" alt="Prosifer, C.A." width={260} height={79} />
        </div>
        <p className="tenue">Inventario, órdenes de corte y despachos</p>
        {aviso && <p className="alerta">{aviso}</p>}
        <label>
          Correo
          <input type="email" autoComplete="username" value={correo} onChange={(e) => setCorreo(e.target.value)}
            required autoFocus />
        </label>
        <label>
          Clave
          <input type="password" autoComplete="current-password" value={clave}
            onChange={(e) => setClave(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primario" disabled={enviando}>{enviando ? 'Entrando…' : 'Entrar'}</button>
      </form>
    </div>
  )
}
