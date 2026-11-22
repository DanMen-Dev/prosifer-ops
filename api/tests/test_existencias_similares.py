"""La entrada avisa si el dueño ya tiene el mismo material con otro código (no se suman)."""
from decimal import Decimal as D

from tests.test_existencias import _entrada, _uow

LC = "LAMHN25012002400"


def test_lamina_mismas_medidas_otro_codigo_avisa():
    u, hyms, otro = _uow()
    _entrada(u, hyms, codigo=LC, unidades=4, descripcion="Lamina L.C. 2,50mm x 1200mm x 2400mm", peso_unitario_kg=D("57.6"))
    r = _entrada(u, hyms, codigo="LAMHP25012002400", unidades=155, descripcion="Lamina 2,50 x 1200 x 2400",
                 peso_unitario_kg=D("57.6"), confirmar=False)
    assert [x.codigo for x in r.similares] == [LC] and r.similares[0].saldo_unidades == 4
    assert any(LC in a for a in r.avisos)
    # con el mismo código se suma y no hay aviso
    r2 = _entrada(u, hyms, codigo=LC, unidades=155, descripcion="Lamina L.C. 2,50mm x 1200mm x 2400mm",
                  peso_unitario_kg=D("57.6"), confirmar=False)
    assert r2.similares == [] and r2.existencia_despues == 159
    # otro dueño u otras medidas: nada
    assert _entrada(u, otro, codigo="LAMHP25012002400", unidades=1, descripcion="x", peso_unitario_kg=D("1"),
                    confirmar=False).similares == []
    assert _entrada(u, hyms, codigo="LAMHN25012002440", unidades=1, descripcion="x", peso_unitario_kg=D("1"),
                    confirmar=False).similares == []


def test_general_misma_descripcion_otro_codigo_avisa():
    u, hyms, _ = _uow()
    _entrada(u, hyms, codigo="TUBVIEJO01", unidades=10, descripcion="Tubo L.F. 1'' x 1'' x 0,90mm", peso_unitario_kg=D("4"))
    r = _entrada(u, hyms, codigo="TUBNUEVO01", unidades=5, descripcion="tubo lf 1'' x 1'' x 0,90mm",
                 peso_unitario_kg=D("4"), confirmar=False)
    assert [x.codigo for x in r.similares] == ["TUBVIEJO01"]
