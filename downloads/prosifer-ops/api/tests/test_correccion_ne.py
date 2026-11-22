"""Corregir una NE de la app: cantidad o producto, con el número intacto (adaptador en memoria)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.dominio.entidades import Documento
from app.errores import ErrorNegocio
from app.esquemas import CorreccionNEIn, NotaEntregaIn
from app.servicios import salidas
from tests.test_casos_uso import _entrada as entrada_bobina
from tests.test_existencias import _entrada, _uow

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 10)
OTRO = "TUB000HPE090A00002A00001L06000"


def _ne(u, dueno, lineas):
    return salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=dueno.id, lineas=lineas, confirmar=True), **U)


def _corregir(u, ne, cambios, confirmar=True):
    return salidas.corregir_nota(u, ne.documento_id, CorreccionNEIn(cambios=cambios, motivo="error de producto en patio",
                                                                    confirmar=confirmar), **U)


def _linea(u, ne):
    return salidas.lineas_vigentes(u, u.documentos.obtener(ne.documento_id))


def test_corregir_cantidad_y_producto_en_piezas():
    u, hyms, _ = _uow()
    a = _entrada(u, hyms, unidades=100).pieza_id                                  # 4,2 kg c/u
    b = _entrada(u, hyms, codigo=OTRO, unidades=50, descripcion="Tubo 2 x 1", peso_unitario_kg=D("6.31")).pieza_id
    ne = _ne(u, hyms, [{"pieza_id": a, "unidades": 30}])
    mv = _linea(u, ne)[0]

    previa = _corregir(u, ne, [{"movimiento_id": mv.id, "unidades": 25}], confirmar=False)
    assert previa.lineas[0].antes_unidades == 30 and previa.lineas[0].despues_unidades == 25
    _corregir(u, ne, [{"movimiento_id": mv.id, "unidades": 25}])
    assert u.piezas.obtener(a).saldo_unidades == 75
    vig = _linea(u, ne)
    assert [(-x.unidades, x.pieza_id) for x in vig] == [(25, a)]

    # Segunda corrección sobre la línea ya corregida: era el otro tubo
    _corregir(u, ne, [{"movimiento_id": vig[0].id, "pieza_id": b}])
    assert u.piezas.obtener(a).saldo_unidades == 100 and u.piezas.obtener(b).saldo_unidades == 25
    assert u.piezas.obtener(a).saldo_kg == D("420.000")
    doc = u.documentos.obtener(ne.documento_id)
    assert doc.numero == ne.numero and len(u.documentos.correcciones(doc.id)) == 2

    # Anular la NE deshace lo vigente (lo de la última corrección)
    salidas.anular(u, ne.documento_id, "no salió nada", **U)
    assert u.piezas.obtener(b).saldo_unidades == 50
    assert all(c.anulado for c in u.documentos.correcciones(doc.id))


def test_corregir_kg_de_un_fleje_o_bobina_y_validaciones():
    u, hyms, otro = _uow()
    pid = entrada_bobina(u, hyms, codigo="K1", peso="5000").pieza_id
    ne = _ne(u, hyms, [{"pieza_id": pid, "kg": D("1200")}])
    mv = _linea(u, ne)[0]
    _corregir(u, ne, [{"movimiento_id": mv.id, "kg": D("1150")}])
    assert u.piezas.obtener(pid).saldo_kg == D("3850")
    with pytest.raises(ErrorNegocio, match="no es una línea vigente"):
        _corregir(u, ne, [{"movimiento_id": mv.id, "kg": D("1000")}], confirmar=False)
    nueva = _linea(u, ne)[0]
    with pytest.raises(ErrorNegocio, match="no cambia nada"):
        _corregir(u, ne, [{"movimiento_id": nueva.id, "kg": D("1150")}], confirmar=False)
    with pytest.raises(ErrorNegocio, match="tiene"):
        _corregir(u, ne, [{"movimiento_id": nueva.id, "kg": D("6000")}], confirmar=False)
    ajena = entrada_bobina(u, otro, codigo="K2", peso="100").pieza_id
    with pytest.raises(ErrorNegocio, match="no del cliente"):
        _corregir(u, ne, [{"movimiento_id": nueva.id, "pieza_id": ajena}], confirmar=False)


def test_ne_del_historico_no_se_corrige_ni_anula():
    u, hyms, _ = _uow()
    h = u.documentos.agregar(Documento(None, "nota_entrega", numero="7129", fecha=HOY, tercero_id=hyms.id,
                                       origen="excel", creado_por="importador"))
    with pytest.raises(ErrorNegocio, match="solo de consulta"):
        salidas.corregir_nota(u, h.id, CorreccionNEIn(cambios=[{"movimiento_id": 1, "unidades": 1}],
                                                      motivo="no debe poder"), **U)
    with pytest.raises(ErrorNegocio, match="solo de consulta"):
        salidas.anular(u, h.id, "no debe poder", **U)
