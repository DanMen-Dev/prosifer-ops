"""Casos de uso de salida del patio: notas de entrega, liberaciones y ajustes de saldo."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.dominio import codigos
from app.dominio import salidas as reglas
from app.dominio.entidades import Documento, Movimiento, Pieza, Tercero
from app.errores import ErrorNegocio
from app.esquemas import (
    CorreccionNEIn, DescargaHistoricaIn, EncabezadoNE, LiberacionIn, LineaCorreccionOut, LineaLibre, LineaLibreIn, LineaResumen,
    NotaEntregaIn, ResumenCorreccionNE, ResumenSalida,
)
from app.puertos import UnidadDeTrabajo
from app.servicios import inventario, planificacion


HISTORICO = "excel"   # origen de las NE cargadas del histórico del Excel: solo consulta
DEL_SLITTER = "importacion"   # NE de bobinas y flejes cargadas del libro de Slitter: también histórico


def es_historica(doc: Documento) -> bool:
    """NE de antes de la app (Excel de NE o libro de Slitter): solo consulta, no se anula ni se corrige."""
    return doc.origen == HISTORICO or (doc.tipo == "nota_entrega" and doc.origen == DEL_SLITTER)


def _idempotencia(uow: UnidadDeTrabajo, clave: str | None) -> None:
    if clave:
        previo = uow.documentos.por_clave(clave)
        if previo is not None:
            raise ErrorNegocio(f"este documento ya se registró ({previo.tipo} {previo.numero})", 409)


def _tercero(uow: UnidadDeTrabajo, id_: int, que: str) -> Tercero:
    t = uow.terceros.obtener(id_)
    if t is None:
        raise ErrorNegocio(f"{que} inexistente", 422)
    return t


def _piezas(uow: UnidadDeTrabajo, ids: list[int], bloquear: bool, *,
            excepto_despacho: int | None = None) -> dict[int, Pieza]:
    if len(set(ids)) != len(ids):
        raise ErrorNegocio("una pieza aparece dos veces en el documento", 422)
    piezas = uow.piezas.obtener_varias(ids, bloquear=bloquear)
    for i in ids:
        p = piezas.get(i)
        if p is None or p.anulada:
            raise ErrorNegocio(f"la pieza {i} no existe o está anulada", 404)
        if p.saldo_unidades is None:   # bobina o fleje: no sale si está en una OC planificada o en otro despacho
            planificacion.verificar_libre(uow, p.id, p.codigo_fisico, excepto_despacho=excepto_despacho)
    return piezas


def evaluar_lineas(uow: UnidadDeTrabajo, cliente: Tercero, pedidas: list, piezas: dict[int, Pieza], *,
                   excepto_despacho: int | None = None) -> tuple[list[LineaResumen], list[str]]:
    """Valida lo que sale de cada pieza (NE, orden de despacho, nota de salida) sin mover nada.

    Las láminas, perfiles y generales reservados en órdenes de despacho abiertas no cuentan como
    disponibles, salvo los de la orden `excepto_despacho` (la que se está despachando).
    """
    from app.servicios import despachos   # evita la importación circular

    umbral = inventario.umbral_agotado(uow)
    resto_aviso = Decimal(inventario.parametro(uow, "resto_aviso_kg", "50"))
    avisos: list[str] = []
    lineas: list[LineaResumen] = []
    for l in pedidas:
        p = piezas[l.pieza_id]
        if p.propietario_id != cliente.id:
            raise ErrorNegocio(f"{p.codigo_fisico} es de {p.propietario_nombre}, no de {cliente.nombre}", 422)
        try:
            if p.saldo_unidades is not None:  # lámina, perfil o general: sale en piezas
                if l.kg is not None:
                    raise reglas.SalidaInvalida("se entrega en piezas, no en kg")
                despachos.verificar_unidades(uow, p, l.unidades, excepto=excepto_despacho)
                ru = reglas.evaluar_linea_unidades(p.saldo_unidades, p.saldo_kg, l.unidades)
                lineas.append(LineaResumen(
                    pieza_id=p.id, codigo=p.codigo_fisico, descripcion=p.descripcion, saldo_antes_kg=p.saldo_kg,
                    kg=ru.kg, saldo_despues_kg=ru.saldo_despues_kg, saldo_antes_unidades=p.saldo_unidades,
                    unidades=ru.unidades, saldo_despues_unidades=ru.saldo_despues_unidades))
                continue
            if l.unidades is not None:
                raise reglas.SalidaInvalida("se entrega en kg, no en piezas")
            r = reglas.evaluar_linea(p.saldo_kg, l.kg, umbral=umbral, resto_aviso=resto_aviso)
        except reglas.SalidaInvalida as exc:
            raise ErrorNegocio(f"{p.codigo_fisico}: {exc}", 422) from exc
        avisos += [f"{p.codigo_fisico}: {a}" for a in r.avisos]
        lineas.append(LineaResumen(pieza_id=p.id, codigo=p.codigo_fisico, descripcion=p.descripcion,
                                   saldo_antes_kg=p.saldo_kg, kg=r.kg, saldo_despues_kg=r.saldo_despues))
    return lineas, avisos


def registrar_salidas(uow: UnidadDeTrabajo, doc: Documento, lineas: list[LineaResumen], *, fecha: dt.date,
                      usuario: str, origen: str) -> None:
    for x in lineas:
        inventario.registrar_movimiento(
            uow, x.pieza_id, "salida", None if x.unidades is not None else -x.kg,
            unidades=-x.unidades if x.unidades is not None else None, usuario=usuario, origen=origen,
            fecha=fecha, documento_id=doc.id)


def evaluar_libres(uow: UnidadDeTrabajo, pedidas: list[LineaLibreIn]) -> list[LineaLibre]:
    """Renglones sin existencia: solo productos marcados así (material de medidas irregulares)."""
    libres = []
    for l in pedidas:
        codigo = l.codigo.strip().upper()
        if not codigos.sin_existencia(codigo):
            raise ErrorNegocio(f"{codigo} lleva existencia: agrégalo como pieza del inventario del cliente", 422)
        prod = uow.catalogos.producto(codigo)
        nombre = prod.nombre if prod else codigos.SIN_EXISTENCIA[codigo]
        detalle = (l.detalle or "").strip()
        libres.append(LineaLibre(codigo=codigo, descripcion=f"{nombre} ({detalle})" if detalle else nombre,
                                 kg=l.kg.quantize(Decimal("0.001"))))
    return libres


def nota_entrega(uow: UnidadDeTrabajo, datos: NotaEntregaIn, *, usuario: str, origen: str) -> ResumenSalida:
    if datos.confirmar:
        _idempotencia(uow, datos.clave_idempotencia)
    cliente = _tercero(uow, datos.tercero_id, "cliente")
    piezas = _piezas(uow, [l.pieza_id for l in datos.lineas], datos.confirmar)
    lineas, avisos = evaluar_lineas(uow, cliente, datos.lineas, piezas)
    libres = evaluar_libres(uow, datos.libres)

    resumen = ResumenSalida(
        guardada=False, tipo="nota_entrega", numero=f"{uow.numerador.ver_siguiente('nota_entrega')} (se asigna al guardar)",
        fecha=datos.fecha, tercero=cliente.nombre, lineas=lineas, libres=libres,
        total_kg=sum((x.kg for x in lineas), Decimal("0")) + sum((x.kg for x in libres), Decimal("0")), avisos=avisos)
    if not datos.confirmar:
        return resumen

    # El número lo asigna el sistema: correlativo, sin huecos ni repetidos.
    numero = str(uow.numerador.siguiente("nota_entrega"))
    doc = uow.documentos.agregar(Documento(
        None, "nota_entrega", numero=numero, fecha=datos.fecha, tercero_id=cliente.id, observacion=datos.observacion,
        origen=origen, creado_por=usuario, clave_idempotencia=datos.clave_idempotencia,
        encabezado=datos.encabezado.limpio() if datos.encabezado else None))
    registrar_salidas(uow, doc, lineas, fecha=datos.fecha, usuario=usuario, origen=origen)
    if libres:   # quedan como renglones del documento; no tocan el inventario de nadie
        uow.documentos.agregar_lineas(doc.id, [{"codigo": x.codigo, "descripcion": x.descripcion, "cantidad": x.kg,
                                               "unidad": "Kg", "kg": x.kg} for x in libres])
    return resumen.model_copy(update={"guardada": True, "documento_id": doc.id, "numero": numero})


def descargar_historica(uow: UnidadDeTrabajo, documento_id: int, datos: DescargaHistoricaIn, *, usuario: str,
                        origen: str) -> ResumenSalida:
    """Descarga del inventario lo que salió con una NE histórica (Excel o libro de Slitter) y en su momento
    se descargó a mano. La salida lleva la fecha de la NE y queda enlazada a ella: en la historia de la
    pieza se lee "Salida · NE 7079", sin gastar un número de NE nuevo."""
    doc = uow.documentos.obtener(documento_id)
    if doc is None or doc.tipo != "nota_entrega":
        raise ErrorNegocio("nota de entrega inexistente", 404)
    if not es_historica(doc):
        raise ErrorNegocio("solo las NE del histórico se descargan así; las de la app ya movieron el inventario", 422)
    if doc.anulado:
        raise ErrorNegocio("la NE está anulada", 422)
    if doc.tercero_id is None:
        raise ErrorNegocio("la NE no tiene cliente", 422)
    cliente = _tercero(uow, doc.tercero_id, "cliente")
    piezas = _piezas(uow, [l.pieza_id for l in datos.lineas], datos.confirmar)
    lineas, avisos = evaluar_lineas(uow, cliente, datos.lineas, piezas)
    fecha = doc.fecha or dt.date.today()
    resumen = ResumenSalida(guardada=False, documento_id=doc.id, tipo="nota_entrega", numero=str(doc.numero),
                            fecha=fecha, tercero=cliente.nombre, lineas=lineas,
                            total_kg=sum((x.kg for x in lineas), Decimal("0")), avisos=avisos)
    if not datos.confirmar:
        return resumen
    registrar_salidas(uow, doc, lineas, fecha=fecha, usuario=usuario, origen=origen)
    uow.auditoria.registrar("documento", doc.id, "descarga_historica", None,
                            ", ".join(f"{x.codigo}: {x.unidades if x.unidades is not None else x.kg}" for x in lineas),
                            usuario=usuario, origen=origen)
    return resumen.model_copy(update={"guardada": True})


def liberacion(uow: UnidadDeTrabajo, datos: LiberacionIn, *, usuario: str, origen: str) -> ResumenSalida:
    if datos.confirmar:
        _idempotencia(uow, datos.clave_idempotencia)
    if datos.propietario_actual_id == datos.propietario_nuevo_id:
        raise ErrorNegocio("el nuevo dueño debe ser distinto del actual", 422)
    actual = _tercero(uow, datos.propietario_actual_id, "dueño actual")
    nuevo = _tercero(uow, datos.propietario_nuevo_id, "nuevo dueño")
    piezas = _piezas(uow, datos.piezas, datos.confirmar)
    umbral = inventario.umbral_agotado(uow)

    avisos: list[str] = []
    if uow.documentos.numero_en_uso("liberacion", datos.numero.strip()):
        avisos.append(f"ya hay una liberación con el número {datos.numero.strip()}")
    lineas: list[LineaResumen] = []
    for i in datos.piezas:
        p = piezas[i]
        if p.propietario_id != actual.id:
            raise ErrorNegocio(f"{p.codigo_fisico} es de {p.propietario_nombre}, no de {actual.nombre}", 422)
        if p.saldo_unidades is not None:
            raise ErrorNegocio(f"{p.codigo_fisico}: la liberación de láminas, perfiles y generales por piezas "
                               "todavía no está; por ahora regístrala como nota de entrega y entrada", 422)
        if p.saldo_kg <= umbral:
            raise ErrorNegocio(f"{p.codigo_fisico} no tiene saldo en patio", 422)
        # La liberación traspasa la pieza completa: lo que tenga de saldo pasa al nuevo dueño.
        lineas.append(LineaResumen(pieza_id=p.id, codigo=p.codigo_fisico, descripcion=p.descripcion,
                                   saldo_antes_kg=p.saldo_kg, kg=p.saldo_kg, saldo_despues_kg=p.saldo_kg))

    resumen = ResumenSalida(guardada=False, tipo="liberacion", numero=datos.numero.strip(), fecha=datos.fecha,
                            tercero=actual.nombre, tercero_nuevo=nuevo.nombre, lineas=lineas,
                            total_kg=sum((x.kg for x in lineas), Decimal("0")), avisos=avisos)
    if not datos.confirmar:
        return resumen

    doc = uow.documentos.agregar(Documento(
        None, "liberacion", numero=resumen.numero, fecha=datos.fecha, tercero_id=actual.id,
        tercero_destino_id=nuevo.id, observacion=datos.observacion, origen=origen, creado_por=usuario,
        clave_idempotencia=datos.clave_idempotencia))
    for x in lineas:
        inventario.registrar_movimiento(uow, x.pieza_id, "liberacion", Decimal("0"), usuario=usuario, origen=origen,
                                        fecha=datos.fecha, documento_id=doc.id, propietario_nuevo_id=nuevo.id)
    return resumen.model_copy(update={"guardada": True, "documento_id": doc.id})


def ajustar(uow: UnidadDeTrabajo, pieza_id: int, saldo_nuevo: Decimal, motivo: str, *, fecha: dt.date | None,
            usuario: str, origen: str, saldo_nuevo_unidades: int | None = None) -> Movimiento:
    pieza = uow.piezas.obtener(pieza_id)
    if pieza is None or pieza.anulada:
        raise ErrorNegocio("pieza inexistente", 404)
    unidades = kg = None
    if pieza.saldo_unidades is not None:
        # En piezas: el conteo manda y el kg se ajusta al peso medio por pieza.
        if saldo_nuevo_unidades is None:
            raise ErrorNegocio("indica el nuevo saldo en piezas", 422)
        unidades = saldo_nuevo_unidades - pieza.saldo_unidades
        if unidades == 0:
            raise ErrorNegocio("el saldo nuevo es igual al actual", 422)
        if unidades > 0:
            base_u = pieza.saldo_unidades or pieza.unidades_entrada or 0
            base_kg = pieza.saldo_kg if pieza.saldo_unidades else pieza.peso_entrada_kg
            if not base_u or base_kg <= 0:
                raise ErrorNegocio("no se conoce el peso por pieza de este producto", 422)
            kg = (base_kg * unidades / base_u).quantize(Decimal("0.001"))
    else:
        kg = saldo_nuevo - pieza.saldo_kg
        if kg == 0:
            raise ErrorNegocio("el saldo nuevo es igual al actual", 422)
    doc = uow.documentos.agregar(Documento(None, "ajuste", fecha=fecha or dt.date.today(),
                                           tercero_id=pieza.propietario_id, observacion=motivo, origen=origen,
                                           creado_por=usuario))
    return inventario.registrar_movimiento(uow, pieza.id, "ajuste", kg, unidades=unidades, usuario=usuario,
                                           origen=origen, fecha=doc.fecha, documento_id=doc.id, observacion=motivo)


def anular(uow: UnidadDeTrabajo, documento_id: int, motivo: str, *, usuario: str, origen: str) -> Documento:
    """Deshace un documento de salida: devuelve los kg o el dueño anterior a cada pieza."""
    doc = uow.documentos.obtener(documento_id)
    if doc is None:
        raise ErrorNegocio("documento inexistente", 404)
    if doc.anulado:
        raise ErrorNegocio("el documento ya estaba anulado")
    if doc.tipo not in ("nota_entrega", "nota_salida", "liberacion", "ajuste"):
        raise ErrorNegocio("este tipo de documento no se anula desde aquí", 422)
    if es_historica(doc):
        raise ErrorNegocio("las notas de entrega del histórico del Excel son solo de consulta", 422)
    nota = f"Anulación de {doc.tipo.replace('_', ' ')} {doc.numero or doc.id}: {motivo}"
    correcciones = uow.documentos.correcciones(doc.id) if doc.tipo == "nota_entrega" else []
    movimientos = lineas_vigentes(uow, doc) if correcciones else uow.movimientos.por_documento(doc.id)
    for mv in movimientos:
        pieza = uow.piezas.obtener(mv.pieza_id)
        if pieza is None or pieza.anulada:
            continue
        if doc.tipo == "liberacion":
            if pieza.propietario_id != mv.propietario_nuevo_id:
                raise ErrorNegocio(f"{pieza.codigo_fisico} ya cambió de dueño otra vez; anula primero ese documento")
            inventario.registrar_movimiento(uow, pieza.id, "liberacion", Decimal("0"), usuario=usuario, origen=origen,
                                            fecha=dt.date.today(), observacion=nota,
                                            propietario_nuevo_id=mv.propietario_anterior_id)
        elif mv.unidades:
            inventario.registrar_movimiento(uow, pieza.id, "ajuste", -mv.kg, unidades=-mv.unidades, usuario=usuario,
                                            origen=origen, fecha=dt.date.today(), observacion=nota, revierte_id=mv.id)
        elif mv.kg != 0:
            inventario.registrar_movimiento(uow, pieza.id, "ajuste", -mv.kg, usuario=usuario, origen=origen,
                                            fecha=dt.date.today(), observacion=nota, revierte_id=mv.id)
    for c in correcciones:
        inventario.aplicar_cambios(uow, c, {"anulado": True}, tabla="documento", usuario=usuario, origen=origen)
        uow.documentos.guardar(c)
    inventario.aplicar_cambios(uow, doc, {"anulado": True}, tabla="documento", usuario=usuario, origen=origen)
    uow.documentos.guardar(doc)
    uow.auditoria.registrar("documento", doc.id, "motivo_anulacion", None, motivo, usuario=usuario, origen=origen)
    if doc.tipo == "nota_salida":   # su orden de despacho vuelve a quedar pendiente, con el material reservado
        from app.servicios import despachos

        despachos.reabrir(uow, doc, usuario=usuario, origen=origen)
    return doc


def lineas_vigentes(uow: UnidadDeTrabajo, ne: Documento) -> list[Movimiento]:
    """Las salidas que hoy forman la NE: las suyas y las de sus correcciones, menos las ya deshechas."""
    movs = [mv for mv in uow.movimientos.por_documento(ne.id) if mv.tipo == "salida"]
    for c in uow.documentos.correcciones(ne.id):
        if not c.anulado:
            movs += [mv for mv in uow.movimientos.por_documento(c.id) if mv.tipo == "salida"]
    deshechos = uow.movimientos.revertidos([mv.id for mv in movs])
    return [mv for mv in movs if mv.id not in deshechos]


def corregir_nota(uow: UnidadDeTrabajo, documento_id: int, datos: CorreccionNEIn, *, usuario: str,
                  origen: str) -> ResumenCorreccionNE:
    """Cambia cantidad o producto de líneas de una NE de la app. Devuelve lo que salió mal (ajuste ligado
    a la línea original) y saca lo correcto; el número de la NE no cambia y todo queda auditado."""
    ne = uow.documentos.obtener(documento_id)
    if ne is None or ne.tipo != "nota_entrega":
        raise ErrorNegocio("nota de entrega inexistente", 404)
    if es_historica(ne):
        raise ErrorNegocio("las notas de entrega del histórico del Excel son solo de consulta", 422)
    if ne.anulado:
        raise ErrorNegocio("la nota de entrega está anulada", 422)
    if datos.confirmar:
        _idempotencia(uow, datos.clave_idempotencia)
    vigentes = {mv.id: mv for mv in lineas_vigentes(uow, ne)}
    ids_mov = [c.movimiento_id for c in datos.cambios]
    if len(set(ids_mov)) != len(ids_mov):
        raise ErrorNegocio("una línea aparece dos veces en la corrección", 422)
    for i in ids_mov:
        if i not in vigentes:
            raise ErrorNegocio(f"la línea {i} no es una línea vigente de esta NE", 422)

    piezas_ids = {vigentes[c.movimiento_id].pieza_id for c in datos.cambios} | \
        {c.pieza_id for c in datos.cambios if c.pieza_id}
    piezas = _piezas(uow, sorted(piezas_ids), datos.confirmar)
    # Lo que se devuelve primero cuenta como disponible para la salida correcta.
    disponible_u = {p.id: p.saldo_unidades for p in piezas.values()}
    disponible_kg = {p.id: p.saldo_kg for p in piezas.values()}
    lineas: list[LineaCorreccionOut] = []
    plan = []
    salidas_nuevas: list[tuple[int, Decimal, int | None]] = []   # pieza, kg, piezas que salen de verdad
    for c in datos.cambios:
        mv = vigentes[c.movimiento_id]
        antes = piezas[mv.pieza_id]
        if antes.saldo_unidades is not None:
            disponible_u[antes.id] += -mv.unidades
        disponible_kg[antes.id] += -mv.kg
        plan.append((c, mv, antes))
    for c, mv, antes in plan:
        despues = piezas[c.pieza_id] if c.pieza_id else antes
        if despues.propietario_id != ne.tercero_id:
            raise ErrorNegocio(f"{despues.codigo_fisico} es de {despues.propietario_nombre}, no del cliente de la NE", 422)
        en_piezas = despues.saldo_unidades is not None
        if en_piezas:
            if c.kg is not None:
                raise ErrorNegocio(f"{despues.codigo_fisico} se entrega en piezas, no en kg", 422)
            unidades = c.unidades or (-mv.unidades if antes.saldo_unidades is not None and despues is not antes else None)
            if unidades is None:
                raise ErrorNegocio(f"{despues.codigo_fisico}: indica cuántas piezas salieron de verdad", 422)
            if unidades > disponible_u[despues.id]:
                raise ErrorNegocio(f"{despues.codigo_fisico}: hay {disponible_u[despues.id]} piezas y se quieren "
                                   f"entregar {unidades}", 422)
            base_u, base_kg = disponible_u[despues.id], disponible_kg[despues.id]
            kg = base_kg if unidades == base_u else (base_kg * unidades / base_u).quantize(Decimal("0.001"))
            disponible_u[despues.id] -= unidades
        else:
            if c.unidades is not None:
                raise ErrorNegocio(f"{despues.codigo_fisico} se entrega en kg, no en piezas", 422)
            kg = c.kg or (-mv.kg if despues is not antes else None)
            if kg is None:
                raise ErrorNegocio(f"{despues.codigo_fisico}: indica los kg que salieron de verdad", 422)
            if kg > disponible_kg[despues.id] + inventario.umbral_agotado(uow):
                raise ErrorNegocio(f"{despues.codigo_fisico}: tiene {disponible_kg[despues.id]} kg y se quieren "
                                   f"entregar {kg}", 422)
            unidades = None
        disponible_kg[despues.id] -= kg
        sin_cambio = unidades == -mv.unidades if en_piezas and mv.unidades else kg == -mv.kg
        if despues is antes and sin_cambio:
            raise ErrorNegocio(f"{antes.codigo_fisico}: la corrección no cambia nada en esa línea", 422)
        lineas.append(LineaCorreccionOut(
            antes_codigo=antes.codigo_fisico, antes_descripcion=antes.descripcion, antes_kg=-mv.kg,
            antes_unidades=-mv.unidades if mv.unidades else None, despues_codigo=despues.codigo_fisico,
            despues_descripcion=despues.descripcion, despues_kg=kg, despues_unidades=unidades))
        salidas_nuevas.append((despues.id, kg, unidades))

    tercero = uow.terceros.obtener(ne.tercero_id) if ne.tercero_id else None
    resumen = ResumenCorreccionNE(guardada=False, numero=ne.numero, tercero=tercero.nombre if tercero else None,
                                  lineas=lineas, avisos=[])
    if not datos.confirmar:
        return resumen

    fecha = datos.fecha or dt.date.today()
    corr = uow.documentos.agregar(Documento(
        None, "correccion_ne", numero=ne.numero, fecha=fecha, tercero_id=ne.tercero_id, observacion=datos.motivo,
        origen=origen, creado_por=usuario, clave_idempotencia=datos.clave_idempotencia, documento_origen_id=ne.id))
    nota = f"Corrección de la NE {ne.numero}: {datos.motivo}"
    for _c, mv, antes in plan:  # primero se devuelve todo lo que salió mal…
        inventario.registrar_movimiento(uow, antes.id, "ajuste", -mv.kg, unidades=-mv.unidades if mv.unidades else None,
                                        usuario=usuario, origen=origen, fecha=fecha, documento_id=corr.id,
                                        observacion=nota, revierte_id=mv.id)
    for pieza_id, kg, unidades in salidas_nuevas:  # …y después sale lo correcto
        inventario.registrar_movimiento(uow, pieza_id, "salida", None if unidades is not None else -kg,
                                        unidades=-unidades if unidades is not None else None, usuario=usuario,
                                        origen=origen, fecha=fecha, documento_id=corr.id, observacion=nota)
    uow.auditoria.registrar("documento", ne.id, "correccion", None, datos.motivo, usuario=usuario, origen=origen)
    return resumen.model_copy(update={"guardada": True, "documento_id": corr.id})


def editar_encabezado(uow: UnidadDeTrabajo, documento_id: int, datos: EncabezadoNE, *, usuario: str,
                      origen: str) -> Documento:
    """Completa o cambia los datos de la NE impresa (chofer, placa, domicilio…). No toca inventario."""
    ne = uow.documentos.obtener(documento_id)
    if ne is None or ne.tipo != "nota_entrega":
        raise ErrorNegocio("nota de entrega inexistente", 404)
    if es_historica(ne):
        raise ErrorNegocio("las notas de entrega del histórico del Excel son solo de consulta", 422)
    if ne.anulado:
        raise ErrorNegocio("la nota de entrega está anulada", 422)
    if inventario.aplicar_cambios(uow, ne, {"encabezado": datos.limpio()}, tabla="documento", usuario=usuario,
                                  origen=origen):
        uow.documentos.guardar(ne)
    return ne
