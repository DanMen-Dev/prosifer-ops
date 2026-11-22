"""Orden de despacho del cliente y nota de salida.

El cliente (desde su portal), el personal o el agente piden retirar material del inventario del
cliente: la orden queda "pendiente" y el material reservado. El patio la prepara y emite la nota de
salida, que es lo que mueve el inventario; la orden pasa a "despachada".

Reservas (decisión del 12 nov 2026):
- Bobinas y flejes de una orden pendiente no entran en otra orden, NE, liberación ni corte.
- Láminas, perfiles y generales: lo reservado no cuenta como disponible para otras salidas.
- Anular la orden libera el material. Anular su nota de salida devuelve el material y la orden
  vuelve a quedar pendiente.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.dominio import salidas as reglas
from app.dominio.entidades import Documento, Pieza
from app.errores import ErrorNegocio
from app.esquemas import (
    LineaDespachoIn, LineaDespachoOut, NotaSalidaIn, OrdenDespachoIn, OrdenDespachoOut, ResumenSalida,
)
from app.puertos import UnidadDeTrabajo
from app.servicios import inventario

TIPO = "orden_despacho"
NOTA = "nota_salida"


# --- reservas -------------------------------------------------------------------

def _lineas(d: Documento) -> list[dict]:
    return list((d.encabezado or {}).get("lineas", []))


def reservada_en(uow: UnidadDeTrabajo, pieza_id: int, *, excepto: int | None = None) -> Documento | None:
    """La orden de despacho abierta que reserva esta pieza, si hay una."""
    for d in uow.documentos.abiertos(TIPO):
        if d.id != excepto and any(int(x["pieza_id"]) == pieza_id for x in _lineas(d)):
            return d
    return None


def unidades_reservadas(uow: UnidadDeTrabajo, pieza_id: int, *, excepto: int | None = None) -> tuple[int, list[str]]:
    total, ordenes = 0, []
    for d in uow.documentos.abiertos(TIPO):
        if d.id == excepto:
            continue
        for x in _lineas(d):
            if int(x["pieza_id"]) == pieza_id and x.get("unidades"):
                total += int(x["unidades"])
                ordenes.append(str(d.numero))
    return total, ordenes


def verificar_unidades(uow: UnidadDeTrabajo, p: Pieza, pedidas: int | None, *, excepto: int | None = None) -> None:
    """Láminas, perfiles y generales: lo pedido no puede tomar piezas reservadas en otras órdenes."""
    reservadas, ordenes = unidades_reservadas(uow, p.id, excepto=excepto)
    if not reservadas:
        return
    libres = (p.saldo_unidades or 0) - reservadas
    pedido = pedidas if pedidas is not None else (p.saldo_unidades or 0)
    if pedido > libres:
        cuales = ", ".join(sorted(set(ordenes)))
        raise reglas.SalidaInvalida(
            f"solo hay {max(libres, 0)} piezas libres: {reservadas} están reservadas en la orden de despacho {cuales}")


# --- salida de datos ------------------------------------------------------------

def a_salida(d: Documento, tercero: str, *, creado_en: dt.datetime | None = None,
             avisos: list[str] | None = None, guardada: bool = True) -> OrdenDespachoOut:
    enc = d.encabezado or {}
    lineas = [LineaDespachoOut(pieza_id=int(x["pieza_id"]), tipo=x.get("tipo", ""), codigo=x.get("codigo", ""),
                               descripcion=x.get("descripcion"), kg=Decimal(str(x["kg"])),
                               unidades=x.get("unidades")) for x in enc.get("lineas", [])]
    unidades = [x.unidades for x in lineas if x.unidades is not None]
    ns = enc.get("nota_salida") or {}
    return OrdenDespachoOut(
        guardada=guardada, id=d.id, numero=str(d.numero), estado="anulada" if d.anulado else (d.estado or "borrador"),
        fecha=d.fecha, tercero_id=d.tercero_id, tercero=tercero, lineas=lineas,
        total_kg=sum((x.kg for x in lineas), Decimal("0")), total_unidades=sum(unidades) if unidades else None,
        retiro=enc.get("retiro"), observacion=d.observacion, origen=d.origen, creado_por=d.creado_por,
        creado_en=creado_en, nota_salida_id=ns.get("id"), nota_salida_numero=ns.get("numero"), avisos=avisos or [])


def _tercero(uow: UnidadDeTrabajo, id_: int):
    t = uow.terceros.obtener(id_)
    if t is None:
        raise ErrorNegocio("cliente inexistente", 422)
    return t


def _orden(uow: UnidadDeTrabajo, id_: int, cliente: int | None = None) -> Documento:
    d = uow.documentos.obtener(id_)
    if d is None or d.tipo != TIPO or (cliente is not None and d.tercero_id != cliente):
        raise ErrorNegocio("orden de despacho inexistente", 404)
    return d


# --- casos de uso ---------------------------------------------------------------

def crear(uow: UnidadDeTrabajo, datos: OrdenDespachoIn, *, usuario: str, origen: str,
          cliente: int | None = None) -> OrdenDespachoOut:
    """Nueva orden de despacho. `cliente`: el tercero del usuario cliente (manda sobre tercero_id)."""
    from app.servicios import salidas   # evita la importación circular

    tercero_id = cliente if cliente is not None else datos.tercero_id
    if tercero_id is None:
        raise ErrorNegocio("indica el cliente dueño del material", 422)
    if datos.confirmar and datos.clave_idempotencia:
        previo = uow.documentos.por_clave(datos.clave_idempotencia)
        if previo is not None:
            raise ErrorNegocio(f"esta orden ya se registró (orden de despacho {previo.numero})", 409)
    t = _tercero(uow, tercero_id)
    piezas = salidas._piezas(uow, [l.pieza_id for l in datos.lineas], datos.confirmar)
    evaluadas, avisos = salidas.evaluar_lineas(uow, t, datos.lineas, piezas)
    retiro = datos.retiro.limpio() if datos.retiro else None
    if datos.retiro and datos.retiro.fecha_retiro and datos.retiro.fecha_retiro < datos.fecha:
        avisos.append("la fecha de retiro es anterior a la fecha de la orden")
    lineas = [{"pieza_id": x.pieza_id, "tipo": piezas[x.pieza_id].tipo, "codigo": x.codigo,
               "descripcion": x.descripcion, "kg": str(x.kg), "unidades": x.unidades} for x in evaluadas]
    numero = (str(uow.numerador.siguiente(TIPO)) if datos.confirmar
              else f"{uow.numerador.ver_siguiente(TIPO)} (se asigna al enviar)")
    d = Documento(None, TIPO, numero=numero, fecha=datos.fecha, tercero_id=t.id, observacion=datos.observacion,
                  origen=origen, creado_por=usuario, clave_idempotencia=datos.clave_idempotencia,
                  encabezado={"lineas": lineas, "retiro": retiro}, estado="pendiente" if datos.confirmar else None)
    if datos.confirmar:
        d = uow.documentos.agregar(d)
    return a_salida(d, t.nombre, avisos=avisos, guardada=datos.confirmar)


def anular(uow: UnidadDeTrabajo, id_: int, motivo: str, *, usuario: str, origen: str,
           cliente: int | None = None) -> OrdenDespachoOut:
    """Libera el material reservado. Solo mientras está pendiente; el cliente, solo las suyas."""
    d = _orden(uow, id_, cliente)
    if d.anulado:
        raise ErrorNegocio("la orden ya estaba anulada")
    if d.estado != "pendiente":
        raise ErrorNegocio(f"la orden ya salió con la nota de salida {(d.encabezado or {}).get('nota_salida', {}).get('numero', '')}: "
                           "anula primero la nota de salida", 422)
    inventario.aplicar_cambios(uow, d, {"anulado": True}, tabla="documento", usuario=usuario, origen=origen)
    uow.documentos.guardar(d)
    uow.auditoria.registrar("documento", d.id, "motivo_anulacion", None, motivo, usuario=usuario, origen=origen)
    return a_salida(d, _tercero(uow, d.tercero_id).nombre)


def nota_salida(uow: UnidadDeTrabajo, id_: int, datos: NotaSalidaIn, *, usuario: str, origen: str) -> ResumenSalida:
    """Emite la nota de salida de una orden pendiente: mueve el inventario y la orden queda despachada."""
    from app.servicios import salidas   # evita la importación circular

    od = _orden(uow, id_)
    if od.anulado or od.estado != "pendiente":
        raise ErrorNegocio("la orden de despacho no está pendiente", 422)
    if datos.confirmar and datos.clave_idempotencia:
        previo = uow.documentos.por_clave(datos.clave_idempotencia)
        if previo is not None:
            raise ErrorNegocio(f"esta nota ya se registró (nota de salida {previo.numero})", 409)
    t = _tercero(uow, od.tercero_id)
    pedidas_od = {int(x["pieza_id"]): x for x in _lineas(od)}
    if datos.lineas is None:
        pedidas = [LineaDespachoIn(pieza_id=k, kg=None if x.get("unidades") else Decimal(str(x["kg"])),
                                   unidades=x.get("unidades")) for k, x in pedidas_od.items()]
    else:
        pedidas = datos.lineas
        for l in pedidas:
            if l.pieza_id not in pedidas_od:
                raise ErrorNegocio(f"la pieza {l.pieza_id} no está en la orden de despacho {od.numero}", 422)
    piezas = salidas._piezas(uow, [l.pieza_id for l in pedidas], datos.confirmar, excepto_despacho=od.id)
    lineas, avisos = salidas.evaluar_lineas(uow, t, pedidas, piezas, excepto_despacho=od.id)
    libres = salidas.evaluar_libres(uow, datos.libres)   # medidas irregulares: solo su peso, sin stock

    salen = {x.pieza_id: x for x in lineas}
    for k, x in pedidas_od.items():
        s = salen.get(k)
        if s is None:
            avisos.append(f"{x.get('codigo')}: no sale; queda libre en el inventario del cliente")
        elif x.get("unidades") and s.unidades is not None and s.unidades < int(x["unidades"]):
            avisos.append(f"{x.get('codigo')}: salen {s.unidades} de {x['unidades']} pedidas; el resto queda libre")
        elif not x.get("unidades") and s.kg < Decimal(str(x["kg"])):
            avisos.append(f"{x.get('codigo')}: salen {s.kg} kg de {x['kg']} pedidos; el resto queda libre")

    resumen = ResumenSalida(guardada=False, tipo=NOTA, numero=f"{uow.numerador.ver_siguiente(NOTA)} (se asigna al guardar)",
                            fecha=datos.fecha, tercero=t.nombre, lineas=lineas, libres=libres,
                            total_kg=sum((x.kg for x in lineas), Decimal("0")) + sum((x.kg for x in libres), Decimal("0")),
                            avisos=avisos)
    if not datos.confirmar:
        return resumen

    numero = str(uow.numerador.siguiente(NOTA))
    retiro = (datos.retiro.limpio() if datos.retiro else None) or (od.encabezado or {}).get("retiro")
    renglones = [{"pieza_id": x.pieza_id, "tipo": piezas[x.pieza_id].tipo, "codigo": x.codigo,
                  "descripcion": x.descripcion, "kg": str(x.kg), "unidades": x.unidades} for x in lineas]
    doc = uow.documentos.agregar(Documento(
        None, NOTA, numero=numero, fecha=datos.fecha, tercero_id=t.id,
        observacion=datos.observacion, origen=origen, creado_por=usuario, clave_idempotencia=datos.clave_idempotencia,
        encabezado={"orden_despacho_id": od.id, "orden_despacho": od.numero, "retiro": retiro, "lineas": renglones,
                    **({"libres": [{"codigo": x.codigo, "descripcion": x.descripcion, "kg": str(x.kg)} for x in libres]}
                       if libres else {})}))
    salidas.registrar_salidas(uow, doc, lineas, fecha=datos.fecha, usuario=usuario, origen=origen)
    if libres:   # renglones del documento (detalle y totales), sin movimiento de inventario
        uow.documentos.agregar_lineas(doc.id, [{"codigo": x.codigo, "descripcion": x.descripcion, "cantidad": x.kg,
                                               "unidad": "Kg", "kg": x.kg} for x in libres])
    inventario.aplicar_cambios(uow, od, {"estado": "despachada"}, tabla="documento", usuario=usuario, origen=origen)
    od.encabezado = {**(od.encabezado or {}), "nota_salida": {"id": doc.id, "numero": numero}}
    uow.documentos.guardar(od)
    return resumen.model_copy(update={"guardada": True, "documento_id": doc.id, "numero": numero})


def reabrir(uow: UnidadDeTrabajo, ns: Documento, *, usuario: str, origen: str) -> None:
    """Al anular una nota de salida, su orden vuelve a pendiente (el material queda reservado otra vez)."""
    od_id = (ns.encabezado or {}).get("orden_despacho_id")
    od = uow.documentos.obtener(int(od_id)) if od_id else None
    if od is None or od.anulado:
        return
    inventario.aplicar_cambios(uow, od, {"estado": "pendiente"}, tabla="documento", usuario=usuario, origen=origen)
    od.encabezado = {k: v for k, v in (od.encabezado or {}).items() if k != "nota_salida"}
    uow.documentos.guardar(od)
