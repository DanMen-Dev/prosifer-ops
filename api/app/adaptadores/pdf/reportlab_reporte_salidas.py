"""Reporte "Servicios de Descarga-Carga" de un cliente (carta vertical), como el del Excel: título y cliente,
fechas de inicio y corte, y una fila por renglón de cada NE (nota de salida, fecha, NE, cantidad despachada,
descripción y masa). Al final, la masa total del período."""
from __future__ import annotations

import datetime as dt
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_ne import MESES
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, LOGO, SUAVE, n
from app.esquemas import ReporteSalidas

FILAS_POR_HOJA = 34
ALTO_FILA = 5.6 * mm
# columna: (título, ancho en mm, alineación)
COLUMNAS = (("Nota de\nSalida", 16, "c"), ("Fecha", 34, "c"), ("Nota de\nEntrega", 18, "c"),
            ("Cantidad\nDespachada", 18, "c"), ("Descripción", 88, "l"), ("Masa (kg)", 22, "r"))


def _fecha_larga(f: dt.date | None) -> str:
    return f"{f.day:02d} de {MESES[f.month - 1]} de {f.year}" if f else ""


def _cortar(texto: str, fuente: str, tam: float, ancho: float) -> str:
    if stringWidth(texto, fuente, tam) <= ancho:
        return texto
    while texto and stringWidth(texto + "…", fuente, tam) > ancho:
        texto = texto[:-1]
    return texto + "…"


def _cabecera(c: canvas.Canvas, r: ReporteSalidas, W: float, H: float, m: float) -> float:
    c.drawImage(LOGO, m, H - m - 14 * mm, width=48 * mm, height=14 * mm, mask="auto", preserveAspectRatio=True,
                anchor="w")
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(m + 52 * mm, H - m - 6 * mm, "Reporte Servicios de Descarga-Carga")
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(m + 52 * mm, H - m - 11 * mm, _cortar(r.tercero, "Helvetica-Bold", 9.5, 80 * mm))
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawRightString(W - m - 34 * mm, H - m - 6 * mm, "Fecha inicio reporte:")
    c.drawRightString(W - m - 34 * mm, H - m - 11 * mm, "Fecha corte del reporte:")
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(W - m, H - m - 6 * mm, _fecha_larga(r.desde))
    c.drawRightString(W - m, H - m - 11 * mm, _fecha_larga(r.hasta))
    y = H - m - 19 * mm
    c.setFillColor(AZUL)
    c.rect(m, y - 9 * mm, W - 2 * m, 9 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    x = m
    for titulo, ancho, _ in COLUMNAS:
        lineas = titulo.split("\n")
        for k, ln in enumerate(lineas):
            c.drawCentredString(x + ancho * mm / 2, y - 3.6 * mm - k * 3.2 * mm + (len(lineas) - 1) * 1.2 * mm, ln)
        x += ancho * mm
    return y - 9 * mm


def _pie(c: canvas.Canvas, r: ReporteSalidas, W: float, m: float, hoja: int, hojas: int, generado: str) -> None:
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7)
    c.drawString(m, m - 2 * mm, f"Fecha y hora del reporte: {generado} · {r.tercero}")
    c.drawRightString(W - m, m - 2 * mm, f"Página {hoja} de {hojas}")


def pdf_reporte_salidas(r: ReporteSalidas, ahora: dt.datetime | None = None) -> bytes:
    buf = io.BytesIO()
    W, H = LETTER
    m = 12 * mm
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Reporte Descarga-Carga {r.tercero} {r.desde:%d-%m-%Y} al {r.hasta:%d-%m-%Y}")
    ahora = ahora or dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))   # hora de Venezuela (sin horario de verano)
    generado = ahora.strftime("%d/%m/%Y %I:%M %p")
    filas = r.filas or []
    hojas = max(1, -(-(len(filas) + 1) // FILAS_POR_HOJA))
    for hoja in range(hojas):
        y = _cabecera(c, r, W, H, m)
        trozo = filas[hoja * FILAS_POR_HOJA:(hoja + 1) * FILAS_POR_HOJA]
        for k, f in enumerate(trozo):
            if k % 2:
                c.setFillColor(SUAVE)
                c.rect(m, y - ALTO_FILA, W - 2 * m, ALTO_FILA, stroke=0, fill=1)
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 7.5)
            valores = (f.nota_salida or "", _fecha_larga(f.fecha), f.nota_entrega or "",
                       n(float(f.cantidad or 0), 0 if (f.cantidad or 0) == int(f.cantidad or 0) else 2),
                       f.descripcion or "", n(float(f.kg), 2))
            x = m
            for (titulo, ancho, al), v in zip(COLUMNAS, valores):
                w = ancho * mm
                yy = y - ALTO_FILA + 1.9 * mm
                if al == "c":
                    c.drawCentredString(x + w / 2, yy, v)
                elif al == "r":
                    c.drawRightString(x + w - 1.5 * mm, yy, v)
                else:
                    c.drawString(x + 1.5 * mm, yy, _cortar(v, "Helvetica", 7.5, w - 3 * mm))
                x += w
            y -= ALTO_FILA
            c.setStrokeColor(LINEA)
            c.setLineWidth(0.3)
            c.line(m, y, W - m, y)
        if hoja == hojas - 1:
            y -= 3 * mm
            c.setFillColor(AZUL)
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(W - m - 24 * mm, y - 4 * mm,
                              f"{r.notas_entrega} notas de entrega · Masa total despachada (kg):")
            c.drawRightString(W - m - 1.5 * mm, y - 4 * mm, n(float(r.total_kg), 2))
            if r.excluidas:
                c.setFillColor(GRIS)
                c.setFont("Helvetica", 7.5)
                c.drawString(m, y - 9 * mm, "No incluye: " + "; ".join(
                    f"{e.nombre.lower()} ({e.renglones} renglones, {n(float(e.kg), 2)} kg)" for e in r.excluidas)
                    + ".")
            if not filas:
                c.setFillColor(GRIS)
                c.setFont("Helvetica", 9)
                c.drawString(m, y - 4 * mm, "Sin salidas en el período.")
        _pie(c, r, W, m, hoja + 1, hojas, generado)
        c.showPage()
    c.save()
    return buf.getvalue()
