"""Conteos físicos en patio (auditorías) contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_usuarios import _entrar, _tercero, _usuario  # noqa: E402


def _existencia(cliente, unidades=50):
    dueno = _tercero(cliente)
    cuerpo = {"codigo_producto": f"TUB{uuid.uuid4().hex[:10].upper()}", "descripcion": "Tubo de prueba 1'' x 1''",
              "propietario_id": dueno["id"], "unidades": unidades, "peso_unitario_kg": "4", "documento_numero": "NE-1",
              "fecha": "2026-11-10", "confirmar": True}
    return cliente.post("/api/entradas/existencias", json=cuerpo, headers=H).json()["pieza_id"], dueno


def _piezas(cliente, pid):
    return cliente.get(f"/api/piezas/{pid}", headers=H).json()["pieza"]["saldo_unidades"]


def test_conteo_que_cuadra_queda_registrado(cliente):
    pid, dueno = _existencia(cliente)
    asistente = _entrar(cliente, _usuario("asistente"))
    previa = cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 50, "confirmar": False}, headers=asistente)
    assert previa.status_code == 200 and previa.json()["guardado"] is False and previa.json()["estado"] == "cuadra"
    assert cliente.get("/api/conteos", params={"pieza_id": pid}, headers=H).json() == []

    r = cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 50, "contado_por": "Nacho", "fecha": "2026-11-19"},
                     headers=asistente)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["estado"] == "cuadra" and c["unidad"] == "pzas" and float(c["diferencia"]) == 0
    assert c["propietario_id"] == dueno["id"] and c["contado_por"] == "Nacho"
    ficha = cliente.get(f"/api/piezas/{pid}", headers=H).json()
    assert [x["id"] for x in ficha["conteos"]] == [c["id"]]
    assert [m["tipo"] for m in ficha["movimientos"]] == ["entrada"]    # contar no mueve inventario
    assert [x["id"] for x in cliente.get("/api/conteos", params={"tercero_id": dueno["id"]}, headers=H).json()] == [c["id"]]


def test_conteo_con_diferencia_pendiente_y_luego_ajustado(cliente):
    pid, _ = _existencia(cliente)
    asistente = _entrar(cliente, _usuario("asistente"))
    # La asistente registra el descuadre, pero no ajusta.
    assert cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 47, "ajustar": True},
                        headers=asistente).status_code == 403
    c = cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 47}, headers=asistente).json()
    assert c["estado"] == "pendiente" and float(c["diferencia"]) == -3 and _piezas(cliente, pid) == 50
    assert cliente.post(f"/api/conteos/{c['id']}/resolver", json={"accion": "ajustar"}, headers=asistente).status_code == 403

    socio = _entrar(cliente, _usuario("socio"))
    r = cliente.post(f"/api/conteos/{c['id']}/resolver", json={"accion": "ajustar"}, headers=socio)
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ajustado" and r.json()["ajuste_documento_id"] and _piezas(cliente, pid) == 47
    assert cliente.post(f"/api/conteos/{c['id']}/resolver", json={"accion": "ajustar"}, headers=socio).status_code == 409
    ajuste = cliente.get(f"/api/documentos/{r.json()['ajuste_documento_id']}", headers=H).json()
    assert "había 50 pzas, se contaron 47 pzas" in (ajuste["documento"]["observacion"] or "")


def test_agente_ajusta_al_registrar_con_idempotencia(cliente):
    pid, _ = _existencia(cliente)
    agente = {**H, "X-Origen": "agente", "X-Usuario": "Prosi"}
    cuerpo = {"contado": 52, "ajustar": True, "contado_por": "Nacho", "clave_idempotencia": f"c-{uuid.uuid4().hex}"}
    a = cliente.post(f"/api/piezas/{pid}/conteo", json=cuerpo, headers=agente).json()
    b = cliente.post(f"/api/piezas/{pid}/conteo", json=cuerpo, headers=agente).json()
    assert a["estado"] == "ajustado" and a["id"] == b["id"] and _piezas(cliente, pid) == 52


def test_pendiente_se_descarta_o_pide_recontar(cliente):
    pid, _ = _existencia(cliente)
    socio = _entrar(cliente, _usuario("socio"))
    c = cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 45}, headers=H).json()
    # Si el saldo se movió después del conteo, ajustar a lo contado sería un error: hay que contar de nuevo.
    d = cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 49, "ajustar": True}, headers=socio).json()
    assert d["estado"] == "ajustado" and _piezas(cliente, pid) == 49
    assert cliente.post(f"/api/conteos/{c['id']}/resolver", json={"accion": "ajustar"}, headers=socio).status_code == 409
    assert cliente.post(f"/api/conteos/{c['id']}/resolver", json={"accion": "descartar"}, headers=socio).status_code == 422
    r = cliente.post(f"/api/conteos/{c['id']}/resolver", json={"accion": "descartar", "motivo": "se recontó"},
                     headers=socio).json()
    assert r["estado"] == "descartado" and _piezas(cliente, pid) == 49
    estados = {x["estado"] for x in cliente.get("/api/conteos", params={"pieza_id": pid}, headers=H).json()}
    assert estados == {"descartado", "ajustado"}
    assert cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 4.5}, headers=H).status_code == 422


def test_resumen_de_conteos_en_pdf(cliente):
    pid, dueno = _existencia(cliente)
    cliente.post(f"/api/piezas/{pid}/conteo", json={"contado": 48, "ajustar": True, "fecha": "2026-11-19"}, headers=H)
    r = cliente.get("/api/conteos/pdf", params={"tercero_id": dueno["id"], "desde": "2026-11-01", "hasta": "2026-11-30"},
                    headers=H)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert cliente.get("/api/conteos/pdf", params={"desde": "2026-11-30", "hasta": "2026-11-01"}, headers=H).status_code == 422
