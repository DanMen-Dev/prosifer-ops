"""Histórico de NE y corrección de NE por la API, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from app.config import config  # noqa: E402
from app.db import SesionLocal  # noqa: E402
from importador import ne_historico_excel as nh  # noqa: E402
from importador.cargar_ne_historico import cargar  # noqa: E402
from tests.test_api import H, cliente  # noqa: E402,F401
from tests.test_usuarios import _entrar, _tercero, _usuario  # noqa: E402


def test_historico_solo_consulta_y_repetible(cliente):
    num = f"H{uuid.uuid4().hex[:6].upper()}"
    nota = nh.NotaHistorica(5, num, f"Cliente histórico {num}", None, False,
                            [nh.Renglon(1, "LAMHP09012002400", 10, "Pza", "Lamina L.F. 0,90mm", 204)], nota_salida="5977")
    with SesionLocal() as s:
        r1, _ = cargar(s, [nota], config.empresa_id)
        s.commit()
        r2, _ = cargar(s, [nota], config.empresa_id)
        s.commit()
    assert r1["nuevas"] == 1 and r1["clientes_nuevos"] == 1 and r2["ya_estaban"] == 1
    docs = cliente.get("/api/documentos", params={"numero": num}, headers=H).json()
    assert docs[0]["origen"] == "excel" and float(docs[0]["total_kg"]) == 204
    det = cliente.get(f"/api/documentos/{docs[0]['id']}", headers=H).json()
    assert det["historico"] and not det["corregible"] and det["lineas"][0]["unidad"] == "Pza"
    r = cliente.post(f"/api/documentos/{docs[0]['id']}/correccion",
                     json={"cambios": [{"movimiento_id": 1, "unidades": 1}], "motivo": "no debe poder"}, headers=H)
    assert r.status_code == 422


def test_corregir_ne_por_la_api(cliente):
    dueno = _tercero(cliente)
    codigo = f"TUB{uuid.uuid4().hex[:10].upper()}"
    ent = {"codigo_producto": codigo, "descripcion": "Tubo de prueba", "propietario_id": dueno["id"], "unidades": 40,
           "peso_unitario_kg": "5", "documento_numero": "C-1", "fecha": "2026-11-10", "confirmar": True}
    pid = cliente.post("/api/entradas/existencias", json=ent, headers=H).json()["pieza_id"]
    ne = cliente.post("/api/salidas/nota-entrega", json={"fecha": "2026-11-10", "tercero_id": dueno["id"],
                                                        "lineas": [{"pieza_id": pid, "unidades": 10}], "confirmar": True},
                      headers=H).json()
    det = cliente.get(f"/api/documentos/{ne['documento_id']}", headers=H).json()
    assert det["corregible"]
    mv = det["lineas"][0]["movimiento_id"]
    cuerpo = {"cambios": [{"movimiento_id": mv, "unidades": 8}], "motivo": "salieron 8, no 10", "confirmar": True}
    r = cliente.post(f"/api/documentos/{ne['documento_id']}/correccion", json=cuerpo, headers=H)
    assert r.status_code == 200, r.text
    det = cliente.get(f"/api/documentos/{ne['documento_id']}", headers=H).json()
    assert det["documento"]["numero"] == ne["numero"] and det["lineas"][0]["unidades"] == -8
    assert len(det["correcciones"]) == 1
    assert cliente.get(f"/api/piezas/{pid}", headers=H).json()["pieza"]["saldo_unidades"] == 32


def test_ne_del_libro_de_slitter_se_completa_no_choca(cliente):
    from app import modelos as m
    num = f"S{uuid.uuid4().hex[:6].upper()}"
    with SesionLocal() as s:
        doc = m.Documento(empresa_id=config.empresa_id, tipo="nota_entrega", numero=num, origen="importacion",
                          creado_por="importador")
        s.add(doc)
        s.commit()
        nota = nh.NotaHistorica(5, num, f"Cliente bobinas {num}", None, False,
                                [nh.Renglon(1, "BOBHP0200", 1, "Bob", "Bobina L.C. 2,00mm", 9000)], nota_salida="5000")
        r1, avisos = cargar(s, [nota], config.empresa_id)
        s.commit()
        r2, _ = cargar(s, [nota], config.empresa_id)
        s.commit()
    assert r1["completadas"] == 1 and r1["choques"] == 0 and not avisos and r2["ya_estaban"] == 1
    det = cliente.get(f"/api/documentos/{doc.id}", headers=H).json()
    assert det["historico"] and not det["corregible"] and det["documento"]["tercero_id"]
    assert float(det["documento"]["total_kg"]) == 9000
    socio = _entrar(cliente, _usuario("socio"))
    r = cliente.request("DELETE", f"/api/documentos/{doc.id}", json={"motivo": "no debe poder"}, headers=socio)
    assert r.status_code == 422


def test_ne_impresa_con_encabezado(cliente):
    dueno = _tercero(cliente)
    codigo = f"TUB{uuid.uuid4().hex[:10].upper()}"
    ent = {"codigo_producto": codigo, "descripcion": "Tubo de prueba", "propietario_id": dueno["id"], "unidades": 20,
           "peso_unitario_kg": "5", "documento_numero": "C-2", "fecha": "2026-11-10", "confirmar": True}
    pid = cliente.post("/api/entradas/existencias", json=ent, headers=H).json()["pieza_id"]
    ne = cliente.post("/api/salidas/nota-entrega", json={
        "fecha": "2026-11-11", "tercero_id": dueno["id"], "lineas": [{"pieza_id": pid, "unidades": 4}],
        "encabezado": {"cotizacion": "D-2939", "chofer": "  ", "notas": "Retira en planta"}, "confirmar": True},
        headers=H).json()
    det = cliente.get(f"/api/documentos/{ne['documento_id']}", headers=H).json()
    assert det["documento"]["encabezado"] == {"cotizacion": "D-2939", "notas": "Retira en planta"}
    r = cliente.put(f"/api/documentos/{ne['documento_id']}/encabezado",
                    json={"cotizacion": "D-2939", "chofer": "Pedro Pérez", "placa": "A12BC3D"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["encabezado"] == {"cotizacion": "D-2939", "chofer": "Pedro Pérez", "placa": "A12BC3D"}
    pdf = cliente.get(f"/api/documentos/{ne['documento_id']}/pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
