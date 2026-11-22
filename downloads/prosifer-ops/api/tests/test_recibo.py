"""Recibo de entrada de material en PDF (media carta, opción B)."""
import datetime as dt
from decimal import Decimal as D

from app.adaptadores.pdf import reportlab_recibo
from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.dominio.impresion import ReciboEntradaImpreso, RenglonRecibo

A = RenglonRecibo(D("46"), "Pza", "Tubo L.F. 2'' x 2'' x 1,10mm x 6,00mts", "TUB000HPE110A00002A00002L06000",
                  D("10.17"), D("467.82"))
B = RenglonRecibo(D("200"), "Pza", "Tubo L.C. 100 x 40 x 2,00mm x 6,00mts", "TUB000HNE200A00100A00040L06000",
                  D("24.80"), D("4960"))


def _recibo(renglones, anulado=False):
    return ReciboEntradaImpreso(numero=1, fecha=dt.date(2026, 11, 11), cliente="Aceros del Valle, C.A.",
                                rif="J-00000000-0", documento_cliente="Carta del 11-11-2026", renglones=renglones,
                                observacion="Material en buen estado", registrado_por="asistente",
                                registrado=dt.datetime(2026, 11, 11, 15, 0), anulado=anulado)


def _hojas(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r")


def test_totales():
    r = _recibo([A, B])
    assert r.total_kg == D("5427.82") and r.total_piezas == D("246")


def test_media_hoja_arriba_o_abajo_y_hojas_completas_si_no_cabe():
    g = GeneradorReportlab()
    assert reportlab_recibo.POR_MEDIA >= 6 and reportlab_recibo.POR_HOJA >= 18
    assert g.recibo_entrada(_recibo([A, B])).startswith(b"%PDF")
    assert g.recibo_entrada(_recibo([A, B]), abajo=True).startswith(b"%PDF")
    assert _hojas(g.recibo_entrada(_recibo([A, B] * 3))) == 1
    assert _hojas(g.recibo_entrada(_recibo([A, B] * 15, anulado=True))) == 2
