from decimal import Decimal as D

import pytest

from app.dominio.salidas import SalidaInvalida, evaluar_linea


def test_total_y_parcial():
    assert evaluar_linea(D("1000"), None).kg == D("1000")
    r = evaluar_linea(D("1000"), D("400"))
    assert r.kg == D("400") and r.saldo_despues == D("600") and r.avisos == []


def test_resto_pequeno_avisa():
    r = evaluar_linea(D("1000"), D("973"))
    assert r.saldo_despues == D("27") and "resto de 27" in r.avisos[0]


def test_tolerancia_del_umbral():
    assert evaluar_linea(D("1000"), D("1000.6")).kg == D("1000")
    with pytest.raises(SalidaInvalida):
        evaluar_linea(D("1000"), D("1002"))


def test_sin_saldo_o_kg_invalido():
    with pytest.raises(SalidaInvalida):
        evaluar_linea(D("0.5"), None)
    with pytest.raises(SalidaInvalida):
        evaluar_linea(D("100"), D("0"))
