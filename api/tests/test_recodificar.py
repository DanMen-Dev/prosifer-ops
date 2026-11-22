"""Recodificar una existencia y unir dos existencias del mismo material (sin perder historial)."""
from decimal import Decimal as D

import pytest

from app.errores import ErrorNegocio
from app.servicios import inventario, salidas
from tests.test_existencias import U, _entrada, _uow

LC = "LAMHN25012002400"
OTRO = "LAMHP25012002400"


def _lam(u, dueno, codigo, n):
    return _entrada(u, dueno, codigo=codigo, unidades=n, descripcion="Lamina 2,50 x 1200 x 2400",
                    peso_unitario_kg=D("57.6")).pieza_id


def test_recodificar_existencia_cambia_codigo_y_medidas_por_dueno():
    u, hyms, otro = _uow()
    pid = _lam(u, hyms, OTRO, 155)
    _lam(u, otro, LC, 3)                                   # el mismo código en otro dueño no estorba
    p = inventario.editar_pieza(u, pid, {"codigo_fisico": "lamhn25012002400"}, **U)
    assert p.codigo_fisico == LC and p.codigo_producto == LC and p.saldo_unidades == 155
    assert (p.espesor_mm, p.ancho_mm, p.largo_mm) == (D("2.5"), D("1200"), D("2400"))
    with pytest.raises(ErrorNegocio, match="no es un código de lamina"):
        inventario.editar_pieza(u, pid, {"codigo_fisico": "TUB000HPE090A00001A00001L06000"}, **U)
    _lam(u, hyms, OTRO, 4)
    with pytest.raises(ErrorNegocio, match="únelas"):
        inventario.editar_pieza(u, pid, {"codigo_fisico": OTRO}, **U)


def test_unir_existencias_pasa_piezas_y_kg_y_se_puede_anular():
    u, hyms, otro = _uow()
    destino = _lam(u, hyms, LC, 4)
    origen = _lam(u, hyms, OTRO, 155)
    doc = inventario.unir_existencias(u, origen, destino, "mismo material, código equivocado", **U)
    a, b = u.piezas.obtener(origen), u.piezas.obtener(destino)
    assert (a.saldo_unidades, a.saldo_kg) == (0, D("0"))
    assert b.saldo_unidades == 159 and b.saldo_kg == D("9158.400")
    assert doc.tipo == "ajuste" and OTRO in doc.observacion
    salidas.anular(u, doc.id, "me equivoqué de existencia", **U)
    assert u.piezas.obtener(origen).saldo_unidades == 155 and u.piezas.obtener(destino).saldo_unidades == 4
    ajena = _lam(u, otro, LC, 1)
    with pytest.raises(ErrorNegocio, match="mismo dueño"):
        inventario.unir_existencias(u, ajena, destino, "no es suya", **U)
