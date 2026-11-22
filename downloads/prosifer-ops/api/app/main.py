"""Prosifer · Inventarios y Procesos (API).

Documentación interactiva en /api/docs una vez levantado.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import config
from app.db import engine
from app.rutas import (avisos, catalogos, conteos, cotizaciones, despachos, ordenes, piezas, productos, reportes, salidas,
                       solicitudes, terceros, usuarios)

app = FastAPI(
    title="Prosifer · Inventarios y Procesos",
    version="0.4.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

if config.cors_origenes:
    app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origenes),
                       allow_methods=["*"], allow_headers=["*"])

app.include_router(catalogos.ruta)
app.include_router(terceros.ruta)
app.include_router(productos.ruta)
app.include_router(piezas.ruta)
app.include_router(usuarios.ruta)
app.include_router(ordenes.ruta)
app.include_router(salidas.ruta)
app.include_router(despachos.ruta)
app.include_router(solicitudes.ruta)
app.include_router(avisos.ruta)
app.include_router(cotizaciones.ruta)
app.include_router(reportes.ruta)
app.include_router(conteos.ruta)


@app.get("/api/salud", tags=["sistema"])
def salud() -> dict:
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return {"ok": True}
