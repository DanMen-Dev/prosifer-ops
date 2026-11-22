import pytest

from app.dominio import claves


def test_hash_y_verificacion():
    h = claves.hash_clave("acero2026x")
    assert h.startswith("scrypt$")
    assert claves.verificar_clave("acero2026x", h)
    assert not claves.verificar_clave("acero2026y", h)
    assert claves.hash_clave("acero2026x") != h  # sal distinta cada vez


def test_verificacion_tolera_basura():
    assert not claves.verificar_clave("x", None)
    assert not claves.verificar_clave("x", "md5$abc")
    assert not claves.verificar_clave("x", "scrypt$no$es$valido$aa$bb")


def test_reglas_de_clave():
    assert claves.clave_valida("corta1") is not None
    assert claves.clave_valida("solamenteletras") is not None
    assert claves.clave_valida("1234567890") is not None
    assert claves.clave_valida("bobina2026fleje") is None


def test_ficha_ida_y_vuelta():
    f = claves.crear_ficha({"u": 7, "e": 1}, "secreto", horas=1, ahora=1000)
    assert claves.leer_ficha(f, "secreto", ahora=1000 + 3599)["u"] == 7


def test_ficha_vencida_o_alterada():
    f = claves.crear_ficha({"u": 7, "e": 1}, "secreto", horas=1, ahora=1000)
    with pytest.raises(claves.FichaInvalida):
        claves.leer_ficha(f, "secreto", ahora=1000 + 3600)
    with pytest.raises(claves.FichaInvalida):
        claves.leer_ficha(f, "otro-secreto", ahora=1000)
    cuerpo, firma = f.split(".")
    otro = claves.crear_ficha({"u": 1, "e": 1}, "x", ahora=1000).split(".")[0]
    with pytest.raises(claves.FichaInvalida):
        claves.leer_ficha(f"{otro}.{firma}", "secreto", ahora=1000)
    with pytest.raises(claves.FichaInvalida):
        claves.leer_ficha("sin-punto", "secreto")
