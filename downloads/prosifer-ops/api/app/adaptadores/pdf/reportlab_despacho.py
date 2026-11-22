"""Orden de despacho del cliente y nota de salida (carta vertical), con la cabecera moderna.

Las dos hojas comparten el dibujo: datos de quién retira, renglones con cantidad, unidad, descripción,
código, kg por pieza y kg, observaciones y firmas. La nota de salida lleva la firma y el sello de
Prosifer, la del que recibe y la de vigilancia (salida de patio).
"""
from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_cabecera import PIE, cabecera, fecha_corta, pie
from app.adaptadores.pdf.reportlab_ne import _partir, firma_y_sello
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, NARANJA, SUAVE, ajustar, marca_anulada, n
from app.dominio.impresion import DespachoImpreso, RenglonRecibo

W, H = LETTER
M = 12 * mm
ANCHO = W - 2 * M
ALTO_FILA = 8.4 * mm
TITULO = {"orden_despacho": "ORDEN DE DESPACHO", "nota_salida": "NOTA DE SALIDA"}
ESTADO = {"pendiente": ("PENDIENTE DE DESPACHO", NARANJA), "despachada": ("DESPACHADA", colors.HexColor("#1D7A55")),
          "anulada": ("ANULADA", colors.HexColor("#B3261E")), "emitida": ("EMITIDA", AZUL)}
COLS = (("CANT.", 18), ("UND", 14), ("DESCRIPCIÓN Y CÓDIGO", None), ("KG / PZA", 24), ("KG", 26))


def _cant(x: Decimal) -> str:
    return n(float(x), 0) if x == x.to_integral_value() else n(float(x), 2)


def _kg(x: Decimal) -> str:
    return n(float(x), 0)


def _anchos() -> list[float]:
    fijo = sum(a for _, a in COLS if a) * mm
    return [(a * mm if a else ANCHO - fijo) for _, a in COLS]


def _estado(c, d: DespachoImpreso, y: float) -> float:
    texto, color = ESTADO.get(d.estado, (d.estado.upper(), GRIS))
    c.setFont("Helvetica-Bold", 8.5)
    ancho = c.stringWidth(texto, "Helvetica-Bold", 8.5) + 8 * mm
    c.setFillColor(color)
    c.roundRect(W - M - ancho, y - 6 * mm, ancho, 6 * mm, 3 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.drawCentredString(W - M - ancho / 2, y - 4.1 * mm, texto)
    if d.referencia:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8.5)
        c.drawRightString(W - M - ancho - 3 * mm, y - 4.1 * mm, d.referencia)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, y - 4.1 * mm, "Material en custodia de Prosifer, propiedad del cliente.")
    return y - 9 * mm


def _retiro(c, d: DespachoImpreso, y: float) -> float:
    r = d.retiro or {}
    alto = 21 * mm
    c.setFillColor(SUAVE)
    c.roundRect(M, y - alto, ANCHO, alto, 2 * mm, fill=1, stroke=0)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(M + 3 * mm, y - 5 * mm, "RETIRA")
    fr = r.get("fecha_retiro")
    try:
        fr = fecha_corta(dt.date.fromisoformat(fr)) if fr else ""
    except ValueError:
        pass
    campos = [("Fecha de retiro", fr or ""), ("Chofer o persona", r.get("retira", "")), ("Cédula", r.get("cedula", "")),
              ("Placa", r.get("placa", "")), ("Transporte", r.get("transporte", "")), ("Teléfono", r.get("telefono", ""))]
    col = (ANCHO - 6 * mm) / 3
    for i, (et, val) in enumerate(campos):
        x = M + 3 * mm + (i % 3) * col
        fila = y - 10.5 * mm - (i // 3) * 7.5 * mm
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 6.8)
        c.drawString(x, fila + 2.6 * mm, et.upper())
        c.setFillColor(colors.black)
        ajustar(c, val or "—", "Helvetica-Bold", 9.5, col - 4 * mm, 6.5)
        c.drawString(x, fila - 1.2 * mm, val or "—")
    return y - alto - 4 * mm


def _columnas(c, y: float) -> float:
    anchos = _anchos()
    c.setFillColor(AZUL)
    c.roundRect(M, y - 7 * mm, ANCHO, 7 * mm, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    x = M
    for (t, _), a in zip(COLS, anchos):
        if t.startswith("DESC"):
            c.drawString(x + 2 * mm, y - 4.6 * mm, t)
        elif t in ("CANT.", "UND"):
            c.drawCentredString(x + a / 2, y - 4.6 * mm, t)
        else:
            c.drawRightString(x + a - 2 * mm, y - 4.6 * mm, t)
        x += a
    return y - 7 * mm


def _fila(c, r: RenglonRecibo, i: int, y: float) -> float:
    anchos = _anchos()
    if i % 2 == 0:
        c.setFillColor(SUAVE)
        c.rect(M, y - ALTO_FILA, ANCHO, ALTO_FILA, fill=1, stroke=0)
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.3)
    c.line(M, y - ALTO_FILA, W - M, y - ALTO_FILA)
    medio = y - ALTO_FILA / 2 - 1.3 * mm
    xs = [M]
    for a in anchos:
        xs.append(xs[-1] + a)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(xs[0] + anchos[0] / 2, medio, _cant(r.cantidad))
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(xs[1] + anchos[1] / 2, medio, r.unidad)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(xs[2] + 2 * mm, y - 3.8 * mm, _partir(r.descripcion, "Helvetica-Bold", 9, anchos[2] - 4 * mm, 1)[0])
    c.setFillColor(GRIS)
    ajustar(c, r.codigo, "Helvetica", 6.8, anchos[2] - 4 * mm, 5)
    c.drawString(xs[2] + 2 * mm, y - 7.2 * mm, r.codigo)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    if r.peso_unitario_kg is not None:
        c.drawRightString(xs[4] - 2 * mm, medio, n(float(r.peso_unitario_kg), 2))
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(xs[5] - 2 * mm, medio, _kg(r.kg))
    return y - ALTO_FILA


def _total(c, d: DespachoImpreso, y: float) -> float:
    c.setStrokeColor(AZUL)
    c.setLineWidth(1)
    c.line(M, y - 0.5 * mm, W - M, y - 0.5 * mm)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(M + 2 * mm, y - 6.2 * mm, f"TOTAL: {len(d.renglones)} renglón{'es' if len(d.renglones) != 1 else ''} · "
                                          f"{_cant(d.total_piezas)} piezas")
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(W - M - 2 * mm, y - 6.6 * mm, f"{_kg(d.total_kg)} kg")
    return y - 12 * mm


def _observacion(c, d: DespachoImpreso, y: float) -> float:
    if not d.observacion:
        return y
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(M, y - 4 * mm, "OBSERVACIONES")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    for i, linea in enumerate(_partir(d.observacion, "Helvetica", 9, ANCHO, 3)):
        c.drawString(M, y - 8.5 * mm - i * 4.2 * mm, linea)
    return y - 22 * mm


def _firmas(c, d: DespachoImpreso) -> None:
    base = M + 14 * mm
    ancho = (ANCHO - 12 * mm) / 3
    if d.tipo == "nota_salida":
        titulos = ("DESPACHADO POR PROSIFER", "RECIBÍ CONFORME: NOMBRE, C.I. Y FIRMA", "VIGILANCIA · SALIDA DE PATIO")
        if not d.anulado:
            firma_y_sello(c, M, base + 2 * mm, ancho, 20 * mm)
    else:
        titulos = ("SOLICITADO POR EL CLIENTE", "RECIBIDO EN PATIO (PROSIFER)", "PREPARADO POR")
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    for i, t in enumerate(titulos):
        x = M + i * (ancho + 6 * mm)
        c.line(x, base, x + ancho, base)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 6.8)
        c.drawString(x, base - 3.5 * mm, t)


def pdf_despacho(d: DespachoImpreso, logo: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    titulo = TITULO.get(d.tipo, d.tipo.upper())
    c.setTitle(f"{titulo.title()} {d.numero} {d.cliente}")
    c.setAuthor("PROSIFER, C.A.")
    quien = "Solicitada por" if d.tipo == "orden_despacho" else "Emitida por"
    nota = f"{quien} {d.creado_por}" + (f" · {d.creado_en:%d/%m/%Y %H:%M}" if d.creado_en else "")
    sub = d.cliente + (f" · RIF {d.rif}" if d.rif else "")
    # renglones por hoja: la primera lleva retiro; la última, total, observaciones y firmas
    tramos: list[list[RenglonRecibo]] = []
    resto = list(d.renglones) or []
    primera = 15
    tramos.append(resto[:primera])
    resto = resto[primera:]
    while resto:
        tramos.append(resto[:22])
        resto = resto[22:]
    for k, tramo in enumerate(tramos, start=1):
        y = cabecera(c, logo, W, H, M, titulo=titulo, subtitulo=sub, numero=d.numero, fecha=fecha_corta(d.fecha),
                     nota=nota, qr_texto=f"{titulo} {d.numero} · {d.cliente}")
        y = _estado(c, d, y)
        if k == 1:
            y = _retiro(c, d, y)
        y = _columnas(c, y)
        inicio = sum(len(t) for t in tramos[:k - 1])
        for i, r in enumerate(tramo, start=inicio + 1):
            y = _fila(c, r, i, y)
        if k == len(tramos):
            y = _total(c, d, y)
            _observacion(c, d, y)
            _firmas(c, d)
        else:
            c.setFillColor(GRIS)
            c.setFont("Helvetica-Oblique", 8)
            c.drawRightString(W - M, y - 5 * mm, "sigue en la próxima hoja…")
        pie(c, W, M, PIE, k, len(tramos))
        if d.anulado:
            marca_anulada(c, W, H)
        c.showPage()
    c.save()
    return buf.getvalue()
