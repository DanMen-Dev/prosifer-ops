import { useEffect, type ReactNode } from 'react'

interface Props {
  titulo: string
  onCerrar: () => void
  children: ReactNode
  ancho?: boolean
}

export default function Modal({ titulo, onCerrar, children, ancho = false }: Props) {
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', tecla)
    return () => window.removeEventListener('keydown', tecla)
  }, [onCerrar])

  return (
    <div className="velo" onMouseDown={(e) => { if (e.target === e.currentTarget) onCerrar() }}>
      <div className={`modal ${ancho ? 'ancho' : ''}`} role="dialog" aria-modal="true" aria-label={titulo}>
        <div className="modal-cabecera">
          <h2>{titulo}</h2>
          <button className="cerrar" onClick={onCerrar} aria-label="Cerrar">×</button>
        </div>
        <div className="modal-cuerpo">{children}</div>
      </div>
    </div>
  )
}
