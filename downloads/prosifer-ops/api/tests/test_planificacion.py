"""OC planificada (hoja de trabajo antes del corte) con el adaptador en memoria."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.dominio import entidades as e
from app.errores import ErrorNegocio
from app.esquemas import NotaEntregaIn, PlanOtIn
from app.servicios import ordenes, planificacion, salidas
from tests.test_casos_uso import _uow
from tests.test_laminas import _entrada, _ot
from tests.test_perfiles import VIG, _flejes, _maquila

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 11)


def _plan(u, **datos):
    return planificacion.planificar(u, PlanOtIn(fecha=HOY, **datos), **U)


def test_lamina_planificada_bloquea_la_bobina_y_se_ejecuta_con_el_mismo_numero():
    u, hyms, _ = _uow()
    u.parametros.valores["ultima_oc_lamina"] = "1085"
    pid = _entrada(u, hyms, codigo="B1085", peso="6844", ancho="1250", espesor=D("1.1")).pieza_id
    p = _plan(u, tipo="lamina", pieza_id=pid, largo_mm=D("2400"))
    assert p.numero == 1086
    o = u.ordenes.obtener(p.orden_id)
    assert o.estado == "planificada" and o.detalle["plan"]["codigo_producto"] == "LAMHP11012502400"
    assert o.detalle["plan"]["por_atado"] == 96 and o.detalle["plan"]["laminas_estimadas"] == 264   # 25,905 kg c/u
    assert u.piezas.obtener(pid).saldo_kg == D("6844")                       # no mueve inventario

    with pytest.raises(ErrorNegocio, match="en proceso en la OC laminadora 1086"):
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": pid, "kg": "100"}],
                                              confirmar=True), **U)
    with pytest.raises(ErrorNegocio, match="en proceso"):
        _plan(u, tipo="lamina", pieza_id=pid, largo_mm=D("2000"))
    with pytest.raises(ErrorNegocio, match="en proceso"):
        _ot(u, pid, atados=[100])                                             # sin el plan no se puede

    hecha = _ot(u, pid, atados=[100, 100, 64], orden_planificada_id=p.orden_id)
    assert hecha.numero == 1086 and not any("ya existe" in a for a in hecha.avisos)
    plan = u.ordenes.obtener(p.orden_id)
    assert plan.estado == "ejecutada" and plan.detalle["orden_resultado_id"] == hecha.orden_id
    assert planificacion.en_proceso(u, pid) is None
    assert ordenes.siguiente_numero(u, "lamina") == 1087


def test_anular_la_planificacion_libera_la_pieza():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, codigo="B2", peso="2000", ancho="1200", espesor=D("0.7")).pieza_id
    p = _plan(u, tipo="ctf", pieza_id=pid, largo_mm=D("2440"))
    ordenes.anular(u, p.orden_id, "se cambió el pedido", **U)
    assert u.ordenes.obtener(p.orden_id).estado == "anulada" and planificacion.en_proceso(u, pid) is None
    assert _ot(u, pid, atados=[50]).numero      # ya se puede cortar sin plan


def test_maquila_planificada_con_varios_flejes():
    u, hyms, _ = _uow()
    u.catalogos.productos[VIG] = e.ProductoCatalogo(1, VIG, "Perfil LC Vigueta 2'' x 1'' x 2,00mm x 6,00mts", D("8.478"))
    fl = _flejes(u, hyms, 2)
    p = _plan(u, tipo="maquila", flejes=fl, codigo_producto=VIG)
    plan = u.ordenes.obtener(p.orden_id).detalle["plan"]
    assert plan["flejes"] == fl and plan["descripcion"].startswith("Perfil LC Vigueta") and plan["perfiles_estimados"]
    with pytest.raises(ErrorNegocio, match="en proceso"):
        _maquila(u, fl[1:], paquetes=[10])
    hecha = _maquila(u, fl, paquetes=[200, 200], orden_planificada_id=p.orden_id)
    assert hecha.numero == p.numero and u.ordenes.obtener(p.orden_id).estado == "ejecutada"


def test_slitter_planificado_valida_los_anchos():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, codigo="B3", peso="8235", ancho="1200").pieza_id
    with pytest.raises(ErrorNegocio, match="suman 1340"):
        _plan(u, tipo="slitter", pieza_id=pid, cortes=[{"ancho_mm": "268", "rollos": 5}])
    p = _plan(u, tipo="slitter", pieza_id=pid, cortes=[{"ancho_mm": "268", "rollos": 4}, {"ancho_mm": "125", "rollos": 1}])
    plan = u.ordenes.obtener(p.orden_id).detalle["plan"]
    assert plan["scrap_ancho_mm"] == "3" and len(plan["cortes"]) == 2
    with pytest.raises(ErrorNegocio, match="entran"):
        _plan(u, tipo="maquila", flejes=[pid], codigo_producto=VIG)        # una bobina no entra a maquila


def test_hojas_de_trabajo_en_pdf():
    from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
    from app.servicios import impresion
    u, hyms, _ = _uow()
    u.catalogos.productos[VIG] = e.ProductoCatalogo(1, VIG, "Perfil LC Vigueta 2'' x 1'' x 2,00mm x 6,00mts", D("8.478"))
    fl = _flejes(u, hyms, 3)
    pid = _entrada(u, hyms, codigo="B9", peso="5000", ancho="1220", espesor=D("2")).pieza_id
    pid2 = _entrada(u, hyms, codigo="B10", peso="5000", ancho="1220", espesor=D("2")).pieza_id
    planes = [_plan(u, tipo="maquila", flejes=fl, codigo_producto=VIG, observacion="Prioridad alta"),
              _plan(u, tipo="lamina", pieza_id=pid, largo_mm=D("2400")),
              _plan(u, tipo="slitter", pieza_id=pid2, cortes=[{"ancho_mm": "300", "rollos": 4}])]
    g = GeneradorReportlab()
    for p in planes:
        pdf = g.hoja_trabajo(impresion.hoja_trabajo(u, u.ordenes.obtener(p.orden_id)))
        assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r") <= 1


def test_slitter_planificado_usa_la_orden_aprobada():
    from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
    from app.servicios import impresion
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, codigo="C22600728510", peso="8235", ancho="1200").pieza_id
    p = _plan(u, tipo="slitter", pieza_id=pid, cortes=[{"ancho_mm": "268", "rollos": 4}, {"ancho_mm": "125", "rollos": 1}])
    o = impresion.orden_slitter_planificada(u, u.ordenes.obtener(p.orden_id))
    assert len(o.rollos) == 5 and o.rollos[0].posicion == "1-A" and o.rollos[0].codigo.endswith(f"OC{p.numero} / 1-A")
    assert abs(sum(r.kg for r in o.rollos) + o.scrap_kg - 8235) < 0.01          # todo el saldo, como un corte total
    assert GeneradorReportlab().orden_slitter(o).startswith(b"%PDF")


def test_maquila_toma_el_largo_del_perfil():
    u, hyms, _ = _uow()
    u.catalogos.productos[VIG] = e.ProductoCatalogo(1, VIG, "Perfil LC Vigueta 2'' x 1'' x 2,00mm x 6,00mts", D("8.478"))
    p = _plan(u, tipo="maquila", flejes=_flejes(u, hyms, 1), codigo_producto=VIG)
    assert u.ordenes.obtener(p.orden_id).detalle["plan"]["largo_mm"] == "6000.00"

