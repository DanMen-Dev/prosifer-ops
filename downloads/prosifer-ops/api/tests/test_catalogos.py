"""Clientes y productos del libro de formatos (filas armadas a mano; no necesita el Excel real)."""
import datetime as dt
from decimal import Decimal as D

from importador import catalogos_excel as ce


def cli(fila, nombre, rif=None, **extra):
    return ce.Cliente(fila, nombre, rif=rif, **extra)


def test_lee_fila_de_cliente_como_la_escribe_el_libro():
    c = ce.cliente_de_fila(272, ("Metalurgica Aurora, C.A. ", "Zona Industrial Demo Norte",
                                 "Carabobo", "j-10000001-0", "0414-0000001", None, "R.O.", "Ciudad Demo",
                                 "29 de agosto de 2024", " ventas@aurora-demo.test "))
    assert c.nombre == "Metalurgica Aurora, C.A." and c.rif == "J-10000001-0"
    assert c.vendedor == "R.O" and c.cliente_desde == dt.date(2024, 8, 29) and c.correo == "ventas@aurora-demo.test"
    assert ce.cliente_de_fila(9, (None, "sin nombre")) is None
    assert ce.cliente_de_fila(9, ("Taller X", None, None, None, None, "contado", "Columna2")).vendedor is None


def test_mismo_nombre_escrito_distinto_se_une_y_completa_datos():
    filas = [cli(184, "Inversiones Delta, C.A.", "J-10000002-8", telefono="0414-0000002"),
             cli(185, "Inversiones DELTA, C.A.", "J-10000002-8", vendedor="Oficina"),
             cli(236, "Carlos Rivera"), cli(237, "Carlos Rivera", ciudad="Valencia")]
    avisos = []
    unidos = ce.unir_clientes(filas, avisos)
    assert [c.nombre for c in unidos] == ["Inversiones Delta, C.A.", "Carlos Rivera"]
    assert unidos[0].telefono == "0414-0000002" and unidos[0].vendedor == "Oficina"
    assert unidos[1].ciudad == "Valencia" and len(avisos) == 2


def test_mismo_rif_con_otro_nombre_no_se_une_pero_avisa():
    avisos = []
    unidos = ce.unir_clientes([cli(49, "Constructora Horizonte, C.A.", "J-10000003-2"),
                               cli(330, "Suministros Metalicos Centro, C.A.", "J 10000003 2")], avisos)
    assert len(unidos) == 2 and "mismo RIF" in avisos[0]


def test_productos_codigo_repetido_con_otro_nombre_se_informa():
    filas = [ce.producto_de_fila(185, (181, "Fleje L.C. 3,00mm x 25mm", "flehn3003175", None, None, None, None, None, 1)),
             ce.producto_de_fila(187, (183, "Fleje L.C. 3,00mm x 31,75mm", "FLEHN3003175", None, None, None, None, None, 1)),
             ce.producto_de_fila(982, (None, "Viga UPL 100mm x 6000mm", "VIGUPLHNE000A00100A00000L06000",
                                       None, None, None, None, None, "49,20"))]
    avisos = []
    prods = ce.depurar_productos(filas, avisos)
    assert [p.codigo for p in prods] == ["FLEHN3003175", "VIGUPLHNE000A00100A00000L06000"]
    assert prods[1].peso_unitario_kg == D("49.2000") and "31,75" in avisos[0]


def test_pesos_y_fechas():
    assert ce.peso("1.234,5") == D("1234.5000") and ce.peso(854.4) == D("854.4000") and ce.peso("0.59") == D("0.5900")
    assert ce.peso(0) is None and ce.peso("n/a") is None
    assert ce.fecha_es("07 de febrero de 2025") == dt.date(2025, 2, 7) and ce.fecha_es("ayer") is None
    assert ce.clave_rif("j-10.000.002-8") == "J100000028"
