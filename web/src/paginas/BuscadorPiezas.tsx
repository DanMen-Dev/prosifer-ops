import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { consulta, ocupacion, pedir, type Existencias, type Pieza } from '../api'
import { kg, mm } from '../formato'

interface Props {
  propietarioId: number | null
  excluir: number[]
  onElegir: (p: Pieza) => void
  deshabilitado?: string | null   // motivo para no buscar todavía (p. ej. "elige el cliente")
  tipo?: string                   // 'bobina', 'fleje' o vacío para todas
  placeholder?: string
  mostrarDueno?: boolean
  autoFocus?: boolean
}

const VISIBLES = 100

/**
 * Campo con lista desplegable de piezas disponibles.
 * Escribir abre la lista filtrada (autocompletar); F4, Enter o el botón la abren completa; ↑ ↓ Re Pág Av Pág Inicio Fin la recorren; Enter o clic eligen;
 * Escape, Tab o un clic fuera la cierran.
 */
export default function BuscadorPiezas({
  propietarioId, excluir, onElegir, deshabilitado, tipo = '', placeholder, mostrarDueno = false, autoFocus = false,
}: Props) {
  const [texto, setTexto] = useState('')
  const [lista, setLista] = useState<Pieza[] | null>(null)
  const [abierta, setAbierta] = useState(false)
  const [marcada, setMarcada] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const contenedor = useRef<HTMLDivElement>(null)
  const listaRef = useRef<HTMLUListElement>(null)
  const campo = useRef<HTMLInputElement>(null)

  useEffect(() => { setLista(null); setAbierta(false) }, [propietarioId, tipo])

  // Cerrar con un clic en cualquier otra parte de la pantalla
  useEffect(() => {
    if (!abierta) return
    const fuera = (e: MouseEvent) => {
      if (contenedor.current && !contenedor.current.contains(e.target as Node)) setAbierta(false)
    }
    document.addEventListener('mousedown', fuera)
    return () => document.removeEventListener('mousedown', fuera)
  }, [abierta])

  // Mantener visible la fila marcada al moverse con el teclado
  useEffect(() => {
    if (!abierta) return
    const fila = listaRef.current?.querySelector<HTMLElement>(`[data-indice="${marcada}"]`)
    fila?.scrollIntoView({ block: 'nearest' })
  }, [marcada, abierta])

  async function abrir() {
    if (deshabilitado) { setError(deshabilitado); return }
    setError(null)
    setMarcada(0)
    setAbierta(true)
    if (lista === null) {
      try {
        const r = await pedir<Existencias>(`/api/existencias${consulta({ propietario_id: propietarioId, tipo, limite: 5000 })}`)
        setLista([...r.piezas].sort((a, b) => a.codigo_fisico.localeCompare(b.codigo_fisico)))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo cargar la lista')
        setAbierta(false)
      }
    }
  }

  const f = texto.trim().toLowerCase()
  const visibles = (lista ?? [])
    .filter((p) => !excluir.includes(p.id))
    .filter((p) => !f || p.codigo_fisico.toLowerCase().includes(f) || (p.descripcion ?? '').toLowerCase().includes(f)
      || (p.codigo_producto ?? '').toLowerCase().includes(f) || p.propietario_nombre.toLowerCase().includes(f))
    .slice(0, VISIBLES)

  function elegir(p: Pieza) {
    onElegir(p)
    setTexto('')
    setMarcada(0)
    setAbierta(false)
    campo.current?.focus()
  }

  function mover(i: number) {
    setMarcada(Math.max(0, Math.min(i, visibles.length - 1)))
  }

  function teclas(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'F4') { e.preventDefault(); if (abierta) setAbierta(false); else void abrir(); return }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (!abierta) { void abrir(); return }
      if (visibles[marcada]) elegir(visibles[marcada])
      return
    }
    if (!abierta) {
      if (e.key === 'ArrowDown') { e.preventDefault(); void abrir() }
      return
    }
    switch (e.key) {
      case 'Escape': e.preventDefault(); setAbierta(false); break
      case 'Tab': setAbierta(false); break
      case 'ArrowDown': e.preventDefault(); mover(marcada + 1); break
      case 'ArrowUp': e.preventDefault(); mover(marcada - 1); break
      case 'PageDown': e.preventDefault(); mover(marcada + 8); break
      case 'PageUp': e.preventDefault(); mover(marcada - 8); break
      case 'Home': if (e.ctrlKey) { e.preventDefault(); mover(0) } break
      case 'End': if (e.ctrlKey) { e.preventDefault(); mover(visibles.length - 1) } break
    }
  }

  return (
    <div className="combo" ref={contenedor}>
      <div className="fila-busqueda">
        <input ref={campo} value={texto} autoFocus={autoFocus}
          onChange={(e) => {
            const v = e.target.value
            setTexto(v)
            setMarcada(0)
            // Autocompletar: al escribir se abre la lista con las coincidencias (se carga la primera vez)
            if (v.trim() && !abierta) void abrir()
          }}
          onKeyDown={teclas}
          placeholder={placeholder ?? 'Agregar pieza: escribe el código · F4 para ver las disponibles'}
          role="combobox" aria-expanded={abierta} aria-autocomplete="list" />
        <button type="button" className="secundario" onClick={() => (abierta ? setAbierta(false) : void abrir())}>
          {abierta ? 'Cerrar lista' : 'Disponibles (F4)'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {abierta && (
        <ul className="desplegable" role="listbox" ref={listaRef}>
          {lista === null && <li className="tenue">Cargando…</li>}
          {lista !== null && visibles.length === 0 && <li className="tenue">Ninguna pieza disponible coincide.</li>}
          {visibles.map((p, i) => (
            <li key={p.id} data-indice={i} role="option" aria-selected={i === marcada} className={i === marcada ? 'marcada' : ''}
              onMouseDown={(e) => { e.preventDefault(); elegir(p) }} onMouseMove={() => { if (i !== marcada) setMarcada(i) }}>
              <span className="codigo">{p.codigo_fisico}</span>
              <span className="tenue pequeno">
                {p.tipo} · {p.saldo_unidades === null || p.saldo_unidades === undefined
                  ? `${mm(p.espesor_mm, true)} × ${mm(p.ancho_mm)} mm · ${kg(p.saldo_kg)}`
                  : `${p.descripcion ?? ''} · ${p.saldo_unidades.toLocaleString('es-VE')} pzas · ${kg(p.saldo_kg)}`}
                {mostrarDueno ? ` · ${p.propietario_nombre}` : ''}
              </span>
              {ocupacion(p).map((t) => <span key={t} className="chip-ocupada">{t}</span>)}
            </li>
          ))}
          {lista !== null && visibles.length === VISIBLES && (
            <li className="tenue pequeno">Se muestran las primeras {VISIBLES}; escribe para acotar.</li>
          )}
        </ul>
      )}
    </div>
  )
}
