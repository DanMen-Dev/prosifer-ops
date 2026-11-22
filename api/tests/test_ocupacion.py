"""Inventario: se ve qué piezas están en una OC planificada o reservadas en una orden de despacho."""
from decimal import Decimal as D

from app.adaptadores.memoria import UnidadMemoria
from app.dominio import entidades as e
from app.esquemas import PiezaOut
from app.servicios import planificacion


def pieza_out(p):   # lo mínimo de PiezaOut (sin la capa SQL)
    return PiezaOut(id=p.id, tipo=p.tipo, codigo_fisico=p.codigo_fisico, codigo_producto=None, descripcion=None,
                    espesor_mm=None, ancho_mm=None, largo_mm=None, calidad=None, propietario_id=p.propietario_id,
                    propietario_nombre="", tipo_acero=None, norma=None, buque=None, pieza_origen_id=None,
                    fecha_entrada=None, peso_entrada_kg=p.peso_entrada_kg, saldo_kg=p.saldo_kg, estado=p.estado,
                    saldo_unidades=p.saldo_unidades)


def test_marca_en_proceso_y_reservas():
    u = UnidadMemoria()
    hyms = u.terceros.nuevo("HYMS")
    bob = u.piezas.agregar(e.Pieza(None, "bobina", "C1", hyms.id, D("8000"), D("8000"), "disponible", "x"))
    fle = u.piezas.agregar(e.Pieza(None, "fleje", "C1-1", hyms.id, D("500"), D("500"), "disponible", "x"))
    lam = u.piezas.agregar(e.Pieza(None, "lamina", "LAMHN25012002400", hyms.id, D("57.6"), D("9158.4"), "disponible", "x",
                                   unidades_entrada=159, saldo_unidades=159))
    libre = u.piezas.agregar(e.Pieza(None, "bobina", "C2", hyms.id, D("1"), D("1"), "disponible", "x"))
    u.ordenes.agregar(e.OrdenTrabajo(None, "slitter", 125, "planificada", D(0), D(0), D(0), "interfaz", "x", pieza_id=bob.id))
    for numero, lineas in (("7", [{"pieza_id": fle.id, "kg": "500"}, {"pieza_id": lam.id, "unidades": 20, "kg": "1"}]),
                           ("9", [{"pieza_id": lam.id, "unidades": 5, "kg": "1"}])):
        u.documentos.agregar(e.Documento(None, "orden_despacho", numero=numero, estado="pendiente",
                                         encabezado={"lineas": lineas}))
    piezas = [pieza_out(u.piezas.obtener(i)) for i in (bob.id, fle.id, lam.id, libre.id)]
    planificacion.marcar_ocupadas(u, piezas)
    b, f, l, x = piezas
    assert b.en_proceso == "OC slitter 125" and b.reservada_en is None
    assert f.reservada_en == "orden de despacho 7"
    assert l.reservada_en == "órdenes de despacho 7, 9" and l.unidades_reservadas == 25
    assert (x.en_proceso, x.reservada_en, x.unidades_reservadas) == (None, None, None)
