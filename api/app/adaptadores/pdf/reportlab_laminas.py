"""Hoja de la OC de corte a lámina (laminadora o CTF) y etiquetas de atado, con ReportLab.

Mismo estilo que la OC de slitter: medidas grandes para el operador, QR en cada etiqueta y
6 etiquetas por hoja carta. Una etiqueta por atado de primera y una por cada clase de segunda.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_slitter import (
    AZUL, GRIS, LINEA, NARANJA, NOMBRE_TIPO, SCRAP, SUAVE, TONOS, ajustar, marca_anulada, mmtxt, n, qr, titulo_seccion,
)
from app.dominio.impresion import AtadoImpreso as Atado
from app.dominio.impresion import GrupoImpreso as Grupo
from app.dominio.impresion import OrdenLaminaImpresa as OrdenLamina

NOMBRE_CLASE = {"1": "Primera", "A": "Segunda A", "B": "Segunda B", "C": "Segunda C"}


def _cabecera(c: canvas.Canvas, o: OrdenLamina, logo: str, W: float, H: float, m: float) -> float:
    c.drawImage(logo, m, H - m - 18 * mm, width=60 * mm, height=18 * mm, mask="auto", preserveAspectRatio=True)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(W - m, H - m - 6 * mm, f"ORDEN DE CORTE · {o.maquina}")
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
    return y


def _esquema(c: canvas.Canvas, o: OrdenLamina, x0: float, y: float, ancho_util: float) -> float:
    """La lámina a escala dentro del ancho de la pieza, con el largo de corte marcado."""
    if not o.ancho_pieza or not o.largo:
        return y
    alto = 30 * mm
    largo_dib = ancho_util * 0.62
    escala = alto / o.ancho_pieza
    c.setFillColor(SUAVE)
    c.setStrokeColor(LINEA)
    c.rect(x0, y - alto, ancho_util, alto, fill=1, stroke=1)
    # láminas sucesivas sobre la bobina desenrollada
    paso = largo_dib / 2.2
    alto_lam = o.ancho * escala
    margen = (alto - alto_lam) / 2
    for i in range(3):
        xi = x0 + 4 * mm + i * paso
        if xi + paso > x0 + ancho_util:
            break
        c.setFillColor(TONOS[0] if i == 0 else TONOS[1])
        c.rect(xi, y - alto + margen, paso - 1.5 * mm, alto_lam, fill=1, stroke=0)
    if margen > 0.3 * mm:
        c.setFillColor(SCRAP)
        c.rect(x0, y - margen, ancho_util, margen, fill=1, stroke=0)
        c.rect(x0, y - alto, ancho_util, margen, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(x0 + 4 * mm + (paso - 1.5 * mm) / 2, y - alto / 2 - 2 * mm, f"{mmtxt(o.largo)} mm")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawString(x0, y - alto - 4 * mm, f"Ancho de la pieza {mmtxt(o.ancho_pieza)} mm · lámina {mmtxt(o.ancho)} × "
                                        f"{mmtxt(o.largo)} mm · espesor {n(o.espesor, 2)} mm")
    return y - alto - 10 * mm


def hoja_orden(c: canvas.Canvas, o: OrdenLamina, logo: str) -> None:
    W, H = LETTER
    m = 14 * mm
    y = _cabecera(c, o, logo, W, H, m)

    y -= 7 * mm
    titulo_seccion(c, m, y, "PIEZA QUE ENTRA")
    y -= 2 * mm
    alto = 30 * mm
    c.setFillColor(SUAVE)
    c.setStrokeColor(LINEA)
    c.roundRect(m, y - alto, W - 2 * m, alto, 3 * mm, fill=1, stroke=1)
    qr(c, o.pieza, W - m - 27 * mm, y - alto + 3 * mm, 24 * mm)
    c.setFillColor(colors.black)
    ajustar(c, o.pieza, "Helvetica-Bold", 17, W - 2 * m - 40 * mm)
    c.drawString(m + 5 * mm, y - 9 * mm, o.pieza)
    c.setFillColor(GRIS)
    linea = f"{o.producto} · {o.descripcion} · {o.tipo_nombre} · {o.norma}"
    ajustar(c, linea, "Helvetica", 9.5, W - 2 * m - 37 * mm)
    c.drawString(m + 5 * mm, y - 14.5 * mm, linea)
    filas = [("Medidas", f"{n(o.espesor, 2)} × {mmtxt(o.ancho_pieza)} mm"), ("Peso de entrada", f"{n(o.peso_entrada)} kg"),
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

    titulo_seccion(c, m, y, "CORTE")
    y -= 5 * mm
    y = _esquema(c, o, m, y, W - 2 * m)

    # Producción por calidad (medidas grandes: las lee el operador)
    titulo_seccion(c, m, y, f"LÁMINAS PRODUCIDAS ({n(o.total_laminas)})")
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    for x0, t in ((m, "Calidad"), (m + 32 * mm, "Láminas"), (m + 58 * mm, "Producto")):
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
        c.setFont("Helvetica", 8)
        c.setFillColor(GRIS)
        ajustar(c, g.descripcion, "Helvetica", 8, W - 2 * m - 90 * mm)
        c.drawString(m + 58 * mm, y - 2.5 * mm, g.descripcion)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(W - m, y, n(g.kg, 1))
    y -= 4 * mm
    c.line(m, y, W - m, y)

    # Balance
    y -= 9 * mm
    producido = sum(g.kg for g in o.grupos)
    dif = abs(o.kg_por_lamina - o.kg_teorico) / o.kg_teorico * 100 if o.kg_teorico else 0.0
    cajas = [("Procesado", f"{n(o.consumido, 1)} kg"), ("Láminas", f"{n(producido, 1)} kg"),
             ("Scrap", f"{n(o.scrap_kg, 1)} kg"), ("Peso por lámina", f"{n(o.kg_por_lamina, 2)} kg"),
             ("Teórico", f"{n(o.kg_teorico, 2)} kg ({n(dif, 1)} %)")]
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

    # Atados
    titulo_seccion(c, m, y, f"ATADOS A ETIQUETAR ({len(o.atados)})")
    y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(GRIS)
    c.drawString(m, y, "Atado")
    c.drawString(m + 15 * mm, y, "Código (va en la etiqueta y en el QR)")
    c.drawRightString(W - m - 42 * mm, y, "Láminas")
    c.drawRightString(W - m - 22 * mm, y, "kg")
    c.drawRightString(W - m, y, "Real")
    c.line(m, y - 2 * mm, W - m, y - 2 * mm)
    for a in o.atados:
        y -= 5.5 * mm
        if y < m + 32 * mm:
            if o.anulada:
                marca_anulada(c, W, H)
            c.showPage()
            c.setFillColor(AZUL)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(m, H - m - 5 * mm, f"ORDEN DE CORTE · {o.maquina} N.º {o.numero} (continuación)")
            y = H - m - 14 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(m, y, str(a.atado))
        c.setFont("Courier", 8.5)
        ajustar(c, a.codigo, "Courier", 8.5, W - 2 * m - 75 * mm)
        c.drawString(m + 15 * mm, y, a.codigo)
        c.setFont("Helvetica", 10)
        c.drawRightString(W - m - 42 * mm, y, n(a.unidades))
        c.drawRightString(W - m - 22 * mm, y, n(a.kg, 1))
        c.setStrokeColor(LINEA)
        c.line(W - m - 17 * mm, y - 1, W - m, y - 1)
    y -= 7 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS)
    c.drawString(m, y, f"Paradas: {o.paradas}    Observación: {o.observacion or '—'}")

    yf = min(m + 13 * mm, y - 14 * mm)
    fw = (W - 2 * m - 16 * mm) / 3
    for i, t in enumerate(["Elaboró (oficina)", f"Operador {o.maquina.lower()}", "Recibe almacén"]):
        x0 = m + i * (fw + 8 * mm)
        c.setStrokeColor(colors.black)
        c.line(x0, yf, x0 + fw, yf)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x0 + fw / 2, yf - 4 * mm, t)
    c.setFont("Helvetica", 7)
    c.setFillColor(GRIS)
    c.drawString(m, m - 2 * mm, f"Registrada en Prosifer Ops por {o.registro}. Peso por lámina = (procesado − scrap) ÷ láminas.")
    if o.anulada:
        marca_anulada(c, W, H)
    c.showPage()


def etiqueta(c: canvas.Canvas, o: OrdenLamina, titulo: str, codigo_producto: str, codigo_qr: str, laminas: int,
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
    t = titulo.replace("Lamina ", "LÁMINA ")
    ajustar(c, t, "Helvetica-Bold", 14, der - 30 * mm - x)
    c.drawString(x, arriba - 5 * mm, t)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRIS)
    c.drawString(x, arriba - 9.5 * mm, f"{NOMBRE_TIPO.get(o.tipo_codigo, o.tipo_nombre)} · {o.norma} · {codigo_producto}")

    base = arriba - 21 * mm
    campos = [("ESPESOR", f"{n(o.espesor, 2)} mm", 16), ("ANCHO × LARGO", f"{mmtxt(o.ancho)} × {mmtxt(o.largo)}", 15),
              ("LÁMINAS", n(laminas), 18), ("PESO", f"{n(kg)} kg", 16), ("", marca, 14)]
    anchos = [27 * mm, 36 * mm, 22 * mm, 28 * mm, 22 * mm]
    xx = x
    for (et, val, tam), w in zip(campos, anchos):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(GRIS)
        c.drawString(xx, base + 6.5 * mm, et)
        c.setFillColor(colors.black)
        ajustar(c, val, "Helvetica-Bold", tam, w - 2 * mm)
        c.drawString(xx, base, val)
        xx += w

    linea = f"Cliente: {o.dueno}   ·   Bobina {o.pieza}   ·   Calidad {calidad}"
    ajustar(c, linea, "Helvetica", 8.5, der - x)
    c.setFillColor(colors.black)
    c.drawString(x, y0 + 7.5 * mm, linea)
    c.setFont("Courier", 7)
    c.setFillColor(GRIS)
    ajustar(c, codigo_qr, "Courier", 7, der - x - 45 * mm, minimo=5)
    c.drawString(x, y0 + p, codigo_qr)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawRightString(der, y0 + p, "MANUFACTURADO POR PROSIFER")


def pdf_orden(o: OrdenLamina, logo: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"OC {o.maquina.capitalize()} {o.numero}")
    hoja_orden(c, o, logo)
    c.save()
    return buf.getvalue()


def pdf_etiquetas(o: OrdenLamina, logo: str, atados: list[Atado] | None = None) -> bytes:
    """6 etiquetas por hoja carta. Sin lista: todos los atados y una etiqueta por clase de segunda."""
    W, H = LETTER
    margen_x, margen_y, sep = 12 * mm, 12 * mm, 5 * mm
    por_hoja = 6
    alto = (H - 2 * margen_y - (por_hoja - 1) * sep) / por_hoja
    ancho = W - 2 * margen_x
    primera = next((g for g in o.grupos if g.clase == "1"), None)
    items: list[tuple] = []
    for a in (atados if atados is not None else o.atados):
        items.append((primera.descripcion if primera else o.descripcion, primera.codigo if primera else "", a.codigo,
                      a.unidades, a.kg, f"AT {a.atado}/{len(o.atados)}", primera.calidad if primera else ""))
    if atados is None:
        segundas: list[Grupo] = [g for g in o.grupos if g.clase != "1"]
        for g in segundas:
            items.append((g.descripcion, g.codigo, f"{g.codigo} / {o.pieza} / OC{o.numero} / 2{g.clase}", g.unidades,
                          g.kg, f"2da {g.clase}", g.calidad))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Etiquetas OC {o.maquina.capitalize()} {o.numero}")
    for i, (titulo, cod, cod_qr, laminas, kg, marca, calidad) in enumerate(items):
        k = i % por_hoja
        if i and k == 0:
            c.showPage()
        y0 = H - margen_y - (k + 1) * alto - k * sep
        etiqueta(c, o, titulo, cod, cod_qr, laminas, kg, marca, calidad, logo, margen_x, y0, ancho, alto)
    c.showPage()
    c.save()
    return buf.getvalue()
