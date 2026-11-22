"""Pruebas de la API contra un PostgreSQL real (en CI lo levanta GitHub Actions).

Se saltan si no hay DATABASE_URL.
"""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

os.environ.setdefault("PROSIFER_API_KEY", "clave-de-prueba")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = {"X-Api-Key": os.environ["PROSIFER_API_KEY"], "X-Usuario": "prueba", "X-Origen": "interfaz"}


@pytest.fixture(scope="session")
def cliente():
    cfg = Config(os.path.join(AQUI, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(AQUI, "migraciones"))
    command.upgrade(cfg, "head")
    return TestClient(app)


@pytest.fixture
def dueno(cliente):
    r = cliente.post("/api/terceros", json={"nombre": f"Cliente {uuid.uuid4().hex[:8]}"}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def _entrada(dueno, codigo, confirmar, **extra):
    return {"documento_numero": "PL-1", "fecha": "2026-11-01", "codigo_bobina": codigo, "tipo_acero": "LAM FRIO",
            "espesor_mm": "0.88", "ancho_mm": "1220", "peso_kg": "6250", "propietario_id": dueno["id"],
            "confirmar": confirmar, **extra}


def test_salud_y_clave(cliente):
    assert cliente.get("/api/salud").json() == {"ok": True}
    assert cliente.get("/api/existencias").status_code == 401
    assert cliente.get("/api/existencias", headers={"X-Api-Key": "otra"}).status_code == 401


def test_catalogo_inicial(cliente):
    codigos = {t["codigo"] for t in cliente.get("/api/catalogos/tipos-acero", headers=H).json()}
    assert codigos == {"HP", "HN", "GV", "ES", "PP", "AL"}


def test_entrada_con_confirmacion(cliente, dueno):
    codigo = f"T-{uuid.uuid4().hex[:10]}"
    previa = cliente.post("/api/entradas/bobinas", json=_entrada(dueno, codigo, False), headers=H).json()
    assert previa["guardada"] is False
    assert previa["codigo_producto"] == "BOBHP0881220"
    assert any("se vende como 0.90" in a for a in previa["avisos"])
    assert cliente.get("/api/existencias", params={"codigo": codigo}, headers=H).json()["total_piezas"] == 0

    hecha = cliente.post("/api/entradas/bobinas", json=_entrada(dueno, codigo, True), headers=H).json()
    assert hecha["guardada"] is True and hecha["pieza_id"]

    ex = cliente.get("/api/existencias", params={"codigo": codigo}, headers=H).json()
    assert ex["total_piezas"] == 1 and float(ex["total_kg"]) == 6250
    assert ex["piezas"][0]["estado"] == "disponible"

    ficha = cliente.get(f"/api/piezas/{hecha['pieza_id']}", headers=H).json()
    assert [m["tipo"] for m in ficha["movimientos"]] == ["entrada"]


def test_codigo_repetido_rechazado(cliente, dueno):
    codigo = f"T-{uuid.uuid4().hex[:10]}"
    assert cliente.post("/api/entradas/bobinas", json=_entrada(dueno, codigo, True), headers=H).status_code == 200
    r = cliente.post("/api/entradas/bobinas", json=_entrada(dueno, codigo.lower(), True), headers=H)
    assert r.status_code == 409


def test_idempotencia(cliente, dueno):
    codigo = f"T-{uuid.uuid4().hex[:10]}"
    cuerpo = _entrada(dueno, codigo, True, clave_idempotencia=f"n8n-{codigo}")
    a = cliente.post("/api/entradas/bobinas", json=cuerpo, headers=H).json()
    b = cliente.post("/api/entradas/bobinas", json=cuerpo, headers=H).json()
    assert a["pieza_id"] == b["pieza_id"]


def test_editar_pieza_queda_auditada(cliente, dueno):
    codigo = f"T-{uuid.uuid4().hex[:10]}"
    pid = cliente.post("/api/entradas/bobinas", json=_entrada(dueno, codigo, True), headers=H).json()["pieza_id"]
    r = cliente.patch(f"/api/piezas/{pid}", json={"buque": "MV Prueba"}, headers=H)
    assert r.status_code == 200 and r.json()["buque"] == "MV Prueba"


def test_tipo_desconocido(cliente, dueno):
    r = cliente.post("/api/entradas/bobinas", json=_entrada(dueno, "T-X", False, tipo_acero="COBRE"), headers=H)
    assert r.status_code == 422
