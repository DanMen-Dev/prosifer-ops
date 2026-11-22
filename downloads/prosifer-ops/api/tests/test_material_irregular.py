"""Material de Medidas Irregulares (MATERIALESIRREG): sale en la NE solo por su peso, sin existencia."""
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from app.errores import ErrorNegocio
from app.esquemas import NotaEntregaIn
from app.servicios import salidas
from tests.test_existencias import HOY, TUBO, U, _entrada, _uow


def test_ne_solo_con_material_irregular_no_toca_inventario():
    u, hyms, _ = _uow()
    datos = dict(fecha=HOY, tercero_id=hyms.id, libres=[{"codigo": "materialesirreg", "kg": "1250.5", "detalle": "chatarra"}])
    previa = salidas.nota_entrega(u, NotaEntregaIn(**datos), **U)
    assert previa.total_kg == D("1250.500") and previa.lineas == []
    assert previa.libres[0].codigo == "MATERIALESIRREG"
    assert previa.libres[0].descripcion == "Material de Medidas Irregulares (chatarra)"
    r = salidas.nota_entrega(u, NotaEntregaIn(**datos, confirmar=True), **U)
    assert r.guardada and r.documento_id
    assert u.documentos.lineas(r.documento_id)[0]["kg"] == D("1250.500")


def test_ne_mixta_suma_piezas_y_material_irregular():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, unidades=100).pieza_id     # 100 x 4,2 kg
    r = salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": pid, "unidades": 10}],
                                              libres=[{"codigo": "MATERIALESIRREG", "kg": "80"}], confirmar=True), **U)
    assert r.total_kg == D("122.000")
    assert u.piezas.obtener(pid).saldo_unidades == 90


def test_reglas_del_material_irregular():
    u, hyms, _ = _uow()
    with pytest.raises(ValidationError):
        NotaEntregaIn(fecha=HOY, tercero_id=hyms.id)                       # nada que sale
    with pytest.raises(ErrorNegocio, match="lleva existencia"):
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, libres=[{"codigo": TUBO, "kg": "5"}]), **U)
    with pytest.raises(ErrorNegocio, match="no lleva existencia"):
        _entrada(u, hyms, codigo="MATERIALESIRREG", unidades=1)


def test_nota_de_salida_con_material_irregular():
    from app.esquemas import NotaSalidaIn
    from app.servicios import despachos
    from tests.test_despachos import _od
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, unidades=100).pieza_id      # 100 x 4,2 kg
    od = _od(u, hyms, [{"pieza_id": pid, "unidades": 10}])
    ns = despachos.nota_salida(u, od.id, NotaSalidaIn(fecha=HOY, confirmar=True,
                               libres=[{"codigo": "MATERIALESIRREG", "kg": "35", "detalle": "recortes"}]), **U)
    assert ns.total_kg == D("77.000") and ns.libres[0].descripcion == "Material de Medidas Irregulares (recortes)"
    doc = u.documentos.obtener(ns.documento_id)
    assert doc.encabezado["libres"][0]["kg"] == "35.000"
    assert u.documentos.lineas(ns.documento_id)[0]["codigo"] == "MATERIALESIRREG"
    assert u.piezas.obtener(pid).saldo_unidades == 90
