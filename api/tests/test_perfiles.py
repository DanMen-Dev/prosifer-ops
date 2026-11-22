"""Maquila de perfiles con el adaptador en memoria: flejes del cliente → perfiles por paquetes."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.dominio import entidades as e
from app.errores import ErrorNegocio
from app.esquemas import OtMaquilaIn
from app.servicios import impresion, ordenes
from tests.test_casos_uso import _slitter, _uow
from tests.test_laminas import _entrada

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 10)
VIG = "PERHNVIG2006000"


def _flejes(u, dueno, n=3):
    pid = _entrada(u, dueno, peso="8235", ancho="1200").pieza_id
    r = _slitter(u, pid)
    return [p.id for p in u.piezas.producidas_por(r.orden_id)][:n]


def _maquila(u, flejes, confirmar=True, **extra):
    datos = dict(fecha=HOY, flejes=[{"pieza_id": f} for f in flejes], codigo_producto=VIG,
                 paquetes=[50] * 10 + [17], calidad="1er-C", confirmar=confirmar)
    datos.update(extra)
    return ordenes.registrar_maquila(u, OtMaquilaIn(**datos), generador=GeneradorReportlab(), **U)


def test_maquila_consume_flejes_y_suma_perfiles():
    u, hyms, _ = _uow()
    u.catalogos.productos[VIG] = e.ProductoCatalogo(1, VIG, "Perfil LC Vigueta 2'' x 1'' x 2,00mm x 6,00mts", D("8.478"))
    u.parametros.valores["ultima_oc_maquila"] = "318"
    fl = _flejes(u, hyms, 1)                      # un fleje de 268 mm: 1.839,15 kg
    previa = _maquila(u, fl, confirmar=False, paquetes=[50, 50], segunda_a=4, scrap_kg=D("10"))
    assert previa.numero == 319 and previa.total_perfiles == 104
    assert [g.codigo_producto for g in previa.grupos] == [VIG, VIG + "-A"]
    assert previa.paquetes[1].codigo == f"{VIG} / OC319 / PQ2"
    assert any("difieren" in a for a in previa.avisos)   # 17,59 kg por perfil frente a 8,478 teórico

    hecha = _maquila(u, fl, paquetes=[50, 50], segunda_a=4, scrap_kg=D("10"))
    assert u.piezas.obtener(fl[0]).estado == "agotado"
    primera = u.piezas.existencia("perfil", VIG, hyms.id)
    segunda = u.piezas.existencia("perfil", VIG + "-A", hyms.id)
    assert primera.saldo_unidades == 100 and segunda.saldo_unidades == 4
    assert primera.saldo_kg + segunda.saldo_kg + D("10") == D("1839.150")
    assert u.archivos.buscar("orden_trabajo", hecha.orden_id, "orden.pdf").startswith(b"%PDF")
    datos = impresion.orden_maquila(u, u.ordenes.obtener(hecha.orden_id))
    assert len(datos.flejes) == 1 and datos.total == 104

    ordenes.anular(u, hecha.orden_id, "cargada por error", **U)
    assert u.piezas.obtener(fl[0]).saldo_kg == D("1839.150") and u.piezas.obtener(primera.id).saldo_unidades == 0


def test_flejes_de_otro_dueno_o_que_no_son_flejes():
    u, hyms, otro = _uow()
    fl = _flejes(u, hyms, 2)
    bob = _entrada(u, otro, codigo="X1").pieza_id
    with pytest.raises(ErrorNegocio, match="solo entran flejes"):
        _maquila(u, [fl[0], bob], confirmar=False, descripcion="Perfil de prueba")
    with pytest.raises(ErrorNegocio, match="catálogo"):
        _maquila(u, fl, confirmar=False)            # sin catálogo ni descripción
    with pytest.raises(ErrorNegocio, match="primera"):
        _maquila(u, fl, confirmar=False, codigo_producto=VIG + "-A", descripcion="x")
    r = _maquila(u, fl, confirmar=False, descripcion="Perfil LC Vigueta de prueba")
    assert any("no está en el catálogo" in a for a in r.avisos) and r.kg_teorico is None
