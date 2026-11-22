"""Reporte de inventario por cliente en PDF (por categoría o total)."""
import datetime as dt
from decimal import Decimal as D

from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.dominio.impresion import FilaInventario, ReporteInventario, SeccionInventario


def _bobinas(k):
    return [FilaInventario(f"C2260079{7400 + i}", "Bobina", "HP", "JIS 3141 G", D("0.60"), D("1200"), None, None,
                           D("8355") + i, dt.date(2026, 10, 1)) for i in range(k)]


def _laminas():
    return [FilaInventario("LAMHP07012002400", "Lamina L.F. 0,70mm x 1200mm x 2400mm", "HP", None, D("0.70"),
                           D("1200"), D("2400"), D("289"), D("4580.65")),
            FilaInventario("LAMGV06012202400", "Lamina Galv. 0,60mm x 1220mm x 2400mm (2A)", "GV", None, D("0.60"),
                           D("1220"), D("2400"), D("223"), D("3297.06"))]


def _perfiles():
    return [FilaInventario("PERHPE090B15L05150", "Perfil LF Marco de Ventana B15 x 0,90mm x 5,15mts", "HP", None,
                           D("0.88"), None, D("5150"), D("299"), D("2532.53"))]


def _reporte(secciones, total):
    return ReporteInventario("Aceros del Valle, C.A.", "J-00000000-0", dt.datetime(2026, 11, 12, 10, 42),
                             "asistente", secciones, total)


def _hojas(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r")


def test_totales_de_seccion():
    s = SeccionInventario("lamina", _laminas())
    assert s.total_piezas == D("512") and s.total_kg == D("7877.71")
    assert SeccionInventario("bobina", _bobinas(3)).total_piezas == 3


def test_una_categoria_pagina_y_el_total():
    g = GeneradorReportlab()
    assert _hojas(g.reporte_inventario(_reporte([SeccionInventario("bobina", _bobinas(5))], False))) == 1
    assert _hojas(g.reporte_inventario(_reporte([SeccionInventario("bobina", _bobinas(80))], False))) >= 2
    total = _reporte([SeccionInventario("bobina", _bobinas(25)), SeccionInventario("lamina", _laminas()),
                      SeccionInventario("perfil", _perfiles()), SeccionInventario("general", [])], True)
    assert g.reporte_inventario(total).startswith(b"%PDF")
    assert total.total_kg > 0
