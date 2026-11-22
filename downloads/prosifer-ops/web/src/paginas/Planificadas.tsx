import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  consulta, pdfOt, pedir, type OpcionProducto, type Orden, type Pieza, type Producto, type SolicitudCorte,
  type Tercero, type VariantesEspesor,
} from '../api'
import { fecha as fechaTexto, hoyIso, kg, mm } from '../formato'
import BuscadorPiezas from './BuscadorPiezas'
import SugerenciasPerfil from './SugerenciasPerfil'

export type TipoPlan = 'slitter' | 'lamina' | 'ctf' | 'maquila'

export const NOMBRE_TIPO: Record<string, string> = {
  slitter: 'Slitter', lamina: 'Laminadora', ctf: 'CTF', maquila: 'Maquila',
}

const dec = (s: string) => s.trim().replace(',', '.')

/** Hoja de trabajo de una OC planificada en PDF. */
export function hojaTrabajo(o: Pick<Orden, 'id' | 'tipo' | 'numero'> & { propietario?: string | null },
  onError: (m: string) => void, guardar = false) {
  pdfOt(`/api/ot/${o.id}/hoja-trabajo`, o.tipo, o.numero, o.propietario, 'hoja', guardar).catch((e: Error) => onError(e.message))
}

function resumenPlan(o: Orden): string {
  const p = (o.plan ?? {}) as Record<string, unknown>
  if (o.tipo === 'slitter') {
    const cortes = (p.cortes as { ancho_mm: string; rollos: number }[] | undefined) ?? []
    return cortes.map((c) => `${c.rollos} × ${mm(c.ancho_mm)}`).join(' + ') + ' mm'
  }
  if (o.tipo === 'maquila') {
    const n = ((p.flejes as number[] | undefined) ?? []).length
    return `${String(p.descripcion ?? p.codigo_producto ?? '')} · ${n} fleje${n === 1 ? '' : 's'}`
  }
  return String(p.descripcion ?? '')
}

/**
 * OC planificadas: se crean antes del corte (la pieza queda "en proceso"), se imprime la hoja de trabajo y,
 * cuando el operador la devuelve anotada, "Registrar resultados" abre la orden con todo precargado.
 */
export default function Planificadas({ onRegistrar }: { onRegistrar: (o: Orden) => void }) {
  const [lista, setLista] = useState<Orden[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nueva, setNueva] = useState(false)
  const [cancelando, setCancelando] = useState<Orden | null>(null)
  const [motivo, setMotivo] = useState('')

  const cargar = useCallback(() => {
    pedir<Orden[]>(`/api/ot${consulta({ estado: 'planificada', limite: 300 })}`).then(setLista)
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(() => { cargar() }, [cargar])

  async function cancelar() {
    if (!cancelando || !motivo.trim()) return
    setError(null)
    try {
      await pedir(`/api/ot/${cancelando.id}/cancelar-plan`, { metodo: 'POST', cuerpo: { motivo: motivo.trim() } })
      setCancelando(null)
      setMotivo('')
      cargar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cancelar')
    }
  }

  return (
    <section>
      <div className="acciones-filtro" style={{ marginBottom: '.8rem' }}>
        {!nueva && <button className="primario" onClick={() => setNueva(true)}>Planificar una orden</button>}
      </div>
      {nueva && <NuevaPlanificada onCancelar={() => setNueva(false)} onHecha={() => { setNueva(false); cargar() }} />}
      {error && <p className="error">{error}</p>}
      <div className="tabla-envoltura tarjeta">
        <table className="tabla">
          <thead><tr><th>OC</th><th>Fecha</th><th>Entra</th><th>Cliente</th><th>Pedido</th><th></th></tr></thead>
          <tbody>
            {(lista ?? []).map((o) => (
              <tr key={o.id}>
                <td><strong>{NOMBRE_TIPO[o.tipo] ?? o.tipo} {o.numero}</strong>
                  {o.plan?.solicitud_numero ? <div><span className="pedido-cliente">Solicitud {String(o.plan.solicitud_numero)} del cliente</span></div> : null}</td>
                <td>{o.fecha ? fechaTexto(o.fecha) : '—'}</td>
                <td className="codigo">{o.codigo_pieza}</td>
                <td>{o.propietario}</td>
                <td>{resumenPlan(o)}</td>
                <td className="acciones-fila">
                  <button className="secundario" onClick={() => hojaTrabajo(o, setError)}>Ver hoja</button>
                  <button className="secundario" onClick={() => hojaTrabajo(o, setError, true)}>Guardar hoja</button>
                  <button className="primario" onClick={() => onRegistrar(o)}>Registrar resultados</button>
                  <button className="enlace" onClick={() => { setCancelando(o); setMotivo('') }}>Cancelar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista !== null && lista.length === 0 && <p className="vacio">No hay órdenes planificadas pendientes.</p>}
      </div>
      {cancelando && (
        <div className="confirmacion">
          <p className="sin-margen">Cancelar la OC {NOMBRE_TIPO[cancelando.tipo]} {cancelando.numero}: la pieza vuelve a quedar libre.</p>
          <label>Motivo<input value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus /></label>
          <div className="acciones">
            <button className="primario" disabled={!motivo.trim()} onClick={() => void cancelar()}>Cancelar la orden</button>
            <button className="secundario" onClick={() => setCancelando(null)}>Volver</button>
          </div>
        </div>
      )}
    </section>
  )
}

interface CortePlan { ancho_mm: string; rollos: string }

/** Formulario de OC planificada. Con `solicitud`, viene precargado con lo que pidió el cliente: lo que
 *  se guarde (con los cambios que haga falta) es la orden autorizada, y la solicitud queda enlazada. */
export function NuevaPlanificada({ onCancelar, onHecha, solicitud }: {
  onCancelar: () => void; onHecha: () => void; solicitud?: SolicitudCorte
}) {
  const s = solicitud
  const [tipo, setTipo] = useState<TipoPlan>(s?.tipo ?? 'lamina')
  const [fecha, setFecha] = useState(hoyIso())
  const [numero, setNumero] = useState('')
  const [pieza, setPieza] = useState<Pieza | null>(s && s.tipo !== 'maquila' ? s.piezas[0] ?? null : null)
  const [precargado, setPrecargado] = useState(!!s)   // el primer cambio de tipo no borra lo precargado
  // maquila
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [cliente, setCliente] = useState(s?.tercero ?? '')
  const [flejes, setFlejes] = useState<Pieza[]>(s?.tipo === 'maquila' ? s.piezas : [])
  const [codigo, setCodigo] = useState(s?.pedido.codigo_producto ?? '')
  const [sugeridos, setSugeridos] = useState<Producto[]>([])
  const [descripcion, setDescripcion] = useState(s?.pedido.descripcion ?? '')
  const [variantes, setVariantes] = useState<VariantesEspesor | null>(null)
  // elegido de las sugerencias: espesor ya decidido (el cliente lo eligió entre real y redondeado)
  const [perfilDecidido, setPerfilDecidido] = useState(s?.pedido.codigo_producto ?? '')
  // laminadora / CTF
  const [largo, setLargo] = useState(s?.pedido.largo_mm ?? '2400')
  const [ancho, setAncho] = useState('')
  const [comercial, setComercial] = useState<string | null>(null)
  const [redondear, setRedondear] = useState<boolean | null>(null)
  // slitter
  const [cortes, setCortes] = useState<CortePlan[]>(
    s?.pedido.cortes?.length ? s.pedido.cortes.map((c) => ({ ancho_mm: c.ancho_mm, rollos: String(c.cortes) })) : [{ ancho_mm: '', rollos: '1' }])
  const [calidad, setCalidad] = useState('')
  const [observacion, setObservacion] = useState(s?.texto ?? '')
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [hecha, setHecha] = useState<{ id: number; numero: number; propietario: string } | null>(null)

  useEffect(() => {
    pedir<{ numero: number }>(`/api/ot/siguiente-numero?tipo=${tipo}`).then((r) => setNumero(String(r.numero))).catch(() => {})
    if (precargado) { setPrecargado(false); return }
    setPieza(null)
    setFlejes([])
    setRedondear(null)
  }, [tipo])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { pedir<Tercero[]>('/api/terceros?rol=cliente').then(setTerceros).catch(() => {}) }, [])
  const elegido = terceros.find((t) => t.nombre.toLowerCase() === cliente.trim().toLowerCase()) ?? null
  // Al cambiar de cliente se quita lo que no es suyo: el buscador solo muestra el inventario de ese cliente
  useEffect(() => {
    if (!elegido) return
    setPieza((p) => (p && p.propietario_id !== elegido.id ? null : p))
    setFlejes((f) => f.filter((x) => x.propietario_id === elegido.id))
  }, [elegido?.id])  // eslint-disable-line react-hooks/exhaustive-deps

  // ¿la bobina tiene un espesor no comercial? entonces se pregunta si las láminas se redondean
  useEffect(() => {
    setComercial(null)
    setRedondear(null)
    if (!pieza?.espesor_mm || (tipo !== 'lamina' && tipo !== 'ctf')) return
    pedir<{ comercial: string; difiere: boolean }>(`/api/productos/espesor-comercial?mm=${pieza.espesor_mm}`)
      .then((r) => setComercial(r.difiere ? r.comercial : null)).catch(() => {})
  }, [pieza?.id, pieza?.espesor_mm, tipo])

  useEffect(() => {
    const q = codigo.trim()
    if (tipo !== 'maquila' || q.length < 2) { setSugeridos([]); return }
    const reloj = setTimeout(() => {
      pedir<Producto[]>(`/api/productos${consulta({ q: `per ${q}`, limite: 40 })}`)
        .then((r) => setSugeridos(r.filter((p) => p.codigo.startsWith('PER') && !/-[ABC]$/.test(p.codigo))))
        .catch(() => setSugeridos([]))
    }, 200)
    return () => clearTimeout(reloj)
  }, [codigo, tipo])
  useEffect(() => {
    const p = sugeridos.find((x) => x.codigo === codigo.trim().toUpperCase())
    if (p) setDescripcion(p.nombre)
  }, [sugeridos, codigo])

  async function guardar(perfil?: OpcionProducto) {
    setError(null)
    setOcupado(true)
    try {
      const ruta = s ? `/api/solicitudes-corte/${s.id}/aprobar` : '/api/ot/planificar'
      const r = await pedir<{ orden_id: number; numero: number; avisos: string[] }>(ruta, {
        metodo: 'POST',
        cuerpo: {
          tipo, fecha, numero: numero ? Number(numero) : null,
          pieza_id: tipo === 'maquila' ? null : pieza?.id ?? null,
          flejes: tipo === 'maquila' ? flejes.map((f) => f.id) : [],
          cortes: tipo === 'slitter' ? cortes.filter((c) => c.ancho_mm.trim()).map((c) => ({ ancho_mm: dec(c.ancho_mm), rollos: Number(c.rollos || '1') })) : [],
          largo_mm: tipo === 'lamina' || tipo === 'ctf' ? dec(largo) : null,
          ancho_mm: (tipo === 'lamina' || tipo === 'ctf') && ancho.trim() ? dec(ancho) : null,
          redondear_espesor: redondear === true,
          codigo_producto: tipo === 'maquila' ? (perfil?.codigo ?? codigo.trim().toUpperCase()) : null,
          descripcion: tipo === 'maquila' ? (perfil?.nombre ?? (descripcion.trim() || null)) : null,
          calidad: calidad.trim() || null,
          observacion: observacion.trim() || null,
        },
      })
      const propietario = tipo === 'maquila' ? (elegido?.nombre ?? '') : (pieza?.propietario_nombre ?? '')
      setHecha({ id: r.orden_id, numero: r.numero, propietario })
      hojaTrabajo({ id: r.orden_id, tipo, numero: r.numero, propietario }, setError)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo planificar')
    } finally {
      setOcupado(false)
    }
  }

  async function enviar(e: FormEvent) {
    e.preventDefault()
    if (tipo === 'maquila' && flejes.length > 0 && flejes[0].espesor_mm && codigo.trim() &&
        codigo.trim().toUpperCase() !== perfilDecidido) {
      try {
        const v = await pedir<VariantesEspesor>('/api/productos/variantes-espesor', {
          metodo: 'POST', cuerpo: { codigo: codigo.trim().toUpperCase(), espesor_mm: flejes[0].espesor_mm },
        })
        if (v.comercial && v.comercial.codigo !== v.real.codigo) { setVariantes(v); return }
      } catch { /* perfil sin regla: se usa el elegido */ }
    }
    await guardar()
  }

  if (hecha) {
    return (
      <div className="exito">
        {s ? `Solicitud ${s.numero} autorizada como ` : ''}OC {NOMBRE_TIPO[tipo]} {hecha.numero} planificada: la hoja de trabajo se abrió en otra pestaña para imprimir.{' '}
        <button className="enlace" onClick={() => hojaTrabajo({ ...hecha, tipo }, setError)}>Abrir la hoja otra vez</button>
        {' · '}<button className="enlace" onClick={() => hojaTrabajo({ ...hecha, tipo }, setError, true)}>Guardar la hoja en carpeta</button>
        {' · '}<button className="enlace" onClick={onHecha}>Listo</button>
      </div>
    )
  }

  const necesitaElegir = (tipo === 'lamina' || tipo === 'ctf') && comercial !== null && redondear === null

  return (
    <form className="tarjeta bloque" onSubmit={enviar}>
      {s && (
        <div className="alerta">
          <strong>Autorizando la solicitud {s.numero} de {s.tercero}.</strong> Viene cargada con lo que pidió; revisa y cambia lo
          que haga falta (cortes, largo, perfil, número, calidad). Lo que guardes es la orden definitiva.
        </div>
      )}
      <div className="formulario cuatro-columnas sin-relleno">
        <label>Máquina
          <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoPlan)}>
            <option value="slitter">Slitter</option><option value="lamina">Laminadora</option>
            <option value="ctf">CTF</option><option value="maquila">Maquila de perfiles</option>
          </select>
        </label>
        <label>Número de OC<input inputMode="numeric" value={numero} onChange={(e) => setNumero(e.target.value)} /></label>
        <label>Fecha<input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} required /></label>
        <label>Calidad<input value={calidad} onChange={(e) => setCalidad(e.target.value)} placeholder="1er-F" /></label>
      </div>

      {tipo !== 'maquila' ? (
        <div className="formulario sin-relleno">
          <label>Cliente dueño del material <span className="tenue pequeno">(opcional: acota el buscador a su inventario)</span>
            <input list="clientes-plan" value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Escribe para buscar" />
            <datalist id="clientes-plan">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
          </label>
          <label>{tipo === 'lamina' ? 'Bobina que entra' : 'Bobina o fleje que entra'}
            <BuscadorPiezas propietarioId={elegido?.id ?? null} excluir={pieza ? [pieza.id] : []} onElegir={setPieza}
              mostrarDueno={!elegido} tipo={tipo === 'lamina' ? 'bobina' : ''}
              placeholder={elegido ? `Inventario de ${elegido.nombre}: código o medida · F4 para ver todo` : 'Código, medida o dueño · F4 para ver todo'} />
          </label>
          {pieza && (
            <p className="pequeno sin-margen"><span className="codigo">{pieza.codigo_fisico}</span> · {pieza.propietario_nombre} ·
              {' '}{mm(pieza.espesor_mm, true)} × {mm(pieza.ancho_mm)} mm · {kg(pieza.saldo_kg)}</p>
          )}
        </div>
      ) : (
        <div className="formulario cuatro-columnas sin-relleno">
          <label className="doble">Cliente dueño de los flejes
            <input list="clientes-plan-maquila" value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Escribe para buscar" />
            <datalist id="clientes-plan-maquila">{terceros.map((t) => <option key={t.id} value={t.nombre} />)}</datalist>
          </label>
          <label className="doble">Agregar fleje (hasta 6)
            <BuscadorPiezas propietarioId={elegido?.id ?? null} excluir={flejes.map((f) => f.id)} tipo="fleje"
              deshabilitado={elegido ? (flejes.length >= 6 ? 'máximo 6 flejes' : null) : 'elige primero el cliente'}
              onElegir={(p) => setFlejes([...flejes, p])} placeholder="Código del fleje" />
          </label>
          {flejes.length > 0 && (
            <ul className="ancho-completo pequeno">
              {flejes.map((f) => (
                <li key={f.id}><span className="codigo">{f.codigo_fisico}</span> · {mm(f.espesor_mm, true)} × {mm(f.ancho_mm)} mm · {kg(f.saldo_kg)}
                  {' '}<button type="button" className="enlace" onClick={() => setFlejes(flejes.filter((x) => x.id !== f.id))}>Quitar</button></li>
              ))}
            </ul>
          )}
          <SugerenciasPerfil fleje={flejes[0] ?? null} elegido={perfilDecidido}
            onElegir={(op) => { setCodigo(op.codigo); setDescripcion(op.nombre); setPerfilDecidido(op.codigo) }} />
          <label className="doble">Perfil (código o nombre)
            <input list="perfiles-plan" value={codigo} onChange={(e) => setCodigo(e.target.value)} placeholder="PERHNVIG2006000 o «vigueta 2,00»" required />
            <datalist id="perfiles-plan">{sugeridos.map((p) => <option key={p.id} value={p.codigo}>{p.nombre}</option>)}</datalist>
          </label>
          <label className="doble">Descripción<input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Del catálogo" /></label>
        </div>
      )}

      {(tipo === 'lamina' || tipo === 'ctf') && (
        <div className="formulario cuatro-columnas sin-relleno">
          <label>Largo de la lámina (mm)<input inputMode="decimal" value={largo} onChange={(e) => setLargo(e.target.value)} required /></label>
          <label>Ancho (mm)<input inputMode="decimal" value={ancho} onChange={(e) => setAncho(e.target.value)} placeholder="El de la bobina" /></label>
          {comercial && pieza && (
            <div className="doble alerta">
              La bobina es de <strong>{pieza.espesor_mm} mm</strong>. ¿Las láminas llevan ese espesor o se redondean a {comercial} mm?
              <div className="acciones">
                <button type="button" className={redondear === false ? 'primario' : 'secundario'} onClick={() => setRedondear(false)}>Mantener {pieza.espesor_mm} mm</button>
                <button type="button" className={redondear === true ? 'primario' : 'secundario'} onClick={() => setRedondear(true)}>Redondear a {comercial} mm</button>
              </div>
            </div>
          )}
        </div>
      )}

      {tipo === 'slitter' && (
        <div className="tabla-envoltura">
          <table className="tabla compacta cortes">
            <thead><tr><th>Ancho (mm)</th><th>Rollos</th><th></th></tr></thead>
            <tbody>
              {cortes.map((c, i) => (
                <tr key={i}>
                  <td><input inputMode="decimal" value={c.ancho_mm} onChange={(e) => setCortes(cortes.map((x, j) => (j === i ? { ...x, ancho_mm: e.target.value } : x)))} /></td>
                  <td><input inputMode="numeric" value={c.rollos} onChange={(e) => setCortes(cortes.map((x, j) => (j === i ? { ...x, rollos: e.target.value } : x)))} /></td>
                  <td>{cortes.length > 1 && <button type="button" className="enlace" onClick={() => setCortes(cortes.filter((_, j) => j !== i))}>Quitar</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {cortes.length < 6 && <button type="button" className="secundario" onClick={() => setCortes([...cortes, { ancho_mm: '', rollos: '1' }])}>Agregar corte</button>}
        </div>
      )}

      <label>Indicaciones para el operador (salen en la hoja)
        <textarea rows={2} value={observacion} onChange={(e) => setObservacion(e.target.value)} />
      </label>

      {variantes && (
        <div className="alerta">
          Los flejes son de <strong>{variantes.espesor_real} mm</strong>. ¿El perfil lleva ese espesor o se redondea a {variantes.espesor_comercial} mm?
          <div className="acciones">
            {[{ t: `Mantener ${variantes.espesor_real} mm`, op: variantes.real }, ...(variantes.comercial ? [{ t: `Redondear a ${variantes.espesor_comercial} mm`, op: variantes.comercial }] : [])].map(({ t, op }) => (
              <button key={op.codigo} type="button" className="primario" disabled={ocupado}
                onClick={() => { setVariantes(null); setCodigo(op.codigo); setDescripcion(op.nombre); void guardar(op) }}>
                {t} · <span className="codigo">{op.codigo}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}
      <div className="acciones">
        <button className="primario" disabled={ocupado || necesitaElegir} title={necesitaElegir ? 'Elige si se redondea el espesor' : undefined}>
          {ocupado ? 'Guardando…' : s ? 'Autorizar, planificar e imprimir hoja' : 'Planificar e imprimir hoja'}
        </button>
        <button type="button" className="secundario" onClick={onCancelar}>Cerrar</button>
      </div>
    </form>
  )
}
