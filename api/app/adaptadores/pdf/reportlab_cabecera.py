"""Cabecera y pie modernos de Prosifer (los de las órdenes de corte), para carta vertical.

La usan el reporte de inventario, la orden de despacho y la nota de salida: logo a la izquierda,
título en azul con su subtítulo, número en naranja con la fecha a la derecha y un QR opcional.
"""
from __future__ import annotations

import datetime as dt

from reportlab.lib import colors
from reportlab.lib.units import mm

from app.adaptadores.pdf.reportlab_ne import PLANTA
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, NARANJA, ajustar, qr

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
PIE = "PROSIFER, C.A. · " + PLANTA.replace("PLANTA: ", "")


def fecha_corta(f: dt.date | None, hora: bool = False) -> str:
    if f is None:
        return ""
    txt = f"{f.day:02d} {MESES[f.month - 1]} {f.year}"
    if hora and isinstance(f, dt.datetime):
        txt += f" · {f:%H:%M}"
    return txt


def cabecera(c, logo: str, W: float, H: float, m: float, *, titulo: str, subtitulo: str = "",
             numero: str | None = None, fecha: str = "", nota: str = "", qr_texto: str | None = None) -> float:
    """Dibuja la cabecera y devuelve la altura donde empieza el contenido."""
    top = H - m
    c.drawImage(logo, m, top - 14 * mm, width=46 * mm, height=14 * mm, mask="auto", preserveAspectRatio=True,
                anchor="w")
    x_der = W - m
    if qr_texto:
        qr(c, qr_texto, W - m - 20 * mm, top - 21 * mm, 20 * mm)
        x_der = W - m - 23 * mm
    ancho_titulo = x_der - (m + 52 * mm) - 48 * mm
    c.setFillColor(AZUL)
    ajustar(c, titulo, "Helvetica-Bold", 15, ancho_titulo, 10)
    c.drawString(m + 52 * mm, top - 6.5 * mm, titulo)
    if subtitulo:
        c.setFillColor(colors.black)
        ajustar(c, subtitulo, "Helvetica-Bold", 10.5, ancho_titulo, 7)
        c.drawString(m + 52 * mm, top - 12 * mm, subtitulo)
    fila = top - 6.5 * mm
    if numero:
        c.setFillColor(NARANJA)
        c.setFont("Helvetica-Bold", 20)
        c.drawRightString(x_der, top - 7.5 * mm, f"N° {numero}")
        fila = top - 13 * mm
    if fecha:
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9.5)
        c.drawRightString(x_der, fila, fecha)
        fila -= 5 * mm
    if nota:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7)
        c.drawRightString(x_der, fila, nota[:70])
    y = top - 23 * mm
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.6)
    c.line(m, y, W - m, y)
    return y - 4 * mm


def pie(c, W: float, m: float, izquierda: str, hoja: int, hojas: int) -> None:
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.8)
    c.line(m, m + 6 * mm, W - m, m + 6 * mm)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7)
    c.drawString(m, m + 2 * mm, izquierda[:150])
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(W - m, m + 2 * mm, f"Hoja {hoja} de {hojas}")
