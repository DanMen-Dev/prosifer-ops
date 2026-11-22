import { useState } from 'react'
import { pedir, type AvisoEntrada, type RenglonAviso, type Usuario } from '../api'
import { AvisosPersonal } from './AvisosEntrada'
import EntradaBobina, { type InicialBobina } from './EntradaBobina'
import EntradaExistencia, { type InicialExistencia } from './EntradaExistencia'
import { Documentos } from './Salidas'

type Pestana = 'avisos' | 'bobina' | 'existencia' | 'recibos'

const txt = (v: string | number | null | undefined) => (v === null || v === undefined ? '' : String(v))

/** Entradas al patio: bobinas (pieza por pieza), láminas, perfiles o generales (por piezas de un código),
 *  los avisos con que los clientes anuncian material por llegar y los documentos de entrada ya registrados. */
export default function Entradas({ usuario, onVerInventario, inicial, avisosPendientes = 0, onCambioAvisos }: {
  usuario: Usuario; onVerInventario: () => void; inicial?: Pestana; avisosPendientes?: number; onCambioAvisos?: () => void
}) {
  const [pestana, setPestana] = useState<Pestana>(inicial ?? 'bobina')
  const [bobina, setBobina] = useState<InicialBobina | null>(null)
  const [existencia, setExistencia] = useState<InicialExistencia | null>(null)
  const [origen, setOrigen] = useState<string | null>(null)
  const [enlace, setEnlace] = useState<{ aviso: AvisoEntrada; indice: number } | null>(null)
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null)

  // Al guardar la entrada que vino de un aviso, queda anotada en su renglón (así se sabe qué falta registrar).
  function guardada(piezaId: number, texto: string) {
    if (!enlace) return
    const { aviso, indice } = enlace
    setEnlace(null)
    pedir(`/api/avisos-entrada/${aviso.id}/renglones/${indice}/entrada`, { metodo: 'POST', cuerpo: { pieza_id: piezaId, texto } })
      .then(() => { setMensaje({ ok: true, texto: `Anotado en el aviso N° ${aviso.numero}, renglón ${indice + 1}.` }); onCambioAvisos?.() })
      .catch((e: Error) => setMensaje({ ok: false, texto: `La entrada se guardó, pero no se pudo anotar en el aviso: ${e.message}` }))
  }

  function registrar(r: RenglonAviso, a: AvisoEntrada, indice: number) {
    setEnlace({ aviso: a, indice })
    setMensaje(null)
    setOrigen(`aviso de entrada N° ${a.numero} de ${a.tercero}, renglón ${indice + 1}`)
    const comunes = { documento_numero: txt(a.documento_numero), propietario: a.tercero ?? '' }
    if (r.tipo === 'bobina') {
      setBobina({ ...comunes, codigo_bobina: '', tipo_acero: txt(r.tipo_acero), espesor_mm: txt(r.espesor_mm),
        ancho_mm: txt(r.ancho_mm), peso_kg: txt(r.peso_kg) })
      setPestana('bobina')
    } else {
      const piezas = r.cantidad ?? null
      const porPieza = piezas && r.peso_kg ? (Number(r.peso_kg) / piezas).toFixed(2) : ''
      setExistencia({ ...comunes, codigo: txt(r.codigo), descripcion: txt(r.descripcion), unidades: txt(piezas), peso: porPieza,
        ...(a.documento_tipo === 'Factura' ? { documento_tipo: 'Factura' } : {}),
        observacion: `Aviso de entrada N° ${a.numero}` })
      setPestana('existencia')
    }
  }
  const ir = (p: Pestana) => { setOrigen(null); setBobina(null); setExistencia(null); setEnlace(null); setPestana(p) }

  return (
    <>
      <nav className="subpestanas" aria-label="Tipo de entrada">
        <button className={pestana === 'avisos' ? 'activa' : ''} onClick={() => ir('avisos')}>
          Avisos de clientes{avisosPendientes > 0 && <span className="contador">{avisosPendientes}</span>}
        </button>
        <button className={pestana === 'bobina' ? 'activa' : ''} onClick={() => ir('bobina')}>Bobina</button>
        <button className={pestana === 'existencia' ? 'activa' : ''} onClick={() => ir('existencia')}>
          Láminas, perfiles y generales
        </button>
        <button className={pestana === 'recibos' ? 'activa' : ''} onClick={() => ir('recibos')}>
          Documentos y recibos
        </button>
      </nav>
      {mensaje && pestana !== 'avisos' && (
        <div className={mensaje.ok ? 'exito' : 'error'}>{mensaje.texto}{' '}
          <button className="enlace" onClick={() => ir('avisos')}>Volver a los avisos</button></div>
      )}
      {pestana === 'avisos' && <AvisosPersonal onRegistrar={registrar} onCambio={onCambioAvisos} />}
      {pestana === 'bobina' && <EntradaBobina onVerInventario={onVerInventario} inicial={bobina} aviso={bobina ? origen : null}
        onGuardada={guardada} />}
      {pestana === 'existencia' && <EntradaExistencia onVerInventario={onVerInventario} inicial={existencia}
        aviso={existencia ? origen : null} onGuardada={guardada} />}
      {pestana === 'recibos' && (
        <section>
          <p className="tenue">
            Cada fila es un producto que entró. Abre cualquiera para sacar el recibo: los productos del mismo cliente,
            documento y fecha salen juntos en un solo recibo. En "Ajustes" queda el historial de las correcciones de
            inventario (conteos en patio), con su motivo.
          </p>
          <Documentos usuario={usuario} tipoInicial="entrada"
            opcionesTipo={[{ valor: 'entrada', nombre: 'Entradas' }, { valor: 'ajuste', nombre: 'Ajustes de inventario' }]} />
        </section>
      )}
    </>
  )
}
