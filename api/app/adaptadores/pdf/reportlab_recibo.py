"""Recibo de entrada de material a media carta (opción B: una tarjeta con sombra por producto).

Usa la cabecera de las órdenes de trabajo para diferenciarlo de la NE y la cotización. Ocupa la
mitad de arriba de la hoja (o la de abajo, para aprovechar una hoja ya usada). Si la entrada trae
más productos de los que caben en media hoja, pasa a hoja completa y sigue en otras hojas.
"""
from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_ne import _partir, firma_y_sello
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, NARANJA, SUAVE, ajustar, n, qr
from app.dominio.impresion import ReciboEntradaImpreso, RenglonRecibo

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
W, H = LETTER
MITAD = H / 2
M = 9 * mm
ALTO_TARJETA = 9 * mm
PASO = ALTO_TARJETA + 1.8 * mm
ARRIBA = 46 * mm          # cabecera + datos del cliente
ABAJO = 26 * mm           # firma, sello y entregado por
ANCHO_TOTAL = 27 * mm


def capacidad(alto_region: float) -> int:
    return int((alto_region - ARRIBA - ABAJO) // PASO)


POR_MEDIA = capacidad(MITAD)       # 6
POR_HOJA = capacidad(H)            # 19


def _cant(x: Decimal) -> str:
    return n(float(x), 0) if x == x.to_integral_value() else n(float(x), 2)


def _kg(x: Decimal) -> str:
    return n(float(x), 0)


def _cabecera(c, r: ReciboEntradaImpreso, logo: str, y0: float, x0: float, x1: float, hoja: str | None) -> float:
    top = y0 - 7 * mm
    c.drawImage(logo, x0, top - 13 * mm, width=44 * mm, height=13 * mm, mask="auto", preserveAspectRatio=True,
                anchor="w")
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0 + 49 * mm, top - 5.5 * mm, "RECIBO DE ENTRADA")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7.5)
    c.drawString(x0 + 49 * mm, top - 10 * mm, "Material recibido en custodia" + (f" · {hoja}" if hoja else ""))
    qr(c, f"Recibo de entrada {r.numero} · {r.cliente}", x1 - 18 * mm, top - 18 * mm, 18 * mm)
    xr = x1 - 21 * mm
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 19)
    c.drawRightString(xr, top - 6.5 * mm, f"N° {r.numero}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    f = r.fecha
    c.drawRightString(xr, top - 11.5 * mm, f"{f.day:02d} {MESES[f.month - 1]} {f.year}" if f else "")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 6.5)
    quien = f"Registró {r.registrado_por}" + (f" · {r.registrado:%d/%m %H:%M}" if r.registrado else "")
    c.drawRightString(xr, top - 15.5 * mm, quien[:60])
    y = top - 19.5 * mm
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.4)
    c.line(x0, y, x1, y)
    return y


def _datos(c, r: ReciboEntradaImpreso, x0: float, x1: float, y: float) -> float:
    y -= 2.5 * mm
    alto = 13 * mm
    c.setFillColor(SUAVE)
    c.roundRect(x0, y - alto, x1 - x0, alto, 2 * mm, fill=1, stroke=0)
    x = x0 + 4 * mm
    for et, val, frac, tam in (("RECIBIDO DE", r.cliente, 0.50, 12), ("RIF", r.rif or "", 0.17, 10),
                               ("DOCUMENTO DEL CLIENTE", r.documento_cliente, 0.33, 10)):
        ancho = (x1 - x0 - 8 * mm) * frac
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 6.5)
        c.drawString(x, y - 4.5 * mm, et)
        c.setFillColor(colors.black)
        ajustar(c, val, "Helvetica-Bold", tam, ancho - 3 * mm)
        c.drawString(x, y - 10 * mm, val)
        x += ancho
    return y - alto


def _tarjeta(c, it: RenglonRecibo, x0: float, ancho: float, y: float) -> None:
    alto = ALTO_TARJETA
    c.setFillColor(colors.Color(0, 0, 0, alpha=0.10))                  # sombra
    c.roundRect(x0 + 0.8 * mm, y - alto - 0.8 * mm, ancho, alto, 2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.5)
    c.roundRect(x0, y - alto, ancho, alto, 2 * mm, fill=1, stroke=1)
    c.setFillColor(AZUL)                                                # cantidad en pastilla
    c.roundRect(x0, y - alto, 24 * mm, alto, 2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    ajustar(c, _cant(it.cantidad), "Helvetica-Bold", 13, 21 * mm, 8)
    c.drawCentredString(x0 + 12 * mm, y - 5 * mm, _cant(it.cantidad))
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(x0 + 12 * mm, y - 7.9 * mm, it.unidad.upper())
    texto = ancho - 28 * mm - 26 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x0 + 28 * mm, y - 4.2 * mm, _partir(it.descripcion, "Helvetica-Bold", 9.5, texto, 1)[0])
    c.setFillColor(GRIS)
    detalle = it.codigo + (f"   ·   {n(float(it.peso_unitario_kg), 2)} kg c/u" if it.peso_unitario_kg is not None else "")
    ajustar(c, detalle, "Helvetica", 6.8, texto, 5)
    c.drawString(x0 + 28 * mm, y - 7.6 * mm, detalle)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(x0 + ancho - 3 * mm, y - 5.8 * mm, f"{_kg(it.kg)} kg")


def _total(c, r: ReciboEntradaImpreso, x1: float, tope: float) -> None:
    x = x1 - ANCHO_TOTAL
    c.setFillColor(NARANJA)
    c.roundRect(x, tope - 24 * mm, ANCHO_TOTAL, 24 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    cx = x + ANCHO_TOTAL / 2
    c.setFont("Helvetica", 7)
    c.drawCentredString(cx, tope - 6 * mm, "TOTAL RECIBIDO")
    ajustar(c, _kg(r.total_kg), "Helvetica-Bold", 14, ANCHO_TOTAL - 3 * mm, 9)
    c.drawCentredString(cx, tope - 13.5 * mm, _kg(r.total_kg))
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(cx, tope - 18 * mm, "kg")
    c.drawCentredString(cx, tope - 21.5 * mm, f"{_cant(r.total_piezas)} piezas")


def _firmas(c, r: ReciboEntradaImpreso, x0: float, x1: float, base: float) -> None:
    if r.anulado:
        c.setStrokeColor(LINEA)
        c.setDash(2, 2)
        c.rect(x1 - 52 * mm, base, 52 * mm, 18 * mm)
        c.setDash()
    else:
        firma_y_sello(c, x1 - 52 * mm, base, 52 * mm, 18 * mm)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    c.line(x0, base + 4 * mm, x0 + 62 * mm, base + 4 * mm)
    c.line(x0 + 66 * mm, base + 4 * mm, x0 + 96 * mm, base + 4 * mm)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 6.5)
    c.drawString(x0, base + 1 * mm, "ENTREGADO POR (NOMBRE Y FIRMA)")
    c.drawString(x0 + 66 * mm, base + 1 * mm, "C.I.")


def _anulado(c, cx: float, cy: float) -> None:
    c.saveState()
    c.setFillColor(colors.Color(0.78, 0.16, 0.16, alpha=0.18))
    c.setFont("Helvetica-Bold", 60)
    c.translate(cx, cy)
    c.rotate(20)
    c.drawCentredString(0, 0, "ANULADO")
    c.restoreState()


def _region(c, r: ReciboEntradaImpreso, logo: str, y0: float, y1: float, items: list[RenglonRecibo],
            hoja: str | None, ultima: bool) -> None:
    """Dibuja el recibo entre y0 (arriba) y y1 (abajo)."""
    x0, x1 = M, W - M
    y = _cabecera(c, r, logo, y0, x0, x1, hoja)
    y = _datos(c, r, x0, x1, y) - 4 * mm
    tope = y
    for it in items:
        _tarjeta(c, it, x0, x1 - x0 - ANCHO_TOTAL - 3 * mm, y)
        y -= PASO
    _total(c, r, x1, tope)
    if ultima and r.observacion:
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(x0, y - 2 * mm, _partir(f"Obs.: {r.observacion}", "Helvetica-Oblique", 7.5,
                                             x1 - x0 - ANCHO_TOTAL - 6 * mm, 1)[0])
    if not ultima:
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Oblique", 8)
        c.drawRightString(x1 - ANCHO_TOTAL - 3 * mm, y - 2 * mm, "sigue en la próxima hoja…")
    _firmas(c, r, x0, x1, y1 + 6 * mm)
    if r.anulado:
        _anulado(c, W / 2, (y0 + y1) / 2)


def _corte(c) -> None:
    c.setStrokeColor(LINEA)
    c.setDash(3, 3)
    c.setLineWidth(0.6)
    c.line(4 * mm, MITAD, W - 4 * mm, MITAD)
    c.setDash()


def pdf_recibo(r: ReciboEntradaImpreso, logo: str, abajo: bool = False) -> bytes:
    """Media hoja (arriba, o abajo si `abajo`) cuando caben los productos; si no, hojas completas."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Recibo de Entrada {r.numero} {r.cliente}")
    c.setAuthor("PROSIFER, C.A.")
    if len(r.renglones) <= POR_MEDIA:
        y0 = MITAD if abajo else H
        _region(c, r, logo, y0, y0 - MITAD, r.renglones, None, True)
        _corte(c)
        c.showPage()
    else:
        tramos = [r.renglones[i:i + POR_HOJA] for i in range(0, len(r.renglones), POR_HOJA)]
        for i, tramo in enumerate(tramos, start=1):
            hoja = f"hoja {i} de {len(tramos)}" if len(tramos) > 1 else None
            _region(c, r, logo, H, 0, tramo, hoja, i == len(tramos))
            c.showPage()
    c.save()
    return buf.getvalue()
