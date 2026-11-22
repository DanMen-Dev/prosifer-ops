"""Existencias en piezas por la API, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_usuarios import _tercero  # noqa: E402


def test_entrada_inventario_y_nota_de_entrega_en_piezas(cliente):
    dueno = _tercero(cliente)
    codigo = f"TUB{uuid.uuid4().hex[:10].upper()}"
    cuerpo = {"codigo_producto": codigo, "descripcion": "Tubo de prueba 1'' x 1''", "propietario_id": dueno["id"],
              "unidades": 50, "peso_unitario_kg": "4.2", "documento_numero": "NE-1", "fecha": "2026-11-10"}
    previa = cliente.post("/api/entradas/existencias", json=cuerpo, headers=H)
    assert previa.status_code == 200, previa.text
    assert previa.json()["tipo"] == "general" and float(previa.json()["kg"]) == 210
    r1 = cliente.post("/api/entradas/existencias", json={**cuerpo, "confirmar": True}, headers=H).json()
    r2 = cliente.post("/api/entradas/existencias", json={**cuerpo, "unidades": 10, "confirmar": True}, headers=H).json()
    assert r1["pieza_id"] == r2["pieza_id"] and r2["existencia_despues"] == 60

    ex = cliente.get("/api/existencias", params={"tipo": "general", "codigo": codigo}, headers=H).json()
    assert ex["total_unidades"] == 60 and ex["piezas"][0]["saldo_unidades"] == 60

    ne = {"fecha": "2026-11-10", "tercero_id": dueno["id"], "lineas": [{"pieza_id": r1["pieza_id"], "unidades": 15}],
          "confirmar": True}
    hecha = cliente.post("/api/salidas/nota-entrega", json=ne, headers=H)
    assert hecha.status_code == 200, hecha.text
    assert float(hecha.json()["lineas"][0]["kg"]) == 63
    ficha = cliente.get(f"/api/piezas/{r1['pieza_id']}", headers=H).json()
    assert ficha["pieza"]["saldo_unidades"] == 45 and ficha["movimientos"][-1]["unidades"] == -15
    det = cliente.get(f"/api/documentos/{hecha.json()['documento_id']}", headers=H)
    assert det.status_code == 200 and det.json()["lineas"][0]["unidades"] == -15


def test_recibo_de_entrada_agrupa_el_documento_y_conserva_el_numero(cliente):
    dueno = _tercero(cliente)
    base = {"propietario_id": dueno["id"], "documento_numero": f"C-{uuid.uuid4().hex[:6]}", "fecha": "2026-11-11",
            "confirmar": True}
    a = cliente.post("/api/entradas/existencias", json={**base, "codigo_producto": f"TUB{uuid.uuid4().hex[:10].upper()}",
                     "descripcion": "Tubo A", "unidades": 46, "peso_unitario_kg": "10.17"}, headers=H).json()
    b = cliente.post("/api/entradas/existencias", json={**base, "codigo_producto": f"TUB{uuid.uuid4().hex[:10].upper()}",
                     "descripcion": "Tubo B", "unidades": 200, "peso_unitario_kg": "24.80"}, headers=H).json()
    assert a["documento_id"] and b["documento_id"] != a["documento_id"]
    n1 = cliente.post(f"/api/documentos/{a['documento_id']}/recibo/numero", headers=H).json()["numero"]
    n2 = cliente.post(f"/api/documentos/{b['documento_id']}/recibo/numero", headers=H).json()["numero"]
    assert n1 == n2                                     # un solo recibo para la carta del cliente
    pdf = cliente.get(f"/api/documentos/{b['documento_id']}/recibo", headers=H)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert f"Nro {n1}" in pdf.headers["content-disposition"]
    assert cliente.get(f"/api/documentos/{a['documento_id']}/recibo", headers=H).status_code == 200
    assert cliente.post(f"/api/documentos/{a['documento_id']}/recibo/numero", headers=H).json()["numero"] == n1
