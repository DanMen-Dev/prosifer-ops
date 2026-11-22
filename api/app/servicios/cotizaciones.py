"""Cotizaciones de Prosifer, en USD: la mayoría por servicios (corte en slitter o laminadora, maquila,
carga y manejo, almacenamiento) y algunas por venta de material.

Siguen la numeración del Excel (D- 2940, D- 2941…): el histórico se carga con el importador y la app
continúa con el siguiente número. No mueven inventario. Se anulan con motivo; las del Excel son solo
consulta. Los abonos (pagos recibidos) se anotan en la cotización.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.dominio.entidades import Documento
from app.errores import ErrorNegocio
from app.esquemas import AbonoCotizacion, BorradorCotizacion, CotizacionIn, CotizacionOut, RenglonCotizacionIn
from app.puertos import UnidadDeTrabajo
from app.servicios import inventario, planificacion

TIPO = "cotizacion"
HISTORICO = "excel"
CENT = Decimal("0.01")

# Servicio que se cotiza por orden, según la máquina y el acero (códigos del catálogo de Prosifer).
SERVICIOS = {
    "slitter": {"HP": "SERVICIOCORTESLITTERHPUL", "HN": "SERVICIOCORTESLITTERHNEG", "GV": "SERVICIOCORTESLITTERGALV02",
                "AL": "SERVICIOCORTESLITTERALUM"},
    "lamina": {"HP": "SERVICIOCORTELAMINAHPUL", "GV": "SERVICIOCORTELAMINAGALV01", "AL": "SERVICIOCORTELAMINAALUMINIO"},
    "maquila": {"HP": "SERVICIOMAQPERHP", "HN": "SERVICIOMAQPERHN", "GV": "SERVICIOMAQPERGV"},
}
SERVICIOS["ctf"] = SERVICIOS["lamina"]
NOMBRES = {
    "SERVICIOCORTESLITTERHPUL": "Servicio de Corte Slitter Material HP",
    "SERVICIOCORTESLITTERHNEG": "Servicio de Corte Slitter Material HN",
    "SERVICIOCORTESLITTERGALV02": "Servicio de Corte Slitter Material Galv",
    "SERVICIOCORTESLITTERALUM": "Servicio de Corte Slitter Material Aluminio",
    "SERVICIOCORTELAMINAHPUL": "Servicio de Corte Laminadora Material HP",
    "SERVICIOCORTELAMINAGALV01": "Servicio de Corte Laminadora Material Galv",
    "SERVICIOCORTELAMINAALUMINIO": "Servicio de Corte Laminadora Material Aluminio",
    "SERVICIOMAQPERHP": "Servicio de Maquila - Perfiladora HP",
    "SERVICIOMAQPERHN": "Servicio de Maquila - Perfiladora HN-LC",
    "SERVICIOMAQPERGV": "Servicio de Maquila - Perfiladora GALV",
}


def total_renglon(cantidad: Decimal, precio: Decimal) -> Decimal:
    return (Decimal(cantidad) * Decimal(precio)).quantize(CENT, rounding=ROUND_HALF_UP)


def _renglon(r: RenglonCotizacionIn) -> dict:
    return {"codigo": (r.codigo or "").strip().upper() or None, "descripcion": r.descripcion.strip(),
            "cantidad": str(r.cantidad), "unidad": r.unidad.strip() or "Pza", "precio_unitario": str(r.precio_unitario),
            "total": str(total_renglon(r.cantidad, r.precio_unitario))}


def _texto_orden(o) -> str:
    return f"OC {planificacion.NOMBRE.get(o.tipo, o.tipo)} {o.numero}"


def _abono(a: AbonoCotizacion, usuario: str) -> dict:
    d = {"fecha": a.fecha.isoformat() if a.fecha else None, "destino": a.destino.strip(),
         "monto": str(a.monto.quantize(CENT)), "por": usuario}
    if a.referencia and a.referencia.strip():
        d["referencia"] = a.referencia.strip()
    return d


def _referencia_libre(uow: UnidadDeTrabajo, a: AbonoCotizacion) -> None:
    if a.referencia and a.referencia.strip():
        otra = uow.documentos.con_referencia_abono(TIPO, a.referencia)
        if otra is not None:
            raise ErrorNegocio(f"el pago {a.referencia.strip()} ya está anotado en la cotización D-{otra.numero}", 409)


def vista(d: Documento, tercero: str | None) -> CotizacionOut:
    """La cotización sin pasar por la base (vista previa del agente)."""
    enc = d.encabezado or {}
    t = calcular(enc)
    return CotizacionOut(id=d.id, numero=str(d.numero), fecha=d.fecha, tercero_id=d.tercero_id, tercero=tercero,
                         renglones=enc.get("renglones", []), subtotal=t["subtotal"], iva_pct=t["iva_pct"], iva=t["iva"],
                         total=t["total"], abonos=enc.get("abonos", []), abonado=t["abonado"], saldo=t["saldo"],
                         vendedor=enc.get("vendedor"), condicion_pago=enc.get("condicion_pago"),
                         nota_entrega=enc.get("nota_entrega"), notas=enc.get("notas"),
                         orden_trabajo_id=enc.get("orden_trabajo_id"), orden=enc.get("orden"), origen=d.origen,
                         creado_por=d.creado_por, guardada=d.id is not None)


def crear(uow: UnidadDeTrabajo, datos: CotizacionIn, *, usuario: str, origen: str) -> Documento:
    """Emite la cotización. Con confirmar=false no guarda nada: devuelve un Documento sin id (vista previa)."""
    if datos.confirmar and datos.clave_idempotencia:
        previa = uow.documentos.por_clave(datos.clave_idempotencia)
        if previa is not None and previa.tipo == TIPO:
            return previa   # el mismo pedido llegó dos veces: no se emite otra
    t = uow.terceros.obtener(datos.tercero_id)
    if t is None:
        raise ErrorNegocio("cliente inexistente", 422)
    orden = None
    if datos.orden_trabajo_id is not None:
        orden = uow.ordenes.obtener(datos.orden_trabajo_id)
        if orden is None:
            raise ErrorNegocio("orden de trabajo inexistente", 404)
    enc = {"renglones": [_renglon(r) for r in datos.renglones], "vendedor": datos.vendedor,
           "condicion_pago": datos.condicion_pago, "nota_entrega": datos.nota_entrega, "notas": datos.notas,
           "iva_pct": str(datos.iva_pct) if datos.iva_pct is not None else None,
           "orden_trabajo_id": orden.id if orden else None, "orden": _texto_orden(orden) if orden else None}
    enc = {k: v for k, v in enc.items() if v not in (None, "")}
    refs = [a.referencia.strip().upper() for a in datos.abonos if a.referencia and a.referencia.strip()]
    if len(refs) != len(set(refs)):
        raise ErrorNegocio("el mismo pago aparece dos veces", 422)
    for a in datos.abonos:
        _referencia_libre(uow, a)
    enc["abonos"] = [_abono(a, usuario) for a in datos.abonos]
    total = calcular(enc)["total"]
    if calcular(enc)["abonado"] > total + CENT:
        raise ErrorNegocio(f"los abonos pasan el total de la cotización ({total} USD)", 422)
    doc = Documento(None, TIPO, numero=None, fecha=datos.fecha, tercero_id=t.id, observacion=datos.notas, origen=origen,
                    creado_por=usuario, encabezado=enc, clave_idempotencia=datos.clave_idempotencia)
    if not datos.confirmar:
        doc.numero = str(uow.numerador.ver_siguiente(TIPO))
        return doc
    doc.numero = str(uow.numerador.siguiente(TIPO))
    return uow.documentos.agregar(doc)


def _cotizacion(uow: UnidadDeTrabajo, id_: int) -> Documento:
    d = uow.documentos.obtener(id_)
    if d is None or d.tipo != TIPO:
        raise ErrorNegocio("cotización inexistente", 404)
    return d


def anular(uow: UnidadDeTrabajo, id_: int, motivo: str, *, usuario: str, origen: str) -> Documento:
    d = _cotizacion(uow, id_)
    if d.anulado:
        raise ErrorNegocio("la cotización ya estaba anulada")
    if d.origen == HISTORICO:
        raise ErrorNegocio("las cotizaciones del histórico del Excel son solo de consulta", 422)
    inventario.aplicar_cambios(uow, d, {"anulado": True}, tabla="documento", usuario=usuario, origen=origen)
    d.encabezado = {**(d.encabezado or {}), "motivo_anulacion": motivo.strip()}
    uow.documentos.guardar(d)
    return d


def abonar(uow: UnidadDeTrabajo, id_: int, abono: AbonoCotizacion, *, usuario: str, origen: str) -> Documento:
    """Anota un pago recibido (destino: caja, banco, Zelle…). No se pasa del total por más de un centavo."""
    d = _cotizacion(uow, id_)
    if d.anulado:
        raise ErrorNegocio("la cotización está anulada", 422)
    enc = dict(d.encabezado or {})
    abonos = list(enc.get("abonos", []))
    total = calcular(enc)["total"]
    abonado = sum((Decimal(str(a["monto"])) for a in abonos), Decimal("0"))
    if abonado + abono.monto > total + CENT:
        raise ErrorNegocio(f"el abono pasa el total: quedan {total - abonado} USD por cobrar", 422)
    _referencia_libre(uow, abono)
    abonos.append(_abono(abono, usuario))
    d.encabezado = {**enc, "abonos": abonos}
    uow.documentos.guardar(d)
    uow.auditoria.registrar("documento", d.id, "abono", None, f"{abono.monto} USD · {abono.destino}",
                            usuario=usuario, origen=origen)
    return d


def calcular(enc: dict) -> dict:
    """Subtotal, IVA y total de una cotización guardada (la del Excel trae el total de cada renglón)."""
    subtotal = Decimal("0")
    for r in enc.get("renglones", []):
        if r.get("total") not in (None, ""):
            subtotal += Decimal(str(r["total"]))
        elif r.get("cantidad") not in (None, "") and r.get("precio_unitario") not in (None, ""):
            subtotal += total_renglon(Decimal(str(r["cantidad"])), Decimal(str(r["precio_unitario"])))
    subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_UP)
    pct = Decimal(str(enc["iva_pct"])) if enc.get("iva_pct") not in (None, "") else None
    iva = (subtotal * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP) if pct else Decimal("0.00")
    abonado = sum((Decimal(str(a["monto"])) for a in enc.get("abonos", []) if a.get("monto") not in (None, "")),
                  Decimal("0")).quantize(CENT)
    total = subtotal + iva
    return {"subtotal": subtotal, "iva_pct": pct, "iva": iva, "total": total, "abonado": abonado,
            "saldo": max(total - abonado, Decimal("0.00"))}


def _ids_de_la_orden(o) -> list[int]:
    ids = planificacion.piezas_del_plan(o)
    for x in (o.detalle or {}).get("flejes", []) or []:
        pid = x.get("pieza_id") if isinstance(x, dict) else x
        if isinstance(pid, int) and pid not in ids:
            ids.append(pid)
    return ids


def _comentario(uow: UnidadDeTrabajo, o, piezas: list) -> str | None:
    """Lo que relaciona el servicio con el material, para las notas de la cotización.

    Slitter y laminadora: el código y la descripción de la bobina. Maquila: el producto perfilado
    (código y nombre) y el primer fleje de la lista."""
    det = o.detalle or {}
    plan = det.get("plan") or {}
    if o.tipo == "maquila":
        grupos = det.get("grupos") or []
        primera = next((g for g in grupos if g.get("clase") in (None, "primera", "1")), grupos[0] if grupos else None)
        codigo = (primera or {}).get("codigo_producto") or plan.get("codigo_producto")
        nombre = (primera or {}).get("descripcion") or plan.get("descripcion")
        flejes = [x.get("codigo") for x in det.get("flejes", []) if isinstance(x, dict) and x.get("codigo")] \
            or [p.codigo_fisico for p in piezas]
        partes = [f"Producto: {codigo}" + (f" {nombre}" if nombre else "") if codigo or nombre else None,
                  f"Fleje: {flejes[0]}" + (f" (+{len(flejes) - 1} más)" if len(flejes) > 1 else "") if flejes else None]
    else:
        bobina = uow.piezas.obtener(o.pieza_id) if o.pieza_id else (piezas[0] if piezas else None)
        partes = [f"Bobina: {bobina.codigo_fisico}" + (f" {bobina.descripcion}" if bobina.descripcion else "")
                  if bobina else None]
    texto = " · ".join(p for p in partes if p)
    return texto[:500] or None


def borrador_desde_orden(uow: UnidadDeTrabajo, orden_id: int) -> BorradorCotizacion:
    """El atajo "Cotizar" de una orden: cliente, servicio según máquina y acero, y los kg procesados.

    Ejecutada: los kg consumidos de la orden. Planificada: el saldo del material que entra. El precio
    queda en cero para que Prosifer lo ponga (los precios sugeridos vendrán aparte)."""
    o = uow.ordenes.obtener(orden_id)
    if o is None:
        raise ErrorNegocio("orden de trabajo inexistente", 404)
    if o.estado == "anulada":
        raise ErrorNegocio("la orden está anulada", 422)
    avisos: list[str] = []
    piezas = [p for p in (uow.piezas.obtener(i) for i in _ids_de_la_orden(o)) if p is not None]
    aceros = sorted({p.tipo_acero_codigo for p in piezas if p.tipo_acero_codigo})
    kg = Decimal(o.kg_consumido or 0)
    if kg <= 0:
        kg = sum((p.saldo_kg for p in piezas), Decimal("0"))
        if o.estado == "planificada":
            avisos.append("orden planificada: los kg son los del material que entra; ajústalos con lo que se cortó")
    tabla = SERVICIOS.get(o.tipo, {})
    acero = aceros[0] if aceros else None
    codigo = tabla.get(acero or "")
    if codigo is None:
        codigo = tabla.get("HP")
        avisos.append(f"no hay un servicio de {planificacion.NOMBRE.get(o.tipo, o.tipo)} para acero {acero or 'sin dato'} "
                      "en el catálogo: se propone el de HP, revísalo")
    if len(aceros) > 1:
        avisos.append(f"la orden mezcla aceros ({', '.join(aceros)}): revisa el servicio")
    prod = uow.catalogos.producto(codigo) if codigo else None
    nombre = prod.nombre if prod else NOMBRES.get(codigo or "", "Servicio de corte")
    propietario = uow.terceros.obtener(o.propietario_id) if o.propietario_id else None
    if propietario is None and piezas:
        propietario = uow.terceros.obtener(piezas[0].propietario_id)
    renglon = RenglonCotizacionIn(codigo=codigo, descripcion=nombre, cantidad=kg.quantize(Decimal("0.01")) if kg > 0 else Decimal("1"),
                                  unidad="Kg", precio_unitario=Decimal("0"))
    if kg <= 0:
        avisos.append("no se pudo saber cuántos kg se procesaron: indícalos")
    return BorradorCotizacion(tercero_id=propietario.id if propietario else None,
                              tercero=propietario.nombre if propietario else None, orden_trabajo_id=o.id,
                              orden=_texto_orden(o), renglones=[renglon], notas=_comentario(uow, o, piezas),
                              avisos=avisos)
