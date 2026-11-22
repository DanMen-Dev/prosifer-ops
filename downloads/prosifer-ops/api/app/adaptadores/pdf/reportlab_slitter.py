"""Adaptador ReportLab del puerto GeneradorDocumentos: hoja de la OC de slitter y etiquetas
de rollo (6 por hoja carta, en franjas como el modelo de Prosifer, con QR)."""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.dominio.impresion import CorteImpreso as Corte
from app.dominio.impresion import OrdenSlitterImpresa as OrdenSlitter
from app.dominio.impresion import RolloImpreso as Rollo

LOGO = str(Path(__file__).with_name("logo.png"))

NARANJA = colors.HexColor("#E8461E")
AZUL = colors.HexColor("#1F3A5F")
GRIS = colors.HexColor("#5D6878")
LINEA = colors.HexColor("#C9D0DA")
SUAVE = colors.HexColor("#EEF2F7")
SCRAP = colors.HexColor("#D9534F")
TONOS = [colors.HexColor(h) for h in ("#2F5D8C", "#4E7FB0", "#3F7A63", "#6C9A80", "#7A5C99", "#9C7FB8")]
NOMBRE_TIPO = {"HP": "LAMINADO EN FRÍO", "HN": "LAMINADO EN CALIENTE", "GV": "GALVANIZADO", "ES": "ESTRUCTURAL",
               "PP": "PREPINTADO", "AL": "ALUMINIO"}


def n(x: float, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def mmtxt(x: float) -> str:
    return n(x, 0) if float(x).is_integer() else n(x, 1)


def ajustar(c: canvas.Canvas, texto: str, fuente: str, tam: float, ancho_max: float, minimo: float = 6) -> float:
    while tam > minimo and stringWidth(texto, fuente, tam) > ancho_max:
        tam -= 0.5
    c.setFont(fuente, tam)
    return tam


def qr(c: canvas.Canvas, texto: str, x: float, y: float, lado: float) -> None:
    w = QrCodeWidget(texto, barLevel="M")
    x0, y0, x1, y1 = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x1 - x0), 0, 0, lado / (y1 - y0), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)


def titulo_seccion(c: canvas.Canvas, x: float, y: float, texto: str) -> None:
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(x, y, texto)


def marca_anulada(c: canvas.Canvas, W: float, H: float) -> None:
    c.saveState()
    c.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.18))
    c.setFont("Helvetica-Bold", 90)
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "ANULADA")
    c.restoreState()


def esquema(c: canvas.Canvas, o: OrdenSlitter, x0: float, y: float, ancho_util: float) -> float:
    """Dibuja la bobina a escala: scrap repartido en los dos bordes y los rollos en medio."""
    esc = ancho_util / o.ancho
    alto = 20 * mm
    borde = o.scrap_ancho / 2
    piezas = []  # (ancho_mm, etiqueta, color, es_scrap)
    if borde > 0:
        piezas.append((borde, f"{mmtxt(borde)}", SCRAP, True))
    for ct in o.cortes:
        for r in range(ct.rollos):
            piezas.append((ct.ancho, f"{ct.posicion}-{chr(65 + r)}", TONOS[(ct.posicion - 1) % len(TONOS)], False))
    if borde > 0:
        piezas.append((borde, f"{mmtxt(borde)}", SCRAP, True))
    usado = sum(p[0] for p in piezas)
    if usado < o.ancho:  # ancho sin asignar: se muestra en gris al final
        piezas.insert(len(piezas) - (1 if borde > 0 else 0), (o.ancho - usado, "libre", colors.HexColor("#B8C0CC"), True))

    minimo = 2.2 * mm  # el scrap de pocos mm no se vería a escala: se dibuja con un ancho mínimo
    dibujado_scrap = sum(max(minimo, p[0] * esc) for p in piezas if p[2] is SCRAP)
    resto_mm = sum(p[0] for p in piezas if p[2] is not SCRAP)
    esc_r = (ancho_util - dibujado_scrap) / resto_mm if resto_mm else esc
    x = x0
    arriba = []
    for ancho_mm, et, color, es_scrap in piezas:
        w = max(minimo, ancho_mm * esc) if color is SCRAP else ancho_mm * esc_r
        c.setFillColor(color)
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.2)
        c.rect(x, y - alto, w, alto, fill=1, stroke=1)
        if not es_scrap:
            if w >= 15 * mm:
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 12)
                c.drawCentredString(x + w / 2, y - alto / 2 + 1.5 * mm, et)
                c.setFont("Helvetica-Bold", 10.5)
                c.drawCentredString(x + w / 2, y - alto / 2 - 4.5 * mm, f"{mmtxt(ancho_mm)} mm")
            else:
                arriba.append((x + w / 2, f"{et} · {mmtxt(ancho_mm)} mm"))
        x += w
    # Rollos angostos: rótulo encima con una línea guía
    c.setFont("Helvetica-Bold", 9.5)
    nivel = 0
    for cx, et in arriba:
        ty = y + 3 * mm + nivel * 4.5 * mm
        c.setStrokeColor(GRIS)
        c.setLineWidth(0.6)
        c.line(cx, y, cx, ty - 1 * mm)
        c.setFillColor(colors.black)
        c.drawCentredString(cx, ty, et)
        nivel = (nivel + 1) % 2
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(x0, y - alto, ancho_util, alto, fill=0, stroke=1)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    pie = f"Ancho de bobina {mmtxt(o.ancho)} mm"
    pie += f"  ·  scrap {mmtxt(o.scrap_ancho)} mm = {mmtxt(borde)} mm en cada borde (rojo)" if borde > 0 else "  ·  sin scrap"
    c.drawString(x0, y - alto - 5 * mm, pie)
    return y - alto - 13 * mm


def hoja_orden(c: canvas.Canvas, o: OrdenSlitter, logo: str) -> None:
    W, H = LETTER
    m = 14 * mm
    c.drawImage(logo, m, H - m - 18 * mm, width=60 * mm, height=18 * mm, mask="auto", preserveAspectRatio=True)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(W - m, H - m - 6 * mm, "ORDEN DE CORTE · SLITTER")
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(W - m, H - m - 15.5 * mm, f"N.º {o.numero}")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9.5)
    c.drawRightString(W - m, H - m - 21 * mm, f"Fecha de corte: {o.fecha}")
    y = H - m - 25 * mm
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.2)
    c.line(m, y, W - m, y)

    # Bobina
    y -= 7 * mm
    titulo_seccion(c, m, y, "BOBINA QUE ENTRA")
    y -= 2 * mm
    alto = 30 * mm
    c.setFillColor(SUAVE)
    c.setStrokeColor(LINEA)
    c.roundRect(m, y - alto, W - 2 * m, alto, 3 * mm, fill=1, stroke=1)
    qr(c, o.bobina, W - m - 27 * mm, y - alto + 3 * mm, 24 * mm)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(m + 5 * mm, y - 9 * mm, o.bobina)
    c.setFillColor(GRIS)
    linea = f"{o.producto} · {o.descripcion} · {o.tipo_nombre} · {o.norma}"
    ajustar(c, linea, "Helvetica", 9.5, W - 2 * m - 37 * mm)
    c.drawString(m + 5 * mm, y - 14.5 * mm, linea)
    filas = [("Medidas", f"{n(o.espesor, 2)} × {mmtxt(o.ancho)} mm"), ("Peso de entrada", f"{n(o.peso_entrada)} kg"),
             ("Se procesa", f"{n(o.consumido)} kg ({o.estatus.lower()})"), ("Dueño", o.dueno)]
    xs = [m + 5 * mm, m + 45 * mm, m + 78 * mm, m + 120 * mm]
    limite = W - m - 30 * mm
    for i, ((et, val), x) in enumerate(zip(filas, xs)):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        c.drawString(x, y - 21 * mm, et.upper())
        fin = xs[i + 1] - 3 * mm if i + 1 < len(xs) else limite
        ajustar(c, val, "Helvetica-Bold", 10.5, fin - x)
        c.setFillColor(colors.black)
        c.drawString(x, y - 26.5 * mm, val)
    y -= alto + 9 * mm

    # Esquema a escala
    if o.ancho and o.cortes:
        titulo_seccion(c, m, y, f"ESQUEMA DE CORTE A ESCALA  ·  calidad {o.calidad}")
        hay_angostos = any(ct.ancho * (W - 2 * m) / o.ancho < 15 * mm for ct in o.cortes)
        y -= 14 * mm if hay_angostos else 5 * mm
        y = esquema(c, o, m, y, W - 2 * m)

    # Tabla de cortes (medidas grandes: las lee el operador)
    titulo_seccion(c, m, y, "CORTES")
    y -= 6 * mm
    cols = [(m, "Pos.", "l"), (m + 14 * mm, "Ancho", "l"), (m + 46 * mm, "Rollos", "l"), (m + 66 * mm, "Producto", "l"),
            (m + 104 * mm, "kg por rollo", "r"), (W - m, "kg del corte", "r")]
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    for x0, t, al in cols:
        (c.drawRightString if al == "r" else c.drawString)(x0 + (28 * mm if t == "kg por rollo" else 0), y, t)
    c.setStrokeColor(LINEA)
    c.line(m, y - 2 * mm, W - m, y - 2 * mm)
    for ct in o.cortes:
        y -= 8.5 * mm
        c.setFillColor(TONOS[(ct.posicion - 1) % len(TONOS)])
        c.circle(m + 3 * mm, y + 1.5 * mm, 2.6 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(m + 3 * mm, y + 0.4 * mm, str(ct.posicion))
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(m + 14 * mm, y, f"{mmtxt(ct.ancho)} mm")
        c.drawString(m + 46 * mm, y, f"× {ct.rollos}")
        c.setFont("Helvetica", 10)
        c.drawString(m + 66 * mm, y + 1.5 * mm, ct.codigo_producto)
        c.setFont("Helvetica", 8)
        c.setFillColor(GRIS)
        c.drawString(m + 66 * mm, y - 2.5 * mm, ct.descripcion)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(m + 132 * mm, y, n(ct.kg / ct.rollos, 1))
        c.drawRightString(W - m, y, n(ct.kg, 1))
    y -= 8.5 * mm
    c.setFillColor(SCRAP)
    c.circle(m + 3 * mm, y + 1.5 * mm, 2.6 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(m + 14 * mm, y, f"{mmtxt(o.scrap_ancho)} mm")
    c.setFont("Helvetica", 10)
    c.drawString(m + 46 * mm, y, f"scrap ({mmtxt(o.scrap_ancho / 2)} + {mmtxt(o.scrap_ancho / 2)} en bordes)" if o.scrap_ancho else "sin scrap")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W - m, y, n(o.scrap_kg, 1))
    y -= 4 * mm
    c.setStrokeColor(LINEA)
    c.line(m, y, W - m, y)

    # Balance
    y -= 9 * mm
    producido = sum(ct.kg for ct in o.cortes)
    dif = abs(o.consumido - producido - o.scrap_kg) / o.consumido * 100 if o.consumido else 0.0
    cajas = [("Consumido", f"{n(o.consumido, 1)} kg"), ("Producido", f"{n(producido, 1)} kg"),
             ("Scrap", f"{n(o.scrap_kg, 1)} kg"), ("Diferencia", f"{n(dif, 1)} %")]
    bw = (W - 2 * m - 9 * mm) / 4
    for i, (et, val) in enumerate(cajas):
        x0 = m + i * (bw + 3 * mm)
        c.setFillColor(SUAVE)
        c.roundRect(x0, y - 6 * mm, bw, 14 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(x0 + 3 * mm, y + 3.5 * mm, et.upper())
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x0 + 3 * mm, y - 2.5 * mm, val)
    y -= 13 * mm

    # Rollos
    titulo_seccion(c, m, y, f"ROLLOS A ETIQUETAR ({len(o.rollos)})")
    y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    c.drawString(m, y, "Rollo")
    c.drawString(m + 15 * mm, y, "Código (va en la etiqueta y en el QR)")
    c.drawRightString(W - m - 22 * mm, y, "kg")
    c.drawRightString(W - m, y, "Real")
    c.line(m, y - 2 * mm, W - m, y - 2 * mm)
    for r in o.rollos:
        y -= 5.5 * mm
        if y < m + 32 * mm:  # muchas piezas: la lista sigue en otra hoja
            if o.anulada:
                marca_anulada(c, W, H)
            c.showPage()
            c.setFillColor(AZUL)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(m, H - m - 5 * mm, f"ORDEN DE CORTE · SLITTER N.º {o.numero} (continuación)")
            y = H - m - 14 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(m, y, r.posicion)
        c.setFont("Courier", 9)
        c.drawString(m + 15 * mm, y, r.codigo)
        c.setFont("Helvetica", 10)
        c.drawRightString(W - m - 22 * mm, y, n(r.kg, 2))
        c.setStrokeColor(LINEA)
        c.line(W - m - 17 * mm, y - 1, W - m, y - 1)
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS)
    c.drawString(m, y, f"Paradas: {o.paradas}    Observación: {o.observacion or '—'}")

    yf = min(m + 13 * mm, y - 14 * mm)
    fw = (W - 2 * m - 16 * mm) / 3
    for i, t in enumerate(["Elaboró (oficina)", "Operador slitter", "Recibe almacén"]):
        x0 = m + i * (fw + 8 * mm)
        c.setStrokeColor(colors.black)
        c.line(x0, yf, x0 + fw, yf)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x0 + fw / 2, yf - 4 * mm, t)
    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS)
    c.drawString(m, m - 2 * mm, f"Registrada en Prosifer Ops por {o.registro}. Columna \"Real\": peso de báscula si difiere.")
    if o.anulada:
        marca_anulada(c, W, H)
    c.showPage()


def etiqueta(c: canvas.Canvas, o: OrdenSlitter, r: Rollo, ct: Corte, logo: str,
             x0: float, y0: float, ancho: float, alto: float) -> None:
    """Etiqueta en franja (como el modelo de Prosifer): QR a la izquierda y datos en tres filas."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.2)
    c.rect(x0, y0, ancho, alto)
    p = 3 * mm
    lado = alto - 2 * p
    qr(c, r.codigo, x0 + p - 1 * mm, y0 + p, lado)
    x = x0 + p + lado + 3 * mm
    der = x0 + ancho - p
    arriba = y0 + alto - p

    # Fila 1: descripción grande, OC y logo
    c.drawImage(logo, der - 27 * mm, arriba - 8 * mm, width=27 * mm, height=8 * mm, mask="auto", preserveAspectRatio=True)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawRightString(der, arriba - 11.5 * mm, f"O/C {o.numero} · {o.fecha}")
    titulo = ct.descripcion.replace("Fleje ", "FLEJE ")
    c.setFillColor(colors.black)
    ajustar(c, titulo, "Helvetica-Bold", 14, der - 30 * mm - x)
    c.drawString(x, arriba - 5 * mm, titulo)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRIS)
    c.drawString(x, arriba - 9.5 * mm, f"{NOMBRE_TIPO.get(o.tipo_codigo, o.tipo_nombre)} · {o.norma} · {ct.codigo_producto}")

    # Fila 2: medidas y peso, en grande
    base = arriba - 21 * mm
    campos = [("ESPESOR", f"{n(o.espesor, 2)} mm", 18), ("ANCHO", f"{mmtxt(ct.ancho)} mm", 18),
              ("PESO", f"{n(r.kg)} kg", 18), ("ROLLO", r.posicion, 16)]
    anchos = [32 * mm, 32 * mm, 36 * mm, 20 * mm]
    xx = x
    for (et, val, tam), w in zip(campos, anchos):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        c.drawString(xx, base + 6.5 * mm, et)
        c.setFillColor(colors.black)
        ajustar(c, val, "Helvetica-Bold", tam, w - 2 * mm)
        c.drawString(xx, base, val)
        xx += w

    # Fila 3: trazabilidad
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    linea = f"Cliente: {o.dueno}   ·   Bobina {o.bobina}   ·   Calidad {o.calidad}"
    ajustar(c, linea, "Helvetica", 8.5, der - x)
    c.drawString(x, y0 + 7.5 * mm, linea)
    c.setFont("Courier", 7)
    c.setFillColor(GRIS)
    c.drawString(x, y0 + p, r.codigo)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawRightString(der, y0 + p, "MANUFACTURADO POR PROSIFER")


def pdf_orden(o: OrdenSlitter, logo: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"OC Slitter {o.numero}")
    hoja_orden(c, o, logo)
    c.save()
    return buf.getvalue()


def pdf_etiquetas(o: OrdenSlitter, logo: str, rollos: list[Rollo] | None = None) -> bytes:
    """6 etiquetas por hoja carta; se puede pasar una lista para reimprimir solo algunas."""
    W, H = LETTER
    margen_x, margen_y, sep = 12 * mm, 12 * mm, 5 * mm
    por_hoja = 6
    alto = (H - 2 * margen_y - (por_hoja - 1) * sep) / por_hoja
    ancho = W - 2 * margen_x
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Etiquetas OC Slitter {o.numero}")
    por_pos = {ct.posicion: ct for ct in o.cortes}
    lista = rollos if rollos is not None else o.rollos
    for i, r in enumerate(lista):
        k = i % por_hoja
        if i and k == 0:
            c.showPage()
        y0 = H - margen_y - (k + 1) * alto - k * sep
        corte = por_pos.get(r.corte) or (o.cortes[0] if o.cortes else Corte(r.corte, 0, 1, r.kg, "", r.codigo))
        etiqueta(c, o, r, corte, logo, margen_x, y0, ancho, alto)
    c.showPage()
    c.save()
    return buf.getvalue()


class GeneradorReportlab:
    """Implementa app.puertos.GeneradorDocumentos."""

    def __init__(self, logo: str = LOGO):
        self.logo = logo

    def orden_slitter(self, orden: OrdenSlitter) -> bytes:
        return pdf_orden(orden, self.logo)

    def etiquetas_slitter(self, orden: OrdenSlitter, rollos: list[Rollo] | None = None) -> bytes:
        return pdf_etiquetas(orden, self.logo, rollos)

    # Corte a lámina (laminadora y CTF): el dibujo vive en reportlab_laminas.py
    def orden_lamina(self, orden) -> bytes:
        from app.adaptadores.pdf import reportlab_laminas

        return reportlab_laminas.pdf_orden(orden, self.logo)

    def etiquetas_lamina(self, orden, atados=None) -> bytes:
        from app.adaptadores.pdf import reportlab_laminas

        return reportlab_laminas.pdf_etiquetas(orden, self.logo, atados)

    # Maquila de perfiles: el dibujo vive en reportlab_perfiles.py
    def orden_maquila(self, orden) -> bytes:
        from app.adaptadores.pdf import reportlab_perfiles

        return reportlab_perfiles.pdf_orden(orden, self.logo)

    def etiquetas_maquila(self, orden, paquetes=None) -> bytes:
        from app.adaptadores.pdf import reportlab_perfiles

        return reportlab_perfiles.pdf_etiquetas(orden, self.logo, paquetes)

    # Hoja de trabajo de la OC planificada: el dibujo vive en reportlab_hoja.py
    def hoja_trabajo(self, hoja) -> bytes:
        from app.adaptadores.pdf import reportlab_hoja

        return reportlab_hoja.pdf_hoja(hoja, self.logo)

    # Orden de despacho y nota de salida: el dibujo vive en reportlab_despacho.py
    def despacho(self, documento) -> bytes:
        from app.adaptadores.pdf import reportlab_despacho

        return reportlab_despacho.pdf_despacho(documento, self.logo)

    # Reporte de inventario por cliente: el dibujo vive en reportlab_inventario.py
    def reporte_inventario(self, reporte) -> bytes:
        from app.adaptadores.pdf import reportlab_inventario

        return reportlab_inventario.pdf_inventario(reporte, self.logo)

    # Recibo de entrada de material: el dibujo vive en reportlab_recibo.py
    def recibo_entrada(self, recibo, abajo: bool = False) -> bytes:
        from app.adaptadores.pdf import reportlab_recibo

        return reportlab_recibo.pdf_recibo(recibo, self.logo, abajo)

    # Cotización (formato de Prosifer, USD): el dibujo vive en reportlab_cotizacion.py
    def cotizacion(self, q) -> bytes:
        from app.adaptadores.pdf import reportlab_cotizacion

        return reportlab_cotizacion.pdf_cotizacion(q, self.logo)

    # Nota de entrega (formato de Prosifer): el dibujo vive en reportlab_ne.py
    def nota_entrega(self, ne) -> bytes:
        from app.adaptadores.pdf import reportlab_ne

        return reportlab_ne.pdf_nota_entrega(ne, self.logo)
