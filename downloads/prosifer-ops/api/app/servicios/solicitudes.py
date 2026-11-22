"""Solicitud de orden de corte que precarga el cliente desde su portal.

No es una orden: queda "pendiente" hasta que Prosifer la revisa en Órdenes de corte > Solicitudes
de clientes. Al autorizarla se abre el formulario de planificación precargado con lo pedido; lo que
Prosifer guarde (con los cambios que haga falta) es la OC planificada definitiva, y la solicitud
queda "aprobada" y enlazada a ella. También se puede rechazar con un motivo que el cliente ve. El
cliente puede cancelarla mientras esté pendiente.

No aparta el material (eso lo hace la OC planificada al autorizarse), pero no se aceptan dos
solicitudes pendientes sobre la misma pieza ni sobre piezas ya en proceso o reservadas.
"""
from __future__ import annotations

from decimal import Decimal

from app.dominio.entidades import Documento
from app.errores import ErrorNegocio
from app.esquemas import AprobacionSolicitudIn, PlanOtOut, SolicitudCorteIn
from app.puertos import UnidadDeTrabajo
from app.servicios import inventario, planificacion

TIPO = "solicitud_corte"
EMBALAJE = {"ojo_al_cielo": "ojo al cielo", "vertical": "vertical"}
PIEZA = {"slitter": ("bobina",), "lamina": ("bobina",), "maquila": ("fleje",)}


def _kg(x: Decimal) -> str:
    return f"{x:,.0f}".replace(",", ".")


def texto(pedido: dict, comentarios: str | None) -> str:
    """El pedido en palabras: va a la observación de la OC (sale en la hoja de trabajo)."""
    partes: list[str] = []
    tipo = pedido.get("tipo")
    if tipo == "slitter":
        cortes = " + ".join(f"{c['cortes']} × {c['ancho_mm']} mm" for c in pedido.get("cortes", []))
        if cortes:
            partes.append(f"cortes {cortes}")
        partes.append("corte total de la bobina" if pedido.get("corte_total", True)
                      else f"corte parcial, hasta {_kg(Decimal(pedido['peso_max_kg']))} kg aprox.")
        if pedido.get("peso_max_rollo_kg"):
            partes.append(f"rollos de máx. {_kg(Decimal(pedido['peso_max_rollo_kg']))} kg")
        if pedido.get("embalaje"):
            partes.append(f"embalaje {EMBALAJE[pedido['embalaje']]}")
    elif tipo == "lamina":
        if pedido.get("largo_mm"):
            partes.append(f"láminas de {pedido['largo_mm']} mm de largo")
        partes.append("corte total de la bobina" if pedido.get("corte_total", True)
                      else f"cortar {pedido['cantidad_laminas']} láminas")
    elif tipo == "maquila" and pedido.get("descripcion"):
        partes.append(str(pedido["descripcion"]))
    salida = "Pedido del cliente" + (": " + "; ".join(partes) if partes else "") + "."
    if comentarios:
        salida += f" Comentario: {comentarios}"
    return salida[:1000]


def _pendientes_con(uow: UnidadDeTrabajo, pieza_id: int) -> Documento | None:
    for d in uow.documentos.abiertos(TIPO):
        if pieza_id in (d.encabezado or {}).get("piezas", []):
            return d
    return None


def crear(uow: UnidadDeTrabajo, datos: SolicitudCorteIn, *, cliente: int | None, usuario: str, origen: str,
          tercero_id: int | None = None) -> Documento:
    ids = list(dict.fromkeys(datos.flejes)) if datos.tipo == "maquila" else ([datos.pieza_id] if datos.pieza_id else [])
    if not ids:
        raise ErrorNegocio("elige el fleje a maquilar" if datos.tipo == "maquila" else "elige la bobina a cortar", 422)
    dueno = cliente if cliente is not None else tercero_id
    piezas = []
    for pid in ids:
        p = uow.piezas.obtener(pid)
        if p is None or p.anulada or (dueno is not None and p.propietario_id != dueno):
            raise ErrorNegocio("esa pieza no está en tu inventario", 404)
        if p.tipo not in PIEZA[datos.tipo]:
            raise ErrorNegocio(f"{p.codigo_fisico} es un {p.tipo}; aquí va un {' o '.join(PIEZA[datos.tipo])}", 422)
        if p.estado != "disponible" or p.saldo_kg <= 0:
            raise ErrorNegocio(f"{p.codigo_fisico} ya no está disponible", 409)
        try:
            planificacion.verificar_libre(uow, p.id, p.codigo_fisico)
        except ErrorNegocio as exc:
            raise ErrorNegocio(f"{p.codigo_fisico} ya está en una orden de corte o reservada para despacho", 409) from exc
        otra = _pendientes_con(uow, p.id)
        if otra is not None:
            raise ErrorNegocio(f"{p.codigo_fisico} ya está en la solicitud {otra.numero}, pendiente de revisión", 409)
        piezas.append(p)
    if len({p.propietario_id for p in piezas}) > 1:
        raise ErrorNegocio("todas las piezas deben ser del mismo cliente", 422)
    if datos.tipo == "maquila" and len({p.ancho_mm for p in piezas}) > 1:
        raise ErrorNegocio("los flejes de una misma orden de maquila deben tener el mismo ancho", 422)

    pedido: dict = {"tipo": datos.tipo, "corte_total": datos.corte_total}
    if datos.tipo == "slitter":
        if not datos.cortes:
            raise ErrorNegocio("indica el ancho de los flejes y cuántos cortes", 422)
        usado = sum((c.ancho_mm * c.cortes for c in datos.cortes), Decimal("0"))
        if piezas[0].ancho_mm and usado > piezas[0].ancho_mm:
            raise ErrorNegocio(f"los cortes suman {usado} mm y la bobina tiene {piezas[0].ancho_mm} mm", 422)
        if not datos.corte_total and not datos.peso_max_kg:
            raise ErrorNegocio("en el corte parcial indica cuántos kg aproximados se cortan", 422)
        pedido["cortes"] = [{"ancho_mm": str(c.ancho_mm), "cortes": c.cortes} for c in datos.cortes]
        if not datos.corte_total:
            pedido["peso_max_kg"] = str(datos.peso_max_kg)
        if datos.peso_max_rollo_kg:
            pedido["peso_max_rollo_kg"] = str(datos.peso_max_rollo_kg)
        if datos.embalaje:
            pedido["embalaje"] = datos.embalaje
    elif datos.tipo == "lamina":
        if not datos.largo_mm:
            raise ErrorNegocio("indica el largo de la lámina", 422)
        if not datos.corte_total and not datos.cantidad_laminas:
            raise ErrorNegocio("indica cuántas láminas cortar, o elige corte total", 422)
        pedido["largo_mm"] = str(datos.largo_mm)
        if not datos.corte_total:
            pedido["cantidad_laminas"] = datos.cantidad_laminas
    else:
        if not (datos.codigo_producto or "").strip():
            raise ErrorNegocio("elige el perfil a fabricar", 422)
        pedido["codigo_producto"] = datos.codigo_producto.strip().upper()
        pedido["descripcion"] = (datos.descripcion or "").strip() or None
    comentarios = (datos.comentarios or "").strip() or None

    return uow.documentos.agregar(Documento(
        None, TIPO, numero=str(uow.numerador.siguiente(TIPO)), fecha=datos.fecha, tercero_id=piezas[0].propietario_id,
        observacion=comentarios, origen=origen, creado_por=usuario, estado="pendiente",
        encabezado={"piezas": [p.id for p in piezas], "pedido": pedido, "texto": texto(pedido, comentarios)}))


def _solicitud(uow: UnidadDeTrabajo, id_: int, cliente: int | None = None) -> Documento:
    d = uow.documentos.obtener(id_)
    if d is None or d.tipo != TIPO or (cliente is not None and d.tercero_id != cliente):
        raise ErrorNegocio("solicitud inexistente", 404)
    return d


def _cerrar(uow: UnidadDeTrabajo, d: Documento, estado: str, extra: dict, *, usuario: str, origen: str) -> Documento:
    if d.anulado or d.estado != "pendiente":
        raise ErrorNegocio("esta solicitud ya se revisó o se canceló", 422)
    inventario.aplicar_cambios(uow, d, {"estado": estado}, tabla="documento", usuario=usuario, origen=origen)
    d.encabezado = {**(d.encabezado or {}), **extra, "revisado_por": usuario}
    uow.documentos.guardar(d)
    return d


def cancelar(uow: UnidadDeTrabajo, id_: int, motivo: str, *, cliente: int | None, usuario: str, origen: str) -> Documento:
    """El cliente la retira mientras nadie la ha revisado."""
    d = _solicitud(uow, id_, cliente)
    return _cerrar(uow, d, "cancelada", {"motivo": motivo}, usuario=usuario, origen=origen)


def rechazar(uow: UnidadDeTrabajo, id_: int, motivo: str, *, usuario: str, origen: str) -> Documento:
    d = _solicitud(uow, id_)
    return _cerrar(uow, d, "rechazada", {"motivo": motivo}, usuario=usuario, origen=origen)


def aprobar(uow: UnidadDeTrabajo, id_: int, datos: AprobacionSolicitudIn, *, usuario: str, origen: str) -> PlanOtOut:
    """Crea la OC planificada definitiva (lo que Prosifer decidió, con o sin cambios) y enlaza la solicitud."""
    d = _solicitud(uow, id_)
    if d.anulado or d.estado != "pendiente":
        raise ErrorNegocio("esta solicitud ya se revisó o se canceló", 422)
    ids = datos.flejes if datos.tipo == "maquila" else ([datos.pieza_id] if datos.pieza_id else [])
    for pid in ids:
        p = uow.piezas.obtener(pid)
        if p is not None and p.propietario_id != d.tercero_id:
            raise ErrorNegocio(f"{p.codigo_fisico} no es del cliente de la solicitud", 422)
    out = planificacion.planificar(uow, datos, usuario=usuario, origen=origen)
    o = uow.ordenes.obtener(out.orden_id)
    detalle = dict(o.detalle or {})
    detalle["plan"] = {**detalle.get("plan", {}), "solicitud_id": d.id, "solicitud_numero": d.numero,
                       "solicitud": (d.encabezado or {}).get("pedido")}
    o.detalle = detalle
    uow.ordenes.guardar(o)
    _cerrar(uow, d, "aprobada", {"orden_id": out.orden_id, "orden_numero": out.numero}, usuario=usuario, origen=origen)
    return out
