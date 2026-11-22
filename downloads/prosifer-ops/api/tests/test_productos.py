"""Catálogo de productos, ficha de clientes y su importación, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid
from decimal import Decimal as D

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from app import modelos as m  # noqa: E402
from app.config import config  # noqa: E402
from app.db import SesionLocal  # noqa: E402
from importador import catalogos_excel as ce  # noqa: E402
from importador.cargar_catalogos import cargar  # noqa: E402
from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_usuarios import _entrar, _tercero, _usuario  # noqa: E402


def _cat(sufijo, nombre_existente):
    return ce.Catalogos(
        clientes=[ce.Cliente(5, f"Ferretería Nueva {sufijo}", rif=f"J-{sufijo}", ciudad="Valencia", vendedor="Oficina"),
                  ce.Cliente(6, nombre_existente.upper() + ".", direccion="Zona Industrial Sur", forma_pago="Contado",
                              telefono="0414-1111111")],
        productos=[ce.Producto(5, f"LAM{sufijo}", f"Lamina de prueba {sufijo} 1220mm x 2400mm", D("44.5100")),
                   ce.Producto(6, f"VIG{sufijo}", f"Viga de prueba {sufijo}", None)])


def test_importar_catalogos_es_repetible_y_no_pisa(cliente):
    existente = _tercero(cliente)                 # como un dueño que entró con el inventario
    cliente.patch(f"/api/terceros/{existente['id']}", json={"telefono": "0241-0000000"}, headers=H)
    suf = uuid.uuid4().hex[:8].upper()
    with SesionLocal() as s:
        r1 = cargar(s, _cat(suf, existente["nombre"]), config.empresa_id)
        s.commit()
    assert r1["clientes_nuevos"] == 1 and r1["clientes_completados"] == 1 and r1["productos_nuevos"] == 2
    with SesionLocal() as s:
        r2 = cargar(s, _cat(suf, existente["nombre"]), config.empresa_id)
        s.commit()
        t = s.get(m.Tercero, existente["id"])
        assert t.direccion == "Zona Industrial Sur" and t.telefono == "0241-0000000"   # completa, no pisa
    assert r2 == {"clientes_nuevos": 0, "clientes_completados": 0, "productos_nuevos": 0, "productos_con_peso": 0}

    por_rif = cliente.get("/api/terceros", params={"q": f"J-{suf}"}, headers=H).json()
    assert [t["nombre"] for t in por_rif] == [f"Ferretería Nueva {suf}"] and por_rif[0]["vendedor"] == "Oficina"


def test_productos_buscar_crear_editar(cliente):
    suf = uuid.uuid4().hex[:8].upper()
    r = cliente.post("/api/productos", json={"codigo": f"tub{suf}", "nombre": "Tubo  L.F. 1'' x 1'' x 0,90mm x 6000mm",
                                             "peso_unitario_kg": "8.2"}, headers=H)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["codigo"] == f"TUB{suf}" and p["nombre"] == "Tubo L.F. 1'' x 1'' x 0,90mm x 6000mm"
    assert cliente.post("/api/productos", json={"codigo": f"TUB{suf}", "nombre": "otro"}, headers=H).status_code == 409

    hallados = cliente.get("/api/productos", params={"q": f"tubo {suf.lower()}"}, headers=H).json()
    assert [x["id"] for x in hallados] == [p["id"]]

    cliente.patch(f"/api/productos/{p['id']}", json={"activo": False, "peso_unitario_kg": "8.25"}, headers=H)
    assert cliente.get("/api/productos", params={"q": suf}, headers=H).json() == []
    todos = cliente.get("/api/productos", params={"q": suf, "incluir_inactivos": True}, headers=H).json()
    assert D(todos[0]["peso_unitario_kg"]) == D("8.25")


def test_sin_codigo_la_app_lo_asigna(cliente):
    # puertas y otros sin familia en el generador: prefijo del nombre + correlativo
    a = cliente.post("/api/productos", json={"nombre": "Zúrdo Puerta Metálica Modelo Flor"}, headers=H)
    b = cliente.post("/api/productos", json={"nombre": "Zurdo Puerta Metálica Modelo Tetris", "codigo": ""}, headers=H)
    assert a.status_code == 201 and b.status_code == 201, (a.text, b.text)
    ca, cb = a.json()["codigo"], b.json()["codigo"]
    assert ca.startswith("ZUR") and len(ca) == 7 and int(cb[3:]) == int(ca[3:]) + 1
    assert cliente.post("/api/productos", json={"nombre": "x", "codigo": "AB"}, headers=H).status_code == 422


def test_cliente_consulta_el_catalogo_pero_no_lo_cambia(cliente):
    # Desde el aviso de entrada el cliente elige el producto por su nombre: ve el catálogo activo
    # (sin el material de medidas irregulares, que no se anuncia), pero no crea ni cambia productos.
    h = _entrar(cliente, _usuario("cliente", _tercero(cliente)["id"]))
    assert cliente.get("/api/productos", headers=h).status_code == 200
    assert cliente.get("/api/productos", params={"q": "MATERIALESIRREG"}, headers=h).json() == []
    suf = uuid.uuid4().hex[:6].upper()
    assert cliente.post("/api/productos", json={"codigo": f"TUB{suf}", "nombre": "no"}, headers=h).status_code == 403
