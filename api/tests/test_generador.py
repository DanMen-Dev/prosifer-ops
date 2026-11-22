"""Generador de códigos y nombres: la regla nueva (10 nov 2026)."""
from decimal import Decimal as D

import pytest

from app.dominio import generador as g
from app.dominio.codigos import ancho_codigo, medidas_lamina


def gen(nombre):
    p = g.leer(nombre)
    assert p is not None, nombre
    return g.generar(p)


@pytest.mark.parametrize("nombre, codigo", [
    # lo que ya estaba bien queda igual
    ("Angulo 25mm x 25mm x 3,00mm x 6000mm", "ANG000HNE300A00025A00025L06000"),
    ("Tubo L.C. 100mm x 100mm x 2,50mm x 6000mm", "TUB000HNE250A00100A00100L06000"),
    ("Tubo L.F. 1 1/2'' x 1/2'' x 0,90mm x 6000mm", "TUB000HPE090A00015A00005L06000"),
    ("Tubo L.F. 2'' x 1'' x 0,80mm x 6000mm", "TUB000HPE080A00002A00001L06000"),
    ("Tubo Ventilacion L.C. 1 1/4'' x 2,00mm x 6000mm (2A)", "TUBVNTHNE200A00125A00000L06000-A"),
    ("Tubo Para Cerca Galv. 2'' x 0,90mm x 3300mm", "TUBCRTGVE090A00002A00000L03300"),
    ("Viga IPE 80mm x 6000mm", "VIGIPEHNE000A00080A00000L06000"),
    ("Malla Truckson 6'' x 6'' x 3,50mm x 25mts2", "MLLTRKHNE350A00006A00006L00025"),
    ("Cercha C-10 100mm x 6000mm", "CERC10HNE000A00100A00000L06000"),
    ("Alambron Liso 5,50mm Por Rollo", "ALALISHNE550A00000A00000L00000"),
    ("Lamina L.C. 2,00mm x 1250mm x 2400mm", "LAMHN20012502400"),
    ("Lamina Est HN 3,00mm x 1200mm x 2400mm", "LAMEST30012002400"),
    ("Lamina Galv. 0,45mm x 1220mm x 2400mm (2C)", "LAMGV04512202400-C"),
    ("Perfil LC Vigueta 2'' x 1'' x 2,35mm x 6,00mts", "PERHNVIG2356000"),
    ("Perfil LF Marco de Puerta B15 x 0,90mm x 5,15mts (2B)", "PERHPP150905150-B"),
    ("Perfil LF Hoja Santa Maria x 0,70mm x 6,10mts", "PERHPHSM0706100"),
    ("Perfil LC Guia Sta Maria 1'' x 2'' x 2,00mm x 6,00mts", "PERHNGUI2006000"),
    ("Bobina L.F. 0,90mm x 1200mm", "BOBHP0901200"),
    # lo que se corrige
    ("Pletina 1 1/2'' x 3/16'' x 6000mm", "PLT000HNF188A00000A00015L06000"),     # antes 1875, sin E
    ("Pletina 1'' x 1/4'' x 6000mm", "PLT000HNF250A00000A00001L06000"),          # antes E025
    ("Cabilla Estriada 1/2'' x 6000mm S60", "CSTS60HNF500A00000A00000L06000"),   # antes E050
    ("Barra Redonda 12mm x 6000mm", "BRD000HN1200A00000A00000L06000"),           # 12 mm: 4 dígitos sin E
    ("Barra Redonda 6,00mm x 6000mm", "BRD000HNE600A00000A00000L06000"),         # antes E006
    ("Tubo L.F. 3'' x 1 1/2'' x 0,90mm x 6000mm", "TUB000HPE090A00003A00015L06000"),  # antes A00150
    ("Lamina L.C. 10,00mm x 1200mm x 2400mm", "LAMHN100012002400"),              # 4 dígitos desde 10 mm
    ("Lamina ALUMINIO 1,00mm x 1220mm x 2400mm", "LAMAL10012202400"),            # antes LAMALU
    ("Fleje L.F. 0,58mm x 45mm", "FLEHP0580045"),                                # antes FLELF0000058045
    ("Fleje L.C. 3,00mm x 38,1mm", "FLEHN3000038D1"),                            # decimales tras D
])
def test_codigos(nombre, codigo):
    assert gen(nombre)[0] == codigo


def test_nombres_ordenados():
    assert gen("Angulo  20mm x 20mm x 2,50mm x 6000mm")[1] == "Angulo 20mm x 20mm x 2,50mm x 6000mm"
    assert gen('Tubo L.F. 1 x 1 x 1,10mm x 6000mm')[1] == "Tubo L.F. 1'' x 1'' x 1,10mm x 6000mm"
    assert gen("Lamina L.F. 0,55mm x 1220mm x 2.400mm")[0] == "LAMHP05512202400"   # punto de miles
    # el espesor se nombra como viene: real o ya redondeado, y el código igual (11 nov 2026)
    assert gen("Lamina L.F. 1,08mm x 1200mm x 2400mm") == ("LAMHP10812002400", "Lamina L.F. 1,08mm x 1200mm x 2400mm")
    assert gen("Bobina L.F. 0,58mm x 1200mm") == ("BOBHP0581200", "Bobina L.F. 0,58mm x 1200mm")
    assert g.leer("Angulo​ 75mm x 75mm x 7,00mm x 6000mm") is not None                       # invisible


def test_slots():
    assert g.slot_espesor(g.Medida.mm("2,5")) == "E250"
    assert g.slot_espesor(g.Medida.mm(10)) == "1000"
    assert g.slot_espesor(g.Medida.pulg("3/16")) == "F188"
    assert g.slot_medida(g.Medida.pulg("1 1/4")) == "A00125"
    assert g.slot_medida(g.Medida.pulg("3/4")) == "A00075"
    assert g.slot_medida(g.Medida.mm(100)) == "A00100"
    assert ancho_codigo(D("19.05")) == "0019D05" and ancho_codigo(D("1220")) == "1220"
    assert medidas_lamina("LAMEST30012002400-A") == ("EST", D("3"), D("1200"), D("2400"))
    assert medidas_lamina("LAMHN100012002400") == ("HN", D("10"), D("1200"), D("2400"))


def test_comparar_estados_y_choques():
    res = g.comparar([
        ("ANG000HNE300A00025A00025L06000", "Angulo 25mm x 25mm x 3,00mm x 6000mm"),
        ("PLT000HN1875A00000A00001L06000", "Pletina 1'' x 3/16'' x 6000mm"),
        ("TUB000HPE090A00002A00015L06000", "Tubo L.F. 2 x 1 1/2 x 0,90mm x 6000mm"),
        ("TUB000HPE090A00002A00150L06000", "Tubo L.F. 2'' x 1 1/2'' x 0,90mm x 6000mm"),
        ("LAMHN29012202400", "Lamina L.C. 3,00mm x 1220mm x 2400mm"),       # nombre redondeado: código también
        ("SERVICIOCARGAYMANEJO0001", "Servicio de Carga y Manejo"),
    ])
    estados = [f.estado for f in res]
    assert estados == ["igual", "cambia_codigo", "choque", "choque", "cambia_codigo", "sin_regla"]
    assert res[4].codigo_nuevo == "LAMHN30012202400"
    assert res[1].codigo_nuevo == "PLT000HNF188A00000A00001L06000"


def test_generar_valida():
    with pytest.raises(g.GeneradorInvalido):
        g.generar(g.Producto("tubo", "HP", espesor=g.Medida.mm(1)))          # faltan medidas
    with pytest.raises(g.GeneradorInvalido):
        g.generar(g.Producto("angulo", "GV", espesor=g.Medida.mm(3), medida1=g.Medida.mm(25), largo_mm=D(6000)))


def test_onge_omega_romanilla():
    assert gen("Perfil LC Onge 1 1/4'' x 2,35mm x 6,00mts")[0] == "PERHNO142356000"
    assert gen("Perfil LC Onge 2'' x 2,00mm x 6,00mts (2A)")[0] == "PERHNO202006000-A"
    assert gen("Perfil LF Omega 60mm x 1,10mm x 6,00mts")[0] == "PERHPOME1106000"
    assert gen("Perfil LF Romanilla 0,90mm x 6,00mts") == ("PERHPROM0906000", "Perfil LF Romanilla 0,90mm x 6,00mts")


def test_perfil_sugerido_por_el_fleje():
    from app.dominio import desarrollos as d
    assert [x.nombre for x in d.para_fleje("HN", D("1.9"), D("90"))] == ["Vigueta 2'' x 1''"]
    assert [x.nombre for x in d.para_fleje("HP", D("0.88"), D("90"))] == ["Romanilla"]       # mismo ancho, delgado
    assert d.para_fleje("HP", D("0.88"), D("178"))[0].nombre == "Hoja Santa María"
    assert len(d.para_fleje("HP", D("0.68"), D("238"))) == 3                                # la asistente elige
    assert d.para_fleje("HN", D("1.9"), D("500")) == []
