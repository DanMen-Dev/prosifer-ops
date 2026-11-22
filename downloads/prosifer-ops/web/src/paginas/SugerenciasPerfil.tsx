import { useEffect, useState } from 'react'
import { pedir, type OpcionProducto, type Pieza } from '../api'
import { mm } from '../formato'

interface PerfilSugerido {
  nombre: string
  espesor_real: string
  espesor_comercial: string | null
  real: OpcionProducto
  comercial: OpcionProducto | null
}

/**
 * Perfiles que suelen salir del fleje (por su ancho, material y espesor). La asistente ratifica con un
 * clic, eligiendo el espesor real o el redondeado; si no es ninguno, busca el perfil en el catálogo.
 */
export default function SugerenciasPerfil({ fleje, elegido, onElegir, ayuda }: {
  fleje: Pieza | null; elegido: string; onElegir: (op: OpcionProducto) => void; ayuda?: string
}) {
  const [lista, setLista] = useState<PerfilSugerido[]>([])
  useEffect(() => {
    setLista([])
    if (!fleje) return
    pedir<PerfilSugerido[]>(`/api/productos/sugerir-perfil?pieza_id=${fleje.id}`).then(setLista).catch(() => setLista([]))
  }, [fleje?.id])
  if (!fleje || lista.length === 0) return null
  return (
    <div className="ancho-completo confirmacion">
      <p className="sin-margen"><strong>Perfil sugerido</strong> para el fleje de {mm(fleje.espesor_mm, true)} × {mm(fleje.ancho_mm)} mm
        {' '}<span className="tenue pequeno">({ayuda ?? 'un clic lo elige; si es otro, búscalo abajo'})</span></p>
      {lista.map((s) => (
        <div key={s.nombre} className="acciones" style={{ alignItems: 'center' }}>
          <span style={{ minWidth: '12rem' }}>{s.nombre}</span>
          {[{ op: s.real, t: `${s.espesor_real} mm` }, ...(s.comercial ? [{ op: s.comercial, t: `redondear a ${s.espesor_comercial} mm` }] : [])]
            .map(({ op, t }) => (
              <button key={op.codigo} type="button" className={elegido === op.codigo ? 'primario' : 'secundario'}
                title={op.nombre} onClick={() => onElegir(op)}>
                {t} · <span className="codigo">{op.codigo}</span>{op.existente ? '' : ' (nuevo)'}
              </button>
            ))}
        </div>
      ))}
    </div>
  )
}
