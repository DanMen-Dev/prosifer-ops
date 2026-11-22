"""OC de corte a lámina (laminadora y CTF) con el adaptador en memoria."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
from app.dominio import laminas
from app.errores import ErrorNegocio
from app.esquemas import EntradaBobinaIn, NotaEntregaIn, OtLaminaIn
from app.servicios import impresion, inventario, ordenes, salidas
from tests.test_casos_uso import _uow

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 10)


def _entrada(u, dueno, codigo="C22600728510", peso="8235", ancho="1200", espesor=D("0.9")):
    return inventario.registrar_entrada_bobina(u, EntradaBobinaIn(
        documento_numero="PL-1", fecha=HOY, codigo_bobina=codigo, tipo_acero="LAM FRIO", espesor_mm=espesor,
        ancho_mm=D(ancho), peso_kg=D(peso), propietario_id=dueno.id, confirmar=True), **U)


def _ot(u, pid, confirmar=True, **extra):
    datos = dict(pieza_id=pid, fecha=HOY, estatus_corte="total", largo_mm=D("2400"), atados=[100, 100, 65],
                 calidad="1er-F", confirmar=confirmar)
    datos.update(extra)
    return ordenes.registrar_lamina(u, OtLaminaIn(**datos), generador=GeneradorReportlab(), **U)


def test_regla_peso_real_y_teorico():
    p = laminas.planificar(espesor=D("1.1"), ancho_pieza=D("1250"), consumido=D("6844"), largo_mm=D("2400"),
                           ancho_mm=None, atados=[100, 100, 65], segundas={"A": 0}, scrap_kg=D("0"))
    assert p.total_laminas == 265 and p.kg_por_lamina == D("25.826") and p.producido == D("6844.000")
    assert p.kg_teorico_por_lamina == D("25.905") and p.avisos == []      # 0,3 % del teórico
    con_2da = laminas.planificar(espesor=D("0.7"), ancho_pieza=D("1200"), consumido=D("1459.9"), largo_mm=D("2460"),
                                 ancho_mm=None, atados=[80], segundas={"A": 10}, scrap_kg=D("10"))
    assert [g.clase for g in con_2da.grupos] == ["1", "A"] and con_2da.producido == D("1449.900")
    with pytest.raises(laminas.CorteLaminaInvalido):
        laminas.planificar(espesor=D("0.7"), ancho_pieza=D("1200"), consumido=D("100"), largo_mm=D("2400"),
                           ancho_mm=D("1250"), atados=[1], segundas={})


def test_oc_lamina_total_suma_existencias_y_guarda_pdfs():
    u, hyms, otro = _uow()
    pid = _entrada(u, hyms, codigo="CS222505150011C033A", peso="6844", ancho="1250", espesor=D("1.1")).pieza_id
    previa = _ot(u, pid, confirmar=False, segunda_a=5)
    assert previa.numero == 1 and previa.total_laminas == 270
    assert [g.codigo_producto for g in previa.grupos] == ["LAMHP11012502400", "LAMHP11012502400-A"]
    assert previa.grupos[1].descripcion.endswith("(2A)") and previa.grupos[1].calidad == "2da-A"
    assert previa.atados[2].codigo == "LAMHP11012502400 / CS222505150011C033A / OC1 / AT3"

    hecha = _ot(u, pid, segunda_a=5)
    assert u.piezas.obtener(pid).estado == "agotado"
    primera = u.piezas.existencia("lamina", "LAMHP11012502400", hyms.id)
    assert primera.saldo_unidades == 265 and primera.ancho_mm == D("1250") and primera.largo_mm == D("2400")
    total_kg = primera.saldo_kg + u.piezas.existencia("lamina", "LAMHP11012502400-A", hyms.id).saldo_kg
    assert total_kg == D("6844.000")                                    # el balance cuadra
    assert u.archivos.buscar("orden_trabajo", hecha.orden_id, "etiquetas.pdf").startswith(b"%PDF")
    datos = impresion.orden_lamina(u, u.ordenes.obtener(hecha.orden_id))
    assert datos.maquina == "LAMINADORA" and [a.unidades for a in datos.atados] == [100, 100, 65]

    # Una segunda OC del mismo producto suma a la misma existencia
    pid2 = _entrada(u, hyms, codigo="B2", peso="2000", ancho="1250", espesor=D("1.1")).pieza_id
    _ot(u, pid2, atados=[77])
    assert u.piezas.existencia("lamina", "LAMHP11012502400", hyms.id).saldo_unidades == 342


def test_parcial_ctf_y_anulacion():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, peso="8345", ancho="1200", espesor=D("0.7")).pieza_id
    r = _ot(u, pid, maquina="ctf", estatus_corte="parcial", kg_procesado=D("1459.9"), largo_mm=D("2460"), atados=[90])
    assert r.maquina == "ctf" and r.saldo_restante_kg == D("6885.1") and u.piezas.obtener(pid).estado == "disponible"
    exist = u.piezas.existencia("lamina", "LAMHP07012002460", hyms.id)
    ordenes.anular(u, r.orden_id, "cargada por error", **U)
    assert u.piezas.obtener(pid).saldo_kg == D("8345") and u.piezas.obtener(exist.id).saldo_unidades == 0
    assert u.ordenes.obtener(r.orden_id).estado == "anulada"


def test_no_se_anula_si_ya_salieron_laminas():
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, peso="2000", ancho="1200", espesor=D("0.7")).pieza_id
    r = _ot(u, pid, atados=[100])
    fila = u.piezas.existencia("lamina", "LAMHP07012002400", hyms.id)
    salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": fila.id, "unidades": 10}],
                                          confirmar=True), **U)
    with pytest.raises(ErrorNegocio, match="ya salieron"):
        ordenes.anular(u, r.orden_id, "no debe poder", **U)


def test_numeracion_sigue_la_del_excel():
    u, hyms, _ = _uow()
    u.parametros.valores["ultima_oc_lamina"] = "1085"
    pid = _entrada(u, hyms, peso="2000", ancho="1200", espesor=D("0.7")).pieza_id
    assert _ot(u, pid, confirmar=False, atados=[10]).numero == 1086


def test_espesor_real_o_redondeado_a_eleccion():
    """Bobina de 0,58: por defecto la lámina lleva 0,58 en nombre y código; si se redondea, 0,60 en ambos."""
    u, hyms, _ = _uow()
    pid = _entrada(u, hyms, codigo="B058", peso="2000", ancho="1200", espesor=D("0.58")).pieza_id
    assert "0,58mm" in u.piezas.obtener(pid).descripcion                      # la bobina no se redondea
    real = _ot(u, pid, confirmar=False, atados=[50])
    assert real.espesor_real == D("0.58") and real.espesor_comercial == D("0.60")
    assert real.grupos[0].codigo_producto == "LAMHP05812002400" and "0,58mm" in real.grupos[0].descripcion
    red = _ot(u, pid, confirmar=False, atados=[50], redondear_espesor=True)
    assert red.grupos[0].codigo_producto == "LAMHP06012002400" and "0,60mm" in red.grupos[0].descripcion
    exacta = _entrada(u, hyms, codigo="B110", peso="2000", ancho="1250", espesor=D("1.1")).pieza_id
    assert _ot(u, exacta, confirmar=False, atados=[50]).espesor_comercial is None   # nada que preguntar
