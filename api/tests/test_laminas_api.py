"""OC de corte a lámina por la API, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_ordenes import _bobina  # noqa: E402
from tests.test_usuarios import _entrar, _usuario  # noqa: E402


def test_oc_laminadora_pdfs_listado_y_anulacion(cliente):
    pid, codigo = _bobina(cliente, peso="6844", ancho="1250")
    cuerpo = {"maquina": "lamina", "pieza_id": pid, "fecha": "2026-11-10", "estatus_corte": "total",
              "largo_mm": "2400", "atados": [100, 100, 65], "segunda_a": 3, "calidad": "1er-F"}
    previa = cliente.post("/api/ot/lamina", json=cuerpo, headers=H)
    assert previa.status_code == 200, previa.text
    assert previa.json()["total_laminas"] == 268 and previa.json()["numero"] >= 1086
    hecha = cliente.post("/api/ot/lamina", json={**cuerpo, "confirmar": True}, headers=H).json()
    assert hecha["guardada"]

    for doc in ("orden", "etiquetas"):
        r = cliente.get(f"/api/ot/{hecha['orden_id']}/pdf/{doc}", headers=H)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
    uno = cliente.get(f"/api/ot/{hecha['orden_id']}/pdf/etiquetas", params={"atados": "2"}, headers=H)
    assert uno.status_code == 200 and uno.content.startswith(b"%PDF")

    det = cliente.get(f"/api/ot/{hecha['orden_id']}", headers=H).json()
    assert det["orden"]["piezas_producidas"] == 268 and len(det["producidas"]) == 2
    assert any(o["id"] == hecha["orden_id"] for o in cliente.get("/api/ot?tipo=lamina", headers=H).json())

    socio = _entrar(cliente, _usuario("socio"))
    r = cliente.request("DELETE", f"/api/ot/{hecha['orden_id']}", json={"motivo": "orden de prueba"}, headers=socio)
    assert r.status_code == 200, r.text
    assert float(cliente.get(f"/api/piezas/{pid}", headers=H).json()["pieza"]["saldo_kg"]) == 6844
