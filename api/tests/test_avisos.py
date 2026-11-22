"""Aviso de entrada del cliente (adaptador en memoria)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from app.dominio import entidades as e
from app.errores import ErrorNegocio
from app.esquemas import AvisoEntradaIn
from app.servicios import avisos
from tests.test_casos_uso import _uow

U = dict(usuario="asistente", origen="interfaz")
HOY = dt.date(2026, 11, 13)


def _aviso(u, cliente, **extra):
    datos = dict(fecha_estimada="2026-11-16", documento_tipo="Nota de entrega", documento_numero="A-551",
                 proveedor="Sidor", transporte={"chofer": "Luis Rojas", "placa": "A45BC9K"},
                 renglones=[{"tipo": "bobina", "codigo": "C22600799001", "tipo_acero": "HP", "espesor_mm": "0.9",
                             "ancho_mm": "1200", "peso_kg": "8350"},
                            {"tipo": "general", "descripcion": "Tubo L.C. 100 x 40 x 2,00mm x 6,00mts",
                             "cantidad": 200, "peso_kg": "4960"}])
    datos.update(extra)
    return avisos.crear(u, AvisoEntradaIn(**datos), cliente=cliente.id, usuario="compras@acerosvalle.test",
                        origen="portal", hoy=HOY)


def test_el_cliente_anuncia_y_prosifer_recibe():
    u, hyms, otro = _uow()
    d = _aviso(u, hyms)
    assert d.estado == "pendiente" and d.numero == "1" and d.tercero_id == hyms.id
    assert d.encabezado["transporte"]["placa"] == "A45BC9K" and len(d.encabezado["renglones"]) == 2
    with pytest.raises(ErrorNegocio, match="aviso inexistente"):
        avisos.cancelar(u, d.id, "no es mío", cliente=otro.id, **U)
    with pytest.raises(ErrorNegocio, match="no suma inventario"):
        avisos.recibir(u, d.id, "Llegó completo", **U)          # sin entradas registradas
    bob = u.piezas.agregar(e.Pieza(None, "bobina", "C22600799001", hyms.id, D("8350"), D("8350"), "disponible", "x"))
    ajena = u.piezas.agregar(e.Pieza(None, "bobina", "AJENA1", otro.id, D("1"), D("1"), "disponible", "x"))
    with pytest.raises(ErrorNegocio, match="no es del cliente"):
        avisos.enlazar_entrada(u, d.id, 0, ajena.id, None, **U)
    d1 = avisos.enlazar_entrada(u, d.id, 0, bob.id, "Bobina C22600799001", **U)
    assert d1.encabezado["renglones"][0]["entrada"]["codigo"] == "C22600799001"
    assert avisos.sin_entrada(d1) == [1]
    with pytest.raises(ErrorNegocio, match="1 renglón"):
        avisos.recibir(u, d.id, None, **U)
    r = avisos.recibir(u, d.id, "Llegó completo, 2 bobinas en vez de 1", forzar=True, **U)
    assert r.estado == "recibido" and "completo" in r.encabezado["nota"]
    avisos.enlazar_entrada(u, d.id, 1, bob.id, None, **U)     # se puede registrar después de recibido
    with pytest.raises(ErrorNegocio, match="ya se cerró"):
        avisos.rechazar(u, d.id, "tarde", **U)


def test_validaciones_y_cancelacion():
    u, hyms, _ = _uow()
    with pytest.raises(ErrorNegocio, match="ya pasó"):
        _aviso(u, hyms, fecha_estimada="2026-11-01")
    with pytest.raises(ErrorNegocio, match="código o una descripción"):
        _aviso(u, hyms, renglones=[{"tipo": "lamina", "cantidad": 10}])
    with pytest.raises(ErrorNegocio, match="cantidad o el peso"):
        _aviso(u, hyms, renglones=[{"tipo": "lamina", "descripcion": "Lámina"}])
    with pytest.raises(ErrorNegocio, match="indica el cliente"):
        avisos.crear(u, AvisoEntradaIn(fecha_estimada="2026-11-16", renglones=[{"tipo": "bobina", "codigo": "X", "peso_kg": "1"}]),
                     cliente=None, usuario="agente", origen="agente", hoy=HOY)
    d = _aviso(u, hyms)
    assert avisos.cancelar(u, d.id, "se pospuso el envío", cliente=hyms.id, **U).estado == "cancelado"
    r = avisos.rechazar(u, _aviso(u, hyms).id, "no llegó en la fecha indicada", **U)
    assert r.estado == "rechazado"
