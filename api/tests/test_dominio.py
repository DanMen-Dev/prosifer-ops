from decimal import Decimal as D

import pytest

from app.dominio import codigos, saldos


@pytest.mark.parametrize("tipo, esp, ancho, esperado", [
    ("LAM FRIO", "0.90", 1220, "BOBHP0901220"),
    ("HN", 2.15, 1250, "BOBHN2151250"),
    ("LAM ESTR", "4.5", 1500, "BOBES4501500"),
    ("ALU", 1.0, 1000, "BOBAL1001000"),   # código viejo de láminas se normaliza
    ("EST", "3,00", 1220, "BOBES3001220"),
])
def test_codigo_bobina(tipo, esp, ancho, esperado):
    assert codigos.codigo_producto("bobina", tipo, esp, ancho) == esperado


def test_codigo_lamina_y_fleje():
    assert codigos.codigo_producto("lamina", "HP", "1.10", 1250, 2400) == "LAMHP11012502400"
    assert codigos.codigo_producto("fleje", "HP", "0.9", 268) == "FLEHP0900268"


def test_codigo_rechaza_fuera_de_rango():
    with pytest.raises(codigos.CodigoInvalido):
        codigos.codigo_producto("bobina", "HP", 12, 1220)  # 1200 centésimas no cabe en 3 dígitos
    with pytest.raises(codigos.CodigoInvalido):
        codigos.codigo_producto("bobina", "XX", 1, 1220)
    with pytest.raises(codigos.CodigoInvalido):
        codigos.codigo_producto("lamina", "HP", 1, 1220)


def test_espesor_comercial():
    assert codigos.espesor_comercial("0.58") == D("0.60")
    assert codigos.espesor_comercial("1,90") == D("2.00")
    assert codigos.espesor_comercial("0.75") == D("0.75")


def test_tipo_pieza_por_codigo():
    assert codigos.tipo_pieza_por_codigo("FLEHP0850200 / HT2BF2048 / 171 / 6") == "fleje"
    assert codigos.tipo_pieza_por_codigo("BOBHP0901220") == "bobina"
    assert codigos.tipo_pieza_por_codigo(None) == "bobina"


def test_saldo_y_estado():
    r = saldos.aplicar(D("1000"), "consumo", D("-999.5"))
    assert r.saldo_kg == D("0.5") and r.estado == "agotado"
    r = saldos.aplicar(D("1000"), "salida", D("-400"))
    assert r.saldo_kg == D("600") and r.estado == "disponible"


def test_no_permite_negativo():
    with pytest.raises(saldos.MovimientoInvalido):
        saldos.aplicar(D("100"), "salida", D("-150"))
    assert saldos.aplicar(D("100"), "salida", D("-150"), permitir_negativo=True).saldo_kg == D("-50")


def test_signos_y_liberacion():
    with pytest.raises(saldos.MovimientoInvalido):
        saldos.aplicar(D("100"), "consumo", D("10"))
    with pytest.raises(saldos.MovimientoInvalido):
        saldos.aplicar(D("100"), "liberacion", D("-10"))
    assert saldos.aplicar(D("100"), "liberacion", D("0")).saldo_kg == D("100")


def test_tolerancia_corte():
    assert saldos.diferencia_corte(D("1000"), D("940"), D("10")) == D("0.05")
    assert saldos.diferencia_corte(D("0"), D("1"), D("0")) == 0


def test_codigo_automatico_para_productos_sin_familia():
    from app.dominio.codigos import codigo_automatico
    assert codigo_automatico("Puerta Metálica 8 Paneles", {"PUERTAMETALP01", "PUE0001", "PUE0009", "PUE12"}) == "PUE0010"
    assert codigo_automatico("Ángulo especial", []) == "ANG0001"
