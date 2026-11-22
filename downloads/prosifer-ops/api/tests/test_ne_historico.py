"""Lectura del histórico de NE del Excel (filas armadas a mano)."""
import datetime as dt
from decimal import Decimal as D

from importador import ne_historico_excel as nh


def _fila(numero, cliente, renglones, fecha="06 de noviembre de 2026", salida=5977):
    r = [numero, cliente] + [None] * 38
    for i, (cod, cant, uni, desc, kg) in enumerate(renglones):
        o = nh.RENGLONES[i]
        r[o:o + 5] = [cod, cant, uni, desc, kg]
    r[nh.COL_FECHA], r[nh.COL_SALIDA] = fecha, salida
    return tuple(r)


def test_lee_ne_con_renglones_fecha_y_nota_de_salida():
    filas = [_fila(7221, "Aceros del Valle, C.A.",
                   [("ANG000HNE300A00040A00040L06000", 2, "Pza", "Angulo 40mm x 40mm x 3,00mm x 6000mm", 21.12),
                    ("tub000hpe090a00015a00015l06000", 10, "Pza", "Tubo L.F. 1 1/2'' x 1 1/2''", 63.1)]),
             _fila(7063.0, "ANULADA", [("LAMHN40012002400", None, None, None, None)], fecha=None, salida=None),
             _fila("1371-A", "Industrias Ferreas, C.A", [(None, 3, "Kg", "Alambron 5,50 mm", "3,00")],
                   fecha=dt.datetime(2023, 2, 14, 9, 11)),
             (None, None, None)]
    notas = nh.leer_hoja(filas)
    assert [n.numero for n in notas] == ["7221", "7063", "1371-A"]
    a, b, c = notas
    assert a.fecha == dt.date(2026, 11, 6) and a.observacion == "Nota de salida 5977"
    assert [r.codigo for r in a.renglones] == ["ANG000HNE300A00040A00040L06000", "TUB000HPE090A00015A00015L06000"]
    assert a.renglones[1].cantidad == D("10") and a.renglones[1].kg == D("63.1")
    assert b.anulada and b.cliente is None and b.fecha is None
    assert c.fecha == dt.date(2023, 2, 14) and c.renglones[0].codigo is None and c.renglones[0].kg == D("3.00")
    assert nh.ultima(notas) == 7221


def test_encabezado_de_la_ne_historica():
    nota = nh.NotaHistorica(5, "7000", "Cliente", None, False, nota_salida="5977", conductor="Pedro", placa=None)
    assert nota.encabezado == {"nota_salida": "5977", "chofer": "Pedro"}
    assert nh.NotaHistorica(6, "7001", "Cliente", None, False).encabezado is None


def test_corrige_fechas_imposibles_con_las_vecinas():
    import datetime as dt
    d = dt.date

    def nota(num, f):
        return nh.NotaHistorica(5, num, "Cliente", f, False)
    notas = [nota("100", d(2024, 9, 18)), nota("101", d(2004, 2, 18)), nota("102", d(202, 4, 6)),
             nota("103", d(2024, 9, 20)), nota("104", d(2029, 6, 30)), nota("105", d(2024, 9, 21)), nota("106", None)]
    nh.corregir_fechas(notas, hoy=d(2026, 11, 10))
    f = {n.numero: n.fecha for n in notas}
    assert f["101"] == d(2024, 9, 18)          # 18/02 no cae entre vecinas: toma la anterior
    assert f["102"] == d(2024, 9, 18)          # año 0202 → anterior válida
    assert f["104"] == d(2024, 9, 20)
    assert f["106"] is None and notas[0].fecha_excel is None
    assert notas[1].fecha_excel == d(2004, 2, 18) and "el Excel decía 18/02/2004" in notas[1].observacion
    vecinas = [nota("1", d(2026, 6, 29)), nota("2", d(2029, 6, 30)), nota("3", d(2026, 6, 30))]
    nh.corregir_fechas(vecinas, hoy=d(2026, 11, 10))
    assert vecinas[1].fecha == d(2026, 6, 30)  # mismo día y mes con el año de las vecinas
