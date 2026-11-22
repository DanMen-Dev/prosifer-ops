"""Nota de entrega en el formato de Prosifer (carta vertical), como la NE del Excel.

La descripción del producto va en primer plano y el código debajo, más pequeño. Si hay más
renglones de los que caben, sigue en otra hoja con el mismo encabezado; el total va en la última.
"""
from __future__ import annotations

import io
from pathlib import Path
from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, SUAVE, ajustar, n
from app.dominio.impresion import NotaEntregaImpresa, RenglonNE

RIF_PROSIFER = "J-00000000-0"
DIRECCION_FISCAL = "Av. Industrial Demo 100, Zona Franca, Ciudad Demo"
PLANTA = "PLANTA: Parque Industrial Demo, Calle 1, Galpón N° 10. Ciudad Demo"
CONTACTO = "Teléfonos: 0000-000.00.00 · Email: demo@prosifer-ops.test"
TRASLADO = "NOTA HABILITADA PARA EL TRASLADO DE BIENES POR TODO EL TERRITORIO NACIONAL"
ROJO = colors.HexColor("#C62828")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")
FILAS_POR_HOJA = 10
ALTO_FILA = 10 * mm


def _cant(x: Decimal) -> str:
    return n(float(x), 0) if x == x.to_integral_value() else n(float(x), 2)


def _kg(x: Decimal) -> str:
    return n(float(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), 0)


def _partir(texto: str, fuente: str, tam: float, ancho: float, max_lineas: int = 2) -> list[str]:
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = f"{actual} {p}".strip()
        if stringWidth(prueba, fuente, tam) <= ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        while stringWidth(lineas[-1] + "…", fuente, tam) > ancho and len(lineas[-1]) > 1:
            lineas[-1] = lineas[-1][:-1]
        lineas[-1] += "…"
    return lineas


def _etiqueta(c: canvas.Canvas, x: float, y: float, texto: str, tam: float = 7.5) -> None:
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", tam)
    c.drawString(x, y, texto)


def _valor(c: canvas.Canvas, x: float, y: float, texto: str | None, ancho: float, tam: float = 9.5) -> None:
    c.setFillColor(colors.black)
    ajustar(c, texto or "", "Helvetica", tam, ancho, 6.5)
    c.drawString(x, y, texto or "")


def _cabecera(c: canvas.Canvas, ne: NotaEntregaImpresa, logo: str, W: float, H: float, m: float,
              hoja: int, hojas: int) -> float:
    c.drawImage(logo, m, H - m - 17 * mm, width=58 * mm, height=17 * mm, mask="auto", preserveAspectRatio=True,
                anchor="w")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(W - m, H - m - 9 * mm, f"RIF: {RIF_PROSIFER}")
    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS)
    c.drawRightString(W - m, H - m - 14 * mm, f"Dirección Fiscal: {DIRECCION_FISCAL}")
    y = H - m - 18 * mm
    c.setStrokeColor(colors.black)
    c.setLineWidth(2.2)
    c.line(m, y, W - m, y)

    # Caja del cliente (izquierda)
    top = y - 4 * mm
    ancho_der = 46 * mm
    xi, xd = m, W - m - ancho_der
    ancho_izq = xd - 4 * mm - xi
    alto = 40 * mm
    c.setLineWidth(1)
    c.rect(xi, top - alto, ancho_izq, alto)
    fila = top - 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "CLIENTE:", 9)
    c.setFillColor(colors.black)
    ajustar(c, ne.cliente, "Helvetica-Bold", 11, ancho_izq - 30 * mm, 7)
    c.drawString(xi + 26 * mm, fila, ne.cliente)
    fila -= 6.5 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "DOMICILIO ENTREGA:")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    for i, l in enumerate(_partir(ne.domicilio_entrega or "", "Helvetica", 8.5, ancho_izq - 36 * mm)):
        c.drawString(xi + 33 * mm, fila - i * 3.6 * mm, l)
    fila -= 8.5 * mm
    mitad = xi + ancho_izq * 0.55
    _etiqueta(c, xi + 2.5 * mm, fila, "TELÉFONOS:")
    _valor(c, xi + 22 * mm, fila, ne.telefonos, mitad - xi - 24 * mm)
    _etiqueta(c, mitad, fila, "RIF:")
    _valor(c, mitad + 9 * mm, fila, ne.rif, xi + ancho_izq - mitad - 11 * mm)
    fila -= 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "COND. DE PAGO:")
    _valor(c, xi + 27 * mm, fila, ne.condicion_pago, mitad - xi - 29 * mm)
    _etiqueta(c, mitad, fila, "VENDEDOR:")
    _valor(c, mitad + 17 * mm, fila, ne.vendedor, xi + ancho_izq - mitad - 19 * mm)
    fila -= 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "COTIZACIÓN N°:")
    _valor(c, xi + 27 * mm, fila, ne.cotizacion, mitad - xi - 29 * mm)
    fila -= 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "CHOFER:")
    _valor(c, xi + 17 * mm, fila, ne.chofer, mitad - xi - 19 * mm)
    _etiqueta(c, mitad, fila, "PLACA:")
    _valor(c, mitad + 12 * mm, fila, ne.placa, xi + ancho_izq - mitad - 14 * mm)

    # Ciudad y fecha; número de la NE (derecha)
    c.rect(xd, top - 19 * mm, ancho_der, 19 * mm)
    cx = xd + ancho_der / 2
    _etiqueta(c, cx - stringWidth("CIUDAD", "Helvetica-Bold", 8) / 2, top - 4.5 * mm, "CIUDAD", 8)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawCentredString(cx, top - 8.5 * mm, ne.ciudad)
    _etiqueta(c, cx - stringWidth("FECHA", "Helvetica-Bold", 8) / 2, top - 12.5 * mm, "FECHA", 8)
    c.setFillColor(colors.black)
    f = ne.fecha
    c.setFont("Helvetica", 9)
    c.drawCentredString(cx, top - 16.5 * mm, f"{f.day:02d} de {MESES[f.month - 1]} de {f.year}" if f else "")
    c.rect(xd, top - alto, ancho_der, 18 * mm)
    c.setFillColor(SUAVE)
    c.rect(xd, top - alto + 12 * mm, ancho_der, 6 * mm, stroke=1, fill=1)
    _etiqueta(c, cx - stringWidth("NOTA DE ENTREGA", "Helvetica-Bold", 8.5) / 2, top - alto + 13.8 * mm,
              "NOTA DE ENTREGA", 8.5)
    c.setFillColor(ROJO)
    c.setFont("Times-Bold", 22)
    c.drawCentredString(cx, top - alto + 3.5 * mm, ne.numero)
    if hojas > 1:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7)
        c.drawRightString(W - m, top - alto - 3 * mm, f"Hoja {hoja} de {hojas}")
    return top - alto - 5 * mm


COLUMNAS = (("CANTIDAD", 22), ("UNIDAD", 16), ("DESCRIPCIÓN", None), ("PESO UNITARIO\n(kg)", 26), ("TOTAL (kg)", 26))


def _tabla(c: canvas.Canvas, renglones: list[RenglonNE], x0: float, ancho: float, top: float) -> tuple:
    fijos = sum(a for _, a in COLUMNAS if a) * mm
    anchos = [(a * mm if a else ancho - fijos) for _, a in COLUMNAS]
    xs = [x0]
    for a in anchos:
        xs.append(xs[-1] + a)
    alto_cab = 10 * mm
    alto_cuerpo = FILAS_POR_HOJA * ALTO_FILA
    c.setLineWidth(1)
    c.setStrokeColor(colors.black)
    c.rect(x0, top - alto_cab - alto_cuerpo, ancho, alto_cab + alto_cuerpo)
    c.line(x0, top - alto_cab, x0 + ancho, top - alto_cab)
    for x in xs[1:-1]:
        c.line(x, top, x, top - alto_cab - alto_cuerpo)
    for (titulo, _), xa, a in zip(COLUMNAS, xs, anchos):
        lineas = titulo.split("\n")
        for i, l in enumerate(lineas):
            tam = 8.5 if len(lineas) == 1 else 7
            yy = top - alto_cab / 2 - 1.2 * mm + (len(lineas) - 1) * 1.6 * mm - i * 3.2 * mm
            _etiqueta(c, xa + a / 2 - stringWidth(l, "Helvetica-Bold", tam) / 2, yy, l, tam)
    y = top - alto_cab
    for r in renglones:
        medio = y - ALTO_FILA / 2
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)
        c.drawCentredString(xs[0] + anchos[0] / 2, medio - 1.3 * mm, _cant(r.cantidad))
        c.drawCentredString(xs[1] + anchos[1] / 2, medio - 1.3 * mm, r.unidad)
        desc = _partir(r.descripcion, "Helvetica-Bold", 9.5, anchos[2] - 4 * mm, 1)[0]
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(xs[2] + 2 * mm, medio + (0.4 * mm if r.codigo else -1.3 * mm), desc)
        if r.codigo:
            c.setFillColor(GRIS)
            ajustar(c, r.codigo, "Helvetica", 6.8, anchos[2] - 4 * mm, 5)
            c.drawString(xs[2] + 2 * mm, medio - 3.4 * mm, r.codigo)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 10)
        if r.peso_unitario_kg is not None:
            c.drawCentredString(xs[3] + anchos[3] / 2, medio - 1.3 * mm, n(float(r.peso_unitario_kg), 2))
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(xs[4] + anchos[4] / 2, medio - 1.3 * mm, _kg(r.kg))
        c.setStrokeColor(LINEA)
        c.setLineWidth(0.4)
        c.line(x0, y - ALTO_FILA, x0 + ancho, y - ALTO_FILA)
        y -= ALTO_FILA
    c.setStrokeColor(colors.black)
    return top - alto_cab - alto_cuerpo, xs, anchos


def _pie(c: canvas.Canvas, ne: NotaEntregaImpresa, x0: float, ancho: float, y: float, xs, anchos,
         ultima: bool, W: float, m: float) -> None:
    alto = 17 * mm
    c.setLineWidth(1)
    c.rect(x0, y - alto, ancho, alto)
    x_tot = xs[3]
    c.line(x_tot, y, x_tot, y - alto)
    c.line(xs[4], y, xs[4], y - alto)
    c.setFillColor(ROJO)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 2 * mm, y - 4.5 * mm, "NOTAS IMPORTANTES:")
    if ne.notas:
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8.5)
        for i, l in enumerate(_partir(ne.notas, "Helvetica", 8.5, x_tot - x0 - 4 * mm, 3)):
            c.drawString(x0 + 2 * mm, y - 9 * mm - i * 3.6 * mm, l)
    _etiqueta(c, x_tot + anchos[3] / 2 - stringWidth("TOTAL", "Helvetica-Bold", 8.5) / 2, y - 9 * mm, "TOTAL", 8.5)
    _etiqueta(c, x_tot + anchos[3] / 2 - stringWidth("(kg)", "Helvetica-Bold", 8) / 2, y - 13 * mm, "(kg)", 8)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(xs[4] + anchos[4] / 2, y - 12 * mm, _kg(ne.total_kg) if ultima else "sigue…")

    y -= alto + 7 * mm
    _etiqueta(c, x0, y, "NOTA SALIDA DE ALMACÉN:", 8)
    c.setFillColor(ROJO)
    c.setFont("Times-Bold", 14)
    c.drawString(x0 + 45 * mm, y - 0.5 * mm, ne.nota_salida or "")
    y -= 6.5 * mm
    _etiqueta(c, x0, y, "FECHA Y HORA DE ELABORACIÓN:", 8)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 55 * mm, y, ne.elaborada.strftime("%d/%m/%Y %H:%M") if ne.elaborada else "")
    y -= 7 * mm
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0, y, TRASLADO)

    # Recibido conforme del cliente (izquierda) y firma y sello de Prosifer (derecha; no en una anulada)
    caja_x = W - m - 62 * mm
    if ne.anulada:
        c.setStrokeColor(LINEA)
        c.setDash(2, 2)
        c.rect(caja_x, y - 25 * mm, 62 * mm, 22 * mm)
        c.setDash()
    else:
        firma_y_sello(c, caja_x, y - 25 * mm, 62 * mm, 22 * mm)
    y -= 21 * mm
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.line(x0, y, x0 + 78 * mm, y)
    c.line(x0 + 84 * mm, y, x0 + 118 * mm, y)
    c.setFillColor(colors.black)
    c.setFont("Times-Roman", 9)
    c.drawCentredString(x0 + 39 * mm, y - 4 * mm, "NOMBRE, FIRMA Y SELLO DE RECIBIDO CONFORME")
    c.drawCentredString(x0 + 101 * mm, y - 4 * mm, "C.I.")


def _final(c: canvas.Canvas, ne: NotaEntregaImpresa, W: float, H: float, m: float) -> None:
    c.setStrokeColor(colors.black)
    c.setLineWidth(2.2)
    c.line(m, m + 9 * mm, W - m, m + 9 * mm)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(W / 2, m + 5 * mm, PLANTA)
    c.drawCentredString(W / 2, m + 1.5 * mm, CONTACTO)
    if ne.historica:
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(m, H - m + 3 * mm, "Reimpresión del histórico (emitida en Excel)")
    if ne.anulada:
        c.saveState()
        c.setFillColor(colors.Color(0.78, 0.16, 0.16, alpha=0.18))
        c.setFont("Helvetica-Bold", 90)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "ANULADA")
        c.restoreState()


FIRMA = str(Path(__file__).with_name("firma.png"))
SELLO = str(Path(__file__).with_name("sello.png"))


def firma_y_sello(c: canvas.Canvas, x: float, y: float, ancho: float, alto: float) -> None:
    """Sello de Prosifer con la firma encima, como se firma a mano. Sirve para NE y cotización."""
    sello_ancho = ancho * 0.92
    sello_alto = sello_ancho * 283 / 727
    c.drawImage(SELLO, x + (ancho - sello_ancho) / 2, y + (alto - sello_alto) / 2, width=sello_ancho,
                height=sello_alto, mask="auto")
    firma_alto = alto * 1.05
    firma_ancho = firma_alto * 350 / 465
    c.drawImage(FIRMA, x + ancho * 0.58 - firma_ancho / 2, y + (alto - firma_alto) / 2 + 1 * mm, width=firma_ancho,
                height=firma_alto, mask="auto")


def pdf_nota_entrega(ne: NotaEntregaImpresa, logo: str) -> bytes:
    buf = io.BytesIO()
    W, H = LETTER
    m = 13 * mm
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Nota de Entrega {ne.numero} {ne.cliente}")
    c.setAuthor("PROSIFER, C.A.")
    tramos = [ne.renglones[i:i + FILAS_POR_HOJA] for i in range(0, len(ne.renglones), FILAS_POR_HOJA)] or [[]]
    for i, tramo in enumerate(tramos, start=1):
        y = _cabecera(c, ne, logo, W, H, m, i, len(tramos))
        y, xs, anchos = _tabla(c, tramo, m, W - 2 * m, y)
        _pie(c, ne, m, W - 2 * m, y, xs, anchos, i == len(tramos), W, m)
        _final(c, ne, W, H, m)
        c.showPage()
    c.save()
    return buf.getvalue()

