"""El adaptador de PDF genera documentos válidos (no necesita base de datos)."""
from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.dominio.impresion import CorteImpreso, OrdenSlitterImpresa, RolloImpreso


def _orden(rollos_por_corte=4, scrap=8.0, anulada=False):
    cortes = [CorteImpreso(1, 268, rollos_por_corte, 7356.6, "FLEHP0900268", "Fleje L.F. 0,90mm x 268mm"),
              CorteImpreso(2, 30, 1, 205.875, "FLEHP0900030", "Fleje L.F. 0,90mm x 30mm")]
    rollos = [RolloImpreso(f"FLEHP0900268 / C226 / OC548 / 1-{chr(65 + i)}", f"1-{chr(65 + i)}", 7356.6 / rollos_por_corte, 1)
              for i in range(rollos_por_corte)] + [RolloImpreso("FLEHP0900030 / C226 / OC548 / 2-A", "2-A", 205.875, 2)]
    return OrdenSlitterImpresa(548, "02/11/2026", "C22600728510", "BOBHP0901200", "Bobina L.F. 0,90mm x 1200mm", "HP",
                               "LAM FRIO", "JIS 3141 G", 0.9, 1200, 8235, 8235, "Aceros del Valle, C.A.",
                               "Total", "1er-F", cortes, scrap, 54.9, rollos, "prueba", anulada=anulada)


def _paginas(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type /Page>")


def test_orden_y_etiquetas():
    g = GeneradorReportlab()
    o = _orden()
    hoja = g.orden_slitter(o)
    assert hoja.startswith(b"%PDF") and len(hoja) > 5000
    etiquetas = g.etiquetas_slitter(o)
    assert etiquetas.startswith(b"%PDF") and _paginas(etiquetas) == 1  # 5 etiquetas caben en una hoja


def test_seis_por_hoja_y_reimpresion_parcial():
    g = GeneradorReportlab()
    o = _orden(rollos_por_corte=12)  # 13 rollos -> 3 hojas
    assert _paginas(g.etiquetas_slitter(o)) == 3
    assert _paginas(g.etiquetas_slitter(o, o.rollos[:2])) == 1


def test_orden_larga_sin_scrap_y_anulada():
    g = GeneradorReportlab()
    o = _orden(rollos_por_corte=15, scrap=0, anulada=True)
    assert _paginas(g.orden_slitter(o)) >= 2  # la lista de rollos sigue en otra hoja


def _ne(renglones: int, anulada=False):
    import datetime as dt
    from decimal import Decimal as D

    from app.dominio.impresion import NotaEntregaImpresa, RenglonNE
    r = [RenglonNE(D(3), "Pza", "Lamina Est HN 3,00mm x 1200mm x 2400mm", "LAMHN30012002400", D("73.44"), D("220.32"))
         for _ in range(renglones)]
    return NotaEntregaImpresa("7237", dt.date(2026, 11, 11), dt.datetime(2026, 11, 11, 9, 14),
                              "Aceros del Valle, C.A.", "J-10000004-9", "Valencia", None, "Contado", None,
                              "D-2939", "Pedro Pérez", "A12BC3D", "5989", "Valencia", None, r, anulada=anulada)


def test_nota_de_entrega_una_hoja_y_varias():
    from decimal import Decimal as D
    g = GeneradorReportlab()
    corta = g.nota_entrega(_ne(6))
    assert corta.startswith(b"%PDF") and _paginas(corta) == 1
    assert _ne(6).total_kg == D("1321.92")
    larga = g.nota_entrega(_ne(23, anulada=True))
    assert _paginas(larga) == 3          # 10 renglones por hoja
    assert g.nota_entrega(_ne(0)).startswith(b"%PDF")
