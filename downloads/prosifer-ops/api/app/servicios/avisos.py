"""Aviso de entrada: el cliente anuncia material que va a llegar al patio.

No mueve inventario. Prosifer lo ve en Entradas > Avisos de clientes, prepara la recepción y, cuando
el material llega, registra la entrada con los formularios de siempre (precargados con el aviso) y
lo marca como recibido. Si no llega o no se acepta, lo rechaza con un motivo que el cliente ve. El
cliente puede cancelarlo mientras está pendiente.
"""
from __future__ import annotations

from decimal import Decimal

from app.dominio.entidades import Documento
from app.errores import ErrorNegocio
from app.esquemas import AvisoEntradaIn
from app.puertos import UnidadDeTrabajo
from app.servicios import inventario

TIPO = "aviso_entrada"


def crear(uow: UnidadDeTrabajo, datos: AvisoEntradaIn, *, cliente: int | None, usuario: str, origen: str,
          hoy) -> Documento:
    tercero_id = cliente if cliente is not None else datos.tercero_id
    if tercero_id is None:
        raise ErrorNegocio("indica el cliente dueño del material", 422)
    if uow.terceros.obtener(tercero_id) is None:
        raise ErrorNegocio("cliente inexistente", 422)
    renglones = []
    for r in datos.renglones:
        if not (r.codigo or r.descripcion):
            raise ErrorNegocio("cada renglón necesita un código o una descripción", 422)
        if not (r.cantidad or r.peso_kg):
            raise ErrorNegocio(f"indica la cantidad o el peso de «{r.codigo or r.descripcion}»", 422)
        renglones.append({k: (str(v) if isinstance(v, Decimal) else v)
                          for k, v in r.model_dump().items() if v not in (None, "")})
    if datos.fecha_estimada < hoy:
        raise ErrorNegocio("la fecha de llegada ya pasó", 422)
    return uow.documentos.agregar(Documento(
        None, TIPO, numero=str(uow.numerador.siguiente(TIPO)), fecha=hoy, tercero_id=tercero_id,
        observacion=(datos.comentarios or "").strip() or None, origen=origen, creado_por=usuario, estado="pendiente",
        encabezado={"fecha_estimada": datos.fecha_estimada.isoformat(), "documento_tipo": datos.documento_tipo,
                    "documento_numero": (datos.documento_numero or "").strip() or None,
                    "proveedor": (datos.proveedor or "").strip() or None,
                    "transporte": datos.transporte.limpio() if datos.transporte else None, "renglones": renglones}))


def _aviso(uow: UnidadDeTrabajo, id_: int, cliente: int | None = None) -> Documento:
    d = uow.documentos.obtener(id_)
    if d is None or d.tipo != TIPO or (cliente is not None and d.tercero_id != cliente):
        raise ErrorNegocio("aviso inexistente", 404)
    return d


def _cerrar(uow: UnidadDeTrabajo, d: Documento, estado: str, nota: str | None, *, usuario: str, origen: str) -> Documento:
    if d.anulado or d.estado != "pendiente":
        raise ErrorNegocio("este aviso ya se cerró", 422)
    inventario.aplicar_cambios(uow, d, {"estado": estado}, tabla="documento", usuario=usuario, origen=origen)
    d.encabezado = {**(d.encabezado or {}), "nota": (nota or "").strip() or None, "revisado_por": usuario}
    uow.documentos.guardar(d)
    return d


def cancelar(uow: UnidadDeTrabajo, id_: int, motivo: str, *, cliente: int | None, usuario: str, origen: str) -> Documento:
    return _cerrar(uow, _aviso(uow, id_, cliente), "cancelado", motivo, usuario=usuario, origen=origen)


def sin_entrada(d: Documento) -> list[int]:
    """Renglones (salvo flejes, que se registran a mano) que todavía no tienen su entrada enlazada."""
    return [i for i, r in enumerate((d.encabezado or {}).get("renglones", []))
            if r.get("tipo") != "fleje" and not r.get("entrada")]


def recibir(uow: UnidadDeTrabajo, id_: int, nota: str | None, *, usuario: str, origen: str,
            forzar: bool = False) -> Documento:
    """El material llegó: el aviso queda cerrado. Marcarlo NO suma inventario; por eso, si algún renglón no
    tiene su entrada registrada, se pide confirmar que se registró a mano (forzar)."""
    d = _aviso(uow, id_)
    faltan = sin_entrada(d)
    if faltan and not forzar:
        raise ErrorNegocio(f"{len(faltan)} renglón(es) sin entrada registrada: marcar el aviso como recibido no suma "
                           "inventario. Registra la entrada de cada renglón o confirma que ya se hizo a mano", 409)
    return _cerrar(uow, d, "recibido", nota, usuario=usuario, origen=origen)


def enlazar_entrada(uow: UnidadDeTrabajo, id_: int, indice: int, pieza_id: int, texto: str | None, *,
                    usuario: str, origen: str) -> Documento:
    """Anota en el renglón del aviso la entrada que se registró con su formulario precargado."""
    d = _aviso(uow, id_)
    if d.anulado or d.estado not in ("pendiente", "recibido"):
        raise ErrorNegocio("este aviso fue cancelado o rechazado", 422)
    renglones = list((d.encabezado or {}).get("renglones", []))
    if not 0 <= indice < len(renglones):
        raise ErrorNegocio("renglón inexistente", 404)
    p = uow.piezas.obtener(pieza_id)
    if p is None or p.anulada:
        raise ErrorNegocio("la entrada registrada no existe o está anulada", 404)
    if p.propietario_id != d.tercero_id:
        raise ErrorNegocio(f"{p.codigo_fisico} no es del cliente del aviso", 422)
    renglones[indice] = {**renglones[indice], "entrada": {"pieza_id": p.id, "codigo": p.codigo_fisico,
                                                          "texto": (texto or "").strip() or None, "por": usuario}}
    d.encabezado = {**(d.encabezado or {}), "renglones": renglones}
    uow.documentos.guardar(d)
    uow.auditoria.registrar("documento", d.id, "entrada_aviso", None, f"renglón {indice + 1}: {p.codigo_fisico}",
                            usuario=usuario, origen=origen)
    return d


def rechazar(uow: UnidadDeTrabajo, id_: int, motivo: str, *, usuario: str, origen: str) -> Documento:
    return _cerrar(uow, _aviso(uow, id_), "rechazado", motivo, usuario=usuario, origen=origen)
