"""Hoja de la OC de maquila de perfiles y etiquetas de paquete, con ReportLab (mismo estilo que slitter)."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_slitter import (
    AZUL, GRIS, LINEA, NARANJA, NOMBRE_TIPO, SUAVE, ajustar, marca_anulada, n, qr, titulo_seccion,
)
from app.dominio.impresion import AtadoImpreso as Paquete
from app.dominio.impresion import OrdenMaquilaImpresa as OrdenMaquila

NOMBRE_CLASE = {"1": "Primera", "A": "Segunda A", "B": "Segunda B", "C": "Segunda C"}


def hoja_orden(c: canvas.Canvas, o: OrdenMaquila, logo: str) -> None:
    W, H = LETTER
    m = 14 * mm
    c.drawImage(logo, m, H - m - 18 * mm, width=60 * mm, height=18 * mm, mask="auto", preserveAspectRatio=True)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(W - m, H - m - 6 * mm, "ORDEN DE MAQUILA · PERFILES")
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(W - m, H - m - 15.5 * mm, f"N.º {o.numero}")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9.5)
    c.drawRightString(W - m, H - m - 21 * mm, f"Fecha: {o.fecha}")
    y = H - m - 25 * mm
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.2)
    c.line(m, y, W - m, y)

    y -= 7 * mm
    titulo_seccion(c, m, y, f"FLEJES QUE ENTRAN ({len(o.flejes)})  ·  cliente {o.dueno}")
    y -= 3 * mm
    alto = (len(o.flejes) + 1) * 7 * mm + 4 * mm
    c.setFillColor(SUAVE)
    c.setStrokeColor(LINEA)
    c.roundRect(m, y - alto, W - 2 * m, alto, 3 * mm, fill=1, stroke=1)
    yy = y - 6 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    c.drawString(m + 4 * mm, yy, "Fleje")
    c.drawRightString(W - m - 4 * mm, yy, "kg procesados")
    for f in o.flejes:
        yy -= 7 * mm
        c.setFillColor(colors.black)
        ajustar(c, f.codigo, "Helvetica-Bold", 11, W - 2 * m - 45 * mm)
        c.drawString(m + 4 * mm, yy, f.codigo)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(W - m - 4 * mm, yy, n(f.kg, 1))
    y -= alto + 6 * mm
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 9)
    c.drawString(m, y, f"{NOMBRE_TIPO.get(o.tipo_codigo, o.tipo_nombre)} · {o.norma} · espesor {n(o.espesor, 2)} mm")
    y -= 9 * mm

    titulo_seccion(c, m, y, f"PERFILES PRODUCIDOS ({n(o.total)})")
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    for x0, t in ((m, "Calidad"), (m + 32 * mm, "Perfiles"), (m + 58 * mm, "Producto")):
        c.drawString(x0, y, t)
    c.drawRightString(W - m, y, "kg")
    c.setStrokeColor(LINEA)
    c.line(m, y - 2 * mm, W - m, y - 2 * mm)
    for g in o.grupos:
        y -= 8.5 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(m, y, NOMBRE_CLASE.get(g.clase, g.clase))
        c.setFont("Helvetica-Bold", 15)
        c.drawString(m + 32 * mm, y, n(g.unidades))
        c.setFont("Helvetica", 10)
        c.drawString(m + 58 * mm, y + 1.5 * mm, g.codigo)
        c.setFillColor(GRIS)
        ajustar(c, g.descripcion, "Helvetica", 8, W - 2 * m - 90 * mm)
        c.drawString(m + 58 * mm, y - 2.5 * mm, g.descripcion)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(W - m, y, n(g.kg, 1))
    y -= 4 * mm
    c.line(m, y, W - m, y)

    y -= 9 * mm
    producido = sum(g.kg for g in o.grupos)
    teorico = f"{n(o.kg_teorico, 2)} kg ({n(abs(o.kg_por_pieza - o.kg_teorico) / o.kg_teorico * 100, 1)} %)" \
        if o.kg_teorico else "—"
    cajas = [("Procesado", f"{n(o.consumido, 1)} kg"), ("Perfiles", f"{n(producido, 1)} kg"),
             ("Scrap", f"{n(o.scrap_kg, 1)} kg"), ("Peso por perfil", f"{n(o.kg_por_pieza, 2)} kg"), ("Teórico", teorico)]
    bw = (W - 2 * m - 12 * mm) / 5
    for i, (et, val) in enumerate(cajas):
        x0 = m + i * (bw + 3 * mm)
        c.setFillColor(SUAVE)
        c.roundRect(x0, y - 6 * mm, bw, 14 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(x0 + 3 * mm, y + 3.5 * mm, et.upper())
        c.setFillColor(colors.black)
        ajustar(c, val, "Helvetica-Bold", 11, bw - 5 * mm)
        c.drawString(x0 + 3 * mm, y - 2.5 * mm, val)
    y -= 13 * mm

    titulo_seccion(c, m, y, f"PAQUETES A ETIQUETAR ({len(o.paquetes)})")
    y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    c.drawString(m, y, "Paquete")
    c.drawString(m + 17 * mm, y, "Código (va en la etiqueta y en el QR)")
    c.drawRightString(W - m - 42 * mm, y, "Perfiles")
    c.drawRightString(W - m - 22 * mm, y, "kg")
    c.drawRightString(W - m, y, "Real")
    c.line(m, y - 2 * mm, W - m, y - 2 * mm)
    for p in o.paquetes:
        y -= 5.5 * mm
        if y < m + 32 * mm:
            if o.anulada:
                marca_anulada(c, W, H)
            c.showPage()
            c.setFillColor(AZUL)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(m, H - m - 5 * mm, f"ORDEN DE MAQUILA · PERFILES N.º {o.numero} (continuación)")
            y = H - m - 14 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(m, y, str(p.atado))
        c.setFont("Courier", 9)
        c.drawString(m + 17 * mm, y, p.codigo)
        c.setFont("Helvetica", 10)
        c.drawRightString(W - m - 42 * mm, y, n(p.unidades))
        c.drawRightString(W - m - 22 * mm, y, n(p.kg, 1))
        c.setStrokeColor(LINEA)
        c.line(W - m - 17 * mm, y - 1, W - m, y - 1)
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS)
    c.drawString(m, y, f"Paradas: {o.paradas}    Observación: {o.observacion or '—'}")
    yf = min(m + 13 * mm, y - 14 * mm)
    fw = (W - 2 * m - 16 * mm) / 3
    for i, t in enumerate(["Elaboró (oficina)", "Operador perfiladora", "Recibe almacén"]):
        x0 = m + i * (fw + 8 * mm)
        c.setStrokeColor(colors.black)
        c.line(x0, yf, x0 + fw, yf)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x0 + fw / 2, yf - 4 * mm, t)
    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS)
    c.drawString(m, m - 2 * mm, f"Registrada en Prosifer Ops por {o.registro}. Peso por perfil = (procesado − scrap) ÷ perfiles.")
    if o.anulada:
        marca_anulada(c, W, H)
    c.showPage()


def etiqueta(c: canvas.Canvas, o: OrdenMaquila, titulo: str, codigo_producto: str, codigo_qr: str, cantidad: int,
             kg: float, marca: str, calidad: str, logo: str, x0: float, y0: float, ancho: float, alto: float) -> None:
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.2)
    c.rect(x0, y0, ancho, alto)
    p = 3 * mm
    lado = alto - 2 * p
    qr(c, codigo_qr, x0 + p - 1 * mm, y0 + p, lado)
    x = x0 + p + lado + 3 * mm
    der = x0 + ancho - p
    arriba = y0 + alto - p
    c.drawImage(logo, der - 27 * mm, arriba - 8 * mm, width=27 * mm, height=8 * mm, mask="auto", preserveAspectRatio=True)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawRightString(der, arriba - 11.5 * mm, f"O/C {o.numero} · {o.fecha}")
    c.setFillColor(colors.black)
    t = titulo.replace("Perfil ", "PERFIL ")
    ajustar(c, t, "Helvetica-Bold", 13, der - 30 * mm - x)
    c.drawString(x, arriba - 5 * mm, t)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRIS)
    c.drawString(x, arriba - 9.5 * mm, f"{NOMBRE_TIPO.get(o.tipo_codigo, o.tipo_nombre)} · {o.norma} · {codigo_producto}")
    base = arriba - 21 * mm
    campos = [("ESPESOR", f"{n(o.espesor, 2)} mm", 16), ("PERFILES", n(cantidad), 18), ("PESO", f"{n(kg)} kg", 16),
              ("", marca, 14)]
    anchos = [30 * mm, 28 * mm, 34 * mm, 26 * mm]
    xx = x
    for (et, val, tam), w in zip(campos, anchos):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        c.drawString(xx, base + 6.5 * mm, et)
        c.setFillColor(colors.black)
        ajustar(c, val, "Helvetica-Bold", tam, w - 2 * mm)
        c.drawString(xx, base, val)
        xx += w
    linea = f"Cliente: {o.dueno}   ·   Calidad {calidad}"
    ajustar(c, linea, "Helvetica", 8.5, der - x)
    c.setFillColor(colors.black)
    c.drawString(x, y0 + 7.5 * mm, linea)
    c.setFont("Courier", 7)
    c.setFillColor(GRIS)
    c.drawString(x, y0 + p, codigo_qr)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawRightString(der, y0 + p, "MANUFACTURADO POR PROSIFER")


def pdf_orden(o: OrdenMaquila, logo: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"OC Maquila {o.numero}")
    hoja_orden(c, o, logo)
    c.save()
    return buf.getvalue()


def pdf_etiquetas(o: OrdenMaquila, logo: str, paquetes: list[Paquete] | None = None) -> bytes:
    W, H = LETTER
    margen_x, margen_y, sep = 12 * mm, 12 * mm, 5 * mm
    por_hoja = 6
    alto = (H - 2 * margen_y - (por_hoja - 1) * sep) / por_hoja
    ancho = W - 2 * margen_x
    primera = next((g for g in o.grupos if g.clase == "1"), None)
    items: list[tuple] = []
    for p in (paquetes if paquetes is not None else o.paquetes):
        items.append((primera.descripcion if primera else "", primera.codigo if primera else "", p.codigo, p.unidades,
                      p.kg, f"PQ {p.atado}/{len(o.paquetes)}", primera.calidad if primera else ""))
    if paquetes is None:
        for g in (g for g in o.grupos if g.clase != "1"):
            items.append((g.descripcion, g.codigo, f"{g.codigo} / OC{o.numero} / 2{g.clase}", g.unidades, g.kg,
                          f"2da {g.clase}", g.calidad))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Etiquetas OC Maquila {o.numero}")
    for i, (titulo, cod, cod_qr, cant, kg, marca, calidad) in enumerate(items):
        k = i % por_hoja
        if i and k == 0:
            c.showPage()
        y0 = H - margen_y - (k + 1) * alto - k * sep
        etiqueta(c, o, titulo, cod, cod_qr, cant, kg, marca, calidad, logo, margen_x, y0, ancho, alto)
    c.showPage()
    c.save()
    return buf.getvalue()
