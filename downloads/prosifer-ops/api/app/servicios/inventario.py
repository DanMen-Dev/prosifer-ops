"""Casos de uso de inventario. Toda escritura de existencias pasa por aquí.

Solo hablan con el exterior por la UnidadDeTrabajo (app.puertos): no saben de SQL
ni de HTTP. La API, el portal, el agente y las pruebas usan las mismas reglas.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from app.dominio import codigos, saldos
from app.dominio.entidades import TIPOS_POR_UNIDADES, Documento, Movimiento, Pieza
from app.errores import ErrorNegocio
from app.esquemas import EntradaBobinaIn, EntradaExistenciaIn, ExistenciaSimilar, ResumenEntrada, ResumenEntradaExistencia
from app.puertos import UnidadDeTrabajo

__all__ = ["ErrorNegocio", "ProductoEnExistencia", "registrar_entrada_bobina", "registrar_movimiento", "sumar_existencia",
           "editar_pieza", "anular_pieza"]

PESO_MIN_BOBINA = Decimal("50")
PESO_MAX_BOBINA = Decimal("25000")


def parametro(uow: UnidadDeTrabajo, clave: str, por_defecto: str) -> str:
    return uow.parametros.valor(clave, por_defecto)


def umbral_agotado(uow: UnidadDeTrabajo) -> Decimal:
    return Decimal(parametro(uow, "umbral_agotado_kg", "1"))


def descripcion_bobina(tipo_nombre: str, espesor: Decimal, ancho: Decimal) -> str:
    e = f"{espesor:.2f}".replace(".", ",")   # espesor real: bobinas y flejes no se redondean (11 nov 2026)
    return f"Bobina {tipo_nombre} {e}mm x {int(ancho)}mm"


def registrar_entrada_bobina(uow: UnidadDeTrabajo, datos: EntradaBobinaIn, *, usuario: str,
                             origen: str) -> ResumenEntrada:
    if datos.clave_idempotencia and datos.confirmar:
        previo = uow.movimientos.por_clave(datos.clave_idempotencia)
        if previo is not None:
            p = uow.piezas.obtener(previo.pieza_id)
            return ResumenEntrada(guardada=True, codigo_producto=p.codigo_producto or "", descripcion=p.descripcion or "",
                                  propietario=p.propietario_nombre,
                                  avisos=["ya estaba registrada (mismo identificador de petición)"], pieza_id=p.id)
    try:
        cod_tipo = codigos.codigo_tipo(datos.tipo_acero)
        codigo_producto = codigos.codigo_producto("bobina", cod_tipo, datos.espesor_mm, datos.ancho_mm)
    except codigos.CodigoInvalido as exc:
        raise ErrorNegocio(str(exc), 422) from exc
    tipo = uow.catalogos.tipo_por_codigo(cod_tipo)
    if tipo is None:
        raise ErrorNegocio(f"el tipo de acero {cod_tipo} no está en el catálogo", 422)
    propietario = uow.terceros.obtener(datos.propietario_id)
    if propietario is None:
        raise ErrorNegocio("propietario inexistente", 422)
    if datos.norma_id is not None and uow.catalogos.norma(datos.norma_id) is None:
        raise ErrorNegocio("norma inexistente", 422)

    codigo_fisico = " ".join(datos.codigo_bobina.split()).upper()
    repetida = uow.piezas.id_por_codigo("bobina", codigo_fisico)
    if repetida is not None:
        raise ErrorNegocio(f"ya existe una bobina con el código {codigo_fisico} (pieza {repetida})")

    avisos = []
    if not PESO_MIN_BOBINA <= datos.peso_kg <= PESO_MAX_BOBINA:
        avisos.append(f"peso fuera del rango habitual ({PESO_MIN_BOBINA}–{PESO_MAX_BOBINA} kg)")
    if datos.fecha > dt.date.today():
        avisos.append("la fecha de entrada es futura")
    comercial = codigos.espesor_comercial(datos.espesor_mm)
    if comercial != datos.espesor_mm.quantize(Decimal("0.01")):
        avisos.append(f"espesor {datos.espesor_mm} se vende como {comercial}")

    descripcion = descripcion_bobina(tipo.nombre, datos.espesor_mm, datos.ancho_mm)
    resumen = ResumenEntrada(guardada=False, codigo_producto=codigo_producto, descripcion=descripcion,
                             propietario=propietario.nombre, avisos=avisos)
    if not datos.confirmar:
        return resumen

    doc = uow.documentos.agregar(Documento(None, "entrada", numero=datos.documento_numero, fecha=datos.fecha,
                                           tercero_id=datos.siderurgica_id, origen=origen, creado_por=usuario))
    pieza = uow.piezas.agregar(Pieza(
        None, "bobina", codigo_fisico, propietario.id, datos.peso_kg, datos.peso_kg,
        saldos.estado_para(datos.peso_kg, umbral_agotado(uow)), usuario, codigo_producto=codigo_producto,
        descripcion=descripcion, tipo_acero_id=tipo.id, norma_id=datos.norma_id, espesor_mm=datos.espesor_mm,
        ancho_mm=datos.ancho_mm, siderurgica_id=datos.siderurgica_id, buque=datos.buque, fecha_entrada=datos.fecha))
    uow.movimientos.agregar(Movimiento(
        None, pieza.id, "entrada", datos.peso_kg, datos.peso_kg, origen, usuario, fecha=datos.fecha,
        documento_id=doc.id, propietario_nuevo_id=propietario.id, clave_idempotencia=datos.clave_idempotencia))
    return resumen.model_copy(update={"guardada": True, "pieza_id": pieza.id})


def registrar_movimiento(uow: UnidadDeTrabajo, pieza_id: int, tipo: str, kg: Decimal | None, *, usuario: str,
                         origen: str, fecha: dt.date | None = None, documento_id: int | None = None,
                         propietario_nuevo_id: int | None = None, observacion: str | None = None,
                         clave_idempotencia: str | None = None, permitir_negativo: bool = False,
                         unidades: int | None = None, revierte_id: int | None = None) -> Movimiento:
    """Aplica un movimiento bloqueando la pieza, para que dos pedidos no consuman los mismos kilos.

    Bobinas y flejes se mueven en kg. Láminas, perfiles y generales se mueven en piezas
    (`unidades`, con signo); si no se da el kg, sale al peso medio de la existencia.
    """
    if clave_idempotencia:
        previo = uow.movimientos.por_clave(clave_idempotencia)
        if previo is not None:
            return previo
    pieza = uow.piezas.obtener(pieza_id, bloquear=True)
    if pieza is None or pieza.anulada:
        raise ErrorNegocio("pieza inexistente o anulada", 404)
    if tipo == "ajuste" and not observacion:
        raise ErrorNegocio("un ajuste necesita motivo", 422)
    saldo_u = None
    try:
        if pieza.saldo_unidades is not None:
            if unidades is None:
                raise saldos.MovimientoInvalido(f"{pieza.codigo_fisico} se mueve en piezas: indica cuántas")
            ru = saldos.aplicar_unidades(pieza.saldo_unidades, pieza.saldo_kg, tipo, unidades, kg)
            kg, saldo_kg, saldo_u, estado = ru.kg, ru.saldo_kg, ru.saldo_unidades, ru.estado
        else:
            if unidades is not None or kg is None:
                raise saldos.MovimientoInvalido(f"{pieza.codigo_fisico} se mueve en kg, no en piezas")
            r = saldos.aplicar(pieza.saldo_kg, tipo, kg, umbral=umbral_agotado(uow),
                               permitir_negativo=permitir_negativo)
            saldo_kg, estado = r.saldo_kg, r.estado
    except saldos.MovimientoInvalido as exc:
        raise ErrorNegocio(str(exc)) from exc
    anterior = pieza.propietario_id
    if propietario_nuevo_id is not None:
        pieza.propietario_id = propietario_nuevo_id
    pieza.saldo_kg, pieza.estado, pieza.saldo_unidades = saldo_kg, estado, saldo_u
    uow.piezas.guardar(pieza)
    return uow.movimientos.agregar(Movimiento(
        None, pieza.id, tipo, kg, saldo_kg, origen, usuario, fecha=fecha, documento_id=documento_id,
        unidades=unidades, saldo_despues_unidades=saldo_u,
        propietario_anterior_id=anterior if propietario_nuevo_id is not None else None,
        propietario_nuevo_id=propietario_nuevo_id, clave_idempotencia=clave_idempotencia, observacion=observacion,
        revierte_id=revierte_id))


@dataclass
class ProductoEnExistencia:
    """Qué es lo que entra a una existencia en piezas: datos del producto, no de la pieza física."""
    tipo: str                         # lamina | perfil | general
    codigo_producto: str
    descripcion: str
    propietario_id: int
    calidad: str | None = None
    tipo_acero_id: int | None = None
    norma_id: int | None = None
    espesor_mm: Decimal | None = None
    ancho_mm: Decimal | None = None
    largo_mm: Decimal | None = None


def sumar_existencia(uow: UnidadDeTrabajo, prod: ProductoEnExistencia, unidades: int, kg: Decimal, *, tipo_mov: str,
                     usuario: str, origen: str, fecha: dt.date | None = None, documento_id: int | None = None,
                     orden_trabajo_id: int | None = None, pieza_origen_id: int | None = None,
                     observacion: str | None = None) -> Movimiento:
    """Suma piezas a la existencia de un código y dueño; la crea si no existe todavía."""
    if prod.tipo not in TIPOS_POR_UNIDADES:
        raise ErrorNegocio(f"{prod.tipo} no se lleva por piezas", 422)
    if unidades <= 0 or kg <= 0:
        raise ErrorNegocio(f"{prod.codigo_producto}: las piezas y el peso que entran deben ser mayores que cero", 422)
    codigo = prod.codigo_producto.strip().upper()
    fila = uow.piezas.existencia(prod.tipo, codigo, prod.propietario_id, bloquear=True)
    if fila is None:
        fila = uow.piezas.agregar(Pieza(
            None, prod.tipo, codigo, prod.propietario_id, Decimal("0"), Decimal("0"), "agotado", usuario,
            codigo_producto=codigo, descripcion=prod.descripcion, tipo_acero_id=prod.tipo_acero_id,
            norma_id=prod.norma_id, espesor_mm=prod.espesor_mm, ancho_mm=prod.ancho_mm, largo_mm=prod.largo_mm,
            calidad=prod.calidad, pieza_origen_id=pieza_origen_id, orden_trabajo_id=orden_trabajo_id,
            fecha_entrada=fecha, unidades_entrada=0, saldo_unidades=0))
    mv = registrar_movimiento(uow, fila.id, tipo_mov, kg, unidades=unidades, usuario=usuario, origen=origen,
                              fecha=fecha, documento_id=documento_id, propietario_nuevo_id=None, observacion=observacion)
    # Lo que ha entrado en total a esta existencia (para la ficha y el almacenaje).
    fila = uow.piezas.obtener(fila.id)
    fila.unidades_entrada = (fila.unidades_entrada or 0) + unidades
    fila.peso_entrada_kg = fila.peso_entrada_kg + kg
    if fecha and (fila.fecha_entrada is None or fecha < fila.fecha_entrada):
        fila.fecha_entrada = fecha
    uow.piezas.guardar(fila)
    return mv


def _texto_igual(s: str | None) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", (s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.replace(".", "").replace(",", "").split())   # «L.F. 0,90» = «lf 0.90»


def existencias_similares(uow: UnidadDeTrabajo, tipo: str, codigo: str, descripcion: str,
                          propietario_id: int) -> list[ExistenciaSimilar]:
    """Existencias del mismo dueño que parecen el mismo material con otro código.

    Láminas: mismo espesor comercial, ancho y largo (sea cual sea el acero o la calidad del código).
    Perfiles y generales: la misma descripción, sin contar mayúsculas, acentos ni puntos."""
    medidas = codigos.medidas_lamina(codigo) if tipo == "lamina" else None
    iguales = []
    for p in uow.piezas.existencias_de(propietario_id, tipo):
        if p.codigo_fisico.upper() == codigo.upper():
            continue
        if medidas:
            otras = codigos.medidas_lamina(p.codigo_fisico)
            esp, ancho, largo = (otras[1], otras[2], otras[3]) if otras else (p.espesor_mm, p.ancho_mm, p.largo_mm)
            if esp is None or ancho is None or largo is None:
                continue
            mismo = (codigos.espesor_comercial(esp) == codigos.espesor_comercial(medidas[1])
                     and Decimal(ancho) == medidas[2] and Decimal(largo) == medidas[3])
        else:
            mismo = bool(descripcion) and _texto_igual(p.descripcion) == _texto_igual(descripcion)
        if mismo:
            iguales.append(ExistenciaSimilar(pieza_id=p.id, codigo=p.codigo_fisico, descripcion=p.descripcion,
                                             saldo_unidades=p.saldo_unidades))
    return iguales


def registrar_entrada_existencia(uow: UnidadDeTrabajo, datos: EntradaExistenciaIn, *, usuario: str,
                                 origen: str) -> ResumenEntradaExistencia:
    """Entrada por piezas de láminas, perfiles o generales que no salen de una OC de la planta."""
    if datos.clave_idempotencia and datos.confirmar:
        previo = uow.documentos.por_clave(datos.clave_idempotencia)
        if previo is not None:
            raise ErrorNegocio(f"esta entrada ya se registró ({previo.numero})", 409)
    codigo = datos.codigo_producto.strip().upper()
    if codigos.sin_existencia(codigo):
        raise ErrorNegocio(f"{codigo} no lleva existencia: se registra solo en la nota de entrega, con su peso", 422)
    tipo = datos.tipo or codigos.tipo_existencia_por_codigo(codigo)
    propietario = uow.terceros.obtener(datos.propietario_id)
    if propietario is None:
        raise ErrorNegocio("propietario inexistente", 422)
    catalogo = uow.catalogos.producto(codigo)
    avisos = []
    descripcion = (datos.descripcion or "").strip() or (catalogo.nombre if catalogo else "")
    if not descripcion:
        raise ErrorNegocio(f"{codigo} no está en el catálogo: escribe su descripción", 422)
    if catalogo is None:
        avisos.append(f"{codigo} no está en el catálogo de productos; conviene darlo de alta")
    peso = datos.peso_unitario_kg or (catalogo.peso_unitario_kg if catalogo else None)
    if not peso:
        raise ErrorNegocio(f"{codigo} no tiene peso por pieza en el catálogo: indícalo", 422)
    if catalogo and catalogo.peso_unitario_kg and datos.peso_unitario_kg and \
            abs(datos.peso_unitario_kg - catalogo.peso_unitario_kg) > catalogo.peso_unitario_kg * Decimal("0.05"):
        avisos.append(f"el peso por pieza ({datos.peso_unitario_kg} kg) difiere más del 5 % del catálogo "
                      f"({catalogo.peso_unitario_kg} kg)")
    tipo_acero_id = espesor = ancho = largo = None
    medidas = codigos.medidas_lamina(codigo) if tipo == "lamina" else None
    if medidas:
        cod_tipo, espesor, ancho, largo = medidas
        t = uow.catalogos.tipo_por_codigo(cod_tipo)
        tipo_acero_id = t.id if t else None
    kg = (peso * datos.unidades).quantize(Decimal("0.001"))
    actual = uow.piezas.existencia(tipo, codigo, propietario.id)
    antes = actual.saldo_unidades if actual else 0
    # Solo si el código es nuevo para ese dueño: si ya tiene existencia con este código, se suma ahí.
    similares = [] if actual else existencias_similares(uow, tipo, codigo, descripcion, propietario.id)
    for x in similares:
        avisos.append(f"{propietario.nombre} ya tiene {x.saldo_unidades} piezas del mismo material con el código "
                      f"{x.codigo}: con {codigo} quedarían en una línea aparte")
    resumen = ResumenEntradaExistencia(
        guardada=False, tipo=tipo, codigo_producto=codigo, descripcion=descripcion, propietario=propietario.nombre,
        unidades=datos.unidades, peso_unitario_kg=peso, kg=kg, existencia_antes=antes,
        existencia_despues=antes + datos.unidades, avisos=avisos, similares=similares)
    if not datos.confirmar:
        return resumen
    doc = uow.documentos.agregar(Documento(
        None, "entrada", numero=f"{datos.documento_tipo} {datos.documento_numero}".strip(), fecha=datos.fecha,
        tercero_id=propietario.id, observacion=datos.observacion, origen=origen, creado_por=usuario,
        clave_idempotencia=datos.clave_idempotencia))
    mv = sumar_existencia(uow, ProductoEnExistencia(
        tipo, codigo, descripcion, propietario.id, calidad=datos.calidad, tipo_acero_id=tipo_acero_id,
        espesor_mm=espesor, ancho_mm=ancho, largo_mm=largo), datos.unidades, kg, tipo_mov="entrada",
        usuario=usuario, origen=origen, fecha=datos.fecha, documento_id=doc.id, observacion=datos.observacion)
    return resumen.model_copy(update={"guardada": True, "pieza_id": mv.pieza_id, "documento_id": doc.id})


def aplicar_cambios(uow: UnidadDeTrabajo, entidad, cambios: dict, *, tabla: str, usuario: str, origen: str) -> list[str]:
    """Cambia campos de una entidad y deja cada cambio en la auditoría. Quien llama la guarda."""
    cambiados = []
    for campo, nuevo in cambios.items():
        viejo = getattr(entidad, campo)
        if viejo == nuevo:
            continue
        setattr(entidad, campo, nuevo)
        uow.auditoria.registrar(tabla, entidad.id, campo, None if viejo is None else str(viejo),
                                None if nuevo is None else str(nuevo), usuario=usuario, origen=origen)
        cambiados.append(campo)
    return cambiados


def obtener_pieza(uow: UnidadDeTrabajo, pieza_id: int) -> Pieza:
    p = uow.piezas.obtener(pieza_id)
    if p is None:
        raise ErrorNegocio("pieza inexistente", 404)
    return p


def editar_pieza(uow: UnidadDeTrabajo, pieza_id: int, cambios: dict, *, usuario: str, origen: str) -> Pieza:
    """Corrige datos descriptivos (código, buque, norma, calidad, fecha). No toca existencias."""
    p = obtener_pieza(uow, pieza_id)
    if "codigo_fisico" in cambios:
        cambios["codigo_fisico"] = " ".join(cambios["codigo_fisico"].split()).upper()
        if p.saldo_unidades is not None:
            cambios.update(_recodificar_existencia(uow, p, cambios["codigo_fisico"], cambios.get("descripcion")))
        else:
            otra = uow.piezas.id_por_codigo(p.tipo, cambios["codigo_fisico"], excluir_id=p.id)
            if otra is not None:
                raise ErrorNegocio(f"ya existe otra pieza con ese código (pieza {otra})")
    if cambios.get("norma_id") is not None and uow.catalogos.norma(cambios["norma_id"]) is None:
        raise ErrorNegocio("norma inexistente", 422)
    if aplicar_cambios(uow, p, cambios, tabla="pieza", usuario=usuario, origen=origen):
        uow.piezas.guardar(p)
    return uow.piezas.obtener(p.id)


def _recodificar_existencia(uow: UnidadDeTrabajo, p: Pieza, codigo: str, descripcion: str | None) -> dict:
    """Nuevo código de una existencia (lámina, perfil o general): conserva su historial y su saldo.

    El código manda en la existencia: también cambian el código de producto, la descripción (la del
    catálogo, si no se da otra) y, en láminas, las medidas y el acero que dice el código."""
    if codigos.sin_existencia(codigo):
        raise ErrorNegocio(f"{codigo} no lleva existencia", 422)
    if codigos.tipo_existencia_por_codigo(codigo) != p.tipo:
        raise ErrorNegocio(f"{codigo} no es un código de {p.tipo}: LAM… lámina, PER… perfil, el resto general", 422)
    otra = uow.piezas.existencia(p.tipo, codigo, p.propietario_id)
    if otra is not None and otra.id != p.id:
        raise ErrorNegocio(f"{p.propietario_nombre} ya tiene una existencia con el código {codigo} "
                           f"({otra.saldo_unidades} piezas): únelas en vez de recodificar", 409)
    catalogo = uow.catalogos.producto(codigo)
    extra: dict = {"codigo_producto": codigo}
    if not descripcion and catalogo:
        extra["descripcion"] = catalogo.nombre
    medidas = codigos.medidas_lamina(codigo) if p.tipo == "lamina" else None
    if medidas:
        t = uow.catalogos.tipo_por_codigo(medidas[0])
        extra.update(tipo_acero_id=t.id if t else None, espesor_mm=medidas[1], ancho_mm=medidas[2], largo_mm=medidas[3])
    return extra


def unir_existencias(uow: UnidadDeTrabajo, origen_id: int, destino_id: int, motivo: str, *, usuario: str,
                     origen: str) -> Documento:
    """Pasa todas las piezas (y sus kg) de una existencia a otra del mismo dueño y tipo: el mismo material
    que quedó en dos líneas con códigos distintos. Queda un documento de ajuste con las dos líneas
    (salida de una, entrada en la otra), anulable como cualquier ajuste; el historial de ambas se conserva."""
    from app.servicios import despachos   # evita la importación circular

    if origen_id == destino_id:
        raise ErrorNegocio("elige otra existencia para unir", 422)
    a, b = obtener_pieza(uow, origen_id), obtener_pieza(uow, destino_id)
    for x in (a, b):
        if x.anulada or x.saldo_unidades is None:
            raise ErrorNegocio(f"{x.codigo_fisico}: solo se unen existencias de láminas, perfiles o generales", 422)
    if a.tipo != b.tipo or a.propietario_id != b.propietario_id:
        raise ErrorNegocio("solo se unen existencias del mismo tipo y del mismo dueño", 422)
    if not a.saldo_unidades:
        raise ErrorNegocio(f"{a.codigo_fisico} no tiene piezas que pasar", 422)
    reservadas, ordenes = despachos.unidades_reservadas(uow, a.id)
    if reservadas:
        raise ErrorNegocio(f"{a.codigo_fisico} tiene {reservadas} piezas reservadas en la orden de despacho "
                           f"{', '.join(sorted(set(ordenes)))}: despáchala o anúlala antes de unir", 409)
    nota = f"Unión de existencias: {a.codigo_fisico} → {b.codigo_fisico}. {motivo.strip()}"
    doc = uow.documentos.agregar(Documento(None, "ajuste", fecha=dt.date.today(), tercero_id=a.propietario_id,
                                           observacion=nota, origen=origen, creado_por=usuario))
    n, kg = a.saldo_unidades, a.saldo_kg
    registrar_movimiento(uow, a.id, "ajuste", -kg, unidades=-n, usuario=usuario, origen=origen, fecha=doc.fecha,
                         documento_id=doc.id, observacion=nota)
    registrar_movimiento(uow, b.id, "ajuste", kg, unidades=n, usuario=usuario, origen=origen, fecha=doc.fecha,
                         documento_id=doc.id, observacion=nota)
    return doc


def anular_pieza(uow: UnidadDeTrabajo, pieza_id: int, motivo: str, *, usuario: str, origen: str) -> Pieza:
    p = obtener_pieza(uow, pieza_id)
    if p.anulada:
        raise ErrorNegocio("la pieza ya estaba anulada")
    aplicar_cambios(uow, p, {"anulada": True}, tabla="pieza", usuario=usuario, origen=origen)
    uow.piezas.guardar(p)
    uow.auditoria.registrar("pieza", p.id, "motivo_anulacion", None, motivo, usuario=usuario, origen=origen)
    return p
