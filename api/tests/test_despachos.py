"""Orden de despacho del cliente, reservas y nota de salida (adaptador en memoria)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.errores import ErrorNegocio
from app.esquemas import NotaEntregaIn, NotaSalidaIn, OrdenDespachoIn, PlanOtIn
from app.servicios import despachos, planificacion, salidas
from tests.test_existencias import _entrada as _tubos
from tests.test_existencias import _uow
from tests.test_laminas import _entrada as _bobina

U = dict(usuario="prueba", origen="interfaz")
HOY = dt.date(2026, 11, 12)


def _od(u, cliente, lineas, confirmar=True, **extra):
    return despachos.crear(u, OrdenDespachoIn(fecha=HOY, lineas=lineas, confirmar=confirmar, **extra),
                           cliente=cliente.id, usuario="cliente@acerosvalle", origen="portal")


def test_el_cliente_pide_y_reserva_sus_piezas():
    u, hyms, otro = _uow()
    tubos = _tubos(u, hyms, unidades=100).pieza_id
    previa = _od(u, hyms, [{"pieza_id": tubos, "unidades": 60}], confirmar=False)
    assert not previa.guardada and previa.estado == "borrador" and previa.total_kg == D("252.000")
    od = _od(u, hyms, [{"pieza_id": tubos, "unidades": 60}],
             retiro={"retira": "José Pérez", "placa": "A12BC3D", "fecha_retiro": "2026-11-13"})
    assert od.guardada and od.numero == "1" and od.estado == "pendiente" and od.retiro["placa"] == "A12BC3D"
    assert u.piezas.obtener(tubos).saldo_unidades == 100              # no mueve inventario

    # lo reservado no cuenta como disponible: ni otra orden ni una NE pueden tomarlo
    with pytest.raises(ErrorNegocio, match="solo hay 40 piezas libres"):
        _od(u, hyms, [{"pieza_id": tubos, "unidades": 50}])
    with pytest.raises(ErrorNegocio, match="reservadas en la orden de despacho 1"):
        salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id, lineas=[{"pieza_id": tubos}],
                                              confirmar=True), **U)
    assert salidas.nota_entrega(u, NotaEntregaIn(fecha=HOY, tercero_id=hyms.id,
                                                 lineas=[{"pieza_id": tubos, "unidades": 40}], confirmar=True), **U).guardada

    # un cliente no pide material de otro
    ajeno = _tubos(u, otro, unidades=5).pieza_id
    with pytest.raises(ErrorNegocio, match="no de Aceros"):
        _od(u, hyms, [{"pieza_id": ajeno}])


def test_la_bobina_reservada_no_entra_en_corte_ni_en_otra_salida():
    u, hyms, _ = _uow()
    pid = _bobina(u, hyms, codigo="B77", peso="5000", ancho="1200").pieza_id
    od = _od(u, hyms, [{"pieza_id": pid}])
    assert od.lineas[0].kg == D("5000")
    with pytest.raises(ErrorNegocio, match="reservado en la orden de despacho 1"):
        planificacion.planificar(u, PlanOtIn(fecha=HOY, tipo="lamina", pieza_id=pid, largo_mm=D("2400")), **U)
    with pytest.raises(ErrorNegocio, match="reservado en la orden de despacho"):
        _od(u, hyms, [{"pieza_id": pid}])
    despachos.anular(u, od.id, "el cliente cambió de idea", cliente=hyms.id, **U)
    assert despachos.reservada_en(u, pid) is None                    # anular libera
    assert planificacion.planificar(u, PlanOtIn(fecha=HOY, tipo="lamina", pieza_id=pid, largo_mm=D("2400")), **U)


def test_nota_de_salida_mueve_inventario_y_cierra_la_orden():
    u, hyms, _ = _uow()
    tubos = _tubos(u, hyms, unidades=100).pieza_id
    pid = _bobina(u, hyms, codigo="B78", peso="4000").pieza_id
    od = _od(u, hyms, [{"pieza_id": tubos, "unidades": 60}, {"pieza_id": pid}])

    previa = despachos.nota_salida(u, od.id, NotaSalidaIn(fecha=HOY), **U)
    assert not previa.guardada and previa.total_kg == D("4252.000")
    # sale menos de lo pedido: el resto queda libre
    ns = despachos.nota_salida(u, od.id, NotaSalidaIn(fecha=HOY, confirmar=True,
                                                      lineas=[{"pieza_id": tubos, "unidades": 50}, {"pieza_id": pid}]), **U)
    assert ns.guardada and ns.numero == "1" and ns.tipo == "nota_salida"
    assert any("salen 50 de 60" in a for a in ns.avisos)
    assert u.piezas.obtener(tubos).saldo_unidades == 50 and u.piezas.obtener(pid).saldo_kg == 0
    orden = u.documentos.obtener(od.id)
    assert orden.estado == "despachada" and orden.encabezado["nota_salida"]["numero"] == "1"
    assert despachos.unidades_reservadas(u, tubos) == (0, [])
    with pytest.raises(ErrorNegocio, match="no está pendiente"):
        despachos.nota_salida(u, od.id, NotaSalidaIn(fecha=HOY, confirmar=True), **U)
    with pytest.raises(ErrorNegocio, match="anula primero la nota de salida"):
        despachos.anular(u, od.id, "ya no la quiere", **U)

    # anular la nota devuelve el material y la orden vuelve a pendiente, con su reserva
    salidas.anular(u, ns.documento_id, "se cargó en el camión equivocado", **U)
    assert u.piezas.obtener(tubos).saldo_unidades == 100
    assert u.documentos.obtener(od.id).estado == "pendiente"
    assert despachos.unidades_reservadas(u, tubos)[0] == 60


def test_la_nota_solo_lleva_piezas_de_su_orden_y_el_personal_indica_el_cliente():
    u, hyms, _ = _uow()
    tubos = _tubos(u, hyms, unidades=10).pieza_id
    pid = _bobina(u, hyms, codigo="B79").pieza_id
    with pytest.raises(ErrorNegocio, match="indica el cliente"):
        despachos.crear(u, OrdenDespachoIn(fecha=HOY, lineas=[{"pieza_id": tubos}], confirmar=True), **U)
    od = despachos.crear(u, OrdenDespachoIn(tercero_id=hyms.id, fecha=HOY, lineas=[{"pieza_id": tubos}],
                                            confirmar=True), usuario="agente", origen="agente")
    assert od.lineas[0].unidades == 10 and od.origen == "agente"
    with pytest.raises(ErrorNegocio, match="no está en la orden"):
        despachos.nota_salida(u, od.id, NotaSalidaIn(fecha=HOY, lineas=[{"pieza_id": pid}]), **U)


def test_pdf_de_orden_y_nota():
    from app.adaptadores.pdf.reportlab_slitter import GeneradorReportlab
    from app.dominio.impresion import DespachoImpreso, RenglonRecibo
    r = [RenglonRecibo(D("60"), "Pza", "Tubo L.F. 1'' x 1'' x 0,90mm x 6000mm", "TUB000HPE090A00001A00001L06000",
                       D("4.2"), D("252")), RenglonRecibo(D("1"), "Bob", "Bobina LAM FRIO 0,90 x 1200", "B78", None,
                                                          D("4000"))]
    g = GeneradorReportlab()
    for tipo, estado in (("orden_despacho", "pendiente"), ("nota_salida", "emitida"), ("orden_despacho", "anulada")):
        d = DespachoImpreso(tipo, "7", HOY, "Aceros del Valle, C.A.", "J-1", estado, "Nota de salida N° 1",
                            r * (12 if estado == "anulada" else 1), {"retira": "José Pérez", "placa": "A12BC3D",
                                                                     "fecha_retiro": "2026-11-13"},
                            "Retira en la mañana", "cliente@acerosvalle", dt.datetime(2026, 11, 12, 9, 30))
        assert g.despacho(d).startswith(b"%PDF")
