import { useEffect, useState } from 'react'
import { consulta, ocupacion, pedir, type Conteo, type Existencias, type FichaPieza as Ficha, type Pieza, type Usuario } from '../api'
import { fecha, hoyIso, kg, mm, NOMBRE_MOVIMIENTO } from '../formato'
import { cantidadConteo, DiferenciaConteo, EstadoConteo } from './Conteos'
import Modal from './Modal'

interface Props {
  id: number
  usuario: Usuario
  onCerrar: () => void
  onCambio: () => void
}

type Editable = Pick<Pieza, 'codigo_fisico' | 'buque' | 'fecha_entrada'>

const ETIQUETAS: Record<keyof Editable, string> = {
  codigo_fisico: 'Código de bobina',
  buque: 'Buque',
  fecha_entrada: 'Fecha de entrada',
}

export default function FichaPieza({ id, usuario, onCerrar, onCambio }: Props) {
  const [ficha, setFicha] = useState<Ficha | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editando, setEditando] = useState<Editable | null>(null)
  const [revisando, setRevisando] = useState(false)
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [ajustando, setAjustando] = useState(false)
  const [saldoNuevo, setSaldoNuevo] = useState('0')
  const [motivoAjuste, setMotivoAjuste] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [uniendo, setUniendo] = useState(false)
  const [candidatas, setCandidatas] = useState<Pieza[] | null>(null)
  const [destino, setDestino] = useState<number | null>(null)
  const [motivoUnion, setMotivoUnion] = useState('')
  const [unida, setUnida] = useState<string | null>(null)
  // Conteo físico en patio (auditoría): queda registrado aunque cuadre.
  const [contando, setContando] = useState(false)
  const [conteo, setConteo] = useState({ contado: '', contado_por: '', fecha: hoyIso(), observacion: '', ajustar: true })
  const [conteoHecho, setConteoHecho] = useState<Conteo | null>(null)
  const [descartando, setDescartando] = useState<number | null>(null)
  const [motivoDescarte, setMotivoDescarte] = useState('')
  const puedeEditar = usuario.rol === 'socio' || usuario.rol === 'asistente'
  // Láminas, perfiles y generales: existencia por código y dueño, en piezas.
  const enPiezas = ficha?.pieza.saldo_unidades !== null && ficha?.pieza.saldo_unidades !== undefined

  useEffect(() => {
    pedir<Ficha>(`/api/piezas/${id}`).then(setFicha).catch((e: Error) => setError(e.message))
  }, [id])

  const cambios = (() => {
    if (!ficha || !editando) return []
    return (Object.keys(ETIQUETAS) as (keyof Editable)[])
      .filter((k) => (editando[k] ?? '') !== (ficha.pieza[k] ?? ''))
      .map((k) => ({ campo: k, antes: ficha.pieza[k] ?? '—', despues: editando[k] || '—' }))
  })()

  async function guardar() {
    if (!editando) return
    setOcupado(true)
    setError(null)
    try {
      const cuerpo = Object.fromEntries(cambios.map((c) => [c.campo, editando[c.campo] || null]))
      const pieza = await pedir<Pieza>(`/api/piezas/${id}`, { metodo: 'PATCH', cuerpo })
      setFicha((f) => (f ? { ...f, pieza } : f))
      setEditando(null)
      setRevisando(false)
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar')
    } finally {
      setOcupado(false)
    }
  }

  async function ajustar() {
    setOcupado(true)
    setError(null)
    try {
      await pedir(`/api/piezas/${id}/ajuste`, {
        metodo: 'POST',
        cuerpo: enPiezas
          ? { saldo_nuevo_kg: '0', saldo_nuevo_unidades: Number(saldoNuevo.trim() || '0'), motivo: motivoAjuste }
          : { saldo_nuevo_kg: saldoNuevo.trim().replace(',', '.'), motivo: motivoAjuste },
      })
      setFicha(await pedir<Ficha>(`/api/piezas/${id}`))
      setAjustando(false)
      setMotivoAjuste('')
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo ajustar')
    } finally {
      setOcupado(false)
    }
  }

  async function registrarConteo() {
    setOcupado(true)
    setError(null)
    try {
      const c = await pedir<Conteo>(`/api/piezas/${id}/conteo`, {
        metodo: 'POST',
        cuerpo: { contado: conteo.contado.trim().replace(',', '.'), contado_por: conteo.contado_por.trim() || null,
          fecha: conteo.fecha || null, observacion: conteo.observacion.trim() || null,
          ajustar: usuario.rol === 'socio' && conteo.ajustar },
      })
      setFicha(await pedir<Ficha>(`/api/piezas/${id}`))
      setConteoHecho(c)
      setContando(false)
      setConteo((x) => ({ ...x, contado: '', observacion: '' }))
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar el conteo')
    } finally {
      setOcupado(false)
    }
  }

  async function resolverConteo(conteoId: number, accion: 'ajustar' | 'descartar') {
    setOcupado(true)
    setError(null)
    try {
      await pedir<Conteo>(`/api/conteos/${conteoId}/resolver`, {
        metodo: 'POST', cuerpo: { accion, motivo: accion === 'descartar' ? motivoDescarte.trim() : null },
      })
      setFicha(await pedir<Ficha>(`/api/piezas/${id}`))
      setDescartando(null)
      setMotivoDescarte('')
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo resolver el conteo')
    } finally {
      setOcupado(false)
    }
  }

  // Unir: las otras existencias del mismo dueño y tipo (el mismo material que quedó con otro código)
  async function abrirUnion() {
    if (!ficha) return
    setUniendo(true)
    setDestino(null)
    try {
      const r = await pedir<Existencias>(`/api/existencias${consulta({ propietario_id: ficha.pieza.propietario_id, tipo: ficha.pieza.tipo,
        incluir_agotadas: true, limite: 5000 })}`)
      const misma = (x: Pieza) => ficha.pieza.espesor_mm && x.espesor_mm === ficha.pieza.espesor_mm && x.ancho_mm === ficha.pieza.ancho_mm
        && x.largo_mm === ficha.pieza.largo_mm
      setCandidatas(r.piezas.filter((x) => x.id !== ficha.pieza.id)
        .sort((a, b) => Number(misma(b)) - Number(misma(a)) || a.codigo_fisico.localeCompare(b.codigo_fisico)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las existencias')
    }
  }

  async function unir() {
    if (!destino) return
    setOcupado(true)
    setError(null)
    try {
      const d = await pedir<Pieza>(`/api/piezas/${id}/unir`, { metodo: 'POST', cuerpo: { destino_id: destino, motivo: motivoUnion } })
      setFicha(await pedir<Ficha>(`/api/piezas/${id}`))
      setUnida(`Listo: las piezas pasaron a ${d.codigo_fisico}, que ahora tiene ${(d.saldo_unidades ?? 0).toLocaleString('es-VE')} pzas. `
        + 'Si fue un error, anula el ajuste en Salidas › Documentos.')
      setUniendo(false)
      setMotivoUnion('')
      onCambio()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo unir')
    } finally {
      setOcupado(false)
    }
  }

  async function anular() {
    setOcupado(true)
    setError(null)
    try {
      await pedir<Pieza>(`/api/piezas/${id}`, { metodo: 'DELETE', cuerpo: { motivo } })
      onCambio()
      onCerrar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo anular')
      setOcupado(false)
    }
  }

  const p = ficha?.pieza
  return (
    <Modal titulo={p ? p.codigo_fisico : 'Pieza'} onCerrar={onCerrar} ancho>
      {error && <p className="error">{error}</p>}
      {!ficha && !error && <p className="tenue">Cargando…</p>}
      {p && ficha && (
        <>
          {ocupacion(p).length > 0 && (
            <div className="alerta">{ocupacion(p).join(' · ')}. {p.reservada_en || p.en_proceso
              ? 'No sale en otra nota, despacho, liberación u orden hasta que se cierre o se anule.' : ''}</div>
          )}
          <div className="ficha-resumen">
            {enPiezas ? (
              <>
                <div><span>Existencia</span><strong>{(p.saldo_unidades ?? 0).toLocaleString('es-VE')} pzas</strong></div>
                <div><span>Saldo</span><strong>{kg(p.saldo_kg)}</strong></div>
                <div><span>Han entrado</span><strong>{(p.unidades_entrada ?? 0).toLocaleString('es-VE')} pzas</strong></div>
              </>
            ) : (
              <>
                <div><span>Saldo</span><strong>{kg(p.saldo_kg)}</strong></div>
                <div><span>Entró con</span><strong>{kg(p.peso_entrada_kg)}</strong></div>
              </>
            )}
            <div><span>Estado</span><strong className={`estado ${p.estado}`}>{p.estado}</strong></div>
          </div>

          {!editando && (
            <dl className="datos">
              <dt>Producto</dt><dd>{p.codigo_producto ?? '—'}</dd>
              <dt>Descripción</dt><dd>{p.descripcion ?? '—'}</dd>
              <dt>Acero / norma</dt><dd>{p.tipo_acero ?? '—'} · {p.norma ?? '—'}</dd>
              <dt>Medidas</dt><dd>{mm(p.espesor_mm, true)} mm × {mm(p.ancho_mm)} mm</dd>
              <dt>Dueño</dt><dd>{p.propietario_nombre}</dd>
              <dt>Fecha de entrada</dt><dd>{fecha(p.fecha_entrada)}</dd>
              <dt>Buque</dt><dd>{p.buque ?? '—'}</dd>
              {ficha.origen && (
                <>
                  <dt>Viene de</dt>
                  <dd>
                    {ficha.origen.codigo ? <span className="codigo">{ficha.origen.codigo}</span> : '—'}
                    {ficha.origen.orden_numero !== null && ` · OC ${ficha.origen.orden_tipo ?? ''} ${ficha.origen.orden_numero}`}
                  </dd>
                </>
              )}
              {p.calidad && <><dt>Calidad</dt><dd>{p.calidad}</dd></>}
            </dl>
          )}

          {editando && (
            <div className="formulario dos-columnas">
              <label>
                {enPiezas ? 'Código del producto' : ETIQUETAS.codigo_fisico}
                {enPiezas && <span className="tenue pequeno"> (recodificar: conserva saldo e historial; descripción y medidas salen del código)</span>}
                <input value={editando.codigo_fisico}
                  onChange={(e) => setEditando({ ...editando, codigo_fisico: e.target.value })} />
              </label>
              <label>
                {ETIQUETAS.fecha_entrada}
                <input type="date" value={editando.fecha_entrada ?? ''}
                  onChange={(e) => setEditando({ ...editando, fecha_entrada: e.target.value || null })} />
              </label>
              <label>
                {ETIQUETAS.buque}
                <input value={editando.buque ?? ''}
                  onChange={(e) => setEditando({ ...editando, buque: e.target.value })} />
              </label>
            </div>
          )}

          {revisando && (
            <div className="confirmacion">
              <p><strong>Vas a cambiar:</strong></p>
              <ul>
                {cambios.map((c) => (
                  <li key={c.campo}>{c.campo === 'codigo_fisico' && enPiezas ? 'Código del producto' : ETIQUETAS[c.campo]}: <s>{c.antes}</s> → <strong>{c.despues}</strong></li>
                ))}
              </ul>
              <p className="tenue pequeno">El cambio queda registrado con tu usuario.</p>
            </div>
          )}

          {puedeEditar && (
            <div className="acciones">
              {!editando && (
                <button className="secundario"
                  onClick={() => setEditando({ codigo_fisico: p.codigo_fisico, buque: p.buque, fecha_entrada: p.fecha_entrada })}>
                  Corregir datos
                </button>
              )}
              {editando && !revisando && (
                <>
                  <button className="primario" disabled={cambios.length === 0} onClick={() => setRevisando(true)}>
                    Revisar cambios
                  </button>
                  <button className="secundario" onClick={() => setEditando(null)}>Cancelar</button>
                </>
              )}
              {revisando && (
                <>
                  <button className="primario" disabled={ocupado} onClick={() => void guardar()}>Confirmar</button>
                  <button className="secundario" onClick={() => setRevisando(false)}>Volver</button>
                </>
              )}
              {!editando && !anulando && !ajustando && !contando && (
                <button className="secundario" onClick={() => { setConteoHecho(null); setContando(true) }}>Registrar conteo</button>
              )}
              {usuario.rol === 'socio' && !editando && !anulando && !ajustando && (
                <button className="secundario" onClick={() => { setSaldoNuevo('0'); setAjustando(true) }}>Ajustar saldo</button>
              )}
              {usuario.rol === 'socio' && enPiezas && (p.saldo_unidades ?? 0) > 0 && !editando && !anulando && !ajustando && !uniendo && (
                <button className="secundario" onClick={() => void abrirUnion()}>Unir con otra existencia</button>
              )}
              {usuario.rol === 'socio' && !editando && !anulando && !ajustando && (
                <button className="peligro" onClick={() => setAnulando(true)}>Anular pieza</button>
              )}
            </div>
          )}

          {unida && <div className="exito">{unida}</div>}
          {conteoHecho && (
            <div className={conteoHecho.estado === 'pendiente' ? 'alerta' : 'exito'}>
              Conteo registrado: {cantidadConteo(conteoHecho.contado, conteoHecho.unidad)}.{' '}
              {conteoHecho.estado === 'cuadra' && 'Cuadra con el sistema.'}
              {conteoHecho.estado === 'ajustado' && <>No cuadraba (<DiferenciaConteo c={conteoHecho} />): el saldo quedó ajustado al conteo.</>}
              {conteoHecho.estado === 'pendiente' && <>No cuadra (<DiferenciaConteo c={conteoHecho} />): queda pendiente para que un socio lo ajuste o lo descarte.</>}
            </div>
          )}
          {contando && (
            <div className="confirmacion">
              <p className="pequeno sin-margen">
                Lo que se contó en el patio. Queda en el historial de conteos aunque cuadre: es el punto de partida si más
                adelante algo no cuadra.
              </p>
              <div className="formulario dos-columnas sin-relleno">
                <label>Según el sistema<input value={enPiezas ? `${p.saldo_unidades} pzas` : kg(p.saldo_kg)} disabled /></label>
                <label>{enPiezas ? 'Piezas contadas' : 'Kg en patio'}
                  <input inputMode={enPiezas ? 'numeric' : 'decimal'} value={conteo.contado} autoFocus
                    onChange={(e) => setConteo({ ...conteo, contado: e.target.value })} />
                </label>
                <label>Contó<input value={conteo.contado_por} placeholder="Quién contó en el patio"
                  onChange={(e) => setConteo({ ...conteo, contado_por: e.target.value })} /></label>
                <label>Fecha del conteo<input type="date" value={conteo.fecha} onChange={(e) => setConteo({ ...conteo, fecha: e.target.value })} /></label>
                <label className="ancho-completo">Observación<textarea rows={2} value={conteo.observacion}
                  placeholder="Opcional: dónde estaba, estado del material…"
                  onChange={(e) => setConteo({ ...conteo, observacion: e.target.value })} /></label>
                {usuario.rol === 'socio' && (
                  <label className="casilla ancho-completo">
                    <input type="checkbox" checked={conteo.ajustar} onChange={(e) => setConteo({ ...conteo, ajustar: e.target.checked })} />
                    Si no cuadra, ajustar el saldo a lo contado
                  </label>
                )}
              </div>
              <div className="acciones">
                <button className="primario" disabled={conteo.contado.trim() === '' || ocupado} onClick={() => void registrarConteo()}>
                  Registrar conteo
                </button>
                <button className="secundario" onClick={() => setContando(false)}>Cancelar</button>
              </div>
            </div>
          )}
          {uniendo && (
            <div className="confirmacion">
              <p className="pequeno sin-margen">
                Para el mismo material que quedó en dos líneas con códigos distintos: las {(p.saldo_unidades ?? 0).toLocaleString('es-VE')} piezas
                ({kg(p.saldo_kg)}) de <strong>{p.codigo_fisico}</strong> pasan a la existencia que elijas, del mismo dueño. Las dos conservan
                su historial y queda un ajuste con el motivo, que se puede anular.
              </p>
              {candidatas === null && <p className="tenue">Cargando…</p>}
              {candidatas !== null && candidatas.length === 0 && <p className="tenue">{p.propietario_nombre} no tiene otra existencia de este tipo.</p>}
              {candidatas !== null && candidatas.length > 0 && (
                <label>Pasar las piezas a
                  <select value={destino ?? ''} onChange={(e) => setDestino(e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Elige la existencia que se queda…</option>
                    {candidatas.map((x) => (
                      <option key={x.id} value={x.id}>{x.codigo_fisico} · {x.descripcion ?? ''} · {(x.saldo_unidades ?? 0).toLocaleString('es-VE')} pzas</option>
                    ))}
                  </select>
                </label>
              )}
              <label>Motivo<textarea rows={2} value={motivoUnion} onChange={(e) => setMotivoUnion(e.target.value)}
                placeholder="Mismo material registrado con otro código" /></label>
              <div className="acciones">
                <button className="primario" disabled={!destino || motivoUnion.trim().length < 5 || ocupado} onClick={() => void unir()}>Unir</button>
                <button className="secundario" onClick={() => setUniendo(false)}>Cancelar</button>
              </div>
            </div>
          )}

          {ajustando && (
            <div className="confirmacion">
              <p className="pequeno sin-margen">
                Para remanentes que no existen en patio o pesos mal cargados. La pieza conserva su historia y el ajuste
                queda registrado con su motivo.
              </p>
              <div className="formulario dos-columnas sin-relleno">
                <label>Saldo actual<input value={enPiezas ? `${p.saldo_unidades} pzas` : kg(p.saldo_kg)} disabled /></label>
                <label>{enPiezas ? 'Piezas que hay de verdad (conteo)' : 'Saldo correcto (kg)'}
                  <input inputMode={enPiezas ? 'numeric' : 'decimal'} value={saldoNuevo} onChange={(e) => setSaldoNuevo(e.target.value)} />
                </label>
                <label className="ancho-completo">Motivo<textarea rows={2} value={motivoAjuste} onChange={(e) => setMotivoAjuste(e.target.value)} /></label>
              </div>
              <div className="acciones">
                <button className="primario" disabled={motivoAjuste.trim().length < 5 || ocupado} onClick={() => void ajustar()}>
                  Ajustar a {enPiezas ? `${Number(saldoNuevo || '0')} pzas` : kg(Number(saldoNuevo.replace(',', '.') || '0'))}
                </button>
                <button className="secundario" onClick={() => setAjustando(false)}>Cancelar</button>
              </div>
            </div>
          )}

          {anulando && (
            <div className="confirmacion peligro-caja">
              <label>
                Motivo de la anulación (queda registrado)
                <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={2} />
              </label>
              <div className="acciones">
                <button className="peligro" disabled={motivo.trim().length < 5 || ocupado} onClick={() => void anular()}>
                  Anular definitivamente
                </button>
                <button className="secundario" onClick={() => setAnulando(false)}>Cancelar</button>
              </div>
            </div>
          )}

          {ficha.conteos && ficha.conteos.length > 0 && (
            <>
              <h3>Conteos físicos</h3>
              <div className="tabla-envoltura">
                <table className="tabla compacta">
                  <thead>
                    <tr><th>Fecha</th><th className="n">Sistema</th><th className="n">Contado</th><th className="n">Diferencia</th><th>Estado</th><th>Contó</th></tr>
                  </thead>
                  <tbody>
                    {ficha.conteos.map((c) => (
                      <tr key={c.id ?? 0} title={[c.observacion, c.resolucion].filter(Boolean).join(' · ') || undefined}>
                        <td>{fecha(c.fecha)}</td>
                        <td className="n">{cantidadConteo(c.sistema, c.unidad)}</td>
                        <td className="n fuerte">{cantidadConteo(c.contado, c.unidad)}</td>
                        <td className="n"><DiferenciaConteo c={c} /></td>
                        <td>
                          <EstadoConteo c={c} />
                          {c.estado === 'pendiente' && usuario.rol === 'socio' && c.id !== null && descartando !== c.id && (
                            <div className="pequeno">
                              <button className="enlace" disabled={ocupado} onClick={() => void resolverConteo(c.id as number, 'ajustar')}>
                                Ajustar a {cantidadConteo(c.contado, c.unidad)}
                              </button>{' · '}
                              <button className="enlace" onClick={() => { setDescartando(c.id); setMotivoDescarte('') }}>Descartar</button>
                            </div>
                          )}
                          {descartando === c.id && c.id !== null && (
                            <div>
                              <input value={motivoDescarte} placeholder="Por qué (p. ej. se recontó)" autoFocus
                                onChange={(e) => setMotivoDescarte(e.target.value)} />
                              <button className="enlace" disabled={!motivoDescarte.trim() || ocupado}
                                onClick={() => void resolverConteo(c.id as number, 'descartar')}>Descartar</button>{' · '}
                              <button className="enlace" onClick={() => setDescartando(null)}>Cancelar</button>
                            </div>
                          )}
                        </td>
                        <td>{c.contado_por ?? '—'}{c.origen === 'agente' && <span className="tenue pequeno"> · vía Prosi</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <h3>Movimientos</h3>
          <div className="tabla-envoltura">
            <table className="tabla compacta">
              <thead>
                <tr><th>Fecha</th><th>Movimiento</th><th>Documento</th>{enPiezas && <th className="n">Piezas</th>}<th className="n">kg</th><th className="n">Saldo</th></tr>
              </thead>
              <tbody>
                {ficha.movimientos.map((m) => (
                  <tr key={m.id} title={m.observacion ?? undefined}>
                    <td>{fecha(m.fecha)}</td>
                    <td>{NOMBRE_MOVIMIENTO[m.tipo] ?? m.tipo}</td>
                    <td>{m.documento_numero ?? '—'}</td>
                    {enPiezas && <td className={`n ${(m.unidades ?? 0) < 0 ? 'negativo' : ''}`}>{m.unidades ?? '—'}</td>}
                    <td className={`n ${Number(m.kg) < 0 ? 'negativo' : ''}`}>{Number(m.kg) === 0 ? '—' : kg(m.kg)}</td>
                    <td className="n">{enPiezas ? `${m.saldo_despues_unidades ?? '—'} pzas · ` : ''}{kg(m.saldo_despues_kg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {ficha.hijas.length > 0 && (
            <>
              <h3>Rollos que salieron de esta pieza</h3>
              <ul className="lista-hijas">
                {ficha.hijas.map((h) => <li key={h.id}>{h.codigo_fisico} · {kg(h.saldo_kg)}</li>)}
              </ul>
            </>
          )}
        </>
      )}
    </Modal>
  )
}
