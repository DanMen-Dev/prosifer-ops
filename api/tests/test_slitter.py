from decimal import Decimal as D

import pytest

from app.dominio import slitter
from app.dominio.slitter import CorteIn


def test_reparte_como_el_excel():
    # OC 548: bobina de 1200 mm y 8235 kg; cortes de 4×268, 1×90, 1×30 y scrap de 8 mm.
    p = slitter.planificar(D("1200"), D("8235"), [CorteIn(D("268"), 4), CorteIn(D("90"), 1), CorteIn(D("30"), 1)],
                           scrap_ancho_mm=D("8"))
    assert p.cortes[0].kg == D("7356.600")
    assert p.cortes[0].kg_rollos == [D("1839.150")] * 4
    assert p.cortes[1].kg == D("617.625") and p.cortes[2].kg == D("205.875")
    assert p.scrap_kg == D("54.900")
    assert p.diferencia == 0 and p.avisos == []


def test_ultimo_rollo_absorbe_el_redondeo():
    assert slitter.repartir(D("1000"), 3) == [D("333.333"), D("333.333"), D("333.334")]


def test_pesos_reales_y_aviso_de_tolerancia():
    p = slitter.planificar(D("1000"), D("5000"), [CorteIn(D("500"), 2, kg=D("4500"))], scrap_kg=D("100"))
    assert p.producido == D("4500.000")
    assert p.diferencia == D("0.08")
    assert any("8.0 %" in a for a in p.avisos)


def test_ancho_sobrante_avisa_y_exceso_rechaza():
    p = slitter.planificar(D("1220"), D("6000"), [CorteIn(D("300"), 3)])
    assert any("sin asignar" in a for a in p.avisos)
    with pytest.raises(slitter.CorteInvalido):
        slitter.planificar(D("1220"), D("6000"), [CorteIn(D("300"), 4), CorteIn(D("30"), 1)])


def test_validaciones():
    with pytest.raises(slitter.CorteInvalido):
        slitter.planificar(D("1220"), D("6000"), [])
    with pytest.raises(slitter.CorteInvalido):
        slitter.planificar(D("1220"), D("6000"), [CorteIn(D("100"), 1)] * 7)
    with pytest.raises(slitter.CorteInvalido):
        slitter.planificar(D("1220"), D("6000"), [CorteIn(D("100"), 16)])
    with pytest.raises(slitter.CorteInvalido):
        slitter.planificar(None, D("6000"), [CorteIn(D("100"), 1)])


def test_codigo_y_descripcion_del_rollo():
    assert slitter.codigo_rollo("FLEHP0900268", "C22600728510", 549, 1, 2) == \
        "FLEHP0900268 / C22600728510 / OC549 / 1-B"
    # bobinas y flejes llevan el espesor real (11 nov 2026)
    assert slitter.descripcion_fleje("HP", D("0.88"), D("268")) == "Fleje L.F. 0,88mm x 268mm"
    assert slitter.descripcion_fleje("HN", D("2"), D("90.5")) == "Fleje L.C. 2,00mm x 90,5mm"
