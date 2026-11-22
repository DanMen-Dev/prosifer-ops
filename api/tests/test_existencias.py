"""Láminas, perfiles y generales: existencia en piezas por código y dueño (adaptador en memoria)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.adaptadores.memoria import UnidadMemoria
from app.dominio import entidades as e
from app.errores import ErrorNegocio
from app.esquemas import EntradaExistenciaIn, LiberacionIn, NotaEntregaIn
from app.servicios import inventario, salidas

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 10)
TUBO = "TUB000HPE090A00001A00001L06000"


def _uow():
    u = UnidadMemoria()
    hyms = u.terceros.nuevo("Aceros del Valle, C.A.")
    otro = u.terceros.nuevo("Daniel Mendoza")
    u.catalogos.productos[TUBO] = e.ProductoCatalogo(1, TUBO, "Tubo L.F. 1'' x 1'' x 0,90mm x 6000mm", D("4.2"))
    return u, hyms, otro


def _entrada(u, dueno, codigo=TUBO, unidades=568, confirmar=True, **extra):
    return inventario.registrar_entrada_existencia(u, EntradaExistenciaIn(
        codigo_producto=codigo, propietario_id=dueno.id, unidades=unidades, documento_numero="NE-03112026",
        fecha=HOY, confirmar=confirmar, **extra), **U)


def test_entrada_suma_a_la_misma_existencia_por_codigo_y_dueno():
    u, hyms, otro = _uow()
    previa = _entrada(u, hyms, confirmar=False)
    assert previa.tipo == "general" and previa.kg == D("2385.600") and previa.existencia_despues == 568
    a = _entrada(u, hyms)
    b = _entrada(u, hyms, unidades=32)
    assert a.pieza_id == b.pieza_id                       # misma fila: código + dueño
    p = u.piezas.obtener(a.pieza_id)
    assert p.saldo_unidades == 600 and p.saldo_kg == D("2520.000") and p.unidades_entrada == 600
    c = _entrada(u, otro, unidades=10)
    assert c.pieza_id != a.pieza_id                       # otro dueño, otra fila


def test_entrada_lamina_toma_medidas_del_codigo_y_exige_peso_fuera_de_catalogo():
    u, hyms, _ = _uow()
    with pytest.raises(ErrorNegocio, match="descripción"):
        _entrada(u, hyms, codigo="LAMHP11012502400", unidades=265)
    r = _entrada(u, hyms, codigo="lamhp11012502400", unidades=265, descripcion="Lamina L.F. 1,10mm x 1250mm x 2400mm",
                 peso_unitario_kg=D("26.565"))
    p = u.piezas.obtener(r.pieza_id)
    assert r.tipo == "lamina" and p.codigo_fisico == "LAMHP11012502400"
    assert (p.espesor_mm, p.ancho_mm, p.largo_mm, p.tipo_acero_codigo) == (D("1.1"), D("1250"), D("2400"), "HP")
    assert any("catálogo" in a for a in r.avisos)


def test_nota_de_entrega_en_piezas_al_peso_medio_y_anulacion():
    u, hyms, otro = _uow()
    pid = _entrada(u, hyms, unidades=100).pieza_id     # 100 x 4,2 = 420 kg
    datos = dict(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": pid, "unidades": 30}])
    previa = salidas.nota_entrega(u, NotaEntregaIn(**datos), **U)
    assert previa.lineas[0].unidades == 30 and previa.lineas[0].kg == D("126.000")
    hecha = salidas.nota_entrega(u, NotaEntregaIn(**datos, confirmar=True), **U)
    p = u.piezas.obtener(pid)
    assert p.saldo_unidades == 70 and p.saldo_kg == D("294.000")
    with pytest.raises(ErrorNegocio, match="piezas"):     # una lámina no sale en kg
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id,
                                              lineas=[{"pieza_id": pid, "kg": D("10")}]), **U)
    with pytest.raises(ErrorNegocio, match="hay 70"):
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id,
                                              lineas=[{"pieza_id": pid, "unidades": 71}]), **U)
    toda = salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": pid}],
                                                 confirmar=True), **U)   # vacío = todas las piezas
    p = u.piezas.obtener(pid)
    assert p.saldo_unidades == 0 and p.saldo_kg == 0 and p.estado == "agotado"
    salidas.anular(u, toda.documento_id, "se cargó por error", **U)
    salidas.anular(u, hecha.documento_id, "también", **U)
    p = u.piezas.obtener(pid)
    assert p.saldo_unidades == 100 and p.saldo_kg == D("420.000") and p.estado == "disponible"


def test_ajuste_por_conteo_y_liberacion_pendiente():
    u, hyms, otro = _uow()
    pid = _entrada(u, hyms, unidades=10).pieza_id     # 42 kg
    mv = salidas.ajustar(u, pid, D("0"), "conteo físico del patio", fecha=HOY, saldo_nuevo_unidades=8, **U)
    assert mv.unidades == -2 and mv.kg == D("-8.400")
    mv = salidas.ajustar(u, pid, D("0"), "aparecieron en el patio", fecha=HOY, saldo_nuevo_unidades=12, **U)
    assert mv.unidades == 4 and u.piezas.obtener(pid).saldo_kg == D("50.400")
    with pytest.raises(ErrorNegocio, match="piezas"):
        salidas.ajustar(u, pid, D("10"), "sin piezas", fecha=HOY, **U)
    with pytest.raises(ErrorNegocio, match="todavía no"):
        salidas.liberacion(u, LiberacionIn(numero="L-1", fecha=HOY, propietario_actual_id=hyms.id,
                                           propietario_nuevo_id=otro.id, piezas=[pid]), **U)


def test_una_bobina_sigue_moviendose_en_kg():
    u, hyms, _ = _uow()
    from tests.test_casos_uso import _entrada as entrada_bobina
    pid = entrada_bobina(u, hyms).pieza_id
    with pytest.raises(ErrorNegocio, match="kg"):
        inventario.registrar_movimiento(u, pid, "salida", None, unidades=-1, **U)


def test_descargar_material_rezagado_de_una_ne_historica():
    from app.esquemas import DescargaHistoricaIn
    from tests.test_laminas import _entrada as _bobina
    u, hyms, otro = _uow()
    tubos = _entrada(u, hyms, unidades=100).pieza_id
    fleje = _bobina(u, hyms, codigo="F7079-1", peso="1200", ancho="268").pieza_id
    ne = u.documentos.agregar(e.Documento(None, "nota_entrega", numero="7079", fecha=dt.date(2026, 10, 9),
                                          tercero_id=hyms.id, origen="excel"))
    previa = salidas.descargar_historica(u, ne.id, DescargaHistoricaIn(lineas=[{"pieza_id": fleje}, {"pieza_id": tubos, "unidades": 30}]), **U)
    assert not previa.guardada and previa.total_kg == D("1326.000") and previa.numero == "7079"
    r = salidas.descargar_historica(u, ne.id, DescargaHistoricaIn(lineas=[{"pieza_id": fleje}, {"pieza_id": tubos, "unidades": 30}],
                                                                  confirmar=True), **U)
    assert r.guardada
    assert u.piezas.obtener(fleje).saldo_kg == 0 and u.piezas.obtener(tubos).saldo_unidades == 70
    movs = u.movimientos.por_documento(ne.id)
    assert len(movs) == 2 and all(m.fecha == dt.date(2026, 10, 9) for m in movs)   # con la fecha de la NE
    # solo NE históricas y del material de su cliente
    app_ne = salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": tubos, "unidades": 1}],
                                                   confirmar=True), **U)
    with pytest.raises(ErrorNegocio, match="solo las NE del histórico"):
        salidas.descargar_historica(u, app_ne.documento_id, DescargaHistoricaIn(lineas=[{"pieza_id": tubos, "unidades": 1}]), **U)
    ajeno = _entrada(u, otro, unidades=5).pieza_id
    with pytest.raises(ErrorNegocio, match="no de Aceros"):
        salidas.descargar_historica(u, ne.id, DescargaHistoricaIn(lineas=[{"pieza_id": ajeno}]), **U)
