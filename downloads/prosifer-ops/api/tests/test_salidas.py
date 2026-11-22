"""Notas de entrega, liberaciones y ajustes contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_usuarios import _entrar, _usuario  # noqa: E402


def _tercero(cliente):
    return cliente.post("/api/terceros", json={"nombre": f"T {uuid.uuid4().hex[:8]}"}, headers=H).json()["id"]


def _bobina(cliente, dueno, peso="5000"):
    r = cliente.post("/api/entradas/bobinas", headers=H, json={
        "documento_numero": "PL-1", "fecha": "2026-11-01", "codigo_bobina": f"N-{uuid.uuid4().hex[:10]}",
        "tipo_acero": "HP", "espesor_mm": "0.9", "ancho_mm": "1220", "peso_kg": peso, "propietario_id": dueno,
        "confirmar": True})
    return r.json()["pieza_id"]


def _saldo(cliente, pid):
    return float(cliente.get(f"/api/piezas/{pid}", headers=H).json()["pieza"]["saldo_kg"])


def test_nota_entrega_parcial_y_total(cliente):
    dueno = _tercero(cliente)
    a, b = _bobina(cliente, dueno), _bobina(cliente, dueno, "3000")
    ne = {"numero": f"NE-{uuid.uuid4().hex[:6]}", "fecha": "2026-11-08", "tercero_id": dueno,
          "lineas": [{"pieza_id": a, "kg": "1200"}, {"pieza_id": b}]}
    previa = cliente.post("/api/salidas/nota-entrega", json={**ne, "confirmar": False}, headers=H).json()
    assert previa["guardada"] is False and float(previa["total_kg"]) == 4200
    assert _saldo(cliente, a) == 5000

    hecha = cliente.post("/api/salidas/nota-entrega", json={**ne, "confirmar": True, "clave_idempotencia": ne["numero"]},
                         headers=H).json()
    assert hecha["guardada"] and _saldo(cliente, a) == 3800 and _saldo(cliente, b) == 0
    assert hecha["numero"].isdigit()  # lo asigna el sistema
    assert cliente.post("/api/salidas/nota-entrega", json={**ne, "confirmar": True, "clave_idempotencia": ne["numero"]},
                        headers=H).status_code == 409

    otra = {**ne, "lineas": [{"pieza_id": a, "kg": "1000"}]}
    segunda = cliente.post("/api/salidas/nota-entrega", json={**otra, "confirmar": True}, headers=H)
    assert segunda.status_code == 200 and int(segunda.json()["numero"]) == int(hecha["numero"]) + 1
    assert _saldo(cliente, a) == 2800  # sin límite de notas parciales

    det = cliente.get(f"/api/documentos/{hecha['documento_id']}", headers=H).json()
    assert len(det["lineas"]) == 2 and float(det["documento"]["total_kg"]) == 4200

    # Anular devuelve los kg (solo socio)
    socio = _entrar(cliente, _usuario("socio"))
    m = {"motivo": "nota cargada por error"}
    assert cliente.request("DELETE", f"/api/documentos/{hecha['documento_id']}", json=m, headers=H).status_code == 403
    assert cliente.request("DELETE", f"/api/documentos/{hecha['documento_id']}", json=m, headers=socio).status_code == 200
    assert _saldo(cliente, a) == 4000 and _saldo(cliente, b) == 3000


def test_reglas_de_la_nota(cliente):
    dueno, otro = _tercero(cliente), _tercero(cliente)
    a = _bobina(cliente, dueno)
    base = {"numero": "X", "fecha": "2026-11-08", "confirmar": False}
    ajena = cliente.post("/api/salidas/nota-entrega", json={**base, "tercero_id": otro, "lineas": [{"pieza_id": a}]},
                         headers=H)
    assert ajena.status_code == 422
    demas = cliente.post("/api/salidas/nota-entrega",
                         json={**base, "tercero_id": dueno, "lineas": [{"pieza_id": a, "kg": "6000"}]}, headers=H)
    assert demas.status_code == 422
    resto = cliente.post("/api/salidas/nota-entrega",
                         json={**base, "tercero_id": dueno, "lineas": [{"pieza_id": a, "kg": "4980"}]}, headers=H).json()
    assert any("resto de 20" in x for x in resto["avisos"])


def test_liberacion_pieza_completa(cliente):
    actual, nuevo = _tercero(cliente), _tercero(cliente)
    a = _bobina(cliente, actual)
    lib = {"numero": f"L-{uuid.uuid4().hex[:6]}", "fecha": "2026-11-08", "propietario_actual_id": actual,
           "propietario_nuevo_id": nuevo, "piezas": [a], "confirmar": True}
    r = cliente.post("/api/salidas/liberacion", json=lib, headers=H)
    assert r.status_code == 200, r.text
    p = cliente.get(f"/api/piezas/{a}", headers=H).json()["pieza"]
    assert p["propietario_id"] == nuevo and float(p["saldo_kg"]) == 5000
    assert cliente.post("/api/salidas/liberacion", json={**lib, "numero": "otra"}, headers=H).status_code == 422

    socio = _entrar(cliente, _usuario("socio"))
    cliente.request("DELETE", f"/api/documentos/{r.json()['documento_id']}", json={"motivo": "error de dueño"},
                    headers=socio)
    assert cliente.get(f"/api/piezas/{a}", headers=H).json()["pieza"]["propietario_id"] == actual


def test_ajuste_solo_socio_o_agente(cliente):
    # La asistente no ajusta; el socio sí, y el agente (clave de la API) también: Prosi solo lo hace
    # después de que un aprobador lo confirma en el grupo (parche 0054).
    a = _bobina(cliente, _tercero(cliente))
    socio = _entrar(cliente, _usuario("socio"))
    asistente = _entrar(cliente, _usuario("asistente"))
    cuerpo = {"saldo_nuevo_kg": "0", "motivo": "remanente que no existe en patio"}
    assert cliente.post(f"/api/piezas/{a}/ajuste", json=cuerpo, headers=asistente).status_code == 403
    r = cliente.post(f"/api/piezas/{a}/ajuste", json=cuerpo, headers=socio)
    assert r.status_code == 200 and float(r.json()["kg"]) == -5000
    assert cliente.get(f"/api/piezas/{a}", headers=H).json()["pieza"]["estado"] == "agotado"
    b = _bobina(cliente, _tercero(cliente))
    agente = {**H, "X-Origen": "agente"}
    r = cliente.post(f"/api/piezas/{b}/ajuste", json={**cuerpo, "motivo": "conteo en patio vía Prosi"}, headers=agente)
    assert r.status_code == 200 and float(r.json()["kg"]) == -5000
