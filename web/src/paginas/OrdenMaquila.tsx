import { useEffect, useState, type FormEvent } from 'react'
import {
  consulta, pdfOt, pedir, type FichaPieza, type OpcionProducto, type Orden, type Pieza, type Producto, type ResumenOtMaquila,
  type Tercero,
  type VariantesEspesor,
} from '../api'
import { hoyIso, kg, mm } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import SugerenciasPerfil from './SugerenciasPerfil'
import Modal from './Modal'
import { hojaTrabajo } from './Planificadas'

interface FlejeElegido { pieza: Pieza; kg: string }

const MAX_FLEJES = 6
const MAX_PAQUETES = 12
const NOMBRE_CLASE: Record<string, string> = { 1: 'Primera', A: 'Segunda A', B: 'Segunda B', C: 'Segunda C' }
const dec = (s: string) => s.trim().replace(',', '.')
const num = (s: string) => Number(dec(s) || '0')
const entero = (s: string) => (s.trim() ? Math.max(0, Math.floor(Number(s))) : 0)
const piezas = new Intl.NumberFormat('es-VE')

/** Maquila de perfiles: hasta 6 flejes del cliente → un perfil del catálogo, por paquetes y segundas. */
export default function OrdenMaquila({ onVerOrden, plan = null, onPlanUsado }: {
  onVerOrden: (id: number) => void; plan?: Orden | null; onPlanUsado?: () => void
}) {
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [cliente, setCliente] = useState('')
  const [flejes, setFlejes] = useState<FlejeElegido[]>([])
  const [numero, setNumero] = useState('')
  const [fecha, setFecha] = useState(hoyIso())
  const [codigo, setCodigo] = useState('')
  const [sugeridos, setSugeridos] = useState<Producto[]>([])
  const [descripcion, setDescripcion] = useState('')
  const [teorico, setTeorico] = useState('')
  const [calidad, setCalidad] = useState('1er')
  const [paquetes, setPaquetes] = useState<string[]>([''])
  const [segundas, setSegundas] = useState({ a: '', b: '', c: '' })
  const [scrap, setScrap] = useState('')
  const [paradas, setParadas] = useState('')
  const [observacion, setObservacion] = useState('')
  const [resumen, setResumen] = useState<ResumenOtMaquila | null>(null)
  // Fleje de espesor no comercial (0,58): se pregunta si el perfil lleva 0,58 o 0,60 (nombre y código)
  const [variantes, setVariantes] = useState<VariantesEspesor | null>(null)
  const [espesorDecidido, setEspesorDecidido] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<{ texto: string; id: number; numero: number; propietario: string } | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const elegido = terceros.find((t) => t.nombre.toLowerCase() === cliente.trim().toLowerCase()) ?? null

  const cargarNumero = () =>
    pedir<{ numero: number }>('/api/ot/siguiente-numero?tipo=maquila').then((r) => setNumero(String(r.numero))).catch(() => {})

  useEffect(() => {
    if (!plan) void cargarNumero()
    pedir<Tercero[]>('/api/terceros?rol=cliente').then(setTerceros).catch(() => {})
  }, [])
  useEffect(() => { if (!plan) setFlejes([]) }, [elegido?.id, plan])
  // Resultados de una OC planificada: se precarga lo de la hoja (flejes, perfil, número)
  useEffect(() => {
    if (!plan) return
    const p = (plan.plan ?? {}) as { flejes?: number[]; codigo_producto?: string; descripcion?: string; peso_teorico_kg?: string | null }
    setNumero(String(plan.numero))
    setCliente(plan.propietario ?? '')
    if (plan.calidad) setCalidad(plan.calidad)
    if (p.codigo_producto) setCodigo(p.codigo_producto)
    if (p.descripcion) setDescripcion(p.descripcion)
    if (p.peso_teorico_kg) setTeorico(String(Number(p.peso_teorico_kg)))
    Promise.all((p.flejes ?? []).map((id) => pedir<FichaPieza>(`/api/piezas/${id}`).then((f) => f.pieza)))
      .then((lista) => {
        setFlejes(lista.map((pieza) => ({ pieza, kg: '' })))
        // el espesor ya se decidió al planificar: no se vuelve a preguntar
        if (lista[0] && p.codigo_producto) setEspesorDecidido(`${p.codigo_producto}|${lista[0].espesor_mm ?? ''}`)
      })
      .catch((e: Error) => setError(e.message))
  }, [plan?.id])

  // Perfiles del catálogo: solo los de primera (PER… sin -A/-B/-C)
  useEffect(() => {
    const q = codigo.trim()
    if (q.length < 2) { setSugeridos([]); return }
    const reloj = setTimeout(() => {
      pedir<Producto[]>(`/api/productos${consulta({ q: `per ${q}`, limite: 40 })}`)
        .then((r) => setSugeridos(r.filter((p) => p.codigo.startsWith('PER') && !/-[ABC]$/.test(p.codigo))))
        .catch(() => setSugeridos([]))
    }, 200)
    return () => clearTimeout(reloj)
  }, [codigo])
  useEffect(() => {
    const p = sugeridos.find((x) => x.codigo === codigo.trim().toUpperCase())
    if (p) { setDescripcion(p.nombre); setTeorico((v) => v || (p.peso_unitario_kg ?? '')) }
  }, [sugeridos, codigo])

  const consumido = flejes.reduce((t, f) => t + (f.kg.trim() ? num(f.kg) : Number(f.pieza.saldo_kg)), 0)
  const total = paquetes.reduce((t, p) => t + entero(p), 0) + entero(segundas.a) + entero(segundas.b) + entero(segundas.c)
  const porPieza = total ? (consumido - num(scrap)) / total : 0

  function cuerpo(confirmar: boolean, perfil?: OpcionProducto) {
    if (!elegido) throw new Error('Elige el cliente dueño de los flejes.')
    if (flejes.length === 0) throw new Error('Agrega al menos un fleje.')
    return {
      fecha,
      numero: numero ? Number(numero) : null,
      flejes: flejes.map((f) => ({ pieza_id: f.pieza.id, kg: f.kg.trim() ? dec(f.kg) : null })),
      codigo_producto: perfil?.codigo ?? codigo.trim().toUpperCase(),
      descripcion: perfil?.nombre ?? (descripcion.trim() || null),
      peso_teorico_kg: teorico.trim() ? dec(teorico) : null,
      paquetes: paquetes.map(entero).filter((n) => n > 0),
      segunda_a: entero(segundas.a),
      segunda_b: entero(segundas.b),
      segunda_c: entero(segundas.c),
      scrap_kg: scrap.trim() ? dec(scrap) : '0',
      calidad: calidad || null,
      paradas: paradas ? Number(paradas) : null,
      observacion: observacion.trim() || null,
      orden_planificada_id: plan?.id ?? null,
      confirmar,
      clave_idempotencia: confirmar ? clave : null,
    }
  }

  const claveEspesor = (cod: string) => `${cod.trim().toUpperCase()}|${flejes[0]?.pieza.espesor_mm ?? ''}`

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    // Si el fleje no tiene un espesor comercial, primero se pregunta si el perfil se redondea
    if (flejes.length > 0 && flejes[0].pieza.espesor_mm && espesorDecidido !== claveEspesor(codigo)) {
      try {
        const v = await pedir<VariantesEspesor>('/api/productos/variantes-espesor', {
          metodo: 'POST', cuerpo: { codigo: codigo.trim().toUpperCase(), espesor_mm: flejes[0].pieza.espesor_mm },
        })
        if (v.comercial && v.comercial.codigo !== v.real.codigo) { setVariantes(v); return }
      } catch { /* perfil sin regla o fuera del catálogo: se sigue con el código elegido */ }
    }
    await revisarAhora()
  }

  async function elegirVariante(opcion: OpcionProducto) {
    setVariantes(null)
    setCodigo(opcion.codigo)
    setDescripcion(opcion.nombre)
    if (opcion.existente?.peso_unitario_kg) setTeorico(opcion.existente.peso_unitario_kg)
    setEspesorDecidido(claveEspesor(opcion.codigo))
    await revisarAhora(opcion)
  }

  async function revisarAhora(perfil?: OpcionProducto) {
    setError(null)
    setOcupado(true)
    try {
      const r = await pedir<ResumenOtMaquila>('/api/ot/maquila', { metodo: 'POST', cuerpo: cuerpo(false, perfil) })
      setClave(crypto.randomUUID())
      setResumen(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo revisar')
    } finally {
      setOcupado(false)
    }
  }

  async function confirmar() {
    setOcupado(true)
    setError(null)
    try {
      const r = await pedir<ResumenOtMaquila>('/api/ot/maquila', { metodo: 'POST', cuerpo: cuerpo(true) })
      setHecho({ texto: `OC ${r.numero} de maquila registrada: ${piezas.format(r.total_perfiles)} perfiles, ${kg(r.kg_producido)}.`,
        id: r.orden_id ?? 0, numero: r.numero, propietario: r.propietario })
      setResumen(null)
      setFlejes([])
      setPaquetes([''])
      setSegundas({ a: '', b: '', c: '' })
      setScrap('')
      setParadas('')
      setObservacion('')
      if (plan) onPlanUsado?.()
      void cargarNumero()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar')
      setResumen(null)
    } finally {
      setOcupado(false)
    }
  }

  const pdf = (doc: 'orden' | 'etiquetas', guardar = false) => {
    if (!hecho) return
    void pdfOt(`/api/ot/${hecho.id}/pdf/${doc}`, 'maquila', hecho.numero, hecho.propietario, doc, guardar)
      .catch((e: Error) => setError(e.message))
  }

  return (
    <section>
      <div className="encabezado-seccion"><h1>Orden de maquila · Perfiles</h1></div>
      {plan && (
        <div className="alerta no-impresion">
          Registrando los resultados de la <strong>OC {plan.numero} planificada</strong>: los datos de la hoja ya están cargados;
          {' '}completa lo que anotó el operador.{' '}
          <button type="button" className="enlace" onClick={() => hojaTrabajo(plan, setError)}>Ver la hoja</button>
        </div>
      )}
      {hecho && (
        <div className="exito">
          <div>{hecho.texto}</div>
          {hecho.id > 0 && (
            <div className="acciones">
              <button className="primario" onClick={() => pdf('orden')}>Hoja de la orden (PDF)</button>
              <button className="secundario" onClick={() => pdf('orden', true)}>Guardar la orden en carpeta</button>
              <button className="primario" onClick={() => pdf('etiquetas')}>Etiquetas de paquetes (PDF)</button>
              <button className="secundario" onClick={() => onVerOrden(hecho.id)}>Ver la orden</button>
            </div>
          )}
        </div>
      )}

      <form className="tarjeta bloque" onSubmit={revisar}>
        <h2 className="sin-margen">1. Cliente y flejes que entran</h2>
        <label>Cliente (dueño de los flejes)
          <input list="clientes-maquila" value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Escribe para buscar" required />
          <datalist id="clientes-maquila">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
        </label>
        {flejes.length < MAX_FLEJES && (
          <BuscadorPiezas propietarioId={elegido?.id ?? null} tipo="fleje" excluir={flejes.map((f) => f.pieza.id)}
            deshabilitado={elegido ? null : 'Primero elige el cliente.'}
            onElegir={(p) => setFlejes([...flejes, { pieza: p, kg: '' }])}
            placeholder="Agregar fleje: código o medida · F4 para ver los disponibles" />
        )}
        {flejes.length > 0 && (
          <div className="tabla-envoltura">
            <table className="tabla compacta cortes">
              <thead><tr><th>Fleje</th><th className="n">Medidas</th><th className="n">Saldo</th><th>kg que se procesan</th><th></th></tr></thead>
              <tbody>
                {flejes.map((f, i) => (
                  <tr key={f.pieza.id}>
                    <td className="codigo">{f.pieza.codigo_fisico}</td>
                    <td className="n">{mm(f.pieza.espesor_mm, true)} × {mm(f.pieza.ancho_mm)}</td>
                    <td className="n">{kg(f.pieza.saldo_kg)}</td>
                    <td><input inputMode="decimal" value={f.kg} placeholder="todo el fleje"
                      onChange={(e) => setFlejes(flejes.map((x, j) => (j === i ? { ...x, kg: e.target.value } : x)))} /></td>
                    <td><button type="button" className="enlace" onClick={() => setFlejes(flejes.filter((_, j) => j !== i))}>Quitar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="pie-tabla">Se procesan <strong>{kg(consumido)}</strong></p>
          </div>
        )}

        <h2>2. Perfil y datos de la orden</h2>
        <div className="formulario cuatro-columnas sin-relleno">
          <SugerenciasPerfil fleje={flejes[0]?.pieza ?? null} elegido={codigo.trim().toUpperCase()}
            onElegir={(op) => {
              setCodigo(op.codigo)
              setDescripcion(op.nombre)
              if (op.existente?.peso_unitario_kg) setTeorico(op.existente.peso_unitario_kg)
              setEspesorDecidido(claveEspesor(op.codigo))
            }} />
          <label className="doble">Perfil (código o nombre)
            <input list="perfiles-catalogo" value={codigo} onChange={(e) => setCodigo(e.target.value)} placeholder="PERHNVIG2006000 o «vigueta 2,00»" required />
            <datalist id="perfiles-catalogo">{sugeridos.map((p) => <option key={p.id} value={p.codigo}>{p.nombre}</option>)}</datalist>
          </label>
          <label className="doble">Descripción<input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Del catálogo" /></label>
          <label>Peso teórico por perfil (kg)<input inputMode="decimal" value={teorico} onChange={(e) => setTeorico(e.target.value)} placeholder="Del catálogo" /></label>
          <label>Número de OC<input inputMode="numeric" value={numero} onChange={(e) => setNumero(e.target.value)} /></label>
          <label>Fecha<input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required /></label>
          <label>Calidad de primera<input value={calidad} onChange={(e) => setCalidad(e.target.value)} /></label>
          <label>Scrap (kg)<input inputMode="decimal" value={scrap} onChange={(e) => setScrap(e.target.value)} placeholder="0" /></label>
          <label>Paradas<input inputMode="numeric" value={paradas} onChange={(e) => setParadas(e.target.value)} placeholder="0" /></label>
        </div>

        <h2>3. Perfiles producidos</h2>
        <p className="tenue pequeno sin-margen">Primera por paquetes (cada paquete lleva su etiqueta). Segunda en A, B y C.</p>
        <div className="formulario cuatro-columnas sin-relleno">
          {paquetes.map((p, i) => (
            <label key={i}>Paquete {i + 1}
              <input inputMode="numeric" value={p} onChange={(e) => setPaquetes(paquetes.map((x, j) => (j === i ? e.target.value : x)))} />
            </label>
          ))}
        </div>
        <div className="acciones sin-margen">
          {paquetes.length < MAX_PAQUETES && <button type="button" className="secundario" onClick={() => setPaquetes([...paquetes, ''])}>Agregar paquete</button>}
          {paquetes.length > 1 && <button type="button" className="enlace" onClick={() => setPaquetes(paquetes.slice(0, -1))}>Quitar el último</button>}
        </div>
        <div className="formulario cuatro-columnas sin-relleno">
          <label>Segunda A<input inputMode="numeric" value={segundas.a} onChange={(e) => setSegundas({ ...segundas, a: e.target.value })} placeholder="0" /></label>
          <label>Segunda B<input inputMode="numeric" value={segundas.b} onChange={(e) => setSegundas({ ...segundas, b: e.target.value })} placeholder="0" /></label>
          <label>Segunda C<input inputMode="numeric" value={segundas.c} onChange={(e) => setSegundas({ ...segundas, c: e.target.value })} placeholder="0" /></label>
        </div>
        <div className="ficha-resumen">
          <div><span>Perfiles</span><strong>{piezas.format(total)}</strong></div>
          <div><span>Peso por perfil</span><strong>{total ? `${porPieza.toFixed(2).replace('.', ',')} kg` : '—'}</strong></div>
          <div><span>Teórico</span><strong>{teorico ? `${teorico.replace('.', ',')} kg` : '—'}</strong></div>
        </div>
        <label className="ancho-completo">Observación<textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} /></label>
        {error && <p className="error">{error}</p>}
        <div className="acciones"><button className="primario" disabled={ocupado}>{ocupado ? 'Revisando…' : 'Revisar orden'}</button></div>
      </form>

      {variantes && (
        <Modal titulo="Espesor del perfil" onCerrar={() => setVariantes(null)}>
          <p>Los flejes son de <strong>{variantes.espesor_real} mm</strong>. ¿El perfil lleva ese espesor o se redondea a
            {' '}<strong>{variantes.espesor_comercial} mm</strong>? Si se redondea, cambian el nombre y el código.</p>
          {[{ titulo: `Mantener ${variantes.espesor_real} mm`, op: variantes.real },
            ...(variantes.comercial ? [{ titulo: `Redondear a ${variantes.espesor_comercial} mm`, op: variantes.comercial }] : [])]
            .map(({ titulo, op }) => (
              <div key={op.codigo} className="confirmacion">
                <button type="button" className="primario" disabled={ocupado} onClick={() => void elegirVariante(op)}>{titulo}</button>
                <p className="sin-margen"><span className="codigo">{op.codigo}</span> · {op.nombre}</p>
                <p className="sin-margen tenue pequeno">{op.existente ? 'Ya está en el catálogo' : 'Todavía no está en el catálogo: la existencia queda con este código y nombre'}</p>
              </div>
            ))}
        </Modal>
      )}
      {resumen && (
        <Modal titulo={`Confirma la OC ${resumen.numero} de maquila`} onCerrar={() => setResumen(null)} ancho>
          <div className="ficha-resumen">
            <div><span>Procesado</span><strong>{kg(resumen.kg_consumido)}</strong></div>
            <div><span>Perfiles</span><strong>{piezas.format(resumen.total_perfiles)} · {kg(resumen.kg_producido)}</strong></div>
            <div><span>Por perfil</span><strong>{resumen.kg_por_pieza} kg</strong></div>
          </div>
          <p className="pequeno">
            Cliente {resumen.propietario} · {resumen.flejes.length} fleje{resumen.flejes.length === 1 ? '' : 's'} · scrap {kg(resumen.kg_scrap)}
            {resumen.kg_teorico && <> · teórico {resumen.kg_teorico} kg ({resumen.diferencia_teorico_pct} %)</>}
          </p>
          {resumen.avisos.length > 0 && (
            <div className="alerta"><strong>Revisa antes de guardar:</strong><ul>{resumen.avisos.map((a) => <li key={a}>{a}</li>)}</ul></div>
          )}
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead><tr><th>Calidad</th><th>Producto</th><th className="n">Perfiles</th><th className="n">kg</th><th className="n">Quedarán</th></tr></thead>
              <tbody>
                {resumen.grupos.map((g) => (
                  <tr key={g.codigo_producto}>
                    <td>{NOMBRE_CLASE[g.clase] ?? g.clase}</td>
                    <td><div className="codigo">{g.codigo_producto}</div><div className="tenue pequeno">{g.descripcion}</div></td>
                    <td className="n">{piezas.format(g.unidades)}</td><td className="n">{kg(g.kg)}</td>
                    <td className="n">{g.existencia_despues === null ? '—' : piezas.format(g.existencia_despues)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tenue pequeno">{resumen.paquetes.length} etiquetas de paquete{resumen.grupos.some((g) => g.clase !== '1') ? ' más una por cada segunda' : ''}.</p>
          <div className="acciones">
            <button className="primario" disabled={ocupado} onClick={() => void confirmar()}>{ocupado ? 'Guardando…' : 'Confirmar y guardar'}</button>
            <button className="secundario" onClick={() => setResumen(null)}>Corregir</button>
          </div>
        </Modal>
      )}
    </section>
  )
}
