"""Solicitud de orden de corte del cliente: revisión, autorización con cambios y rechazo (memoria)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.dominio import entidades as e
from app.errores import ErrorNegocio
from app.esquemas import AprobacionSolicitudIn, SolicitudCorteIn
from app.servicios import planificacion, solicitudes
from tests.test_casos_uso import _uow
from tests.test_laminas import _entrada
from tests.test_perfiles import VIG, _flejes

U = dict(usuario="asistente", origen="interfaz")
HOY = dt.date(2026, 11, 12)


def _pide(u, cliente, **datos):
    return solicitudes.crear(u, SolicitudCorteIn(fecha=HOY, **datos), cliente=cliente.id,
                             usuario="compras@acerosvalle.test", origen="portal")


def test_la_solicitud_no_es_orden_hasta_que_prosifer_la_autoriza():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, codigo="B501", peso="8235", ancho="1200").pieza_id
    d = _pide(u, hyms, tipo="slitter", pieza_id=pid, cortes=[{"ancho_mm": "268", "cortes": 4}],
              corte_total=False, peso_max_kg="5000", peso_max_rollo_kg="1500", embalaje="ojo_al_cielo",
              comentarios="Urgente para el lunes")
    assert d.estado == "pendiente" and d.numero == "1"
    t = d.encabezado["texto"]
    assert "4 × 268 mm" in t and "hasta 5.000 kg" in t and "ojo al cielo" in t and "Urgente" in t
    assert planificacion.en_proceso(u, pid) is None                 # todavía no aparta la bobina
    assert u.ordenes.planificadas() == []
    with pytest.raises(ErrorNegocio, match="ya está en la solicitud 1"):
        _pide(u, hyms, tipo="lamina", pieza_id=pid, largo_mm="2400")

    # Prosifer la autoriza cambiando lo pedido: 3 cortes de 268 y uno de 300
    out = solicitudes.aprobar(u, d.id, AprobacionSolicitudIn(
        tipo="slitter", fecha=HOY, pieza_id=pid, cortes=[{"ancho_mm": "268", "rollos": 3}, {"ancho_mm": "300", "rollos": 1}],
        observacion=t), **U)
    o = u.ordenes.obtener(out.orden_id)
    assert o.estado == "planificada" and o.detalle["plan"]["solicitud_numero"] == "1"
    assert planificacion.en_proceso(u, pid) is not None              # ahora sí, en proceso
    s = u.documentos.obtener(d.id)
    assert s.estado == "aprobada" and s.encabezado["orden_numero"] == out.numero
    with pytest.raises(ErrorNegocio, match="ya se revisó"):
        solicitudes.rechazar(u, d.id, "tarde", **U)


def test_rechazo_y_cancelacion():
    u, hyms, otro = _uow()
    pid = _entrada(u, hyms, codigo="B503", peso="6844", ancho="1250", espesor=D("1.1")).pieza_id
    d = _pide(u, hyms, tipo="lamina", pieza_id=pid, largo_mm="2400", corte_total=False, cantidad_laminas=300)
    assert "cortar 300 láminas" in d.encabezado["texto"]
    with pytest.raises(ErrorNegocio, match="no está en tu inventario"):
        _pide(u, otro, tipo="lamina", pieza_id=pid, largo_mm="2400")
    with pytest.raises(ErrorNegocio, match="solicitud inexistente"):
        solicitudes.cancelar(u, d.id, "no era mía", cliente=otro.id, **U)
    r = solicitudes.rechazar(u, d.id, "la laminadora está en mantenimiento esta semana", **U)
    assert r.estado == "rechazada" and "mantenimiento" in r.encabezado["motivo"]
    d2 = _pide(u, hyms, tipo="lamina", pieza_id=pid, largo_mm="2000")       # otra vez libre para pedir
    solicitudes.cancelar(u, d2.id, "ya no la necesito", cliente=hyms.id, **U)
    assert u.documentos.obtener(d2.id).estado == "cancelada"


def test_maquila_y_validaciones():
    u, hyms, _ = _uow()
    u.catalogos.productos[VIG] = e.ProductoCatalogo(1, VIG, "Perfil LC Vigueta 2'' x 1'' x 2,00mm x 6,00mts", D("8.478"))
    fl = _flejes(u, hyms, 2)
    d = _pide(u, hyms, tipo="maquila", flejes=fl, codigo_producto=VIG, descripcion="Perfil LC Vigueta 2'' x 1''")
    assert d.encabezado["piezas"] == fl
    with pytest.raises(ErrorNegocio, match="aquí va un bobina"):
        _pide(u, hyms, tipo="slitter", pieza_id=fl[0], cortes=[{"ancho_mm": "50", "cortes": 1}])
    pid = _entrada(u, hyms, codigo="B504").pieza_id
    with pytest.raises(ErrorNegocio, match="indica cuántos kg"):
        _pide(u, hyms, tipo="slitter", pieza_id=pid, cortes=[{"ancho_mm": "300", "cortes": 2}], corte_total=False)
    out = solicitudes.aprobar(u, d.id, AprobacionSolicitudIn(tipo="maquila", fecha=HOY, flejes=fl, codigo_producto=VIG), **U)
    assert u.ordenes.obtener(out.orden_id).detalle["plan"]["flejes"] == fl
