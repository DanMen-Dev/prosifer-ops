"""Reportes. El mensual de salidas por cliente ("Servicios de Descarga-Carga") es la base del cobro de
descarga, almacén y carga por la masa despachada; desde él se arma la cotización de ese servicio."""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.adaptadores.pdf.reportlab_reporte_salidas import pdf_reporte_salidas
from app.adaptadores.sql import consultas
from app.db import sesion
from app.dominio import codigos
from app.esquemas import BorradorCotizacion, ReporteSalidas
from app.seguridad import Actor, actor, editor

ruta = APIRouter(prefix="/api/reportes", tags=["reportes"])


# Por omisión no se cuentan bobinas ni flejes: ya pagaron su servicio (slitter, laminadora, maquila) o tienen
# su propio servicio de carga y descarga. Las láminas sí (HYMS las retira por partes a lo largo del mes).
EXCLUIR_POR_OMISION = "bobina,fleje"
EXCLUIR = Query(default=EXCLUIR_POR_OMISION, description="Categorías que no cuentan, separadas por comas: "
                + ", ".join(codigos.CATEGORIAS_SALIDA) + ". Vacío = todo")


def _excluir(texto: str | None) -> set[str]:
    return {x.strip().lower() for x in (texto or "").split(",") if x.strip().lower() in codigos.CATEGORIAS_SALIDA}


def _reporte(s: Session, a: Actor, tercero_id: int, desde: dt.date, hasta: dt.date,
             excluir: str | None = EXCLUIR_POR_OMISION) -> ReporteSalidas:
    if hasta < desde:
        raise HTTPException(422, "la fecha de corte es anterior a la de inicio")
    if (hasta - desde).days > 400:
        raise HTTPException(422, "el período no puede pasar de un año")
    r = consultas.reporte_salidas(s, a.empresa_id, tercero_id, desde, hasta, a.cliente, _excluir(excluir))
    if r is None:
        raise HTTPException(404, "cliente inexistente")
    return r


@ruta.get("/salidas", response_model=ReporteSalidas,
          summary="Salidas de material de un cliente en un período (NE no anuladas), renglón por renglón")
def salidas(tercero_id: int, desde: dt.date, hasta: dt.date, excluir: str = EXCLUIR, s: Session = Depends(sesion),
            a: Actor = Depends(actor)):
    return _reporte(s, a, tercero_id, desde, hasta, excluir)


@ruta.get("/salidas/pdf", response_class=Response, summary="Reporte Servicios de Descarga-Carga en PDF")
def salidas_pdf(tercero_id: int, desde: dt.date, hasta: dt.date, excluir: str = EXCLUIR, s: Session = Depends(sesion),
                a: Actor = Depends(actor)):
    r = _reporte(s, a, tercero_id, desde, hasta, excluir)
    nombre = f"Reporte Descarga-Carga {r.tercero} {desde:%d-%m-%Y} al {hasta:%d-%m-%Y}.pdf"
    simple = re.sub(r"[^A-Za-z0-9 ._-]+", "", nombre) or "reporte.pdf"
    return Response(pdf_reporte_salidas(r), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{simple}"; filename*=UTF-8\'\'{quote(nombre)}'})


@ruta.get("/salidas/cotizar", response_model=BorradorCotizacion,
          summary="Borrador de cotización del servicio de descarga, almacén y carga por la masa del período")
def salidas_cotizar(tercero_id: int, desde: dt.date, hasta: dt.date, excluir: str = EXCLUIR,
                    s: Session = Depends(sesion), a: Actor = Depends(editor)):
    return consultas.borrador_reporte_salidas(s, a.empresa_id, _reporte(s, a, tercero_id, desde, hasta, excluir))
