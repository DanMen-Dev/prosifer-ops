"""Consultas de lectura (existencias, fichas, listados) directamente en SQL.

El lado de lectura no pasa por los casos de uso: no cambia nada y necesita filtros,
uniones y totales que en SQL son baratos. Cada función recibe `cliente`: el tercero
de un usuario cliente (solo ve lo suyo) o None para el personal de Prosifer.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import BigInteger, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app import modelos as m
from app.dominio import codigos
from app.dominio import entidades as e
from app.dominio.impresion import (
    DespachoImpreso, FilaInventario, NotaEntregaImpresa, ReciboEntradaImpreso, RenglonNE, RenglonRecibo, ReporteInventario,
    SeccionInventario,
)
from app.esquemas import (
    BorradorCotizacion, ConteoOut, DetalleDocumento, DetalleOrden, DocumentoOut, ExcluidoReporte, Existencias, FichaPieza,
    FilaReporteSalidas,
    LineaDocumento, MovimientoOut, OrdenOut, OrigenPieza, PiezaOut, RenglonCotizacionIn, ReporteSalidas,
)

TIPOS_SALIDA = ["nota_entrega", "nota_salida", "liberacion", "ajuste"]
TOL_ESPESOR = Decimal("0.06")   # mm: 0,58 real = 0,60 comercial; 2,45 = 2,50


def pieza_out(p: m.Pieza | e.Pieza) -> PiezaOut:
    if isinstance(p, e.Pieza):
        dueno, tipo, norma = p.propietario_nombre, p.tipo_acero_codigo, p.norma_nombre
    else:
        dueno = p.propietario.nombre if p.propietario else ""
        tipo = p.tipo_acero.codigo if p.tipo_acero else None
        norma = p.norma.nombre if p.norma else None
    return PiezaOut(
        id=p.id, tipo=p.tipo, codigo_fisico=p.codigo_fisico, codigo_producto=p.codigo_producto,
        descripcion=p.descripcion, espesor_mm=p.espesor_mm, ancho_mm=p.ancho_mm, largo_mm=p.largo_mm,
        calidad=p.calidad, propietario_id=p.propietario_id, propietario_nombre=dueno, tipo_acero=tipo, norma=norma,
        buque=p.buque, pieza_origen_id=p.pieza_origen_id, fecha_entrada=p.fecha_entrada,
        peso_entrada_kg=p.peso_entrada_kg, saldo_kg=p.saldo_kg, estado=p.estado,
        unidades_entrada=p.unidades_entrada, saldo_unidades=p.saldo_unidades)


def movimiento_out(x: m.Movimiento | e.Movimiento, doc_tipo: str | None, doc_numero: str | None,
                   para_cliente: bool) -> MovimientoOut:
    return MovimientoOut(
        id=x.id, tipo=x.tipo, kg=x.kg, saldo_despues_kg=x.saldo_despues_kg, unidades=x.unidades,
        saldo_despues_unidades=x.saldo_despues_unidades, fecha=x.fecha, documento_tipo=doc_tipo,
        documento_numero=doc_numero, propietario_anterior_id=x.propietario_anterior_id,
        propietario_nuevo_id=x.propietario_nuevo_id, origen=x.origen,
        # Las notas internas y quién registró no se muestran en el portal de clientes.
        observacion=None if para_cliente else x.observacion,
        creado_por="Prosifer" if para_cliente else x.creado_por, creado_en=x.creado_en)


# --- Piezas ----------------------------------------------------------------

def existencias(s: Session, empresa_id: int, cliente: int | None, *, tipo: str | None, propietario_id: int | None,
                tipo_acero: str | None, espesor_mm: Decimal | None, ancho_mm: Decimal | None, codigo: str | None,
                incluir_agotadas: bool, limite: int, espesor_aprox: Decimal | None = None,
                ancho_aprox: Decimal | None = None, texto: str | None = None) -> Existencias:
    filtros = [m.Pieza.empresa_id == empresa_id, m.Pieza.anulada.is_(False)]
    if cliente is not None:
        propietario_id = cliente  # un cliente solo ve lo suyo, pida lo que pida
    if not incluir_agotadas:
        filtros.append(m.Pieza.estado == "disponible")
    if tipo:
        filtros.append(m.Pieza.tipo == tipo)
    if propietario_id:
        filtros.append(m.Pieza.propietario_id == propietario_id)
    if tipo_acero:
        filtros.append(m.Pieza.tipo_acero.has(m.TipoAcero.codigo == tipo_acero.upper()))
    if espesor_mm is not None:
        filtros.append(m.Pieza.espesor_mm == espesor_mm)
    if ancho_mm is not None:
        filtros.append(m.Pieza.ancho_mm == ancho_mm)
    # Búsqueda tolerante (agente, patio): 0,58 y 0,60 son el mismo material dicho real o comercial,
    # y un ancho medido en patio puede diferir unos milímetros del registrado.
    if espesor_aprox is not None:
        filtros.append(m.Pieza.espesor_mm.between(espesor_aprox - TOL_ESPESOR, espesor_aprox + TOL_ESPESOR))
    if ancho_aprox is not None:
        filtros.append(m.Pieza.ancho_mm.between(ancho_aprox * Decimal("0.98"), ancho_aprox * Decimal("1.02")))
    if codigo:
        patron = f"%{codigo.strip()}%"
        filtros.append(m.Pieza.codigo_fisico.ilike(patron) | m.Pieza.codigo_producto.ilike(patron))
    # Texto libre (agente): cada palabra debe estar en la descripción o en los códigos ("tornillo 1/4 galv").
    for palabra in (texto or "").split()[:8]:
        patron = f"%{palabra}%"
        filtros.append(m.Pieza.descripcion.ilike(patron) | m.Pieza.codigo_fisico.ilike(patron)
                       | m.Pieza.codigo_producto.ilike(patron))
    total_piezas, total_kg, total_u, filas_kg = s.execute(
        select(func.count(m.Pieza.id), func.coalesce(func.sum(m.Pieza.saldo_kg), 0),
               func.coalesce(func.sum(m.Pieza.saldo_unidades), 0),
               func.count(m.Pieza.id).filter(m.Pieza.saldo_unidades.is_(None))).where(*filtros)).one()
    piezas = s.scalars(select(m.Pieza).where(*filtros)
                       .order_by(m.Pieza.espesor_mm, m.Pieza.ancho_mm, m.Pieza.largo_mm, m.Pieza.codigo_fisico,
                                 m.Pieza.id).limit(limite)).all()
    # Las piezas de láminas, perfiles y generales solo se suman si todas las filas se llevan en piezas.
    return Existencias(piezas=[pieza_out(p) for p in piezas], total_piezas=total_piezas, total_kg=total_kg,
                       total_unidades=total_u if total_piezas and not filas_kg else None)


def pieza_visible(s: Session, empresa_id: int, cliente: int | None, id_: int) -> m.Pieza | None:
    p = s.get(m.Pieza, id_)
    if p is None or p.empresa_id != empresa_id or (cliente is not None and p.propietario_id != cliente):
        return None
    return p


def ficha(s: Session, empresa_id: int, cliente: int | None, id_: int) -> FichaPieza | None:
    p = pieza_visible(s, empresa_id, cliente, id_)
    if p is None:
        return None
    movs = s.scalars(select(m.Movimiento).where(m.Movimiento.pieza_id == p.id).order_by(m.Movimiento.id)).all()
    hijas = s.scalars(select(m.Pieza).where(m.Pieza.pieza_origen_id == p.id).order_by(m.Pieza.id)).all()
    if cliente is not None:
        hijas = [h for h in hijas if h.propietario_id == cliente]
    origen = None
    if p.pieza_origen_id or p.orden_trabajo_id:
        madre = s.get(m.Pieza, p.pieza_origen_id) if p.pieza_origen_id else None
        orden = s.get(m.OrdenTrabajo, p.orden_trabajo_id) if p.orden_trabajo_id else None
        origen = OrigenPieza(pieza_id=madre.id if madre else None, codigo=madre.codigo_fisico if madre else None,
                             orden_id=orden.id if orden else None, orden_numero=orden.numero if orden else None,
                             orden_tipo=orden.tipo if orden else None)
    cuentas = [] if cliente is not None else conteos(s, empresa_id, pieza_id=p.id, limite=50)
    return FichaPieza(
        origen=origen, pieza=pieza_out(p), hijas=[pieza_out(h) for h in hijas], conteos=cuentas,
        movimientos=[movimiento_out(x, x.documento.tipo if x.documento else None,
                                    x.documento.numero if x.documento else None, cliente is not None) for x in movs])


# --- Conteos físicos en patio ------------------------------------------------

def conteo_out(c: m.Conteo) -> ConteoOut:
    return ConteoOut(
        id=c.id, pieza_id=c.pieza_id, codigo=c.pieza.codigo_fisico, descripcion=c.pieza.descripcion, tipo=c.pieza.tipo,
        propietario_id=c.propietario_id, propietario=c.propietario.nombre if c.propietario else None, fecha=c.fecha,
        unidad=c.unidad, sistema=c.sistema, contado=c.contado, diferencia=c.diferencia, estado=c.estado,
        ajuste_documento_id=c.ajuste_documento_id, ajuste_anulado=bool(c.ajuste_documento and c.ajuste_documento.anulado),
        contado_por=c.contado_por, observacion=c.observacion, resolucion=c.resolucion, origen=c.origen,
        creado_por=c.creado_por, creado_en=c.creado_en, resuelto_por=c.resuelto_por)


def conteos(s: Session, empresa_id: int, *, pieza_id: int | None = None, tercero_id: int | None = None,
            desde: dt.date | None = None, hasta: dt.date | None = None, estado: str | None = None,
            texto: str | None = None, limite: int = 500) -> list[ConteoOut]:
    q = select(m.Conteo).join(m.Pieza, m.Pieza.id == m.Conteo.pieza_id).where(m.Conteo.empresa_id == empresa_id)
    if pieza_id:
        q = q.where(m.Conteo.pieza_id == pieza_id)
    if tercero_id:
        q = q.where(m.Conteo.propietario_id == tercero_id)
    if desde:
        q = q.where(m.Conteo.fecha >= desde)
    if hasta:
        q = q.where(m.Conteo.fecha <= hasta)
    if estado:
        q = q.where(m.Conteo.estado.in_([x.strip() for x in estado.split(",") if x.strip()]))
    for palabra in (texto or "").split():
        patron = f"%{palabra}%"
        q = q.where(or_(m.Pieza.codigo_fisico.ilike(patron), m.Pieza.descripcion.ilike(patron)))
    q = q.order_by(m.Conteo.fecha.desc(), m.Conteo.id.desc()).limit(limite)
    return [conteo_out(c) for c in s.scalars(q).unique()]


# --- Órdenes de trabajo ----------------------------------------------------

def orden_out(o: m.OrdenTrabajo, producidas: int) -> OrdenOut:
    if o.tipo != "slitter" and o.detalle:
        # Láminas y perfiles van a existencias por código: lo producido es el total de piezas de la orden.
        producidas = int(o.detalle.get("total_unidades") or o.detalle.get("total_laminas") or producidas)
    return OrdenOut(
        id=o.id, tipo=o.tipo, numero=o.numero, fecha=o.fecha, estado=o.estado, pieza_id=o.pieza_id,
        codigo_pieza=o.pieza.codigo_fisico if o.pieza else None,
        propietario=o.propietario.nombre if o.propietario else None, estatus_corte=o.estatus_corte,
        kg_consumido=o.kg_consumido, kg_producido=o.kg_producido, kg_scrap=o.kg_scrap,
        piezas_producidas=producidas, calidad=o.calidad, paradas=o.paradas, observacion=o.observacion,
        origen=o.origen, creado_por=o.creado_por,
        plan=(o.detalle or {}).get("plan") if o.estado in ("planificada", "ejecutada") else None)


def ordenes(s: Session, empresa_id: int, cliente: int | None, *, tipo: str | None, desde: dt.date | None,
            hasta: dt.date | None, codigo: str | None, numero: int | None, incluir_anuladas: bool,
            limite: int, estado: str | None = None) -> list[OrdenOut]:
    filtros = [m.OrdenTrabajo.empresa_id == empresa_id]
    if cliente is not None:
        filtros.append(m.OrdenTrabajo.propietario_id == cliente)
    if tipo:
        filtros.append(m.OrdenTrabajo.tipo == tipo)
    if desde:
        filtros.append(m.OrdenTrabajo.fecha >= desde)
    if hasta:
        filtros.append(m.OrdenTrabajo.fecha <= hasta)
    if numero:
        filtros.append(m.OrdenTrabajo.numero == numero)
    if estado:
        filtros.append(m.OrdenTrabajo.estado == estado)
    else:
        # Las planificadas van en su propia lista; una ejecutada ya tiene su orden con resultados.
        filtros.append(m.OrdenTrabajo.estado.not_in(("planificada", "ejecutada")))
        if not incluir_anuladas:
            filtros.append(m.OrdenTrabajo.estado != "anulada")
    if codigo:
        filtros.append(m.OrdenTrabajo.pieza.has(m.Pieza.codigo_fisico.ilike(f"%{codigo.strip()}%")))
    filas = s.scalars(select(m.OrdenTrabajo).where(*filtros)
                      .order_by(m.OrdenTrabajo.fecha.desc().nulls_last(), m.OrdenTrabajo.numero.desc())
                      .limit(limite)).all()
    conteo = dict(s.execute(
        select(m.Pieza.orden_trabajo_id, func.count(m.Pieza.id))
        .where(m.Pieza.orden_trabajo_id.in_([o.id for o in filas]), m.Pieza.anulada.is_(False))
        .group_by(m.Pieza.orden_trabajo_id)).all()) if filas else {}
    return [orden_out(o, conteo.get(o.id, 0)) for o in filas]


def orden_visible(s: Session, empresa_id: int, cliente: int | None, id_: int) -> m.OrdenTrabajo | None:
    o = s.get(m.OrdenTrabajo, id_)
    if o is None or o.empresa_id != empresa_id or (cliente is not None and o.propietario_id != cliente):
        return None
    return o


def detalle_orden(s: Session, empresa_id: int, cliente: int | None, id_: int) -> DetalleOrden | None:
    o = orden_visible(s, empresa_id, cliente, id_)
    if o is None:
        return None
    if o.tipo == "slitter" or o.documento_id is None:
        producidas = s.scalars(select(m.Pieza).where(m.Pieza.orden_trabajo_id == o.id).order_by(m.Pieza.id)).all()
    else:  # existencias por código y dueño a las que esta orden sumó piezas
        producidas = s.scalars(select(m.Pieza).where(m.Pieza.id.in_(
            select(m.Movimiento.pieza_id).where(m.Movimiento.documento_id == o.documento_id,
                                                m.Movimiento.tipo == "produccion"))).order_by(m.Pieza.id)).all()
    vivas = [p for p in producidas if not p.anulada]
    return DetalleOrden(orden=orden_out(o, len(vivas)), detalle=o.detalle,
                        pieza_entrada=pieza_out(o.pieza) if o.pieza else None,
                        producidas=[pieza_out(p) for p in producidas])


# --- Documentos de salida --------------------------------------------------

def documento_out(d: m.Documento, piezas: int, total) -> DocumentoOut:
    return DocumentoOut(
        id=d.id, tipo=d.tipo, numero=d.numero, fecha=d.fecha, tercero_id=d.tercero_id,
        tercero=d.tercero.nombre if d.tercero else None,
        tercero_nuevo=d.tercero_destino.nombre if d.tercero_destino else None, piezas=piezas, total_kg=total,
        anulado=d.anulado, origen=d.origen, creado_por=d.creado_por, observacion=d.observacion,
        encabezado=d.encabezado)


def _vigentes_por_ne(s: Session, ids: list[int]) -> dict[int, list[m.Movimiento]]:
    """Salidas vigentes de cada NE: las suyas y las de sus correcciones, menos las ya deshechas."""
    if not ids:
        return {}
    correcciones = {d.id: d.documento_origen_id for d in s.scalars(
        select(m.Documento).where(m.Documento.documento_origen_id.in_(ids), m.Documento.anulado.is_(False)))}
    movs = s.scalars(select(m.Movimiento).where(
        m.Movimiento.documento_id.in_(ids + list(correcciones)), m.Movimiento.tipo == "salida")
        .order_by(m.Movimiento.id)).all()
    deshechos = set(s.scalars(select(m.Movimiento.revierte_id).where(
        m.Movimiento.revierte_id.in_([x.id for x in movs])))) if movs else set()
    salida: dict[int, list[m.Movimiento]] = {}
    for x in movs:
        if x.id not in deshechos:
            salida.setdefault(correcciones.get(x.documento_id, x.documento_id), []).append(x)
    return salida


def documentos(s: Session, empresa_id: int, cliente: int | None, *, tipo: str | None, numero: str | None,
               tercero_id: int | None, desde: dt.date | None, hasta: dt.date | None, incluir_anulados: bool,
               limite: int) -> list[DocumentoOut]:
    filtros = [m.Documento.empresa_id == empresa_id, m.Documento.tipo.in_([tipo] if tipo else TIPOS_SALIDA)]
    if cliente is not None:
        filtros.append(or_(m.Documento.tercero_id == cliente, m.Documento.tercero_destino_id == cliente))
    if numero:
        filtros.append(m.Documento.numero.ilike(f"%{numero.strip()}%"))
    if tercero_id:
        filtros.append(or_(m.Documento.tercero_id == tercero_id, m.Documento.tercero_destino_id == tercero_id))
    if desde:
        filtros.append(m.Documento.fecha >= desde)
    if hasta:
        filtros.append(m.Documento.fecha <= hasta)
    if not incluir_anulados:
        filtros.append(m.Documento.anulado.is_(False))
    # Lo más reciente arriba; el mismo día, por número de NE de mayor a menor (no por orden de carga).
    numero_ne = case((m.Documento.numero.op("~")("^[0-9]{1,7}$"), cast(m.Documento.numero, BigInteger)), else_=None)
    docs = s.scalars(select(m.Documento).where(*filtros)
                     .order_by(m.Documento.fecha.desc().nulls_last(), numero_ne.desc().nulls_last(),
                               m.Documento.id.desc()).limit(limite)).all()
    if not docs:
        return []
    ids = [d.id for d in docs]
    totales = {fila[0]: (fila[1], fila[2]) for fila in s.execute(
        select(m.Movimiento.documento_id, func.count(m.Movimiento.id),
               func.coalesce(func.sum(func.abs(m.Movimiento.kg)), 0))
        .where(m.Movimiento.documento_id.in_(ids)).group_by(m.Movimiento.documento_id)).all()}
    # NE corregidas: lo vigente. Histórico del Excel: sus líneas tal como se emitieron.
    corregidas = set(s.scalars(select(m.Documento.documento_origen_id).where(m.Documento.documento_origen_id.in_(ids))))
    for ne, movs in _vigentes_por_ne(s, [i for i in ids if i in corregidas]).items():
        totales[ne] = (len(movs), sum((abs(x.kg) for x in movs), Decimal("0")))
    historicos = [d.id for d in docs if d.origen == "excel" or (d.tipo == "nota_entrega" and d.origen == "importacion")]
    if historicos:
        for fila in s.execute(select(m.DocumentoLinea.documento_id, func.count(m.DocumentoLinea.id),
                                     func.coalesce(func.sum(m.DocumentoLinea.kg), 0))
                              .where(m.DocumentoLinea.documento_id.in_(historicos))
                              .group_by(m.DocumentoLinea.documento_id)).all():
            totales[fila[0]] = (fila[1], fila[2])
    # NE de la app con material sin existencia (medidas irregulares): se suman sus renglones
    de_app = [d.id for d in docs if d.tipo in ("nota_entrega", "nota_salida") and d.id not in set(historicos)]
    if de_app:
        for fila in s.execute(select(m.DocumentoLinea.documento_id, func.count(m.DocumentoLinea.id),
                                     func.coalesce(func.sum(m.DocumentoLinea.kg), 0))
                              .where(m.DocumentoLinea.documento_id.in_(de_app))
                              .group_by(m.DocumentoLinea.documento_id)).all():
            n, kg = totales.get(fila[0], (0, 0))
            totales[fila[0]] = (n + fila[1], kg + fila[2])
    return [documento_out(d, *totales.get(d.id, (0, 0))) for d in docs]


def documento_visible(s: Session, empresa_id: int, cliente: int | None, id_: int) -> m.Documento | None:
    d = s.get(m.Documento, id_)
    if d is None or d.empresa_id != empresa_id or (
            cliente is not None and cliente not in (d.tercero_id, d.tercero_destino_id)):
        return None
    return d


def detalle_documento(s: Session, empresa_id: int, cliente: int | None, id_: int) -> DetalleDocumento | None:
    d = documento_visible(s, empresa_id, cliente, id_)
    if d is None:
        return None
    hist = s.scalars(select(m.DocumentoLinea).where(m.DocumentoLinea.documento_id == d.id)
                     .order_by(m.DocumentoLinea.posicion)).all() \
        if d.origen == "excel" or (d.tipo == "nota_entrega" and d.origen == "importacion") else []
    if d.origen == "excel" or hist:
        # Histórico: la NE tal como se emitió en el Excel (las del libro de Slitter, completadas con sus renglones).
        # (entradas históricas: el material entró, kg en positivo)
        entra = d.tipo == "entrada"
        lineas = [LineaDocumento(movimiento_id=None, pieza_id=None, codigo=x.codigo or "—", descripcion=x.descripcion,
                                 tipo_movimiento="entrada" if entra else "salida",
                                 kg=(x.kg or 0) if entra else -(x.kg or 0), saldo_despues_kg=0, cantidad=x.cantidad,
                                 unidad=x.unidad) for x in hist]
        total = sum((x.kg or 0 for x in hist), Decimal("0"))
        # lo que ya se descargó del inventario con esta NE (descarga de material rezagado)
        descargas = [LineaDocumento(movimiento_id=mv.id, pieza_id=p.id, codigo=p.codigo_fisico,
                                    descripcion=p.descripcion, tipo_movimiento=mv.tipo, kg=mv.kg,
                                    saldo_despues_kg=mv.saldo_despues_kg, unidades=mv.unidades,
                                    saldo_despues_unidades=mv.saldo_despues_unidades)
                     for mv, p in s.execute(select(m.Movimiento, m.Pieza).join(m.Pieza, m.Pieza.id == m.Movimiento.pieza_id)
                                            .where(m.Movimiento.documento_id == d.id).order_by(m.Movimiento.id)).all()]
        return DetalleDocumento(documento=documento_out(d, len(lineas), total), lineas=lineas, historico=True,
                                descargas=descargas)

    correcciones = []
    if d.tipo == "nota_entrega":
        correcciones = s.scalars(select(m.Documento).where(m.Documento.documento_origen_id == d.id)
                                 .order_by(m.Documento.id)).all()
    if correcciones:
        movs = _vigentes_por_ne(s, [d.id]).get(d.id, [])
        piezas = {p.id: p for p in s.scalars(select(m.Pieza).where(m.Pieza.id.in_([x.pieza_id for x in movs])))} \
            if movs else {}
        filas = [(x, piezas[x.pieza_id]) for x in movs]
    else:
        filas = s.execute(select(m.Movimiento, m.Pieza).join(m.Pieza, m.Pieza.id == m.Movimiento.pieza_id)
                          .where(m.Movimiento.documento_id == d.id).order_by(m.Movimiento.id)).all()
    lineas = [LineaDocumento(movimiento_id=mv.id, pieza_id=p.id, codigo=p.codigo_fisico, descripcion=p.descripcion,
                             tipo_movimiento=mv.tipo, kg=mv.kg if d.tipo != "liberacion" else p.saldo_kg,
                             saldo_despues_kg=mv.saldo_despues_kg, unidades=mv.unidades,
                             saldo_despues_unidades=mv.saldo_despues_unidades) for mv, p in filas]
    if d.tipo in ("nota_entrega", "nota_salida"):   # material sin existencia: renglón del documento, sin movimiento
        lineas += [LineaDocumento(movimiento_id=None, pieza_id=None, codigo=x.codigo or "—", descripcion=x.descripcion,
                                  tipo_movimiento="salida", kg=-(x.kg or 0), saldo_despues_kg=0, cantidad=x.cantidad,
                                  unidad=x.unidad)
                   for x in s.scalars(select(m.DocumentoLinea).where(m.DocumentoLinea.documento_id == d.id)
                                      .order_by(m.DocumentoLinea.posicion))]
    total = sum((abs(x.kg) for x in lineas), 0)
    return DetalleDocumento(
        documento=documento_out(d, len(lineas), total), lineas=lineas,
        corregible=d.tipo == "nota_entrega" and not d.anulado and cliente is None and d.origen != "importacion",
        correcciones=[documento_out(c, 0, 0) for c in correcciones])


UNIDAD_POR_TIPO = {"bobina": "Bob", "fleje": "Rollo"}
CIUDAD_EMISION = "Valencia"


def _descripcion(p: m.Pieza) -> str:
    if p.descripcion:
        return p.descripcion
    medidas = " x ".join(f"{x.normalize():f}".replace(".", ",") + "mm" for x in (p.espesor_mm, p.ancho_mm) if x)
    return f"{p.tipo.capitalize()} {medidas}".strip()


def ne_impresa(s: Session, empresa_id: int, cliente: int | None, id_: int) -> NotaEntregaImpresa | None:
    """La NE lista para imprimir: encabezado (lo que falte, de la ficha del cliente) y renglones vigentes."""
    d = documento_visible(s, empresa_id, cliente, id_)
    if d is None or d.tipo != "nota_entrega":
        return None
    enc = d.encabezado or {}
    t = d.tercero
    propias = s.scalars(select(m.DocumentoLinea).where(m.DocumentoLinea.documento_id == d.id)
                        .order_by(m.DocumentoLinea.posicion)).all()
    es_hist = d.origen == "excel" or (d.origen == "importacion" and bool(propias))
    hist = propias if es_hist else []
    renglones: list[RenglonNE] = []
    if hist:
        for x in hist:
            kg = x.kg or Decimal("0")
            pu = (kg / x.cantidad).quantize(Decimal("0.01")) if x.cantidad else None
            renglones.append(RenglonNE(x.cantidad or Decimal("0"), x.unidad or "", x.descripcion or x.codigo or "—",
                                       x.codigo, pu, kg))
    else:
        movs = _vigentes_por_ne(s, [d.id]).get(d.id) if s.scalar(
            select(func.count(m.Documento.id)).where(m.Documento.documento_origen_id == d.id)) else None
        if movs is None:
            movs = list(s.scalars(select(m.Movimiento).where(m.Movimiento.documento_id == d.id)
                                  .order_by(m.Movimiento.id)))
        piezas = {p.id: p for p in s.scalars(select(m.Pieza).where(m.Pieza.id.in_({x.pieza_id for x in movs})))} \
            if movs else {}
        for mv in movs:
            p = piezas[mv.pieza_id]
            kg = abs(mv.kg)
            if mv.unidades is not None:
                cant = Decimal(abs(mv.unidades))
                pu = (kg / cant).quantize(Decimal("0.01")) if cant else None
                renglones.append(RenglonNE(cant, "Pza", _descripcion(p), p.codigo_fisico, pu, kg))
            else:
                renglones.append(RenglonNE(Decimal("1"), UNIDAD_POR_TIPO.get(p.tipo, "Pza"), _descripcion(p),
                                           p.codigo_fisico, kg, kg))
        for x in propias:   # material de medidas irregulares: se registra por su peso
            renglones.append(RenglonNE(x.kg or Decimal("0"), x.unidad or "Kg", x.descripcion or x.codigo or "—",
                                       x.codigo, None, x.kg or Decimal("0")))
    elaborada = d.creado_en
    if elaborada is not None and d.origen != "excel":
        try:
            from zoneinfo import ZoneInfo
            elaborada = elaborada.astimezone(ZoneInfo("America/Caracas"))
        except Exception:  # noqa: BLE001 - sin base de zonas: queda la hora guardada
            pass
    else:
        elaborada = None

    def dato(clave: str, ficha: str | None) -> str | None:
        return enc.get(clave) or ficha or None

    return NotaEntregaImpresa(
        numero=d.numero or str(d.id), fecha=d.fecha, elaborada=elaborada, cliente=t.nombre if t else "—",
        rif=t.rif if t else None,
        domicilio_entrega=dato("domicilio_entrega", t.direccion if t else None),
        telefonos=dato("telefonos", t.telefono if t else None),
        condicion_pago=dato("condicion_pago", t.forma_pago if t else None),
        vendedor=dato("vendedor", t.vendedor if t else None),
        cotizacion=enc.get("cotizacion"), chofer=enc.get("chofer"), placa=enc.get("placa"),
        nota_salida=enc.get("nota_salida"), ciudad=enc.get("ciudad") or CIUDAD_EMISION, notas=enc.get("notas"),
        renglones=renglones, anulada=d.anulado, historica=es_hist)


def grupo_entrada(s: Session, empresa_id: int, d: m.Documento) -> list[m.Documento]:
    """Las entradas que van en un mismo recibo: mismo cliente, mismo documento del cliente y misma fecha
    (por ejemplo los dos productos de la carta de HYMS del 11-11-2026)."""
    return list(s.scalars(select(m.Documento).where(
        m.Documento.empresa_id == empresa_id, m.Documento.tipo == "entrada", m.Documento.tercero_id == d.tercero_id,
        m.Documento.numero == d.numero, m.Documento.fecha == d.fecha).order_by(m.Documento.id)))


def recibo_entrada(s: Session, empresa_id: int, cliente: int | None, id_: int, numero: int) -> ReciboEntradaImpreso | None:
    d = documento_visible(s, empresa_id, cliente, id_)
    if d is None or d.tipo != "entrada":
        return None
    grupo = grupo_entrada(s, empresa_id, d)
    vivos = [g for g in grupo if not g.anulado] or grupo
    movs = s.execute(select(m.Movimiento, m.Pieza).join(m.Pieza, m.Pieza.id == m.Movimiento.pieza_id).where(
        m.Movimiento.documento_id.in_([g.id for g in vivos]), m.Movimiento.revierte_id.is_(None))
        .order_by(m.Movimiento.id)).all()
    renglones: list[RenglonRecibo] = []
    for mv, p in movs:
        kg = abs(mv.kg)
        if mv.unidades is not None:
            cant = Decimal(abs(mv.unidades))
            pu = (kg / cant).quantize(Decimal("0.01")) if cant else None
            renglones.append(RenglonRecibo(cant, "Pza", _descripcion(p), p.codigo_fisico, pu, kg))
        else:
            renglones.append(RenglonRecibo(Decimal("1"), UNIDAD_POR_TIPO.get(p.tipo, "Pza"), _descripcion(p),
                                           p.codigo_fisico, kg, kg))
    t = d.tercero
    registrado = d.creado_en
    if registrado is not None:
        try:
            from zoneinfo import ZoneInfo
            registrado = registrado.astimezone(ZoneInfo("America/Caracas"))
        except Exception:  # noqa: BLE001
            pass
    observaciones = "; ".join(dict.fromkeys(g.observacion for g in vivos if g.observacion)) or None
    return ReciboEntradaImpreso(numero=numero, fecha=d.fecha, cliente=t.nombre if t else "—", rif=t.rif if t else None,
                                documento_cliente=d.numero or "", renglones=renglones, observacion=observaciones,
                                registrado_por=d.creado_por or "", registrado=registrado,
                                anulado=all(g.anulado for g in grupo))


# --- Reporte de inventario ---------------------------------------------------

CATEGORIAS = ("bobina", "fleje", "lamina", "perfil", "general")


def reporte_inventario(s: Session, empresa_id: int, cliente: int | None, propietario_id: int, tipos: list[str],
                       generado_por: str) -> ReporteInventario | None:
    """Lo disponible de un cliente, por categoría, para auditar en patio. None si el cliente no existe o no se ve."""
    from zoneinfo import ZoneInfo

    if cliente is not None:
        propietario_id = cliente
    t = s.get(m.Tercero, propietario_id)
    if t is None or t.empresa_id != empresa_id:
        return None
    secciones = []
    for tipo in tipos:
        q = (select(m.Pieza).where(m.Pieza.empresa_id == empresa_id, m.Pieza.anulada.is_(False),
                                   m.Pieza.estado == "disponible", m.Pieza.tipo == tipo,
                                   m.Pieza.propietario_id == propietario_id))
        if tipo in ("bobina", "fleje"):   # como el libro de bobinas: la última que entró, arriba
            q = q.order_by(m.Pieza.fecha_entrada.desc().nulls_last(), m.Pieza.id.desc())
        else:
            q = q.order_by(m.Pieza.tipo_acero_id, m.Pieza.espesor_mm, m.Pieza.ancho_mm, m.Pieza.largo_mm,
                           m.Pieza.descripcion)
        filas = [FilaInventario(
            codigo=(p.codigo_fisico if p.saldo_unidades is None else (p.codigo_producto or p.codigo_fisico)),
            descripcion=p.descripcion or "", tipo_acero=p.tipo_acero.codigo if p.tipo_acero else None,
            norma=p.norma.nombre if p.norma else None, espesor_mm=p.espesor_mm, ancho_mm=p.ancho_mm,
            largo_mm=p.largo_mm, piezas=Decimal(p.saldo_unidades) if p.saldo_unidades is not None else None,
            kg=p.saldo_kg, fecha_entrada=p.fecha_entrada) for p in s.scalars(q)]
        if filas or len(tipos) == 1:
            secciones.append(SeccionInventario(tipo, filas))
    return ReporteInventario(cliente=t.nombre, rif=t.rif, generado=dt.datetime.now(ZoneInfo("America/Caracas")),
                             generado_por=generado_por, secciones=secciones, total=len(tipos) > 1)


# --- Órdenes de despacho y notas de salida ------------------------------------

def _orden_despacho_out(r: m.Documento):
    from app.adaptadores.sql.repositorios import a_documento
    from app.servicios import despachos as srv

    return srv.a_salida(a_documento(r), r.tercero.nombre if r.tercero else "", creado_en=r.creado_en)


def despachos(s: Session, empresa_id: int, cliente: int | None, *, estado: str | None, tercero_id: int | None,
              desde: dt.date | None, hasta: dt.date | None, limite: int):
    """Órdenes de despacho, la más reciente arriba. estado: pendiente | despachada | anulada | None (todas)."""
    filtros = [m.Documento.empresa_id == empresa_id, m.Documento.tipo == "orden_despacho"]
    if cliente is not None:
        tercero_id = cliente
    if tercero_id:
        filtros.append(m.Documento.tercero_id == tercero_id)
    if estado == "anulada":
        filtros.append(m.Documento.anulado.is_(True))
    elif estado:
        filtros += [m.Documento.anulado.is_(False), m.Documento.estado == estado]
    if desde:
        filtros.append(m.Documento.fecha >= desde)
    if hasta:
        filtros.append(m.Documento.fecha <= hasta)
    filas = s.scalars(select(m.Documento).where(*filtros).order_by(m.Documento.id.desc()).limit(limite)).all()
    return [_orden_despacho_out(r) for r in filas]


def despacho(s: Session, empresa_id: int, cliente: int | None, id_: int):
    r = s.get(m.Documento, id_)
    if r is None or r.empresa_id != empresa_id or r.tipo != "orden_despacho" or (
            cliente is not None and r.tercero_id != cliente):
        return None
    return _orden_despacho_out(r)


def _renglones_despacho(lineas: list[dict]) -> list[RenglonRecibo]:
    out = []
    for x in lineas:
        kg = Decimal(str(x["kg"]))
        u = x.get("unidades")
        out.append(RenglonRecibo(Decimal(u) if u else Decimal("1"),
                                 "Pza" if u else UNIDAD_POR_TIPO.get(x.get("tipo", ""), "Pza"),
                                 x.get("descripcion") or x.get("codigo", ""), x.get("codigo", ""),
                                 (kg / Decimal(u)) if u else None, kg))
    return out


def _local(t: dt.datetime | None) -> dt.datetime | None:
    from zoneinfo import ZoneInfo

    return t.astimezone(ZoneInfo("America/Caracas")) if t else None


def despacho_impreso(s: Session, empresa_id: int, cliente: int | None, id_: int) -> DespachoImpreso | None:
    """La orden de despacho (id de la orden) o la nota de salida (id de la nota) para imprimir."""
    r = s.get(m.Documento, id_)
    if r is None or r.empresa_id != empresa_id or r.tipo not in ("orden_despacho", "nota_salida") or (
            cliente is not None and r.tercero_id != cliente):
        return None
    enc = r.encabezado or {}
    if r.tipo == "orden_despacho":
        ns = enc.get("nota_salida") or {}
        estado = "anulada" if r.anulado else (r.estado or "pendiente")
        referencia = f"Nota de salida N° {ns['numero']}" if ns.get("numero") else None
    else:
        estado = "anulada" if r.anulado else "emitida"
        referencia = f"Orden de despacho N° {enc['orden_despacho']}" if enc.get("orden_despacho") else None
    t = r.tercero
    return DespachoImpreso(
        tipo=r.tipo, numero=str(r.numero), fecha=r.fecha, cliente=t.nombre if t else "", rif=t.rif if t else None,
        estado=estado, referencia=referencia,
        renglones=_renglones_despacho(enc.get("lineas", [])) + [   # material de medidas irregulares (nota de salida)
            RenglonRecibo(Decimal(str(x["kg"])), "Kg", x.get("descripcion") or x.get("codigo", ""), x.get("codigo", ""),
                          None, Decimal(str(x["kg"]))) for x in enc.get("libres", [])],
        retiro=enc.get("retiro"), observacion=r.observacion,
        creado_por="Prosifer" if cliente is not None and r.tipo == "nota_salida" else (r.creado_por or ""),
        creado_en=_local(r.creado_en))


# --- Solicitudes de orden de corte del cliente ---------------------------------

def _solicitud_out(s: Session, r: m.Documento):
    from app.esquemas import SolicitudCorteOut

    enc = r.encabezado or {}
    piezas = [pieza_out(p) for p in (s.get(m.Pieza, pid) for pid in enc.get("piezas", [])) if p is not None]
    return SolicitudCorteOut(
        id=r.id, numero=str(r.numero), estado=r.estado or "pendiente", tipo=enc.get("pedido", {}).get("tipo", ""),
        fecha=r.fecha, tercero_id=r.tercero_id, tercero=r.tercero.nombre if r.tercero else "", piezas=piezas,
        pedido=enc.get("pedido", {}), texto=enc.get("texto", ""), comentarios=r.observacion, creado_por=r.creado_por,
        creado_en=r.creado_en, orden_id=enc.get("orden_id"), orden_numero=enc.get("orden_numero"),
        motivo=enc.get("motivo"), revisado_por=enc.get("revisado_por"))


def solicitudes_corte(s: Session, empresa_id: int, cliente: int | None, *, estado: str | None, limite: int):
    filtros = [m.Documento.empresa_id == empresa_id, m.Documento.tipo == "solicitud_corte"]
    if cliente is not None:
        filtros.append(m.Documento.tercero_id == cliente)
    if estado:
        filtros.append(m.Documento.estado == estado)
    return [_solicitud_out(s, r) for r in s.scalars(select(m.Documento).where(*filtros)
                                                 .order_by(m.Documento.id.desc()).limit(limite))]


def solicitud_corte(s: Session, empresa_id: int, cliente: int | None, id_: int):
    r = s.get(m.Documento, id_)
    if r is None or r.empresa_id != empresa_id or r.tipo != "solicitud_corte" or (
            cliente is not None and r.tercero_id != cliente):
        return None
    return _solicitud_out(s, r)


# --- Avisos de entrada del cliente ---------------------------------------------

def _aviso_out(r: m.Documento):
    from app.esquemas import AvisoEntradaOut

    enc = r.encabezado or {}
    renglones = enc.get("renglones", [])
    fe = enc.get("fecha_estimada")
    return AvisoEntradaOut(
        id=r.id, numero=str(r.numero), estado=r.estado or "pendiente", fecha=r.fecha,
        fecha_estimada=dt.date.fromisoformat(fe) if fe else None, tercero_id=r.tercero_id,
        tercero=r.tercero.nombre if r.tercero else "", documento_tipo=enc.get("documento_tipo"),
        documento_numero=enc.get("documento_numero"), proveedor=enc.get("proveedor"), transporte=enc.get("transporte"),
        renglones=renglones, total_kg=sum((Decimal(str(x["peso_kg"])) for x in renglones if x.get("peso_kg")), Decimal("0")),
        total_piezas=sum(int(x.get("cantidad") or 0) for x in renglones), comentarios=r.observacion,
        creado_por=r.creado_por, creado_en=r.creado_en, nota=enc.get("nota"), revisado_por=enc.get("revisado_por"))


def avisos_entrada(s: Session, empresa_id: int, cliente: int | None, *, estado: str | None, limite: int):
    filtros = [m.Documento.empresa_id == empresa_id, m.Documento.tipo == "aviso_entrada"]
    if cliente is not None:
        filtros.append(m.Documento.tercero_id == cliente)
    if estado:
        filtros.append(m.Documento.estado == estado)
    return [_aviso_out(r) for r in s.scalars(select(m.Documento).where(*filtros)
                                             .order_by(m.Documento.id.desc()).limit(limite))]


def aviso_entrada(s: Session, empresa_id: int, cliente: int | None, id_: int):
    r = s.get(m.Documento, id_)
    if r is None or r.empresa_id != empresa_id or r.tipo != "aviso_entrada" or (
            cliente is not None and r.tercero_id != cliente):
        return None
    return _aviso_out(r)


# --- Cotizaciones ------------------------------------------------------------------

def cotizacion_out(r: m.Documento, para_cliente: bool = False):
    from app.esquemas import CotizacionOut
    from app.servicios.cotizaciones import calcular

    enc = r.encabezado or {}
    t = calcular(enc)
    return CotizacionOut(
        id=r.id, numero=str(r.numero), fecha=r.fecha, tercero_id=r.tercero_id,
        tercero=r.tercero.nombre if r.tercero else enc.get("cliente_excel"),
        renglones=enc.get("renglones", []), subtotal=t["subtotal"], iva_pct=t["iva_pct"], iva=t["iva"], total=t["total"],
        abonos=[{k: v for k, v in a.items() if k != "por"} for a in enc.get("abonos", [])] if para_cliente
        else enc.get("abonos", []), abonado=t["abonado"], saldo=t["saldo"], vendedor=enc.get("vendedor"),
        condicion_pago=enc.get("condicion_pago"), nota_entrega=enc.get("nota_entrega"), notas=enc.get("notas"),
        orden_trabajo_id=enc.get("orden_trabajo_id"), orden=enc.get("orden"), anulada=r.anulado,
        motivo_anulacion=enc.get("motivo_anulacion"), historica=r.origen == "excel", origen=r.origen,
        creado_por="Prosifer" if para_cliente else r.creado_por, creado_en=r.creado_en)


def cotizaciones(s: Session, empresa_id: int, *, tercero_id: int | None, q: str | None, orden_trabajo_id: int | None,
                 limite: int, cliente: int | None = None, desde: dt.date | None = None, hasta: dt.date | None = None,
                 incluir_anuladas: bool = True):
    filtros = [m.Documento.empresa_id == empresa_id, m.Documento.tipo == "cotizacion"]
    if cliente is not None:
        tercero_id = cliente   # un cliente solo ve las suyas, pida lo que pida
        filtros.append(m.Documento.tercero_id == cliente)
    elif tercero_id:
        filtros.append(m.Documento.tercero_id == tercero_id)
    if desde:
        filtros.append(m.Documento.fecha >= desde)
    if hasta:
        filtros.append(m.Documento.fecha <= hasta)
    if not incluir_anuladas:
        filtros.append(m.Documento.anulado.is_(False))
    if q and q.strip():
        t = q.strip().upper().removeprefix("D-").strip()
        filtros.append(or_(m.Documento.numero == t, m.Documento.tercero.has(m.Tercero.nombre.ilike(f"%{q.strip()}%"))))
    numero = case((m.Documento.numero.op("~")("^[0-9]{1,7}$"), cast(m.Documento.numero, BigInteger)), else_=None)
    filas = s.scalars(select(m.Documento).where(*filtros)
                      .order_by(numero.desc().nulls_last(), m.Documento.id.desc()).limit(limite * 3 if orden_trabajo_id else limite)).all()
    out = [cotizacion_out(r, para_cliente=cliente is not None) for r in filas]
    if orden_trabajo_id:
        out = [x for x in out if x.orden_trabajo_id == orden_trabajo_id][:limite]
    return out


def cotizacion(s: Session, empresa_id: int, id_: int, cliente: int | None = None):
    r = s.get(m.Documento, id_)
    if r is None or r.empresa_id != empresa_id or r.tipo != "cotizacion" or (cliente is not None and r.tercero_id != cliente):
        return None
    return r


def cotizacion_impresa(s: Session, empresa_id: int, id_: int, cliente: int | None = None):
    from decimal import Decimal as D

    from app.dominio.impresion import CotizacionImpresa, RenglonCotizacionImpreso
    r = cotizacion(s, empresa_id, id_, cliente)
    if r is None:
        return None
    c = cotizacion_out(r)
    enc = r.encabezado or {}
    t = r.tercero

    def dec(v):
        return D(str(v)) if v not in (None, "") else None

    renglones = [RenglonCotizacionImpreso(dec(x.get("cantidad")) or D("0"), x.get("unidad") or "",
                                          x.get("descripcion") or x.get("codigo") or "—", x.get("codigo"),
                                          dec(x.get("precio_unitario")), dec(x.get("total")) or D("0"))
                 for x in c.renglones]
    abonos = [" · ".join(p for p in (a.get("fecha") and _fecha_abono(a["fecha"]), a.get("destino"),
                                      f"{D(str(a['monto'])):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                                      a.get("referencia") and f"ref. {a['referencia']}")
                         if p) for a in c.abonos]
    return CotizacionImpresa(
        numero=c.numero, fecha=c.fecha, cliente=c.tercero or "—", rif=t.rif if t else None,
        domicilio=enc.get("domicilio") or (t.direccion if t else None), telefonos=enc.get("telefonos") or (t.telefono if t else None),
        condicion_pago=c.condicion_pago or (t.forma_pago if t else None), vendedor=c.vendedor or (t.vendedor if t else None),
        nota_entrega=c.nota_entrega, ciudad=CIUDAD_EMISION, notas=c.notas, renglones=renglones, subtotal=c.subtotal,
        iva_pct=c.iva_pct, iva=c.iva, total=c.total, abonos=abonos, anulada=c.anulada, historica=c.historica)


def _fecha_abono(v: str) -> str:
    try:
        return dt.date.fromisoformat(v).strftime("%d/%m/%Y")
    except ValueError:
        return v   # del Excel: "18-03"


# ---------------------------------------------------------------- reporte mensual de salidas (descarga-carga)

def reporte_salidas(s: Session, empresa_id: int, tercero_id: int, desde: dt.date, hasta: dt.date,
                    cliente: int | None = None, excluir: set[str] | None = None) -> ReporteSalidas | None:
    """Las NE del cliente en el período (no anuladas), renglón por renglón, con la masa despachada: lo
    mismo que el reporte "Servicios de Descarga-Carga" del Excel. Incluye las NE históricas del Excel,
    las de la app (con sus correcciones) y el material sin existencia (medidas irregulares)."""
    if cliente is not None and cliente != tercero_id:
        return None
    t = s.get(m.Tercero, tercero_id)
    if t is None or t.empresa_id != empresa_id:
        return None
    nes = s.scalars(select(m.Documento).where(
        m.Documento.empresa_id == empresa_id, m.Documento.tipo == "nota_entrega", m.Documento.anulado.is_(False),
        m.Documento.tercero_id == tercero_id, m.Documento.fecha >= desde, m.Documento.fecha <= hasta)
        .order_by(m.Documento.fecha.desc(), m.Documento.id.desc())).all()
    excluir = excluir or set()
    filas: list[FilaReporteSalidas] = []
    fuera: dict[str, list] = {}
    tipos = {}
    for d in nes:
        det = detalle_documento(s, empresa_id, None, d.id)
        if det is None:
            continue
        ns = (d.encabezado or {}).get("nota_salida")
        for ln in det.lineas:
            if ln.cantidad is not None:
                cant = abs(Decimal(ln.cantidad))
            elif ln.unidades is not None:
                cant = Decimal(abs(ln.unidades))
            else:
                cant = Decimal(1)        # una bobina o un fleje
            if ln.pieza_id and ln.pieza_id not in tipos:
                p = s.get(m.Pieza, ln.pieza_id)
                tipos[ln.pieza_id] = (p.tipo, p.codigo_producto) if p else (None, None)
            tipo, cod_prod = tipos.get(ln.pieza_id, (None, None))
            cat = codigos.categoria_salida(tipo, cod_prod or ln.codigo, ln.descripcion)
            f = FilaReporteSalidas(nota_salida=str(ns) if ns else None, fecha=d.fecha, nota_entrega=d.numero,
                                   documento_id=d.id, cantidad=cant, descripcion=ln.descripcion or ln.codigo,
                                   kg=abs(Decimal(ln.kg or 0)).quantize(Decimal("0.01")), categoria=cat)
            (fuera.setdefault(cat, []) if cat in excluir else filas).append(f)
    total = sum((f.kg for f in filas), Decimal("0"))
    excluidas = [ExcluidoReporte(categoria=k, nombre=codigos.CATEGORIAS_SALIDA.get(k, k), renglones=len(v),
                                 kg=sum((f.kg for f in v), Decimal("0"))) for k, v in sorted(fuera.items())]
    return ReporteSalidas(tercero_id=t.id, tercero=t.nombre, desde=desde, hasta=hasta, filas=filas,
                          notas_entrega=len({f.documento_id for f in filas}), total_kg=total, excluidas=excluidas)


def _servicio_descarga(s: Session, empresa_id: int) -> m.Producto | None:
    """El servicio del catálogo para descarga, almacén y carga (el nombre manda: 'Descarga' antes que 'Carga')."""
    cands = s.scalars(select(m.Producto).where(
        m.Producto.empresa_id == empresa_id, m.Producto.codigo.ilike("SERVICIO%"),
        or_(m.Producto.nombre.ilike("%descarga%"), m.Producto.nombre.ilike("%carga%"),
            m.Producto.nombre.ilike("%almac%")))).all()
    def puntos(p):
        n = (p.nombre or "").lower()
        return ("descarga" in n) * 4 + ("carga" in n) * 2 + ("almac" in n) * 1
    cands = sorted(cands, key=lambda p: (-puntos(p), p.codigo))
    return cands[0] if cands else None


def borrador_reporte_salidas(s: Session, empresa_id: int, rep: ReporteSalidas) -> BorradorCotizacion:
    """El atajo "Cotizar este reporte": el servicio de descarga-almacén-carga por la masa del período, con el
    último precio y la misma unidad que se le cotizaron a ese cliente por ese servicio (si los hay)."""
    avisos: list[str] = []
    prod = _servicio_descarga(s, empresa_id)
    if prod is None:
        avisos.append("no encontré en el catálogo un servicio de descarga / carga: elige el servicio en el renglón")
    codigo = prod.codigo if prod else None
    precio, unidad = Decimal("0"), "Kg"
    previas = s.scalars(select(m.Documento).where(
        m.Documento.empresa_id == empresa_id, m.Documento.tipo == "cotizacion", m.Documento.anulado.is_(False),
        m.Documento.tercero_id == rep.tercero_id).order_by(m.Documento.fecha.desc().nulls_last(), m.Documento.id.desc())
        .limit(300)).all()
    for d in previas:
        r = next((r for r in (d.encabezado or {}).get("renglones", [])
                  if (codigo and (r.get("codigo") or "").upper() == codigo)
                  or "descarga" in (r.get("descripcion") or "").lower()), None)
        if r:
            precio = Decimal(str(r.get("precio_unitario") or 0))
            unidad = r.get("unidad") or unidad
            codigo = codigo or r.get("codigo")
            avisos.append(f"precio y unidad de la última cotización de este servicio al cliente (D-{d.numero}, "
                          f"{d.fecha:%d/%m/%Y}): revísalos")
            break
    else:
        avisos.append("no hay cotizaciones anteriores de este servicio para el cliente: pon el precio")
    kg = rep.total_kg
    ton = unidad.strip().lower() in ("tm", "ton", "t", "tonelada", "toneladas")
    cantidad = (kg / 1000).quantize(Decimal("0.001")) if ton else kg.quantize(Decimal("0.01"))
    if cantidad <= 0:
        cantidad = Decimal("1")
        avisos.append("el período no tiene salidas con masa: revisa las fechas")
    nombre = prod.nombre if prod else "Servicio de Descarga - Almacén - Carga"
    renglon = RenglonCotizacionIn(codigo=codigo, descripcion=nombre, cantidad=cantidad, unidad=unidad,
                                  precio_unitario=precio)
    kg_txt = f"{kg:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    notas = (f"Servicio de descarga, almacén y carga del {rep.desde:%d/%m/%Y} al {rep.hasta:%d/%m/%Y}: "
             f"{rep.notas_entrega} notas de entrega, {kg_txt} kg despachados"
             + (f" (no incluye {', '.join(e.nombre.lower() for e in rep.excluidas)})" if rep.excluidas else "") + ".")
    return BorradorCotizacion(tercero_id=rep.tercero_id, tercero=rep.tercero, renglones=[renglon], notas=notas,
                              avisos=avisos)

