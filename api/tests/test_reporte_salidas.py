"""PDF del reporte mensual de salidas (Servicios de Descarga-Carga): sin base de datos."""
import datetime as dt
from decimal import Decimal

from app.adaptadores.pdf.reportlab_reporte_salidas import FILAS_POR_HOJA, pdf_reporte_salidas
from app.esquemas import FilaReporteSalidas, ReporteSalidas


def _reporte(n: int) -> ReporteSalidas:
    filas = [FilaReporteSalidas(nota_salida=str(5600 + i), fecha=dt.date(2026, 10, 1 + i % 28), nota_entrega=str(7000 + i),
                                documento_id=i, cantidad=Decimal(5), descripcion="Lamina L.F. 0,85mm x 1200mm x 2400mm",
                                kg=Decimal("98.53")) for i in range(n)]
    return ReporteSalidas(tercero_id=1, tercero="Aceros del Valle, C.A.", desde=dt.date(2026, 10, 1),
                          hasta=dt.date(2026, 10, 31), filas=filas, notas_entrega=n, total_kg=sum((f.kg for f in filas), Decimal(0)))


def test_pdf_reparte_las_filas_en_hojas():
    pdf = pdf_reporte_salidas(_reporte(FILAS_POR_HOJA * 2 + 3))
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 3


def test_pdf_sin_salidas():
    assert pdf_reporte_salidas(_reporte(0)).startswith(b"%PDF")


def test_categoria_de_cada_renglon():
    from app.dominio.codigos import categoria_salida as cat
    assert cat("bobina", "C22202039020", "Bobina L.F. 0,70mm x 1200mm") == "bobina"
    assert cat(None, "FLEHP0600040", "Fleje L.F. 0,60mm x 40mm") == "fleje"
    assert cat(None, "LAMHP08512002400", "Lamina L.F. 0,85mm x 1200mm x 2400mm") == "lamina"
    assert cat(None, "MATERIALESIRREG", "Materiales de Medidas Irregulares") == "irregular"
    assert cat(None, None, "Fleje L.C. 2,00mm x 125mm") == "fleje"          # histórico sin código
    assert cat(None, "TUB000HNE200A00080A00040L06000", "Tubo L.C. 80 x 40") == "general"
