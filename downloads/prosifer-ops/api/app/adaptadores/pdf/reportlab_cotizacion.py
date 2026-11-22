"""Cotización en el formato de Prosifer (carta vertical), como la del Excel: cliente a la izquierda,
ciudad, fecha y número D- a la derecha, renglones con precio unitario y total en USD, abonos, notas,
condiciones de venta, datos para la transferencia y firma y sello."""
from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_ne import (
    CONTACTO, DIRECCION_FISCAL, MESES, PLANTA, RIF_PROSIFER, ROJO, _cant, _etiqueta, _partir, _valor, firma_y_sello,
)
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, SUAVE, ajustar, n
from app.dominio.impresion import CotizacionImpresa, RenglonCotizacionImpreso

FILAS_POR_HOJA = 10
ALTO_FILA = 9 * mm
CONDICIONES = ("1- Cotización válida por 1 día  /  2- Los precios no incluyen flete",
               "3- Condiciones de venta: despacho previa cancelación",
               "4- Tiempo de entrega: a convenir luego de verificado el pago")
BANCO = (("FAVOR REALIZAR TRANSFERENCIA A NOMBRE DE:", "Helvetica", 7.5, colors.black),
         ("Productos Siderúrgicos y Ferreteros PROSIFER, C.A.", "Helvetica-Bold", 8, AZUL),
         ("BANCO: BANESCO PANAMÁ", "Helvetica-Bold", 8, colors.black),
         ("Dirección Banco: Av. Aquilino de la Guardia y Calle 47, Torre Banesco Apartado 0823-05799 Panamá",
          "Helvetica", 6.5, colors.black),
         ("Cta Nro: 201800269818", "Helvetica-Bold", 8, colors.black),
         ("Código SWIFT (BIC): BANSPAPAXXX", "Helvetica-Bold", 8, colors.black),
         ("En caso de ser necesario: Banco Intermediario: Citibank NA", "Helvetica", 7, colors.black),
         ("Dirección Banco: 111 Wall Street NY City, 10005 USA · Código SWIFT: CITIUS33XXX", "Helvetica", 6.5, colors.black),
         ("Cuenta Banesco con Banco Intermediario: 36893058", "Helvetica-Bold", 7.5, colors.black),
         ("Para pagos ZELLE: PROSIFERLLC@GMAIL.COM", "Helvetica-Bold", 8, ROJO))


def _usd(x: Decimal) -> str:
    return n(float(x), 2)


def _precio(x: Decimal) -> str:
    # 0,040 por kg o 181,820 por servicio: tres decimales, como el Excel
    return n(float(x), 3)


def _cabecera(c: canvas.Canvas, q: CotizacionImpresa, logo: str, W: float, H: float, m: float,
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

    top = y - 4 * mm
    ancho_der = 46 * mm
    xi, xd = m, W - m - ancho_der
    ancho_izq = xd - 4 * mm - xi
    alto = 34 * mm
    c.setLineWidth(1)
    c.rect(xi, top - alto, ancho_izq, alto)
    fila = top - 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "CLIENTE:", 9)
    c.setFillColor(colors.black)
    ajustar(c, q.cliente, "Helvetica-Bold", 11, ancho_izq - 30 * mm, 7)
    c.drawString(xi + 26 * mm, fila, q.cliente)
    fila -= 6.5 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "DOMICILIO FISCAL:")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    for i, l in enumerate(_partir(q.domicilio or "", "Helvetica", 8.5, ancho_izq - 36 * mm)):
        c.drawString(xi + 31 * mm, fila - i * 3.6 * mm, l)
    fila -= 8.5 * mm
    mitad = xi + ancho_izq * 0.55
    _etiqueta(c, xi + 2.5 * mm, fila, "TELÉFONOS:")
    _valor(c, xi + 22 * mm, fila, q.telefonos, mitad - xi - 24 * mm)
    _etiqueta(c, mitad, fila, "RIF:")
    _valor(c, mitad + 9 * mm, fila, q.rif, xi + ancho_izq - mitad - 11 * mm)
    fila -= 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "COND. DE PAGO:")
    _valor(c, xi + 27 * mm, fila, q.condicion_pago, mitad - xi - 29 * mm)
    _etiqueta(c, mitad, fila, "VENDEDOR:")
    _valor(c, mitad + 17 * mm, fila, q.vendedor, xi + ancho_izq - mitad - 19 * mm)
    fila -= 6 * mm
    _etiqueta(c, xi + 2.5 * mm, fila, "NOTA DE ENTREGA N°:")
    _valor(c, xi + 35 * mm, fila, q.nota_entrega, mitad - xi - 37 * mm)

    c.rect(xd, top - 19 * mm, ancho_der, 19 * mm)
    cx = xd + ancho_der / 2
    _etiqueta(c, cx - stringWidth("CIUDAD", "Helvetica-Bold", 8) / 2, top - 4.5 * mm, "CIUDAD", 8)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawCentredString(cx, top - 8.5 * mm, q.ciudad)
    _etiqueta(c, cx - stringWidth("FECHA", "Helvetica-Bold", 8) / 2, top - 12.5 * mm, "FECHA", 8)
    c.setFillColor(colors.black)
    f = q.fecha
    c.setFont("Helvetica", 9)
    c.drawCentredString(cx, top - 16.5 * mm, f"{f.day:02d} de {MESES[f.month - 1]} de {f.year}" if f else "")
    c.rect(xd, top - alto, ancho_der, 13 * mm)
    c.setFillColor(SUAVE)
    c.rect(xd, top - alto + 7.5 * mm, ancho_der, 5.5 * mm, stroke=1, fill=1)
    _etiqueta(c, cx - stringWidth("COTIZACIÓN", "Helvetica-Bold", 8.5) / 2, top - alto + 9.2 * mm, "COTIZACIÓN", 8.5)
    c.setFillColor(ROJO)
    c.setFont("Times-Bold", 20)
    c.drawCentredString(cx, top - alto + 1.8 * mm, f"D- {q.numero}")
    if hojas > 1:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7)
        c.drawRightString(W - m, top - alto - 3 * mm, f"Hoja {hoja} de {hojas}")
    return top - alto - 5 * mm


COLUMNAS = (("CANTIDAD", 22), ("UNIDAD", 18), ("DESCRIPCIÓN", None), ("PRECIO\nUNITARIO (USD)", 28), ("TOTAL (USD)", 28))


def _tabla(c: canvas.Canvas, renglones: list[RenglonCotizacionImpreso], x0: float, ancho: float, top: float):
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
        if r.precio_unitario is not None:
            c.drawRightString(xs[4] - 2.5 * mm, medio - 1.3 * mm, _precio(r.precio_unitario))
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(xs[5] - 2.5 * mm, medio - 1.3 * mm, _usd(r.total))
        c.setStrokeColor(LINEA)
        c.setLineWidth(0.4)
        c.line(x0, y - ALTO_FILA, x0 + ancho, y - ALTO_FILA)
        y -= ALTO_FILA
    c.setStrokeColor(colors.black)
    return top - alto_cab - alto_cuerpo, xs, anchos


def _totales(c: canvas.Canvas, q: CotizacionImpresa, x0: float, ancho: float, y: float, xs, anchos,
             ultima: bool) -> float:
    filas = (("SUB-TOTAL", q.subtotal), (f"IVA {n(float(q.iva_pct), 0)}%" if q.iva_pct else "IVA", q.iva if q.iva_pct else None),
             ("TOTAL", q.total))
    alto_fila = 10 * mm
    alto = alto_fila * 3
    c.setLineWidth(1)
    c.rect(x0, y - alto, ancho, alto)
    c.line(xs[3], y, xs[3], y - alto)
    c.line(xs[4], y, xs[4], y - alto)
    for i in (1, 2):
        c.line(xs[3], y - i * alto_fila, x0 + ancho, y - i * alto_fila)
    for i, (etq, val) in enumerate(filas):
        yy = y - i * alto_fila - alto_fila / 2 - 1.3 * mm
        _etiqueta(c, xs[3] + anchos[3] / 2 - stringWidth(etq, "Helvetica-Bold", 8.5) / 2, yy, etq, 8.5)
        c.setFillColor(AZUL if etq == "TOTAL" else colors.black)
        c.setFont("Helvetica-Bold", 12 if etq == "TOTAL" else 10)
        texto = ("sigue…" if not ultima else (_usd(val) if val is not None else ""))
        c.drawRightString(xs[5] - 2.5 * mm, yy, texto)
    # abonos y notas a la izquierda
    ancho_izq = xs[3] - x0 - 4 * mm
    c.setFillColor(ROJO)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 2 * mm, y - 4.5 * mm, "ABONOS REALIZADOS:")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    linea_abonos = " / ".join(q.abonos) if q.abonos else ""
    for i, l in enumerate(_partir(linea_abonos, "Helvetica", 8, ancho_izq - 34 * mm, 2)):
        c.drawString(x0 + 36 * mm, y - 4.5 * mm - i * 3.4 * mm, l)
    c.setFillColor(ROJO)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 2 * mm, y - 13.5 * mm, "NOTAS ADICIONALES:")
    c.setFillColor(AZUL)
    c.setFont("Helvetica", 8.5)
    for i, l in enumerate(_partir(q.notas or "", "Helvetica", 8.5, ancho_izq - 34 * mm, 2)):
        c.drawString(x0 + 36 * mm, y - 13.5 * mm - i * 3.6 * mm, l)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 7.5)
    for i, l in enumerate(CONDICIONES):
        c.drawString(x0 + 2 * mm, y - 21.5 * mm - i * 3.1 * mm, l)
    return y - alto


def _banco(c: canvas.Canvas, q: CotizacionImpresa, x0: float, y: float, W: float, m: float) -> None:
    yy = y - 5 * mm
    for texto, fuente, tam, color in BANCO:
        c.setFillColor(color)
        c.setFont(fuente, tam)
        c.drawString(x0, yy, texto)
        yy -= tam * 0.42 * mm + 1.6 * mm
    caja_x = W - m - 62 * mm
    if q.anulada:
        c.setStrokeColor(LINEA)
        c.setDash(2, 2)
        c.rect(caja_x, y - 30 * mm, 62 * mm, 24 * mm)
        c.setDash()
    else:
        firma_y_sello(c, caja_x, y - 30 * mm, 62 * mm, 24 * mm)


def _final(c: canvas.Canvas, q: CotizacionImpresa, W: float, H: float, m: float) -> None:
    c.setStrokeColor(colors.black)
    c.setLineWidth(2.2)
    c.line(m, m + 9 * mm, W - m, m + 9 * mm)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(W / 2, m + 5 * mm, PLANTA)
    c.drawCentredString(W / 2, m + 1.5 * mm, CONTACTO)
    if q.historica:
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(m, H - m + 3 * mm, "Reimpresión del histórico (emitida en Excel)")
    if q.anulada:
        c.saveState()
        c.setFillColor(colors.Color(0.78, 0.16, 0.16, alpha=0.18))
        c.setFont("Helvetica-Bold", 90)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "ANULADA")
        c.restoreState()


def pdf_cotizacion(q: CotizacionImpresa, logo: str) -> bytes:
    buf = io.BytesIO()
    W, H = LETTER
    m = 13 * mm
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Cotizacion D-{q.numero} {q.cliente}")
    c.setAuthor("PROSIFER, C.A.")
    tramos = [q.renglones[i:i + FILAS_POR_HOJA] for i in range(0, len(q.renglones), FILAS_POR_HOJA)] or [[]]
    for i, tramo in enumerate(tramos, start=1):
        y = _cabecera(c, q, logo, W, H, m, i, len(tramos))
        y, xs, anchos = _tabla(c, tramo, m, W - 2 * m, y)
        y = _totales(c, q, m, W - 2 * m, y, xs, anchos, i == len(tramos))
        _banco(c, q, m, y, W, m)
        _final(c, q, W, H, m)
        c.showPage()
    c.save()
    return buf.getvalue()
