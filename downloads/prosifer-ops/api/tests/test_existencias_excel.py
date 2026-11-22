"""Lectura de la hoja Consolidado_Item_Cliente (filas armadas a mano)."""
from decimal import Decimal as D

from importador import existencias_excel as xe
from importador.existencias_excel import paridad, peso_teorico_lamina

ENC_LAM = ("LISTA DE PROPIETARIOS", "CODIGO", "DESCRIPCION", "TIPO", "NORMA", "ESPESOR (mm)", "ANCHO (mm)",
           "LARGO (mm)", "CALIDAD", "PESO (KG)", "celda disponible", "Daniel Mendoza", "Aceros del Valle, C.A.",
           "Metales Unidos, C.A.", None, "basura")


def test_laminas_positivos_se_cargan_y_negativos_se_informan():
    filas = [("Lamina…",), ENC_LAM, ("x",),
             ("Romer", "LAMHP09012002400", "Lamina L.F. 0,90mm x 1200mm x 2400mm", "LAM FRIO", "ASTM A1008", 0.9, 1200,
              2400, "1er-F", 20.40192, None, 62, -47, 15, None, 999),
             (None, "LAMHP07012002000", "Lamina L.F. 0,70mm x 1200mm x 2000mm", "LAM FRIO", None, 0.7, 1200, 2000,
              "1er-F", None, None, 0, -8, 0),
             (None, None, None)]
    libro = xe.leer_hoja("lamina", filas)
    assert libro.duenos == ["Daniel Mendoza", "Aceros del Valle, C.A.", "Metales Unidos, C.A."]
    assert len(libro.filas) == 1 and libro.filas[0].por_dueno == {"Daniel Mendoza": 62, "Metales Unidos, C.A.": 15}
    assert [(n.codigo, n.piezas) for n in libro.negativos] == [("LAMHP09012002400", -47), ("LAMHP07012002000", -8)]
    assert libro.total_piezas == 77 and libro.filas[0].ancho_mm == D("1200")
    assert paridad(libro, {"Daniel Mendoza": 62, "Metales Unidos, C.A.": 15}) == []
    assert paridad(libro, {"Daniel Mendoza": 60}) != []


def test_perfiles_largo_en_metros_y_peso_con_coma():
    enc = ("FECHA", "CODIGO BOBINA", "CODIGO PRODUCTO", "DESCRIPCION", "TIPO", "NORMA", "ESPESOR", "ANCHO", "LARGO",
           "PESO", "CALIDAD", "C1", "C2A", "C2B", "C2C", "TOTAL", "PROPIETARIOS", "Prosifer", "Daniel Mendoza")
    filas = [("x",), enc, ("y",),
             (None, None, "perhpp100905150", "Perfil LF Marco de Puerta B10 x 0,90mm x 5,15mts", "LAM FRIO",
              "JIS 3141 G", 0.88, 214, "5,15", "7,7556", "1er-F", 2423, 0, 0, 0, 2423, "Prosifer", 0, 111)]
    f = xe.leer_hoja("perfil", filas).filas[0]
    assert f.codigo == "PERHPP100905150" and f.largo_mm == D("5150") and f.peso_unitario_kg == D("7.7556")
    assert f.ancho_mm is None and f.por_dueno == {"Daniel Mendoza": 111}


def test_peso_teorico_de_lamina():
    f = xe.FilaExistencia(1, "LAMHP14010002000", "x", "LAM FRIO", None, D("1.4"), D("1000"), D("2000"), "1er-F", None)
    assert peso_teorico_lamina(f) == D("21.9800")
    assert xe.numero("1,40") == D("1.40") and xe.numero(0) is None and xe.numero("Agotado") is None
