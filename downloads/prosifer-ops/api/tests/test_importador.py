"""Reglas de importación con un libro armado a mano (no necesita el Excel real)."""
import datetime as dt
from decimal import Decimal as D

from importador import paridad, reglas
from importador.excel import Corte, Entrada, FilaConsolidado, Libro, Salida

F = dt.date


def entrada(fila, codigo, peso, fecha=F(2024, 1, 1), dueno="Prosifer"):
    return Entrada(fila, "Doc", fecha, codigo, "BOBHP0901220", "LAM FRIO", None, "JIS", D("0.9"), D("1220"),
                   D(peso), None, None, dueno)


def salida(fila, codigo, kg, doc="Nota de Entrega Nro", numero="1", fecha=F(2024, 2, 1), dueno="Cliente"):
    return Salida(fila, codigo, D(kg), dueno, doc, numero, fecha)


def test_entrada_duplicada_vale_la_mas_antigua():
    libro = Libro([entrada(4, "X1", "100", F(2024, 5, 10)), entrada(9, "X1", "100", F(2023, 12, 8))], [], [], [])
    plan = reglas.construir(libro)
    assert len(plan.piezas) == 1
    assert plan.piezas["X1"].entrada.fecha == F(2023, 12, 8)
    assert [i.tipo for i in plan.incidencias] == ["entrada_duplicada"]


def test_corte_y_nota_de_entrega_parcial_sin_limite():
    libro = Libro(
        [entrada(4, "B1", "1000")],
        [Corte("Producto", 5, "776", "B1", D("400"), F(2024, 1, 5))],
        [salida(6, "B1", "100", numero="10"), salida(7, "B1", "100", numero="11"),
         salida(8, "B1", "100", numero="12")],
        [])
    p = reglas.construir(libro).piezas["B1"]
    assert p.saldo == D("300") and p.estado == "disponible"
    assert [m.tipo for m in p.movimientos] == ["entrada", "consumo", "salida", "salida", "salida"]


def test_nota_de_entrega_repetida_cuenta_una_vez():
    libro = Libro([entrada(4, "B1", "500")], [], [salida(5, "B1", "500"), salida(6, "B1", "500")], [])
    plan = reglas.construir(libro)
    assert plan.piezas["B1"].saldo == 0
    assert "salida_duplicada" in [i.tipo for i in plan.incidencias]


def test_ajuste_interno_deja_en_cero():
    libro = Libro([entrada(4, "B1", "1000")],
                  [Corte("Producto", 5, "1", "B1", D("900"), F(2023, 1, 1))],
                  [salida(6, "B1", "259.5", numero="Ajuste Inventario Interno", fecha=F(2023, 10, 25)),
                   salida(7, "B1", "33", doc=None, numero=None, fecha=None)],
                  [])
    p = reglas.construir(libro).piezas["B1"]
    assert p.saldo == 0
    assert p.movimientos[-1].tipo == "ajuste" and p.movimientos[-1].kg == D("-67")


def test_liberacion_total_cambia_dueno_y_parcial_no():
    libro = Libro(
        [entrada(4, "B1", "1000"), entrada(5, "B2", "1000")],
        [Corte("ProductoF", 6, "9", "B1", D("400"), F(2024, 1, 2))],
        [salida(7, "B1", "600", doc="Liberacion Nro", dueno="Nuevo", fecha=F(2024, 1, 3)),
         salida(8, "B2", "300", doc="Liberacion Nro", dueno="Otro", fecha=F(2024, 1, 3))],
        [])
    plan = reglas.construir(libro)
    assert plan.piezas["B1"].propietario == "Nuevo"          # liberó todo lo que quedaba
    assert plan.piezas["B1"].saldo == D("600")               # la liberación no descuenta
    assert plan.piezas["B2"].propietario == "Prosifer"       # parcial: no cambia
    assert [i.tipo for i in plan.incidencias] == ["liberacion_parcial"]


def test_paridad_detecta_diferencia_de_kg():
    libro = Libro([entrada(4, "B1", "1000")], [], [],
                  [FilaConsolidado(4, "B1", D("900"), "Disponible", "Prosifer")])
    r = paridad.comparar(libro, reglas.construir(libro))
    assert r["diferencias"][0][1] == "kg"
