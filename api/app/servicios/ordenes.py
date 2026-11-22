"""Casos de uso de órdenes de trabajo. Primera: corte en slitter (bobina → flejes)."""
from __future__ import annotations

from decimal import Decimal

from app.dominio import codigos, laminas, perfiles, slitter
from app.dominio.entidades import Documento, Movimiento, OrdenTrabajo, Pieza
from app.errores import ErrorNegocio
from app.esquemas import (
    AtadoOut, CortePlanOut, FlejeConsumidoOut, GrupoLaminaOut, OtLaminaIn, OtMaquilaIn, OtSlitterIn, PaqueteOut,
    ResumenOtLamina, ResumenOtMaquila, ResumenOtSlitter, RolloPlan,
)
from app.puertos import GeneradorDocumentos, UnidadDeTrabajo
from app.servicios import impresion, inventario, planificacion


def siguiente_numero(uow: UnidadDeTrabajo, tipo: str) -> int:
    """Sigue la numeración de la app o, si todavía no hay órdenes de ese tipo, la del Excel."""
    excel = int(inventario.parametro(uow, f"ultima_oc_{tipo}", "0") or 0)
    return max(uow.ordenes.ultimo_numero(tipo), excel) + 1


def _param(uow: UnidadDeTrabajo, clave: str, por_defecto: str) -> Decimal:
    return Decimal(inventario.parametro(uow, clave, por_defecto))


def registrar_slitter(uow: UnidadDeTrabajo, datos: OtSlitterIn, *, usuario: str, origen: str,
                      generador: GeneradorDocumentos | None = None) -> ResumenOtSlitter:
    if datos.clave_idempotencia and datos.confirmar:
        previa = uow.ordenes.por_clave(datos.clave_idempotencia)
        if previa is not None:
            raise ErrorNegocio(f"esta orden ya se registró (OC {previa.numero})", 409)

    # Al confirmar se bloquea la bobina: dos órdenes no pueden cortar los mismos kilos.
    bobina = uow.piezas.obtener(datos.pieza_id, bloquear=datos.confirmar)
    if bobina is None or bobina.anulada:
        raise ErrorNegocio("pieza inexistente o anulada", 404)
    if bobina.tipo not in ("bobina", "fleje"):
        raise ErrorNegocio("al slitter solo entran bobinas o flejes", 422)
    if bobina.estado != "disponible":
        raise ErrorNegocio(f"la pieza {bobina.codigo_fisico} está agotada", 409)
    if bobina.tipo_acero_codigo is None or bobina.espesor_mm is None:
        raise ErrorNegocio("la pieza no tiene tipo de acero o espesor; corrígelo en su ficha", 422)
    plan_ot = planificacion.tomar_plan(uow, datos.orden_planificada_id, "slitter", [bobina.id])
    if plan_ot is None:
        planificacion.verificar_libre(uow, bobina.id, bobina.codigo_fisico)

    umbral = inventario.umbral_agotado(uow)
    if datos.estatus_corte == "total":
        consumido = bobina.saldo_kg
    else:
        if datos.kg_procesado is None:
            raise ErrorNegocio("en un corte parcial indica los kg procesados", 422)
        consumido = datos.kg_procesado
        if consumido > bobina.saldo_kg + umbral:
            raise ErrorNegocio(f"se quieren procesar {consumido} kg y la pieza tiene {bobina.saldo_kg} kg")

    try:
        plan = slitter.planificar(
            bobina.ancho_mm, consumido,
            [slitter.CorteIn(c.ancho_mm, c.rollos, c.kg, c.calidad or datos.calidad) for c in datos.cortes],
            scrap_ancho_mm=datos.scrap_ancho_mm, scrap_kg=datos.scrap_kg,
            tolerancia=_param(uow, "tolerancia_corte", "0.05"),
            tolerancia_ancho_mm=_param(uow, "tolerancia_ancho_mm", "2"))
    except slitter.CorteInvalido as exc:
        raise ErrorNegocio(str(exc), 422) from exc

    numero = datos.numero or (plan_ot.numero if plan_ot else siguiente_numero(uow, "slitter"))
    avisos = list(plan.avisos)
    if datos.numero and not (plan_ot and datos.numero == plan_ot.numero) and \
            uow.ordenes.numero_en_uso("slitter", datos.numero):
        avisos.append(f"ya existe una OC de slitter con el número {datos.numero}")
    restante = bobina.saldo_kg - consumido
    if datos.estatus_corte == "parcial" and restante <= umbral:
        avisos.append("el corte parcial deja la bobina sin saldo: ¿no es total?")

    tipo_cod = bobina.tipo_acero_codigo
    cortes_out = []
    for c in plan.cortes:
        try:
            cod_prod = codigos.codigo_producto("fleje", tipo_cod, bobina.espesor_mm, c.ancho_mm)
        except codigos.CodigoInvalido as exc:
            raise ErrorNegocio(f"corte {c.posicion}: {exc}", 422) from exc
        rollos = [RolloPlan(codigo=slitter.codigo_rollo(cod_prod, bobina.codigo_fisico, numero, c.posicion, i), kg=kg)
                  for i, kg in enumerate(c.kg_rollos, start=1)]
        cortes_out.append(CortePlanOut(
            posicion=c.posicion, ancho_mm=c.ancho_mm, rollos=c.rollos, kg=c.kg, codigo_producto=cod_prod,
            descripcion=slitter.descripcion_fleje(tipo_cod, bobina.espesor_mm, c.ancho_mm), calidad=c.calidad,
            detalle_rollos=rollos))

    resumen = ResumenOtSlitter(
        guardada=False, numero=numero, bobina=bobina.codigo_fisico, propietario=bobina.propietario_nombre,
        estatus_corte=datos.estatus_corte, kg_consumido=consumido, kg_producido=plan.producido,
        kg_scrap=plan.scrap_kg, diferencia_pct=(plan.diferencia * 100).quantize(Decimal("0.1")),
        saldo_restante_kg=restante, cortes=cortes_out, avisos=avisos)
    if not datos.confirmar:
        return resumen

    doc = uow.documentos.agregar(Documento(None, "ot_slitter", numero=str(numero), fecha=datos.fecha,
                                           tercero_id=bobina.propietario_id, origen=origen, creado_por=usuario))
    orden = uow.ordenes.agregar(OrdenTrabajo(
        None, "slitter", numero, "cerrada", consumido, plan.producido, plan.scrap_kg, origen, usuario,
        fecha=datos.fecha, pieza_id=bobina.id, propietario_id=bobina.propietario_id,
        estatus_corte=datos.estatus_corte, paradas=datos.paradas, calidad=datos.calidad, documento_id=doc.id,
        observacion=datos.observacion, clave_idempotencia=datos.clave_idempotencia,
        detalle={
            "ancho_bobina_mm": str(bobina.ancho_mm),
            "cortes": [{"posicion": c.posicion, "ancho_mm": str(c.ancho_mm), "rollos": c.rollos, "kg": str(c.kg),
                        "codigo_producto": c.codigo_producto, "calidad": c.calidad} for c in cortes_out],
            "scrap": {"ancho_mm": str(plan.scrap_ancho_mm), "kg": str(plan.scrap_kg)},
            "avisos": avisos,
        }))
    planificacion.cerrar_plan(uow, plan_ot, orden.id, usuario=usuario, origen=origen)

    inventario.registrar_movimiento(uow, bobina.id, "consumo", -consumido, usuario=usuario, origen=origen,
                                    fecha=datos.fecha, documento_id=doc.id, observacion=f"OC slitter {numero}")
    for c in cortes_out:
        for r in c.detalle_rollos:
            fleje = uow.piezas.agregar(Pieza(
                None, "fleje", r.codigo, bobina.propietario_id, r.kg, r.kg,
                "disponible" if r.kg > umbral else "agotado", usuario, codigo_producto=c.codigo_producto,
                descripcion=c.descripcion, tipo_acero_id=bobina.tipo_acero_id, norma_id=bobina.norma_id,
                espesor_mm=bobina.espesor_mm, ancho_mm=c.ancho_mm, calidad=c.calidad,
                pieza_origen_id=bobina.id, orden_trabajo_id=orden.id, fecha_entrada=datos.fecha))
            uow.movimientos.agregar(Movimiento(
                None, fleje.id, "produccion", r.kg, r.kg, origen, usuario, fecha=datos.fecha, documento_id=doc.id,
                propietario_nuevo_id=bobina.propietario_id))
    if generador is not None:
        # La hoja de la orden y las etiquetas se generan con la OC y quedan guardadas para reimprimir.
        impresion.guardar_pdfs_slitter(uow, uow.ordenes.obtener(orden.id), generador, usuario)
    return resumen.model_copy(update={"guardada": True, "orden_id": orden.id})


NOMBRE_MAQUINA = {"lamina": "laminadora", "ctf": "CTF"}


def registrar_lamina(uow: UnidadDeTrabajo, datos: OtLaminaIn, *, usuario: str, origen: str,
                     generador: GeneradorDocumentos | None = None) -> ResumenOtLamina:
    """Corte a lámina (laminadora o CTF): consume kg de la pieza y suma láminas a la existencia del dueño."""
    if datos.clave_idempotencia and datos.confirmar:
        previa = uow.ordenes.por_clave(datos.clave_idempotencia)
        if previa is not None:
            raise ErrorNegocio(f"esta orden ya se registró (OC {previa.numero})", 409)
    pieza = uow.piezas.obtener(datos.pieza_id, bloquear=datos.confirmar)
    if pieza is None or pieza.anulada:
        raise ErrorNegocio("pieza inexistente o anulada", 404)
    if pieza.tipo not in ("bobina", "fleje") or pieza.saldo_unidades is not None:
        raise ErrorNegocio("a la laminadora y a la CTF solo entran bobinas o flejes", 422)
    if pieza.estado != "disponible":
        raise ErrorNegocio(f"la pieza {pieza.codigo_fisico} está agotada", 409)
    if pieza.tipo_acero_codigo is None or pieza.espesor_mm is None or pieza.ancho_mm is None:
        raise ErrorNegocio("la pieza no tiene tipo de acero, espesor o ancho; corrígelo en su ficha", 422)
    plan_ot = planificacion.tomar_plan(uow, datos.orden_planificada_id, datos.maquina, [pieza.id])
    if plan_ot is None:
        planificacion.verificar_libre(uow, pieza.id, pieza.codigo_fisico)

    umbral = inventario.umbral_agotado(uow)
    if datos.estatus_corte == "total":
        consumido = pieza.saldo_kg
    else:
        if datos.kg_procesado is None:
            raise ErrorNegocio("en un corte parcial indica los kg procesados", 422)
        consumido = datos.kg_procesado
        if consumido > pieza.saldo_kg + umbral:
            raise ErrorNegocio(f"se quieren procesar {consumido} kg y la pieza tiene {pieza.saldo_kg} kg")
    try:
        plan = laminas.planificar(
            espesor=pieza.espesor_mm, ancho_pieza=pieza.ancho_mm, consumido=consumido, largo_mm=datos.largo_mm,
            ancho_mm=datos.ancho_mm, atados=datos.atados,
            segundas={"A": datos.segunda_a, "B": datos.segunda_b, "C": datos.segunda_c}, scrap_kg=datos.scrap_kg,
            tolerancia=_param(uow, "tolerancia_corte", "0.05"), tolerancia_ancho_mm=_param(uow, "tolerancia_ancho_mm", "2"))
        # Espesor real de la bobina, salvo que el usuario elija redondear: entonces nombre y código van con el
        # comercial, para distinguirlas de las que no se redondean (decisión del 11 nov 2026).
        comercial = codigos.espesor_comercial(pieza.espesor_mm)
        espesor_lamina = comercial if datos.redondear_espesor else pieza.espesor_mm
        base = codigos.codigo_producto("lamina", pieza.tipo_acero_codigo, espesor_lamina, plan.ancho_mm, plan.largo_mm)
    except (laminas.CorteLaminaInvalido, codigos.CodigoInvalido) as exc:
        raise ErrorNegocio(str(exc), 422) from exc
    desc_base = laminas.descripcion_lamina(pieza.tipo_acero_codigo, espesor_lamina, plan.ancho_mm, plan.largo_mm)

    numero = datos.numero or (plan_ot.numero if plan_ot else siguiente_numero(uow, datos.maquina))
    avisos = list(plan.avisos)
    if datos.numero and not (plan_ot and datos.numero == plan_ot.numero) and \
            uow.ordenes.numero_en_uso(datos.maquina, datos.numero):
        avisos.append(f"ya existe una OC de {NOMBRE_MAQUINA[datos.maquina]} con el número {datos.numero}")
    restante = pieza.saldo_kg - consumido
    if datos.estatus_corte == "parcial" and restante <= umbral:
        avisos.append("el corte parcial deja la pieza sin saldo: ¿no es total?")

    grupos: list[GrupoLaminaOut] = []
    for g in plan.grupos:
        cod = base if g.clase == "1" else codigos.codigo_segunda(base, g.clase)
        desc = desc_base if g.clase == "1" else codigos.descripcion_segunda(desc_base, g.clase)
        actual = uow.piezas.existencia("lamina", cod, pieza.propietario_id)
        grupos.append(GrupoLaminaOut(
            clase=g.clase, calidad=laminas.calidad_de(g.clase, datos.calidad), codigo_producto=cod, descripcion=desc,
            unidades=g.unidades, kg=g.kg, existencia_despues=(actual.saldo_unidades if actual else 0) + g.unidades))
    atados = [AtadoOut(atado=i, unidades=n, kg=kg, codigo=laminas.codigo_atado(base, pieza.codigo_fisico, numero, i))
              for i, (n, kg) in enumerate(zip(datos.atados, plan.kg_atados), start=1)]

    resumen = ResumenOtLamina(
        guardada=False, maquina=datos.maquina, numero=numero, pieza=pieza.codigo_fisico,
        propietario=pieza.propietario_nombre, estatus_corte=datos.estatus_corte, kg_consumido=consumido,
        kg_producido=plan.producido, kg_scrap=plan.scrap_kg, saldo_restante_kg=restante, largo_mm=plan.largo_mm,
        ancho_mm=plan.ancho_mm, total_laminas=plan.total_laminas, kg_por_lamina=plan.kg_por_lamina,
        kg_teorico_por_lamina=plan.kg_teorico_por_lamina,
        diferencia_teorico_pct=(plan.diferencia_teorico * 100).quantize(Decimal("0.1")), grupos=grupos, atados=atados,
        espesor_real=pieza.espesor_mm, espesor_comercial=comercial if comercial != pieza.espesor_mm else None,
        avisos=avisos)
    if not datos.confirmar:
        return resumen

    doc = uow.documentos.agregar(Documento(None, f"ot_{datos.maquina}", numero=str(numero), fecha=datos.fecha,
                                           tercero_id=pieza.propietario_id, origen=origen, creado_por=usuario))
    orden = uow.ordenes.agregar(OrdenTrabajo(
        None, datos.maquina, numero, "cerrada", consumido, plan.producido, plan.scrap_kg, origen, usuario,
        fecha=datos.fecha, pieza_id=pieza.id, propietario_id=pieza.propietario_id, estatus_corte=datos.estatus_corte,
        paradas=datos.paradas, calidad=datos.calidad, documento_id=doc.id, observacion=datos.observacion,
        clave_idempotencia=datos.clave_idempotencia,
        detalle={
            "largo_mm": str(plan.largo_mm), "ancho_mm": str(plan.ancho_mm), "ancho_pieza_mm": str(pieza.ancho_mm),
            "total_laminas": plan.total_laminas, "kg_por_lamina": str(plan.kg_por_lamina),
            "kg_teorico_por_lamina": str(plan.kg_teorico_por_lamina),
            "grupos": [{"clase": g.clase, "calidad": g.calidad, "codigo_producto": g.codigo_producto,
                        "descripcion": g.descripcion, "unidades": g.unidades, "kg": str(g.kg)} for g in grupos],
            "atados": [{"atado": a.atado, "unidades": a.unidades, "kg": str(a.kg), "codigo": a.codigo} for a in atados],
            "avisos": avisos,
        }))
    planificacion.cerrar_plan(uow, plan_ot, orden.id, usuario=usuario, origen=origen)
    inventario.registrar_movimiento(uow, pieza.id, "consumo", -consumido, usuario=usuario, origen=origen,
                                    fecha=datos.fecha, documento_id=doc.id,
                                    observacion=f"OC {NOMBRE_MAQUINA[datos.maquina]} {numero}")
    for g in grupos:
        inventario.sumar_existencia(
            uow, inventario.ProductoEnExistencia(
                "lamina", g.codigo_producto, g.descripcion, pieza.propietario_id, calidad=g.calidad,
                tipo_acero_id=pieza.tipo_acero_id, norma_id=pieza.norma_id, espesor_mm=pieza.espesor_mm,
                ancho_mm=plan.ancho_mm, largo_mm=plan.largo_mm),
            g.unidades, g.kg, tipo_mov="produccion", usuario=usuario, origen=origen, fecha=datos.fecha,
            documento_id=doc.id, orden_trabajo_id=orden.id, pieza_origen_id=pieza.id,
            observacion=f"OC {NOMBRE_MAQUINA[datos.maquina]} {numero}")
    if generador is not None:
        impresion.guardar_pdfs_lamina(uow, uow.ordenes.obtener(orden.id), generador, usuario)
    return resumen.model_copy(update={"guardada": True, "orden_id": orden.id})


def registrar_maquila(uow: UnidadDeTrabajo, datos: OtMaquilaIn, *, usuario: str, origen: str,
                      generador: GeneradorDocumentos | None = None) -> ResumenOtMaquila:
    """Maquila de perfiles: consume flejes del cliente y suma perfiles a su existencia."""
    if datos.clave_idempotencia and datos.confirmar:
        previa = uow.ordenes.por_clave(datos.clave_idempotencia)
        if previa is not None:
            raise ErrorNegocio(f"esta orden ya se registró (OC {previa.numero})", 409)
    ids = [f.pieza_id for f in datos.flejes]
    if len(set(ids)) != len(ids):
        raise ErrorNegocio("un fleje aparece dos veces en la orden", 422)
    piezas = uow.piezas.obtener_varias(ids, bloquear=datos.confirmar)
    umbral = inventario.umbral_agotado(uow)
    flejes_out: list[FlejeConsumidoOut] = []
    dueno_id = None
    for f in datos.flejes:
        p = piezas.get(f.pieza_id)
        if p is None or p.anulada:
            raise ErrorNegocio(f"el fleje {f.pieza_id} no existe o está anulado", 404)
        if p.tipo != "fleje" or p.saldo_unidades is not None:
            raise ErrorNegocio(f"{p.codigo_fisico}: a la maquila de perfiles solo entran flejes", 422)
        if p.estado != "disponible":
            raise ErrorNegocio(f"el fleje {p.codigo_fisico} está agotado", 409)
        if dueno_id is None:
            dueno_id, primero = p.propietario_id, p
        elif p.propietario_id != dueno_id:
            raise ErrorNegocio(f"{p.codigo_fisico} es de {p.propietario_nombre}: todos los flejes deben ser del "
                               "mismo cliente", 422)
        kg = f.kg if f.kg is not None else p.saldo_kg
        if kg > p.saldo_kg + umbral:
            raise ErrorNegocio(f"se quieren procesar {kg} kg de {p.codigo_fisico} y tiene {p.saldo_kg} kg", 422)
        kg = min(kg, p.saldo_kg)
        if datos.orden_planificada_id is None:
            planificacion.verificar_libre(uow, p.id, p.codigo_fisico)
        flejes_out.append(FlejeConsumidoOut(pieza_id=p.id, codigo=p.codigo_fisico, kg=kg, saldo_restante_kg=p.saldo_kg - kg))
    consumido = sum((f.kg for f in flejes_out), Decimal("0"))
    plan_ot = planificacion.tomar_plan(uow, datos.orden_planificada_id, "maquila", ids)

    codigo = datos.codigo_producto.strip().upper()
    if not codigo.startswith("PER") or codigo[-2:] in ("-A", "-B", "-C"):
        raise ErrorNegocio("indica el código del perfil de primera (PER…, sin -A/-B/-C)", 422)
    catalogo = uow.catalogos.producto(codigo)
    descripcion = (datos.descripcion or "").strip() or (catalogo.nombre if catalogo else "")
    if not descripcion:
        raise ErrorNegocio(f"{codigo} no está en el catálogo: escribe su descripción", 422)
    teorico = datos.peso_teorico_kg or (catalogo.peso_unitario_kg if catalogo else None)
    try:
        plan = perfiles.planificar(
            consumido=consumido, paquetes=datos.paquetes,
            segundas={"A": datos.segunda_a, "B": datos.segunda_b, "C": datos.segunda_c},
            peso_teorico=teorico, scrap_kg=datos.scrap_kg, tolerancia=_param(uow, "tolerancia_corte", "0.05"))
    except perfiles.MaquilaInvalida as exc:
        raise ErrorNegocio(str(exc), 422) from exc

    numero = datos.numero or (plan_ot.numero if plan_ot else siguiente_numero(uow, "maquila"))
    avisos = list(plan.avisos)
    if catalogo is None:
        avisos.append(f"{codigo} no está en el catálogo de productos; conviene darlo de alta")
    if datos.numero and not (plan_ot and datos.numero == plan_ot.numero) and \
            uow.ordenes.numero_en_uso("maquila", datos.numero):
        avisos.append(f"ya existe una OC de maquila con el número {datos.numero}")

    grupos: list[GrupoLaminaOut] = []
    for g in plan.grupos:
        cod = codigo if g.clase == "1" else codigos.codigo_segunda(codigo, g.clase)
        desc = descripcion if g.clase == "1" else codigos.descripcion_segunda(descripcion, g.clase)
        actual = uow.piezas.existencia("perfil", cod, dueno_id)
        grupos.append(GrupoLaminaOut(
            clase=g.clase, calidad=laminas.calidad_de(g.clase, datos.calidad), codigo_producto=cod, descripcion=desc,
            unidades=g.unidades, kg=g.kg, existencia_despues=(actual.saldo_unidades if actual else 0) + g.unidades))
    paquetes = [PaqueteOut(paquete=i, unidades=n, kg=kg, codigo=perfiles.codigo_paquete(codigo, numero, i))
                for i, (n, kg) in enumerate(zip(datos.paquetes, plan.kg_paquetes), start=1)]
    resumen = ResumenOtMaquila(
        guardada=False, numero=numero, propietario=primero.propietario_nombre, flejes=flejes_out,
        kg_consumido=consumido, kg_producido=plan.producido, kg_scrap=plan.scrap_kg, total_perfiles=plan.total,
        kg_por_pieza=plan.kg_por_pieza, kg_teorico=teorico,
        diferencia_teorico_pct=(plan.diferencia_teorico * 100).quantize(Decimal("0.1"))
        if plan.diferencia_teorico is not None else None, grupos=grupos, paquetes=paquetes, avisos=avisos)
    if not datos.confirmar:
        return resumen

    doc = uow.documentos.agregar(Documento(None, "ot_maquila", numero=str(numero), fecha=datos.fecha,
                                           tercero_id=dueno_id, origen=origen, creado_por=usuario))
    orden = uow.ordenes.agregar(OrdenTrabajo(
        None, "maquila", numero, "cerrada", consumido, plan.producido, plan.scrap_kg, origen, usuario,
        fecha=datos.fecha, pieza_id=primero.id, propietario_id=dueno_id,
        estatus_corte="total" if all(f.saldo_restante_kg <= umbral for f in flejes_out) else "parcial",
        paradas=datos.paradas, calidad=datos.calidad, documento_id=doc.id, observacion=datos.observacion,
        clave_idempotencia=datos.clave_idempotencia,
        detalle={
            "total_unidades": plan.total, "kg_por_pieza": str(plan.kg_por_pieza),
            "kg_teorico": str(teorico) if teorico else None,
            "flejes": [{"pieza_id": f.pieza_id, "codigo": f.codigo, "kg": str(f.kg)} for f in flejes_out],
            "grupos": [{"clase": g.clase, "calidad": g.calidad, "codigo_producto": g.codigo_producto,
                        "descripcion": g.descripcion, "unidades": g.unidades, "kg": str(g.kg)} for g in grupos],
            "paquetes": [{"paquete": x.paquete, "unidades": x.unidades, "kg": str(x.kg), "codigo": x.codigo}
                         for x in paquetes],
            "avisos": avisos,
        }))
    planificacion.cerrar_plan(uow, plan_ot, orden.id, usuario=usuario, origen=origen)
    for f in flejes_out:
        inventario.registrar_movimiento(uow, f.pieza_id, "consumo", -f.kg, usuario=usuario, origen=origen,
                                        fecha=datos.fecha, documento_id=doc.id, observacion=f"OC maquila {numero}")
    for g in grupos:
        inventario.sumar_existencia(
            uow, inventario.ProductoEnExistencia(
                "perfil", g.codigo_producto, g.descripcion, dueno_id, calidad=g.calidad,
                tipo_acero_id=primero.tipo_acero_id, norma_id=primero.norma_id, espesor_mm=primero.espesor_mm),
            g.unidades, g.kg, tipo_mov="produccion", usuario=usuario, origen=origen, fecha=datos.fecha,
            documento_id=doc.id, orden_trabajo_id=orden.id, pieza_origen_id=primero.id,
            observacion=f"OC maquila {numero}")
    if generador is not None:
        impresion.guardar_pdfs_maquila(uow, uow.ordenes.obtener(orden.id), generador, usuario)
    return resumen.model_copy(update={"guardada": True, "orden_id": orden.id})


def obtener(uow: UnidadDeTrabajo, orden_id: int) -> OrdenTrabajo:
    o = uow.ordenes.obtener(orden_id)
    if o is None:
        raise ErrorNegocio("orden inexistente", 404)
    return o


def anular(uow: UnidadDeTrabajo, orden_id: int, motivo: str, *, usuario: str, origen: str) -> OrdenTrabajo:
    """Deshace una orden si nada de lo producido se ha movido todavía."""
    orden = obtener(uow, orden_id)
    if orden.estado == "anulada":
        raise ErrorNegocio("la orden ya estaba anulada")
    if orden.estado == "ejecutada":
        raise ErrorNegocio("esta planificación ya se ejecutó: anula la orden con los resultados", 422)
    if orden.estado == "planificada":   # no movió nada: se libera la pieza y listo
        inventario.aplicar_cambios(uow, orden, {"estado": "anulada"}, tabla="orden_trabajo", usuario=usuario,
                                   origen=origen)
        uow.ordenes.guardar(orden)
        uow.auditoria.registrar("orden_trabajo", orden.id, "motivo_anulacion", None, motivo, usuario=usuario,
                                origen=origen)
        return orden
    if orden.tipo != "slitter":
        return _anular_por_movimientos(uow, orden, motivo, usuario=usuario, origen=origen)
    producidas = [p for p in uow.piezas.producidas_por(orden.id) if not p.anulada]
    for p in producidas:
        if uow.movimientos.contar(p.id, excepto_tipo="produccion"):
            raise ErrorNegocio(f"no se puede anular: la pieza {p.codigo_fisico} ya tuvo movimientos")
    for p in producidas:
        inventario.aplicar_cambios(uow, p, {"anulada": True}, tabla="pieza", usuario=usuario, origen=origen)
        uow.piezas.guardar(p)
    if orden.pieza_id is not None and orden.kg_consumido > 0:
        inventario.registrar_movimiento(
            uow, orden.pieza_id, "ajuste", orden.kg_consumido, usuario=usuario, origen=origen, fecha=orden.fecha,
            observacion=f"Anulación de la OC {orden.tipo} {orden.numero}: {motivo}")
    inventario.aplicar_cambios(uow, orden, {"estado": "anulada"}, tabla="orden_trabajo", usuario=usuario, origen=origen)
    uow.ordenes.guardar(orden)
    uow.auditoria.registrar("orden_trabajo", orden.id, "motivo_anulacion", None, motivo, usuario=usuario, origen=origen)
    return orden


def _anular_por_movimientos(uow: UnidadDeTrabajo, orden: OrdenTrabajo, motivo: str, *, usuario: str,
                            origen: str) -> OrdenTrabajo:
    """Láminas y perfiles: se devuelven las piezas producidas (si siguen en existencia) y los kg consumidos."""
    if orden.documento_id is None:
        raise ErrorNegocio("esta orden no tiene movimientos que deshacer", 422)
    nota = f"Anulación de la OC {orden.tipo} {orden.numero}: {motivo}"
    movs = uow.movimientos.por_documento(orden.documento_id)
    for mv in movs:  # primero se verifica todo, después se mueve
        if mv.tipo == "produccion" and mv.unidades:
            p = uow.piezas.obtener(mv.pieza_id)
            if p is None or (p.saldo_unidades or 0) < mv.unidades:
                raise ErrorNegocio(f"no se puede anular: de {p.codigo_fisico if p else mv.pieza_id} ya salieron "
                                   "piezas de esta orden; anula primero esas notas de entrega")
    for mv in movs:
        if mv.tipo == "produccion" and mv.unidades:
            inventario.registrar_movimiento(uow, mv.pieza_id, "ajuste", -mv.kg, unidades=-mv.unidades, usuario=usuario,
                                            origen=origen, fecha=orden.fecha, observacion=nota)
        elif mv.tipo == "consumo" and mv.kg:
            inventario.registrar_movimiento(uow, mv.pieza_id, "ajuste", -mv.kg, usuario=usuario, origen=origen,
                                            fecha=orden.fecha, observacion=nota)
    inventario.aplicar_cambios(uow, orden, {"estado": "anulada"}, tabla="orden_trabajo", usuario=usuario, origen=origen)
    uow.ordenes.guardar(orden)
    uow.auditoria.registrar("orden_trabajo", orden.id, "motivo_anulacion", None, motivo, usuario=usuario, origen=origen)
    return orden
