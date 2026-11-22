"""OC de slitter contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_usuarios import _entrar, _usuario  # noqa: E402


def _bobina(cliente, peso="8235", ancho="1200"):
    dueno = cliente.post("/api/terceros", json={"nombre": f"Cliente {uuid.uuid4().hex[:8]}"}, headers=H).json()
    codigo = f"S-{uuid.uuid4().hex[:10]}"
    r = cliente.post("/api/entradas/bobinas", headers=H, json={
        "documento_numero": "PL-1", "fecha": "2026-11-01", "codigo_bobina": codigo, "tipo_acero": "HP",
        "espesor_mm": "0.9", "ancho_mm": ancho, "peso_kg": peso, "propietario_id": dueno["id"], "confirmar": True})
    return r.json()["pieza_id"], codigo


def _orden(pid, confirmar, **extra):
    return {"pieza_id": pid, "fecha": "2026-11-08", "estatus_corte": "total", "calidad": "1er-F",
            "cortes": [{"ancho_mm": "268", "rollos": 4}, {"ancho_mm": "90", "rollos": 1}, {"ancho_mm": "30", "rollos": 1}],
            "scrap_ancho_mm": "8", "confirmar": confirmar, **extra}


def test_slitter_completo(cliente):
    pid, codigo = _bobina(cliente)
    previa = cliente.post("/api/ot/slitter", json=_orden(pid, False), headers=H)
    assert previa.status_code == 200, previa.text
    p = previa.json()
    assert p["guardada"] is False and float(p["kg_producido"]) == pytest.approx(8180.1)
    assert p["cortes"][0]["codigo_producto"] == "FLEHP0900268"
    assert p["cortes"][0]["detalle_rollos"][1]["codigo"].endswith(f"/ {codigo.upper()} / OC{p['numero']} / 1-B")

    hecha = cliente.post("/api/ot/slitter", json=_orden(pid, True, clave_idempotencia=f"t-{codigo}"), headers=H).json()
    assert hecha["guardada"] and hecha["orden_id"]
    repetida = cliente.post("/api/ot/slitter", json=_orden(pid, True, clave_idempotencia=f"t-{codigo}"), headers=H)
    assert repetida.status_code == 409

    bobina = cliente.get(f"/api/piezas/{pid}", headers=H).json()
    assert bobina["pieza"]["estado"] == "agotado" and len(bobina["hijas"]) == 6

    flejes = cliente.get("/api/existencias", params={"tipo": "fleje", "codigo": codigo}, headers=H).json()
    assert flejes["total_piezas"] == 6

    fleje = cliente.get(f"/api/piezas/{bobina['hijas'][0]['id']}", headers=H).json()
    assert fleje["origen"]["codigo"] == codigo.upper() and fleje["origen"]["orden_numero"] == hecha["numero"]

    for doc in ("orden", "etiquetas"):  # copias guardadas al crear la OC
        pdf = cliente.get(f"/api/ot/{hecha['orden_id']}/pdf/{doc}", headers=H)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    parcial = cliente.get(f"/api/ot/{hecha['orden_id']}/pdf/etiquetas",
                          params={"piezas": str(bobina["hijas"][0]["id"])}, headers=H)
    assert parcial.status_code == 200 and parcial.content.startswith(b"%PDF")

    det = cliente.get(f"/api/ot/{hecha['orden_id']}", headers=H).json()
    assert det["orden"]["piezas_producidas"] == 6 and det["pieza_entrada"]["id"] == pid
    assert any(o["id"] == hecha["orden_id"] for o in cliente.get("/api/ot?tipo=slitter", headers=H).json())

    # Solo el socio anula, y la bobina recupera su saldo.
    motivo = {"motivo": "orden de prueba"}
    assert cliente.request("DELETE", f"/api/ot/{hecha['orden_id']}", json=motivo, headers=H).status_code == 403
    socio = _entrar(cliente, _usuario("socio"))
    assert cliente.request("DELETE", f"/api/ot/{hecha['orden_id']}", json=motivo, headers=socio).status_code == 200
    assert float(cliente.get(f"/api/piezas/{pid}", headers=H).json()["pieza"]["saldo_kg"]) == 8235


def test_parcial_y_ancho_excedido(cliente):
    pid, _ = _bobina(cliente, peso="10000", ancho="1220")
    cuerpo = _orden(pid, True, estatus_corte="parcial", kg_procesado="4000",
                    cortes=[{"ancho_mm": "600", "rollos": 2}], scrap_ancho_mm="20")
    r = cliente.post("/api/ot/slitter", json=cuerpo, headers=H)
    assert r.status_code == 200, r.text
    assert float(r.json()["saldo_restante_kg"]) == 6000
    assert cliente.get(f"/api/piezas/{pid}", headers=H).json()["pieza"]["estado"] == "disponible"

    malo = _orden(pid, False, cortes=[{"ancho_mm": "700", "rollos": 2}])
    assert cliente.post("/api/ot/slitter", json=malo, headers=H).status_code == 422


def test_anular_bloqueado_si_un_fleje_se_movio(cliente):
    pid, _ = _bobina(cliente)
    hecha = cliente.post("/api/ot/slitter", json=_orden(pid, True), headers=H).json()
    det = cliente.get(f"/api/ot/{hecha['orden_id']}", headers=H).json()
    socio = _entrar(cliente, _usuario("socio"))
    fid = det["producidas"][0]["id"]
    cliente.patch(f"/api/piezas/{fid}", json={"buque": "x"}, headers=H)  # editar datos no es un movimiento
    from decimal import Decimal

    from app.adaptadores.sql.repositorios import UnidadSql
    from app.db import SesionLocal
    from app.servicios import inventario
    with SesionLocal() as s:
        inventario.registrar_movimiento(UnidadSql(s, 1), fid, "salida", -Decimal("100"), usuario="t", origen="interfaz")
        s.commit()
    r = cliente.request("DELETE", f"/api/ot/{hecha['orden_id']}", json={"motivo": "no debe poder"}, headers=socio)
    assert r.status_code == 409
