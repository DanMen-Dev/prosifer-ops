"""Lectura del histórico de entradas (libros de Láminas y de Generales): sin base de datos."""
import datetime as dt
from decimal import Decimal

import openpyxl

from importador import entradas_historico_excel as eh

TITULOS = ["PROPIETARIO", "CODIGO", "DESCRIPCION", "TIPO", "NORMA", "ESPESOR", "ANCHO", "LARGO", "CALIDAD", "TOTAL",
           "FECHA", "DOCUMENTO ", "NUMERO", "NOMBRE DOCUMENTO", "PESO (KG)"]


def _libro(tmp_path, filas_def, filas_otra=()):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in (("Entradas_Lam_Almacen_Otras", filas_otra), ("Entradas_Lam_Almacen_Otras_Def", filas_def)):
        ws = wb.create_sheet(nombre)
        ws.append(list(range(1, 16)))
        ws.append(TITULOS)
        ws.append(["INICIO"] * 14)
        for f in filas:
            ws.append(f)
    ruta = tmp_path / "Inventario_de_Laminas.xlsm"
    wb.save(ruta)
    return str(ruta)


def _fila(dueno, codigo, total, fecha, num, peso=None):
    return [dueno, codigo, f"Lamina {codigo}", "LAM", None, 3, 1200, 2400, "1er", total, fecha,
            "Nota de Entrega Nro", num, f"Nota de Entrega Nro.{num}", peso]


def test_agrupa_por_nota_calcula_kg_y_lee_las_dos_hojas(tmp_path):
    hyms = "Aceros del Valle, C.A."
    ruta = _libro(tmp_path,
                  [_fila(hyms, "LAMHN30012002400", 100, dt.datetime(2026, 10, 20), 20102026, 69.12),
                   _fila(hyms, "LAMHN60012002400", 1, dt.datetime(2026, 10, 20), 20102026, 138.24),
                   _fila("Prosifer", "LAMHN30010002400", 76, dt.datetime(2027, 8, 9), 873413)],
                  [_fila(hyms, "LAMHP08510002000", 319, dt.datetime(2026, 11, 3), 3112026, 13.685)])
    es = eh.leer(ruta, hoy=dt.date(2026, 11, 18))
    assert len(es) == 3
    nota = next(e for e in es if e.documento == "Nota de Entrega Nro.20102026")
    assert [r.cantidad for r in nota.renglones] == [Decimal("100"), Decimal("1")]
    assert nota.renglones[0].kg == Decimal("6912.000")
    futura = next(e for e in es if e.propietario == "Prosifer")
    assert futura.avisos and "futuro" in futura.avisos[0]
    assert futura.renglones[0].kg is None          # sin peso por pieza: se toma del catálogo al cargar
