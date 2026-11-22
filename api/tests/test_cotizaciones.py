"""Cotizaciones en USD: emitir, abonar, anular y el borrador desde una orden de corte."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.dominio import entidades as e
from app.errores import ErrorNegocio
from app.esquemas import AbonoCotizacion, CotizacionIn
from app.servicios import cotizaciones
from importador import cotizaciones_excel as cx
from tests.test_existencias import U, _uow

HOY = dt.date(2026, 11, 14)


def test_emitir_abonar_y_anular():
    u, hyms, _ = _uow()
    d = cotizaciones.crear(u, CotizacionIn(tercero_id=hyms.id, fecha=HOY, renglones=[
        {"codigo": "serviciocargaymanejo0001", "descripcion": "Servicio de Carga y Manejo", "cantidad": "57744",
         "unidad": "Kg", "precio_unitario": "0.04"},
        {"descripcion": "Servicio de Almacenamiento (Planta Valencia)", "cantidad": 1, "unidad": "Servicio",
         "precio_unitario": "181.82"}], notas="Periodo de facturación: septiembre"), **U)
    assert d.numero == "2939" and d.encabezado["renglones"][0]["codigo"] == "SERVICIOCARGAYMANEJO0001"
    t = cotizaciones.calcular(d.encabezado)
    assert t["subtotal"] == D("2491.58") and t["total"] == D("2491.58") and t["saldo"] == D("2491.58")
    d = cotizaciones.abonar(u, d.id, AbonoCotizacion(fecha=HOY, destino="Zelle", monto=D("2000")), **U)
    assert cotizaciones.calcular(d.encabezado)["saldo"] == D("491.58")
    with pytest.raises(ErrorNegocio, match="pasa el total"):
        cotizaciones.abonar(u, d.id, AbonoCotizacion(destino="Caja USD", monto=D("500")), **U)
    a = cotizaciones.anular(u, d.id, "el cliente pidió rehacerla", **U)
    assert a.anulado and a.encabezado["motivo_anulacion"].startswith("el cliente")
    assert cotizaciones.crear(u, CotizacionIn(tercero_id=hyms.id, fecha=HOY, renglones=[
        {"descripcion": "x", "cantidad": 1, "precio_unitario": 0}], iva_pct=16), **U).numero == "2940"


def test_borrador_desde_orden_de_slitter():
    u, hyms, _ = _uow()
    hp = u.catalogos.tipos.get("HP") if hasattr(u.catalogos, "tipos") else None
    bob = u.piezas.agregar(e.Pieza(None, "bobina", "C77", hyms.id, D("8235"), D("8235"), "disponible", "x",
                                   tipo_acero_id=hp.id if hp else None))
    o = u.ordenes.agregar(e.OrdenTrabajo(None, "slitter", 501, "ejecutada", D("8235"), D("8200"), D("35"), "interfaz", "x",
                                         pieza_id=bob.id, propietario_id=hyms.id))
    b = cotizaciones.borrador_desde_orden(u, o.id)
    assert b.tercero_id == hyms.id and b.orden == "OC slitter 501"
    r = b.renglones[0]
    assert r.codigo.startswith("SERVICIOCORTESLITTER") and r.cantidad == D("8235.00") and r.unidad == "Kg"
    assert b.notas == "Bobina: C77"


def test_borrador_de_maquila_lleva_el_perfil_y_el_primer_fleje():
    u, hyms, _ = _uow()
    f1 = u.piezas.agregar(e.Pieza(None, "fleje", "C77-2", hyms.id, D("500"), D("500"), "disponible", "x"))
    f2 = u.piezas.agregar(e.Pieza(None, "fleje", "C77-3", hyms.id, D("500"), D("500"), "disponible", "x"))
    o = u.ordenes.agregar(e.OrdenTrabajo(None, "maquila", 320, "planificada", D(0), D(0), D(0), "interfaz", "x",
                                         pieza_id=f1.id, propietario_id=hyms.id,
                                         detalle={"plan": {"flejes": [f1.id, f2.id], "codigo_producto": "PERHP0901010L06000",
                                                           "descripcion": "Perfil vigueta 1x1 0,90 x 6m"}}))
    b = cotizaciones.borrador_desde_orden(u, o.id)
    assert b.notas == "Producto: PERHP0901010L06000 Perfil vigueta 1x1 0,90 x 6m · Fleje: C77-2 (+1 más)"
    assert b.renglones[0].cantidad == D("1000.00")


def test_lee_una_fila_del_excel():
    fila = [None] * 100
    fila[0:6] = [2941, "Aceros del Valle, C.A.", "SERVICIOCARGAYMANEJO0001", "57.744", "Kg",
                 "Servicio de Carga y Manejo"]
    fila[31], fila[32:35] = "13 de noviembre de 2026", ["13-11", "Zelle", "100"]
    fila[57], fila[64], fila[92] = 0.040000000000000036, 2309.76, "R.O."
    q = cx.cotizacion_de_fila(5, tuple(fila))
    assert q.numero == "2941" and q.fecha == dt.date(2026, 11, 13) and q.vendedor == "R.O."
    assert q.renglones[0].precio == D("0.04") and q.renglones[0].total == D("2309.76")
    assert q.abonos == [{"fecha": "13-11", "destino": "Zelle", "monto": "100"}]


def test_vista_previa_idempotencia_y_pago_con_referencia():
    u, hyms, otro = _uow()
    base = dict(tercero_id=hyms.id, fecha=HOY, renglones=[{"descripcion": "Lamina L.C. 8,00mm", "cantidad": 5,
                                                          "unidad": "Pza", "precio_unitario": "229.15"}])
    previa = cotizaciones.crear(u, CotizacionIn(**base, confirmar=False), **U)
    assert previa.id is None and previa.numero == "2939"
    assert cotizaciones.vista(previa, "HYMS").total == D("1145.75")
    pago = {"fecha": "2026-11-14", "destino": "Binance", "monto": "1145.75", "referencia": "464772051928145922"}
    d = cotizaciones.crear(u, CotizacionIn(**base, abonos=[pago], clave_idempotencia="wa-123"), **U)
    assert d.numero == "2939" and cotizaciones.calcular(d.encabezado)["saldo"] == D("0.00")
    otra_vez = cotizaciones.crear(u, CotizacionIn(**base, abonos=[pago], clave_idempotencia="wa-123"), **U)
    assert otra_vez.id == d.id                                  # el doble 👍 no emite otra
    e2 = cotizaciones.crear(u, CotizacionIn(**base), **U)
    with pytest.raises(ErrorNegocio, match="ya está anotado en la cotización D-2939"):
        cotizaciones.abonar(u, e2.id, AbonoCotizacion(destino="Binance", monto=D("10"), referencia="464772051928145922"), **U)


def test_planificar_en_vista_previa_no_guarda_y_la_clave_no_duplica():
    from app.esquemas import PlanOtIn
    from app.servicios import planificacion
    u, hyms, _ = _uow()
    bob = u.piezas.agregar(e.Pieza(None, "bobina", "CS222505100011C051A-2", hyms.id, D("5822"), D("5822"), "disponible",
                                   "x", espesor_mm=D("1.1"), ancho_mm=D("1250")))
    datos = dict(tipo="slitter", fecha=HOY, pieza_id=bob.id, cortes=[{"ancho_mm": "600", "rollos": 2}])
    previa = planificacion.planificar(u, PlanOtIn(**datos, confirmar=False), **U)
    assert not previa.guardada and previa.orden_id is None and previa.piezas[0]["codigo"] == "CS222505100011C051A-2"
    assert u.ordenes.planificadas() == []
    a = planificacion.planificar(u, PlanOtIn(**datos, clave_idempotencia="wa-9"), **U)
    b = planificacion.planificar(u, PlanOtIn(**datos, clave_idempotencia="wa-9"), **U)
    assert a.orden_id == b.orden_id and len(u.ordenes.planificadas()) == 1
