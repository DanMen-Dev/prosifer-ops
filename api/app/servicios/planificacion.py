"""OC planificada: la orden se crea antes del corte, se imprime la hoja de trabajo para que el operador
anote a mano lo que sale, y los resultados se cargan después (en la pantalla o, más adelante, por WhatsApp).

- La bobina o los flejes quedan "en proceso": no se venden ni entran en otra orden mientras la
  planificada esté abierta (decisión del 11 nov 2026: vale para slitter, laminadora, CTF y maquila).
- No mueve inventario. Al registrar los resultados con orden_planificada_id, la orden de resultados
  usa el mismo número y la planificada queda "ejecutada", enlazada a ella.
- Se anula sin más trámite: no tiene movimientos.
"""
from __future__ import annotations

from decimal import Decimal

from app.dominio import codigos, generador, laminas
from app.dominio.entidades import OrdenTrabajo
from app.errores import ErrorNegocio
from app.esquemas import PlanOtIn, PlanOtOut
from app.puertos import UnidadDeTrabajo
from app.servicios import inventario

CERO = Decimal("0")
TIPO_PIEZA = {"slitter": ("bobina", "fleje"), "lamina": ("bobina",), "ctf": ("bobina", "fleje"), "maquila": ("fleje",)}
NOMBRE = {"slitter": "slitter", "lamina": "laminadora", "ctf": "CTF", "maquila": "maquila"}


def piezas_del_plan(o: OrdenTrabajo) -> list[int]:
    plan = (o.detalle or {}).get("plan", {})
    ids = [int(x) for x in plan.get("flejes", [])]
    if o.pieza_id is not None and o.pieza_id not in ids:
        ids.insert(0, o.pieza_id)
    return ids


def en_proceso(uow: UnidadDeTrabajo, pieza_id: int, *, excepto: int | None = None) -> OrdenTrabajo | None:
    """La OC planificada abierta que tiene esta pieza, si hay una."""
    for o in uow.ordenes.planificadas():
        if o.id != excepto and pieza_id in piezas_del_plan(o):
            return o
    return None


def ocupaciones(uow: UnidadDeTrabajo) -> dict[int, dict]:
    """Por pieza: en qué OC planificada está y en qué órdenes de despacho abiertas está reservada (y cuántas
    piezas, en láminas, perfiles y generales). Es lo mismo que bloquea verificar_libre, para mostrarlo."""
    from app.servicios import despachos   # evita la importación circular

    ocup: dict[int, dict] = {}
    for o in uow.ordenes.planificadas():
        for pid in piezas_del_plan(o):
            ocup.setdefault(pid, {})["en_proceso"] = f"OC {NOMBRE.get(o.tipo, o.tipo)} {o.numero}"
    for d in uow.documentos.abiertos(despachos.TIPO):
        for x in (d.encabezado or {}).get("lineas", []):
            o = ocup.setdefault(int(x["pieza_id"]), {})
            o.setdefault("despachos", [])
            if str(d.numero) not in o["despachos"]:
                o["despachos"].append(str(d.numero))
            if x.get("unidades"):
                o["unidades"] = o.get("unidades", 0) + int(x["unidades"])
    return ocup


def marcar_ocupadas(uow: UnidadDeTrabajo, piezas: list) -> None:
    """Completa en_proceso / reservada_en / unidades_reservadas de una lista de PiezaOut."""
    if not piezas:
        return
    ocup = ocupaciones(uow)
    for p in piezas:
        o = ocup.get(p.id)
        if not o:
            continue
        p.en_proceso = o.get("en_proceso")
        if o.get("despachos"):
            p.reservada_en = ("orden de despacho " if len(o["despachos"]) == 1 else "órdenes de despacho ") + \
                ", ".join(o["despachos"])
        p.unidades_reservadas = o.get("unidades")


def verificar_libre(uow: UnidadDeTrabajo, pieza_id: int, codigo: str, *, excepto: int | None = None,
                    excepto_despacho: int | None = None) -> None:
    """Bobina o fleje libre: ni en una OC planificada ni reservado en una orden de despacho abierta."""
    from app.servicios import despachos   # evita la importación circular

    o = en_proceso(uow, pieza_id, excepto=excepto)
    if o is not None:
        raise ErrorNegocio(f"{codigo} está en proceso en la OC {NOMBRE[o.tipo]} {o.numero} (planificada): registra "
                           "sus resultados o anula la planificación", 409)
    d = despachos.reservada_en(uow, pieza_id, excepto=excepto_despacho)
    if d is not None:
        raise ErrorNegocio(f"{codigo} está reservado en la orden de despacho {d.numero}: emite su nota de salida o "
                           "anula la orden", 409)


def _num(x) -> str | None:
    return None if x is None else str(x)


def planificar(uow: UnidadDeTrabajo, datos: PlanOtIn, *, usuario: str, origen: str) -> PlanOtOut:
    from app.servicios.ordenes import siguiente_numero   # evita la importación circular

    avisos: list[str] = []
    if datos.confirmar and datos.clave_idempotencia:
        previa = uow.ordenes.por_clave(datos.clave_idempotencia)
        if previa is not None:   # el mismo pedido llegó dos veces (reintento, doble 👍): se devuelve la ya creada
            return PlanOtOut(orden_id=previa.id, tipo=previa.tipo, numero=previa.numero,
                             avisos=["esta orden ya se había creado con esa clave"], plan=(previa.detalle or {}).get("plan"))
    ids = list(dict.fromkeys(datos.flejes)) if datos.tipo == "maquila" else ([datos.pieza_id] if datos.pieza_id else [])
    if not ids:
        raise ErrorNegocio("indica los flejes que entran" if datos.tipo == "maquila" else "indica la bobina que entra", 422)
    piezas = []
    for pid in ids:
        p = uow.piezas.obtener(pid)
        if p is None or p.anulada:
            raise ErrorNegocio(f"pieza {pid} inexistente", 404)
        if p.tipo not in TIPO_PIEZA[datos.tipo]:
            raise ErrorNegocio(f"{p.codigo_fisico} es {p.tipo}: a {NOMBRE[datos.tipo]} entran "
                               f"{' o '.join(TIPO_PIEZA[datos.tipo])}", 422)
        if p.estado != "disponible" or p.saldo_kg <= 0:
            raise ErrorNegocio(f"{p.codigo_fisico} no está disponible ({p.estado})", 409)
        verificar_libre(uow, p.id, p.codigo_fisico)
        piezas.append(p)
    duenos = {p.propietario_id for p in piezas}
    if len(duenos) > 1:
        raise ErrorNegocio("todos los flejes deben ser del mismo cliente", 422)
    principal = piezas[0]

    plan: dict = {"kg_disponible": str(sum((p.saldo_kg for p in piezas), CERO))}
    if datos.tipo == "slitter":
        if not datos.cortes:
            raise ErrorNegocio("indica los anchos y rollos del corte", 422)
        usado = sum((c.ancho_mm * c.rollos for c in datos.cortes), CERO)
        if principal.ancho_mm and usado > principal.ancho_mm:
            raise ErrorNegocio(f"los cortes suman {usado} mm y la bobina tiene {principal.ancho_mm} mm", 422)
        plan["cortes"] = [{"ancho_mm": str(c.ancho_mm), "rollos": c.rollos} for c in datos.cortes]
        if principal.ancho_mm:
            plan["scrap_ancho_mm"] = str(principal.ancho_mm - usado)
    elif datos.tipo in ("lamina", "ctf"):
        if not datos.largo_mm:
            raise ErrorNegocio("indica el largo de la lámina", 422)
        if not principal.espesor_mm or not principal.ancho_mm:
            raise ErrorNegocio("la pieza no tiene espesor o ancho registrado; corrígelo en su ficha", 422)
        ancho = datos.ancho_mm or principal.ancho_mm
        if ancho > principal.ancho_mm + 2:
            raise ErrorNegocio(f"la lámina de {ancho} mm no sale de una pieza de {principal.ancho_mm} mm", 422)
        espesor = codigos.espesor_comercial(principal.espesor_mm) if datos.redondear_espesor else principal.espesor_mm
        teorico = laminas.peso_teorico(principal.espesor_mm, ancho, datos.largo_mm)
        kg_atado = Decimal(inventario.parametro(uow, "kg_por_atado", "2500"))
        try:
            codigo = codigos.codigo_producto("lamina", principal.tipo_acero_codigo, espesor, ancho, datos.largo_mm)
        except codigos.CodigoInvalido as exc:
            raise ErrorNegocio(str(exc), 422) from exc
        plan.update({
            "largo_mm": str(datos.largo_mm), "ancho_mm": str(ancho), "redondear_espesor": datos.redondear_espesor,
            "codigo_producto": codigo,
            "descripcion": laminas.descripcion_lamina(principal.tipo_acero_codigo or "", espesor, ancho, datos.largo_mm),
            "peso_teorico_kg": str(teorico),
            "por_atado": int(kg_atado / teorico) if teorico else None,
            "laminas_estimadas": int(principal.saldo_kg / teorico) if teorico else None,
        })
    else:  # maquila
        codigo = (datos.codigo_producto or "").strip().upper()
        if not codigo.startswith("PER"):
            raise ErrorNegocio("indica el código del perfil de primera (PER…)", 422)
        catalogo = uow.catalogos.producto(codigo)
        descripcion = (datos.descripcion or "").strip() or (catalogo.nombre if catalogo else "")
        if not descripcion:
            raise ErrorNegocio(f"{codigo} no está en el catálogo: escribe su descripción", 422)
        teorico = datos.peso_teorico_kg or (catalogo.peso_unitario_kg if catalogo else None)
        total = sum((p.saldo_kg for p in piezas), CERO)
        largo = datos.largo_mm
        if largo is None and (leido := generador.leer(descripcion)) is not None:
            largo = leido.largo_mm          # "x 6,00mts" -> 6000: va en grande en la hoja
        plan.update({
            "flejes": [p.id for p in piezas], "codigo_producto": codigo, "descripcion": descripcion,
            "peso_teorico_kg": _num(teorico), "largo_mm": _num(largo),
            "perfiles_estimados": int(total / teorico) if teorico else None,
        })
        if not teorico:
            avisos.append("sin peso teórico: la hoja no estimará cuántos perfiles salen")

    numero = datos.numero or siguiente_numero(uow, datos.tipo)
    if datos.numero and uow.ordenes.numero_en_uso(datos.tipo, datos.numero):
        raise ErrorNegocio(f"ya existe una OC de {NOMBRE[datos.tipo]} con el número {datos.numero}", 409)
    entran = [{"id": p.id, "codigo": p.codigo_fisico, "descripcion": p.descripcion, "kg": str(p.saldo_kg),
               "tipo_acero": p.tipo_acero_codigo} for p in piezas]
    resumen = dict(propietario=principal.propietario_nombre or None, piezas=entran, plan=plan)
    if not datos.confirmar:   # vista previa (agente): todo validado, nada guardado; el número puede cambiar
        return PlanOtOut(orden_id=None, tipo=datos.tipo, numero=numero, avisos=avisos, guardada=False, **resumen)
    orden = uow.ordenes.agregar(OrdenTrabajo(
        None, datos.tipo, numero, "planificada", CERO, CERO, CERO, origen, usuario, fecha=datos.fecha,
        pieza_id=principal.id, propietario_id=principal.propietario_id, calidad=datos.calidad,
        observacion=datos.observacion, detalle={"plan": plan}, clave_idempotencia=datos.clave_idempotencia))
    uow.auditoria.registrar("orden_trabajo", orden.id, "estado", None, "planificada", usuario=usuario, origen=origen)
    return PlanOtOut(orden_id=orden.id, tipo=datos.tipo, numero=numero, avisos=avisos, **resumen)


def tomar_plan(uow: UnidadDeTrabajo, plan_id: int | None, tipo: str, piezas: list[int]) -> OrdenTrabajo | None:
    """Al registrar resultados: la planificada que se ejecuta (verificada) o None.
    Sin plan, ninguna de las piezas puede estar en proceso en otra orden."""
    if plan_id is None:
        return None
    o = uow.ordenes.obtener(plan_id)
    if o is None or o.estado != "planificada":
        raise ErrorNegocio("esa OC planificada no existe o ya se ejecutó", 409)
    if (o.tipo != tipo) and not ({o.tipo, tipo} <= {"lamina", "ctf"}):
        raise ErrorNegocio(f"la OC planificada {o.numero} es de {NOMBRE[o.tipo]}", 422)
    if not set(piezas) <= set(piezas_del_plan(o)):
        raise ErrorNegocio(f"las piezas no son las de la OC planificada {o.numero}", 422)
    return o


def cerrar_plan(uow: UnidadDeTrabajo, plan: OrdenTrabajo | None, resultado_id: int, *, usuario: str,
                origen: str) -> None:
    if plan is None:
        return
    detalle = dict(plan.detalle or {})
    detalle["orden_resultado_id"] = resultado_id
    inventario.aplicar_cambios(uow, plan, {"estado": "ejecutada", "detalle": detalle}, tabla="orden_trabajo",
                               usuario=usuario, origen=origen)
    uow.ordenes.guardar(plan)

