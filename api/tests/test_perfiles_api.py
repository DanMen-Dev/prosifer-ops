"""Maquila de perfiles por la API, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_ordenes import _bobina, _orden  # noqa: E402


def test_maquila_por_la_api(cliente):
    pid, _ = _bobina(cliente)
    oc = cliente.post("/api/ot/slitter", json=_orden(pid, True), headers=H).json()
    flejes = [p["id"] for p in cliente.get(f"/api/ot/{oc['orden_id']}", headers=H).json()["producidas"][:2]]
    codigo = f"PERHNVIG{uuid.uuid4().hex[:6].upper()}"
    cuerpo = {"fecha": "2026-11-10", "flejes": [{"pieza_id": f} for f in flejes], "codigo_producto": codigo,
              "descripcion": "Perfil LC Vigueta de prueba", "peso_teorico_kg": "8.478", "paquetes": [50, 50, 30],
              "segunda_a": 2}
    previa = cliente.post("/api/ot/maquila", json=cuerpo, headers=H)
    assert previa.status_code == 200, previa.text
    assert previa.json()["numero"] >= 319 and previa.json()["total_perfiles"] == 132
    hecha = cliente.post("/api/ot/maquila", json={**cuerpo, "confirmar": True}, headers=H).json()
    ex = cliente.get("/api/existencias", params={"tipo": "perfil", "codigo": codigo}, headers=H).json()
    assert ex["total_unidades"] == 132
    pdf = cliente.get(f"/api/ot/{hecha['orden_id']}/pdf/etiquetas", params={"atados": "1,3"}, headers=H)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert cliente.get(f"/api/ot/{hecha['orden_id']}", headers=H).json()["orden"]["piezas_producidas"] == 132
