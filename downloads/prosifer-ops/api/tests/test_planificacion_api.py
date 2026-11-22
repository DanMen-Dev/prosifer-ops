"""OC planificada por la API, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_ordenes import _bobina  # noqa: E402


def test_planificar_hoja_resultados_y_cancelar(cliente):
    pid, _ = _bobina(cliente, peso="6844", ancho="1250")
    r = cliente.post("/api/ot/planificar", headers=H, json={
        "tipo": "lamina", "pieza_id": pid, "fecha": "2026-11-11", "largo_mm": "2400", "calidad": "1er-F"})
    assert r.status_code == 201, r.text
    plan = r.json()
    hoja = cliente.get(f"/api/ot/{plan['orden_id']}/hoja-trabajo", headers=H)
    assert hoja.status_code == 200 and hoja.content.startswith(b"%PDF")
    lista = cliente.get("/api/ot", params={"estado": "planificada"}, headers=H).json()
    fila = next(o for o in lista if o["id"] == plan["orden_id"])
    assert fila["plan"]["largo_mm"] == "2400" and fila["codigo_pieza"]
    assert all(o["id"] != plan["orden_id"] for o in cliente.get("/api/ot", headers=H).json())   # no en la lista normal

    ocupada = cliente.post("/api/ot/planificar", headers=H, json={
        "tipo": "ctf", "pieza_id": pid, "fecha": "2026-11-11", "largo_mm": "2000"})
    assert ocupada.status_code == 409

    cuerpo = {"maquina": "lamina", "pieza_id": pid, "fecha": "2026-11-11", "estatus_corte": "total",
              "largo_mm": "2400", "atados": [100, 100, 64], "orden_planificada_id": plan["orden_id"], "confirmar": True}
    hecha = cliente.post("/api/ot/lamina", json=cuerpo, headers=H)
    assert hecha.status_code == 200, hecha.text
    assert hecha.json()["numero"] == plan["numero"]
    assert cliente.post(f"/api/ot/{plan['orden_id']}/cancelar-plan", json={"motivo": "ya no"}, headers=H).status_code == 422

    pid2, _ = _bobina(cliente, peso="3000", ancho="1200")
    p2 = cliente.post("/api/ot/planificar", headers=H, json={
        "tipo": "slitter", "pieza_id": pid2, "fecha": "2026-11-11", "cortes": [{"ancho_mm": "300", "rollos": 4}]}).json()
    c = cliente.post(f"/api/ot/{p2['orden_id']}/cancelar-plan", json={"motivo": "cambio de pedido"}, headers=H)
    assert c.status_code == 200 and c.json()["estado"] == "anulada"
