"""Arma los datos de impresión de una orden a partir de lo guardado.

Sirve igual para una OC recién creada, una importada del Excel o una reimpresión.
"""
from __future__ import annotations

import re
from decimal import Decimal

from app.dominio import codigos, slitter
from app.dominio.entidades import OrdenTrabajo
from app.dominio.impresion import (
    AtadoImpreso, CorteImpreso, FlejeImpreso, GrupoImpreso, HojaTrabajo, OrdenLaminaImpresa, OrdenMaquilaImpresa,
    OrdenSlitterImpresa, PiezaHoja, RolloImpreso,
)
from app.puertos import GeneradorDocumentos, UnidadDeTrabajo

POSICION = re.compile(r"^(\d+)-([A-O])$")
NOMBRES = {"orden": "orden.pdf", "etiquetas": "etiquetas.pdf"}


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def orden_slitter(uow: UnidadDeTrabajo, orden: OrdenTrabajo, solo_piezas: list[int] | None = None) -> OrdenSlitterImpresa:
    bobina = uow.piezas.obtener(orden.pieza_id) if orden.pieza_id else None
    producidas = uow.piezas.producidas_por(orden.id)
    if orden.estado != "anulada":
        producidas = [p for p in producidas if not p.anulada]
    detalle = orden.detalle or {}
    tipo_cod = bobina.tipo_acero_codigo if bobina else None
    espesor = bobina.espesor_mm if bobina else None

    cortes: list[CorteImpreso] = []
    for c in detalle.get("cortes", []):
        ancho = _f(c.get("ancho_mm"))
        muestra = next((p for p in producidas if p.ancho_mm is not None and float(p.ancho_mm) == ancho), None)
        cod = c.get("codigo_producto") or (muestra.codigo_producto if muestra else None)
        if not cod and tipo_cod and espesor:
            try:
                cod = codigos.codigo_producto("fleje", tipo_cod, espesor, ancho)
            except codigos.CodigoInvalido:
                cod = ""
        desc = (muestra.descripcion if muestra and muestra.descripcion else None) or (
            slitter.descripcion_fleje(tipo_cod, espesor, Decimal(str(c.get("ancho_mm"))))
            if tipo_cod and espesor and ancho else "")
        cortes.append(CorteImpreso(int(c.get("posicion") or len(cortes) + 1), ancho, int(c.get("rollos") or 1),
                                   _f(c.get("kg")), cod or "", desc))

    rollos: list[RolloImpreso] = []
    for p in producidas:
        if solo_piezas is not None and p.id not in solo_piezas:
            continue
        sufijo = p.codigo_fisico.rsplit("/", 1)[-1].strip()
        g = POSICION.match(sufijo)
        if g:
            corte = int(g.group(1))
        else:  # OC importadas: el corte se deduce por el ancho
            corte = next((c.posicion for c in cortes if p.ancho_mm is not None and c.ancho == float(p.ancho_mm)), 1)
        rollos.append(RolloImpreso(p.codigo_fisico, sufijo if g else f"#{len(rollos) + 1}", _f(p.peso_entrada_kg),
                                   corte, p.calidad))

    scrap = detalle.get("scrap") or {}
    return OrdenSlitterImpresa(
        numero=orden.numero, fecha=orden.fecha.strftime("%d/%m/%Y") if orden.fecha else "—",
        bobina=bobina.codigo_fisico if bobina else "—", producto=(bobina.codigo_producto or "") if bobina else "",
        descripcion=(bobina.descripcion or "") if bobina else "", tipo_codigo=tipo_cod or "",
        tipo_nombre=(bobina.tipo_acero_nombre or "") if bobina else "", norma=(bobina.norma_nombre or "") if bobina else "",
        espesor=_f(espesor), ancho=_f(bobina.ancho_mm if bobina else detalle.get("ancho_bobina_mm")),
        peso_entrada=_f(bobina.peso_entrada_kg if bobina else 0), consumido=_f(orden.kg_consumido),
        dueno=orden.propietario_nombre, estatus=(orden.estatus_corte or "").capitalize(),
        calidad=orden.calidad or "", cortes=cortes, scrap_ancho=_f(scrap.get("ancho_mm")), scrap_kg=_f(orden.kg_scrap),
        rollos=rollos, registro=orden.creado_por, paradas=orden.paradas or 0, observacion=orden.observacion or "",
        anulada=orden.estado == "anulada")


def guardar_pdfs_slitter(uow: UnidadDeTrabajo, orden: OrdenTrabajo, generador: GeneradorDocumentos,
                         usuario: str) -> None:
    datos = orden_slitter(uow, orden)
    uow.archivos.guardar("orden_trabajo", orden.id, NOMBRES["orden"], generador.orden_slitter(datos),
                         tipo_mime="application/pdf", usuario=usuario)
    uow.archivos.guardar("orden_trabajo", orden.id, NOMBRES["etiquetas"], generador.etiquetas_slitter(datos),
                         tipo_mime="application/pdf", usuario=usuario)


def pdf_slitter(uow: UnidadDeTrabajo, orden: OrdenTrabajo, doc: str, generador: GeneradorDocumentos, *,
                piezas: list[int] | None = None, regenerar: bool = False) -> bytes:
    """La copia guardada al crear la orden; si no hay (OC importada), se pide un subconjunto o se
    pide regenerar, se arma con los datos de la orden."""
    if not piezas and not regenerar and orden.estado != "anulada":
        guardado = uow.archivos.buscar("orden_trabajo", orden.id, NOMBRES[doc])
        if guardado:
            return guardado
    datos = orden_slitter(uow, orden, solo_piezas=piezas)
    return generador.orden_slitter(datos) if doc == "orden" else generador.etiquetas_slitter(datos)


MAQUINAS = {"lamina": "LAMINADORA", "ctf": "CTF"}


def orden_lamina(uow: UnidadDeTrabajo, orden: OrdenTrabajo) -> OrdenLaminaImpresa:
    """Todo sale del detalle guardado con la orden: la reimpresión es idéntica a la original."""
    pieza = uow.piezas.obtener(orden.pieza_id) if orden.pieza_id else None
    d = orden.detalle or {}
    return OrdenLaminaImpresa(
        numero=orden.numero, maquina=MAQUINAS.get(orden.tipo, orden.tipo.upper()),
        fecha=orden.fecha.strftime("%d/%m/%Y") if orden.fecha else "—",
        pieza=pieza.codigo_fisico if pieza else "—", producto=(pieza.codigo_producto or "") if pieza else "",
        descripcion=(pieza.descripcion or "") if pieza else "", tipo_codigo=(pieza.tipo_acero_codigo or "") if pieza else "",
        tipo_nombre=(pieza.tipo_acero_nombre or "") if pieza else "", norma=(pieza.norma_nombre or "") if pieza else "",
        espesor=_f(pieza.espesor_mm if pieza else 0), ancho_pieza=_f(d.get("ancho_pieza_mm")),
        peso_entrada=_f(pieza.peso_entrada_kg if pieza else 0), consumido=_f(orden.kg_consumido),
        dueno=orden.propietario_nombre, estatus=(orden.estatus_corte or "").capitalize(), largo=_f(d.get("largo_mm")),
        ancho=_f(d.get("ancho_mm")), kg_por_lamina=_f(d.get("kg_por_lamina")), kg_teorico=_f(d.get("kg_teorico_por_lamina")),
        grupos=[GrupoImpreso(g["clase"], g.get("calidad") or "", g["codigo_producto"], g["descripcion"],
                             int(g["unidades"]), _f(g["kg"])) for g in d.get("grupos", [])],
        atados=[AtadoImpreso(int(a["atado"]), int(a["unidades"]), _f(a["kg"]), a["codigo"]) for a in d.get("atados", [])],
        scrap_kg=_f(orden.kg_scrap), registro=orden.creado_por, paradas=orden.paradas or 0,
        observacion=orden.observacion or "", anulada=orden.estado == "anulada")


def guardar_pdfs_lamina(uow: UnidadDeTrabajo, orden: OrdenTrabajo, generador: GeneradorDocumentos,
                        usuario: str) -> None:
    datos = orden_lamina(uow, orden)
    uow.archivos.guardar("orden_trabajo", orden.id, NOMBRES["orden"], generador.orden_lamina(datos),
                         tipo_mime="application/pdf", usuario=usuario)
    uow.archivos.guardar("orden_trabajo", orden.id, NOMBRES["etiquetas"], generador.etiquetas_lamina(datos),
                         tipo_mime="application/pdf", usuario=usuario)


def pdf_lamina(uow: UnidadDeTrabajo, orden: OrdenTrabajo, doc: str, generador: GeneradorDocumentos, *,
               atados: list[int] | None = None, regenerar: bool = False) -> bytes:
    if not atados and not regenerar and orden.estado != "anulada":
        guardado = uow.archivos.buscar("orden_trabajo", orden.id, NOMBRES[doc])
        if guardado:
            return guardado
    datos = orden_lamina(uow, orden)
    if doc == "orden":
        return generador.orden_lamina(datos)
    elegidos = [a for a in datos.atados if a.atado in atados] if atados else None
    return generador.etiquetas_lamina(datos, elegidos)


def orden_maquila(uow: UnidadDeTrabajo, orden: OrdenTrabajo) -> OrdenMaquilaImpresa:
    primero = uow.piezas.obtener(orden.pieza_id) if orden.pieza_id else None
    d = orden.detalle or {}
    return OrdenMaquilaImpresa(
        numero=orden.numero, fecha=orden.fecha.strftime("%d/%m/%Y") if orden.fecha else "—", dueno=orden.propietario_nombre,
        flejes=[FlejeImpreso(f["codigo"], _f(f["kg"])) for f in d.get("flejes", [])],
        tipo_codigo=(primero.tipo_acero_codigo or "") if primero else "",
        tipo_nombre=(primero.tipo_acero_nombre or "") if primero else "", norma=(primero.norma_nombre or "") if primero else "",
        espesor=_f(primero.espesor_mm if primero else 0), consumido=_f(orden.kg_consumido), scrap_kg=_f(orden.kg_scrap),
        kg_por_pieza=_f(d.get("kg_por_pieza")), kg_teorico=_f(d["kg_teorico"]) if d.get("kg_teorico") else None,
        grupos=[GrupoImpreso(g["clase"], g.get("calidad") or "", g["codigo_producto"], g["descripcion"],
                             int(g["unidades"]), _f(g["kg"])) for g in d.get("grupos", [])],
        paquetes=[AtadoImpreso(int(x["paquete"]), int(x["unidades"]), _f(x["kg"]), x["codigo"]) for x in d.get("paquetes", [])],
        registro=orden.creado_por, paradas=orden.paradas or 0, observacion=orden.observacion or "",
        anulada=orden.estado == "anulada")


def guardar_pdfs_maquila(uow: UnidadDeTrabajo, orden: OrdenTrabajo, generador: GeneradorDocumentos,
                         usuario: str) -> None:
    datos = orden_maquila(uow, orden)
    uow.archivos.guardar("orden_trabajo", orden.id, NOMBRES["orden"], generador.orden_maquila(datos),
                         tipo_mime="application/pdf", usuario=usuario)
    uow.archivos.guardar("orden_trabajo", orden.id, NOMBRES["etiquetas"], generador.etiquetas_maquila(datos),
                         tipo_mime="application/pdf", usuario=usuario)


def pdf_maquila(uow: UnidadDeTrabajo, orden: OrdenTrabajo, doc: str, generador: GeneradorDocumentos, *,
                paquetes: list[int] | None = None, regenerar: bool = False) -> bytes:
    if not paquetes and not regenerar and orden.estado != "anulada":
        guardado = uow.archivos.buscar("orden_trabajo", orden.id, NOMBRES[doc])
        if guardado:
            return guardado
    datos = orden_maquila(uow, orden)
    if doc == "orden":
        return generador.orden_maquila(datos)
    elegidos = [p for p in datos.paquetes if p.atado in paquetes] if paquetes else None
    return generador.etiquetas_maquila(datos, elegidos)


def hoja_trabajo(uow: UnidadDeTrabajo, orden: OrdenTrabajo) -> HojaTrabajo:
    """La hoja de la OC planificada: las piezas que entran (con su saldo de ahora) y lo pedido."""
    from app.servicios.planificacion import piezas_del_plan

    piezas: list[PiezaHoja] = []
    for pid in piezas_del_plan(orden):
        p = uow.piezas.obtener(pid)
        if p is None:
            continue
        norma = uow.catalogos.norma(p.norma_id) if p.norma_id else None
        piezas.append(PiezaHoja(p.codigo_fisico, p.descripcion or "", p.espesor_mm, p.ancho_mm, p.saldo_kg,
                                norma.nombre if norma else None, p.tipo_acero_nombre))
    return HojaTrabajo(orden.id, orden.tipo, orden.numero, orden.fecha, orden.propietario_nombre or "", piezas,
                       (orden.detalle or {}).get("plan", {}), orden.calidad, orden.observacion, orden.creado_por,
                       anulada=orden.estado == "anulada")


def orden_slitter_planificada(uow: UnidadDeTrabajo, orden: OrdenTrabajo) -> OrdenSlitterImpresa:
    """Slitter planificado: la misma Orden de Slitter aprobada, con los rollos y kg calculados para el
    corte total de la bobina. El operador solo firma; la asistente registra los resultados en la app
    y ahí se generan los flejes (decisión del 11 nov 2026)."""
    bobina = uow.piezas.obtener(orden.pieza_id) if orden.pieza_id else None
    plan = (orden.detalle or {}).get("plan", {})
    if bobina is None or not bobina.ancho_mm or not bobina.espesor_mm or not bobina.tipo_acero_codigo:
        raise ValueError("la bobina no tiene ancho, espesor o tipo de acero")
    cortes_in = [slitter.CorteIn(Decimal(c["ancho_mm"]), int(c["rollos"]), None, orden.calidad) for c in plan.get("cortes", [])]
    calculo = slitter.planificar(bobina.ancho_mm, bobina.saldo_kg, cortes_in,
                                 scrap_ancho_mm=Decimal(plan.get("scrap_ancho_mm") or "0"))
    cortes: list[CorteImpreso] = []
    rollos: list[RolloImpreso] = []
    for c in calculo.cortes:
        cod = codigos.codigo_producto("fleje", bobina.tipo_acero_codigo, bobina.espesor_mm, c.ancho_mm)
        cortes.append(CorteImpreso(c.posicion, float(c.ancho_mm), c.rollos, float(c.kg), cod,
                                   slitter.descripcion_fleje(bobina.tipo_acero_codigo, bobina.espesor_mm, c.ancho_mm)))
        for i, kg in enumerate(c.kg_rollos, start=1):
            codigo = slitter.codigo_rollo(cod, bobina.codigo_fisico, orden.numero, c.posicion, i)
            rollos.append(RolloImpreso(codigo, f"{c.posicion}-{slitter.LETRAS[i - 1]}", float(kg), c.posicion,
                                       c.calidad))
    return OrdenSlitterImpresa(
        numero=orden.numero, fecha=orden.fecha.strftime("%d/%m/%Y") if orden.fecha else "—",
        bobina=bobina.codigo_fisico, producto=bobina.codigo_producto or "", descripcion=bobina.descripcion or "",
        tipo_codigo=bobina.tipo_acero_codigo, tipo_nombre=bobina.tipo_acero_nombre or "", norma=bobina.norma_nombre or "",
        espesor=_f(bobina.espesor_mm), ancho=_f(bobina.ancho_mm), peso_entrada=_f(bobina.peso_entrada_kg),
        consumido=_f(bobina.saldo_kg), dueno=orden.propietario_nombre, estatus="Total", calidad=orden.calidad or "",
        cortes=cortes, scrap_ancho=_f(calculo.scrap_ancho_mm), scrap_kg=_f(calculo.scrap_kg), rollos=rollos,
        registro=orden.creado_por, observacion=orden.observacion or "", anulada=orden.estado == "anulada")
