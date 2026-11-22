"""Roles y permisos contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

os.environ.setdefault("PROSIFER_API_KEY", "clave-de-prueba")

from app.config import config  # noqa: E402
from app.db import SesionLocal  # noqa: E402
from app.adaptadores.sql import usuarios  # noqa: E402
from tests.test_api import H, cliente  # noqa: E402,F401  (fixture que migra la base)

CLAVE = "bobina2026fleje"


def _usuario(rol, tercero_id=None):
    correo = f"{rol}-{uuid.uuid4().hex[:8]}@prueba.com"
    with SesionLocal() as s:
        usuarios.crear(s, config.empresa_id, correo=correo, nombre=rol.title(), rol=rol, clave=CLAVE,
                       tercero_id=tercero_id)
        s.commit()
    return correo


def _entrar(cliente, correo, clave=CLAVE):
    r = cliente.post("/api/auth/ingresar", json={"correo": correo, "clave": clave})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['ficha']}"}


def _tercero(cliente):
    return cliente.post("/api/terceros", json={"nombre": f"Cliente {uuid.uuid4().hex[:8]}"}, headers=H).json()


def _bobina(cliente, dueno_id):
    codigo = f"U-{uuid.uuid4().hex[:10]}"
    r = cliente.post("/api/entradas/bobinas", headers=H, json={
        "documento_numero": "PL-9", "fecha": "2026-11-01", "codigo_bobina": codigo, "tipo_acero": "HP",
        "espesor_mm": "0.9", "ancho_mm": "1220", "peso_kg": "5000", "propietario_id": dueno_id,
        "confirmar": True})
    return r.json()["pieza_id"]


def test_ingreso_y_clave_incorrecta(cliente):
    correo = _usuario("asistente")
    h = _entrar(cliente, correo.upper())  # el correo no distingue mayúsculas
    assert cliente.get("/api/auth/yo", headers=h).json()["rol"] == "asistente"
    assert cliente.post("/api/auth/ingresar", json={"correo": correo, "clave": "otra2026clave"}).status_code == 401
    assert cliente.get("/api/auth/yo", headers={"Authorization": "Bearer basura.basura"}).status_code == 401


def test_cliente_solo_ve_lo_suyo(cliente):
    mio, ajeno = _tercero(cliente), _tercero(cliente)
    p_mia, p_ajena = _bobina(cliente, mio["id"]), _bobina(cliente, ajeno["id"])
    h = _entrar(cliente, _usuario("cliente", mio["id"]))

    ex = cliente.get("/api/existencias", params={"propietario_id": ajeno["id"]}, headers=h).json()
    assert {p["propietario_id"] for p in ex["piezas"]} == {mio["id"]}
    assert cliente.get(f"/api/piezas/{p_mia}", headers=h).status_code == 200
    assert cliente.get(f"/api/piezas/{p_ajena}", headers=h).status_code == 404
    assert cliente.get("/api/terceros", headers=h).status_code == 403
    assert cliente.patch(f"/api/piezas/{p_mia}", json={"buque": "x"}, headers=h).status_code == 403


def test_solo_el_socio_anula(cliente):
    pid = _bobina(cliente, _tercero(cliente)["id"])
    asistente = _entrar(cliente, _usuario("asistente"))
    socio = _entrar(cliente, _usuario("socio"))
    motivo = {"motivo": "cargada por error en prueba"}
    assert cliente.request("DELETE", f"/api/piezas/{pid}", json=motivo, headers=asistente).status_code == 403
    assert cliente.request("DELETE", f"/api/piezas/{pid}", json=motivo, headers=H).status_code == 403
    r = cliente.request("DELETE", f"/api/piezas/{pid}", json=motivo, headers=socio)
    assert r.status_code == 200
    assert cliente.get(f"/api/piezas/{pid}", headers=socio).status_code == 200  # sigue existiendo, anulada


def test_gestion_de_usuarios(cliente):
    socio = _entrar(cliente, _usuario("socio"))
    asistente = _entrar(cliente, _usuario("asistente"))
    assert cliente.get("/api/usuarios", headers=asistente).status_code == 403
    assert cliente.get("/api/usuarios", headers=H).status_code == 403

    nuevo = {"correo": f"n-{uuid.uuid4().hex[:6]}@prueba.com", "nombre": "Nueva", "rol": "asistente",
             "clave": CLAVE}
    r = cliente.post("/api/usuarios", json=nuevo, headers=socio)
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert cliente.post("/api/usuarios", json=nuevo, headers=socio).status_code == 409  # correo repetido
    assert cliente.post("/api/usuarios", json={**nuevo, "correo": "x@prueba.com", "clave": "corta"},
                        headers=socio).status_code == 422
    assert cliente.post("/api/usuarios", json={**nuevo, "correo": "otro@x.com", "rol": "cliente"},
                        headers=socio).status_code == 422  # cliente sin tercero

    h = _entrar(cliente, nuevo["correo"])
    cliente.patch(f"/api/usuarios/{uid}", json={"activo": False}, headers=socio)
    assert cliente.get("/api/auth/yo", headers=h).status_code == 401  # desactivar aplica al momento
