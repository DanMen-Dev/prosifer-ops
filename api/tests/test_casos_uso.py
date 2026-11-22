"""Casos de uso con el adaptador en memoria: las mismas reglas que en producción, sin PostgreSQL.

Es la ventaja de la arquitectura hexagonal: el núcleo no sabe qué base de datos hay detrás.
"""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.adaptadores.memoria import UnidadMemoria
from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.errores import ErrorNegocio
from app.esquemas import EntradaBobinaIn, LiberacionIn, NotaEntregaIn, OtSlitterIn
from app.servicios import impresion, inventario, ordenes, salidas

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 8)


def _uow():
    u = UnidadMemoria()
    hyms = u.terceros.nuevo("Aceros del Valle, C.A.")
    otro = u.terceros.nuevo("Laminados Norte, C.A.")
    return u, hyms, otro


def _entrada(u, dueno, codigo="C22600728510", peso="8235", ancho="1200", confirmar=True, **extra):
    return inventario.registrar_entrada_bobina(u, EntradaBobinaIn(
        documento_numero="NE-07082026", fecha=HOY, codigo_bobina=codigo, tipo_acero="LAM FRIO", espesor_mm=D("0.9"),
        ancho_mm=D(ancho), peso_kg=D(peso), propietario_id=dueno.id, confirmar=confirmar, **extra), **U)


def _slitter(u, pid, confirmar=True, **extra):
    datos = dict(pieza_id=pid, fecha=HOY, estatus_corte="total", calidad="1er-F", scrap_ancho_mm=D("8"),
                 cortes=[{"ancho_mm": D("268"), "rollos": 4}, {"ancho_mm": D("90"), "rollos": 1},
                         {"ancho_mm": D("30"), "rollos": 1}], confirmar=confirmar)
    datos.update(extra)
    return ordenes.registrar_slitter(u, OtSlitterIn(**datos), generador=GeneradorReportlab(), **U)


def test_entrada_con_revision_y_codigo_unico():
    u, hyms, _ = _uow()
    previa = _entrada(u, hyms, confirmar=False)
    assert previa.guardada is False and previa.codigo_producto == "BOBHP0901200"
    assert u.piezas.t.filas == {}
    r = _entrada(u, hyms)
    p = u.piezas.obtener(r.pieza_id)
    assert p.saldo_kg == D("8235") and p.estado == "disponible" and p.propietario_nombre.startswith("Aceros")
    with pytest.raises(ErrorNegocio):
        _entrada(u, hyms, codigo="c22600728510")  # mismo código, otra mayúscula


def test_entrada_idempotente():
    u, hyms, _ = _uow()
    a = _entrada(u, hyms, clave_idempotencia="n8n-1")
    b = _entrada(u, hyms, clave_idempotencia="n8n-1")
    assert a.pieza_id == b.pieza_id and len(u.piezas.t.filas) == 1


def test_slitter_crea_rollos_y_pdf():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms).pieza_id
    r = _slitter(u, pid)
    assert r.guardada and r.numero == 1 and r.kg_producido == D("8180.100")
    bobina = u.piezas.obtener(pid)
    assert bobina.saldo_kg == 0 and bobina.estado == "agotado"
    flejes = u.piezas.producidas_por(r.orden_id)
    assert len(flejes) == 6
    assert flejes[0].codigo_fisico == "FLEHP0900268 / C22600728510 / OC1 / 1-A"
    assert flejes[0].saldo_kg == D("1839.150") and flejes[0].pieza_origen_id == pid
    # Las copias de la hoja y las etiquetas quedan guardadas al crear la orden
    assert u.archivos.buscar("orden_trabajo", r.orden_id, "orden.pdf").startswith(b"%PDF")
    datos = impresion.orden_slitter(u, u.ordenes.obtener(r.orden_id))
    assert [x.posicion for x in datos.rollos] == ["1-A", "1-B", "1-C", "1-D", "2-A", "3-A"]
    assert datos.dueno.startswith("Aceros") and datos.scrap_ancho == 8


def test_slitter_parcial_y_errores():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, peso="10000", ancho="1220").pieza_id
    r = _slitter(u, pid, estatus_corte="parcial", kg_procesado=D("4000"), scrap_ancho_mm=D("20"),
                 cortes=[{"ancho_mm": D("600"), "rollos": 2}])
    assert r.saldo_restante_kg == D("6000") and u.piezas.obtener(pid).estado == "disponible"
    with pytest.raises(ErrorNegocio):  # los anchos pasan el de la bobina
        _slitter(u, pid, confirmar=False, cortes=[{"ancho_mm": D("700"), "rollos": 2}])
    with pytest.raises(ErrorNegocio):  # parcial sin kg
        _slitter(u, pid, confirmar=False, estatus_corte="parcial")


def test_anular_oc_devuelve_kg_solo_si_nada_se_movio():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms).pieza_id
    r = _slitter(u, pid)
    ordenes.anular(u, r.orden_id, "prueba", **U)
    assert u.piezas.obtener(pid).saldo_kg == D("8235")
    assert all(p.anulada for p in u.piezas.producidas_por(r.orden_id))
    assert u.ordenes.obtener(r.orden_id).estado == "anulada"

    r2 = _slitter(u, pid)
    fleje = u.piezas.producidas_por(r2.orden_id)[0]
    inventario.registrar_movimiento(u, fleje.id, "salida", -D("100"), **U)
    with pytest.raises(ErrorNegocio):
        ordenes.anular(u, r2.orden_id, "no debe poder", **U)


def test_nota_entrega_numerada_y_parcial_sin_limite():
    u, hyms, otro = _uow()
    a = _entrada(u, hyms, codigo="A1", peso="5000").pieza_id
    b = _entrada(u, hyms, codigo="B1", peso="3000").pieza_id
    datos = dict(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": a, "kg": D("1200")}, {"pieza_id": b}])
    previa = salidas.nota_entrega(u, NotaEntregaIn(**datos, confirmar=False), **U)
    assert previa.numero.startswith("7225") and previa.total_kg == D("4200")
    hecha = salidas.nota_entrega(u, NotaEntregaIn(**datos, confirmar=True), **U)
    assert hecha.numero == "7225"
    assert u.piezas.obtener(a).saldo_kg == D("3800") and u.piezas.obtener(b).estado == "agotado"
    otra = salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": a, "kg": D("1000")}],
                                                 confirmar=True), **U)
    assert otra.numero == "7226" and u.piezas.obtener(a).saldo_kg == D("2800")
    with pytest.raises(ErrorNegocio):  # pieza de otro dueño
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=otro.id, lineas=[{"pieza_id": a}]), **U)
    with pytest.raises(ErrorNegocio):  # más kg de los que hay
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": a, "kg": D("9000")}]), **U)

    salidas.anular(u, hecha.documento_id, "nota cargada por error", **U)
    assert u.piezas.obtener(a).saldo_kg == D("4000") and u.piezas.obtener(b).saldo_kg == D("3000")


def test_liberacion_completa_y_anulacion():
    u, hyms, otro = _uow()
    a = _entrada(u, hyms, codigo="L1", peso="5000").pieza_id
    lib = salidas.liberacion(u, LiberacionIn(numero="L-9", fecha=HOY, propietario_actual_id=hyms.id,
                                             propietario_nuevo_id=otro.id, piezas=[a], confirmar=True), **U)
    p = u.piezas.obtener(a)
    assert p.propietario_id == otro.id and p.saldo_kg == D("5000")
    with pytest.raises(ErrorNegocio):  # ya no es de HYMS
        salidas.liberacion(u, LiberacionIn(numero="L-10", fecha=HOY, propietario_actual_id=hyms.id,
                                           propietario_nuevo_id=otro.id, piezas=[a]), **U)
    salidas.anular(u, lib.documento_id, "error de dueño", **U)
    assert u.piezas.obtener(a).propietario_id == hyms.id


def test_ajuste_y_edicion_auditados():
    u, hyms, _ = _uow()
    a = _entrada(u, hyms, codigo="R1", peso="500").pieza_id
    mv = salidas.ajustar(u, a, D("0"), "remanente que no existe en patio", fecha=None, **U)
    assert mv.kg == D("-500") and u.piezas.obtener(a).estado == "agotado"
    inventario.editar_pieza(u, a, {"buque": "MV Prueba"}, **U)
    assert u.piezas.obtener(a).buque == "MV Prueba"
    assert ("pieza", a, "buque", None, "MV Prueba", "prueba", "interfaz") in u.auditoria.registros
    with pytest.raises(ErrorNegocio):
        salidas.ajustar(u, a, D("0"), "otra vez lo mismo", fecha=None, **U)
