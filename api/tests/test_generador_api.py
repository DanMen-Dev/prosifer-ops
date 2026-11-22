"""Generador de códigos por la API y reporte, contra PostgreSQL (se salta sin DATABASE_URL)."""
import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("sin DATABASE_URL: pruebas de API omitidas", allow_module_level=True)

from app.config import config  # noqa: E402
from app.db import SesionLocal  # noqa: E402
from importador import reporte_codigos  # noqa: E402
from tests.test_api import H, cliente  # noqa: E402,F401


def test_familias_y_generar(cliente):
    fams = cliente.get("/api/productos/familias", headers=H).json()
    tubo = next(f for f in fams if f["clave"] == "tubo")
    assert {c["clave"] for c in tubo["campos"]} == {"medida1", "medida2", "espesor", "largo_mm"}
    r = cliente.post("/api/productos/generar", headers=H, json={
        "familia": "tubo", "material": "HP", "medida1": "3''", "medida2": "1 1/2''", "espesor": "0,90",
        "largo_mm": 6000})
    assert r.status_code == 200, r.text
    assert r.json()["codigo"] == "TUB000HPE090A00003A00015L06000"
    assert r.json()["nombre"] == "Tubo L.F. 3'' x 1 1/2'' x 0,90mm x 6000mm"
    malo = cliente.post("/api/productos/generar", headers=H, json={"familia": "tubo", "material": "HP"})
    assert malo.status_code == 422


def test_reporte_no_cambia_nada():
    with SesionLocal() as s:
        antes = s.execute(reporte_codigos.select(reporte_codigos.m.Producto.codigo)).all()
        res = reporte_codigos.filas(s, config.empresa_id)
        assert "productos activos" in reporte_codigos.resumen(res)
        assert s.execute(reporte_codigos.select(reporte_codigos.m.Producto.codigo)).all() == antes


def test_variantes_de_espesor_para_maquila(cliente):
    cliente.post("/api/productos", headers=H, json={"codigo": "PERHPHSM0606100",
                                                   "nombre": "Perfil LF Hoja Santa Maria x 0,60mm x 6,10mts"})
    r = cliente.post("/api/productos/variantes-espesor", headers=H, json={"codigo": "PERHPHSM0606100", "espesor_mm": "0.58"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["real"]["codigo"] == "PERHPHSM0586100" and "0,58mm" in v["real"]["nombre"]
    assert v["comercial"]["codigo"] == "PERHPHSM0606100" and v["comercial"]["existente"]
    igual = cliente.post("/api/productos/variantes-espesor", headers=H,
                         json={"codigo": "PERHPHSM0606100", "espesor_mm": "0.60"}).json()
    assert igual["comercial"] is None


def test_sugerir_perfil_para_un_fleje(cliente):
    from tests.test_ordenes import _bobina
    pid, _ = _bobina(cliente, peso="3000", ancho="1200")
    r = cliente.get("/api/productos/sugerir-perfil", params={"pieza_id": pid}, headers=H)
    assert r.status_code == 200 and r.json() == []          # una bobina de 1200 mm no es desarrollo de perfil
