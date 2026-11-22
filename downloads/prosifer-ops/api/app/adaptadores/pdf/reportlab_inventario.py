"""Reporte de inventario por cliente (carta vertical), para auditar el material en patio.

Una categoría (bobinas, flejes, láminas, perfiles o generales) o el total del cliente con un resumen
al inicio. Cada renglón trae una casilla para marcar lo verificado y al final van las firmas de
quien audita. Cabecera moderna de Prosifer, la de las órdenes de corte.
"""
from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_cabecera import PIE, cabecera, fecha_corta, pie
from app.adaptadores.pdf.reportlab_ne import _partir
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, NARANJA, SUAVE, ajustar, n
from app.dominio.impresion import FilaInventario, ReporteInventario, SeccionInventario

W, H = LETTER
M = 12 * mm
ANCHO = W - 2 * M
TIPO_CORTO = {"HP": "LAM FRIO", "HN": "LAM CALI", "GV": "LAM GALV", "ES": "LAM ESTR", "PP": "LAM PREP",
              "AL": "ALUMINIO"}
TITULO = {"bobina": "INVENTARIO DE BOBINAS", "fleje": "INVENTARIO DE FLEJES", "lamina": "INVENTARIO DE LÁMINAS",
          "perfil": "INVENTARIO DE PERFILES", "general": "INVENTARIO DE PRODUCTOS GENERALES"}
PLURAL = {"bobina": "Bobinas", "fleje": "Flejes", "lamina": "Láminas", "perfil": "Perfiles",
          "general": "Productos generales"}

ALTO_TITULO = 9 * mm
ALTO_COLUMNAS = 7 * mm
ALTO_TOTAL = 9 * mm
ALTO_FIRMAS = 24 * mm


def _d(x) -> float:
    return float(x) if x is not None else 0.0


def _medida(x) -> str:
    if x is None:
        return ""
    v = _d(x)
    return n(v, 0) if v == int(v) else n(v, 2)


def _kg(x: Decimal) -> str:
    return n(_d(x), 0)


def _piezas(x: Decimal | None) -> str:
    if x is None:
        return "1"
    return n(_d(x), 0) if x == x.to_integral_value() else n(_d(x), 2)


def _tipo(f: FilaInventario) -> str:
    return TIPO_CORTO.get(f.tipo_acero or "", f.tipo_acero or "")


# columnas: (título, ancho en mm o None = el resto, alineación, valor)
def _columnas(tipo: str):
    if tipo in ("bobina", "fleje"):
        return [("#", 8, "c", None), ("Código", 46, "l", lambda f: f.codigo), ("Tipo", 20, "c", _tipo),
                ("Norma", None, "l", lambda f: f.norma or ""), ("Esp. (mm)", 16, "r", lambda f: _medida(f.espesor_mm)),
                ("Ancho (mm)", 18, "r", lambda f: _medida(f.ancho_mm)),
                ("Entrada", 20, "c", lambda f: f.fecha_entrada.strftime("%d/%m/%y") if f.fecha_entrada else ""),
                ("Disponible (kg)", 25, "r", lambda f: _kg(f.kg)), ("OK", 9, "c", None)]
    tercera = (("Ancho (mm)", 15, "r", lambda f: _medida(f.ancho_mm)) if tipo == "lamina"
               else ("Kg / pza", 15, "r", lambda f: n(_d(f.peso_unitario_kg), 2) if f.peso_unitario_kg else ""))
    return [("#", 8, "c", None), ("Tipo", 18, "c", _tipo), ("Esp. (mm)", 14, "r", lambda f: _medida(f.espesor_mm)),
            tercera, ("Largo (mm)", 16, "r", lambda f: _medida(f.largo_mm)), ("Descripción", None, "l", None),
            ("Disponible (pzas)", 22, "r", lambda f: _piezas(f.piezas)), ("Kg", 20, "r", lambda f: _kg(f.kg)),
            ("OK", 9, "c", None)]


def _anchos(cols) -> list[float]:
    fijo = sum(a for _, a, _, _ in cols if a) * mm
    return [(a * mm if a else ANCHO - fijo) for _, a, _, _ in cols]


def _alto_fila(tipo: str) -> float:
    return 6.4 * mm if tipo in ("bobina", "fleje") else 8.2 * mm


def _resumen_txt(s: SeccionInventario) -> str:
    if s.tipo in ("bobina", "fleje"):
        k = len(s.filas)
        return f"{k} {PLURAL[s.tipo].lower() if k != 1 else s.tipo}"
    return f"{_piezas(s.total_piezas)} piezas en {len(s.filas)} producto{'s' if len(s.filas) != 1 else ''}"


# --- composición en páginas ---------------------------------------------------

def _componer(r: ReporteInventario, alto_util_primera: float, alto_util: float) -> list[list[tuple]]:
    paginas: list[list[tuple]] = [[]]
    libre = alto_util_primera

    def poner(elem: tuple, alto: float) -> None:
        nonlocal libre
        paginas[-1].append(elem)
        libre -= alto

    def nueva() -> None:
        nonlocal libre
        paginas.append([])
        libre = alto_util

    if r.total:
        alto_res = (len(r.secciones) + 3) * 7 * mm + 6 * mm
        poner(("resumen", None), alto_res)
    for s in r.secciones:
        fila = _alto_fila(s.tipo)
        if libre < ALTO_TITULO + ALTO_COLUMNAS + fila * 2:
            nueva()
        poner(("titulo", s, False), ALTO_TITULO)
        poner(("columnas", s), ALTO_COLUMNAS)
        for i, f in enumerate(s.filas, start=1):
            if libre < fila:
                nueva()
                poner(("titulo", s, True), ALTO_TITULO)
                poner(("columnas", s), ALTO_COLUMNAS)
            poner(("fila", s, f, i), fila)
        if not s.filas:
            poner(("vacia", s), fila)
        if libre < ALTO_TOTAL:
            nueva()
        poner(("total", s), ALTO_TOTAL + 3 * mm)
    if libre < ALTO_FIRMAS:
        nueva()
    poner(("firmas", None), ALTO_FIRMAS)
    return paginas


# --- dibujo -------------------------------------------------------------------

def _titulo(c, s: SeccionInventario, sigue: bool, y: float) -> float:
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(M, y - 6 * mm, PLURAL[s.tipo].upper() + ("  (continúa)" if sigue else ""))
    if not sigue:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8)
        c.drawRightString(W - M, y - 6 * mm, f"{_resumen_txt(s)} · {_kg(s.total_kg)} kg")
    return y - ALTO_TITULO


def _columnas_dibujo(c, s: SeccionInventario, y: float) -> float:
    cols = _columnas(s.tipo)
    anchos = _anchos(cols)
    c.setFillColor(AZUL)
    c.roundRect(M, y - ALTO_COLUMNAS, ANCHO, ALTO_COLUMNAS, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    x = M
    for (t, _, al, _), a in zip(cols, anchos):
        ajustar(c, t, "Helvetica-Bold", 7.5, a - 2 * mm, 5.5)
        if al == "r":
            c.drawRightString(x + a - 1.5 * mm, y - 4.6 * mm, t)
        elif al == "c":
            c.drawCentredString(x + a / 2, y - 4.6 * mm, t)
        else:
            c.drawString(x + 1.5 * mm, y - 4.6 * mm, t)
        x += a
    return y - ALTO_COLUMNAS


def _fila(c, s: SeccionInventario, f: FilaInventario, i: int, y: float) -> float:
    alto = _alto_fila(s.tipo)
    if i % 2 == 0:
        c.setFillColor(SUAVE)
        c.rect(M, y - alto, ANCHO, alto, fill=1, stroke=0)
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.3)
    c.line(M, y - alto, W - M, y - alto)
    cols = _columnas(s.tipo)
    anchos = _anchos(cols)
    medio = y - alto / 2 - 1.2 * mm
    x = M
    for (t, _, al, valor), a in zip(cols, anchos):
        c.setFillColor(colors.black)
        if t == "#":
            c.setFillColor(GRIS)
            c.setFont("Helvetica", 7)
            c.drawCentredString(x + a / 2, medio, str(i))
        elif t == "OK":
            c.setStrokeColor(GRIS)
            c.setLineWidth(0.6)
            c.rect(x + a / 2 - 1.8 * mm, y - alto / 2 - 1.8 * mm, 3.6 * mm, 3.6 * mm, fill=0, stroke=1)
        elif t == "Descripción":
            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 1.5 * mm, y - 3.6 * mm, _partir(f.descripcion, "Helvetica-Bold", 8, a - 3 * mm, 1)[0])
            c.setFillColor(GRIS)
            ajustar(c, f.codigo, "Helvetica", 6.3, a - 3 * mm, 5)
            c.drawString(x + 1.5 * mm, y - 6.8 * mm, f.codigo)
        else:
            texto = valor(f)
            fuerte = t.startswith("Disponible")
            fuente = "Helvetica-Bold" if (fuerte or t == "Código") else "Helvetica"
            tam = 9 if fuerte else 8
            ajustar(c, texto, fuente, tam, a - 2.5 * mm, 5.5)
            if al == "r":
                c.drawRightString(x + a - 1.5 * mm, medio, texto)
            elif al == "c":
                c.drawCentredString(x + a / 2, medio, texto)
            else:
                c.drawString(x + 1.5 * mm, medio, texto)
        x += a
    return y - alto


def _total(c, s: SeccionInventario, y: float) -> float:
    c.setStrokeColor(AZUL)
    c.setLineWidth(1)
    c.line(M, y - 0.5 * mm, W - M, y - 0.5 * mm)
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M + 1.5 * mm, y - 6 * mm, f"TOTAL {PLURAL[s.tipo].upper()}: {_resumen_txt(s)}")
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 11)
    tm = n(_d(s.total_kg) / 1000, 2)
    c.drawRightString(W - M - 1.5 * mm, y - 6.2 * mm, f"{_kg(s.total_kg)} kg  ({tm} TM)")
    return y - ALTO_TOTAL - 3 * mm


def _resumen(c, r: ReporteInventario, y: float) -> float:
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(M, y - 6 * mm, "RESUMEN DEL INVENTARIO")
    y -= 9 * mm
    xs = [M, M + 70 * mm, M + 105 * mm, M + 140 * mm, W - M]
    c.setFillColor(SUAVE)
    c.rect(M, y - 7 * mm, ANCHO, 7 * mm, fill=1, stroke=0)
    c.setFillColor(GRIS)
    c.setFont("Helvetica-Bold", 7.5)
    for t, x0, x1 in zip(("CATEGORÍA", "RENGLONES", "PIEZAS", "KG"), xs, xs[1:]):
        (c.drawString(x0 + 2 * mm, y - 4.7 * mm, t) if t == "CATEGORÍA" else c.drawRightString(x1 - 2 * mm, y - 4.7 * mm, t))
    y -= 7 * mm
    for s in r.secciones:
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        c.drawString(xs[0] + 2 * mm, y - 4.8 * mm, PLURAL[s.tipo])
        c.drawRightString(xs[2] - 2 * mm, y - 4.8 * mm, str(len(s.filas)))
        c.drawRightString(xs[3] - 2 * mm, y - 4.8 * mm, _piezas(s.total_piezas))
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(xs[4] - 2 * mm, y - 4.8 * mm, _kg(s.total_kg))
        c.setStrokeColor(LINEA)
        c.setLineWidth(0.3)
        c.line(M, y - 7 * mm, W - M, y - 7 * mm)
        y -= 7 * mm
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(xs[0] + 2 * mm, y - 5.2 * mm, "TOTAL EN PATIO")
    c.setFillColor(NARANJA)
    c.drawRightString(xs[4] - 2 * mm, y - 5.2 * mm, f"{_kg(r.total_kg)} kg  ({n(_d(r.total_kg) / 1000, 2)} TM)")
    return y - 13 * mm


def _firmas(c, y: float) -> float:
    y -= 14 * mm
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    ancho = (ANCHO - 12 * mm) / 3
    for i, t in enumerate(("AUDITADO POR (NOMBRE Y FIRMA)", "FECHA DEL CONTEO", "REVISADO POR PROSIFER")):
        x = M + i * (ancho + 6 * mm)
        c.line(x, y, x + ancho, y)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7)
        c.drawString(x, y - 3.5 * mm, t)
    return y - 10 * mm


def pdf_inventario(r: ReporteInventario, logo: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    titulo = "INVENTARIO TOTAL" if r.total else TITULO[r.secciones[0].tipo]
    c.setTitle(f"{titulo.title()} {r.cliente}")
    c.setAuthor("PROSIFER, C.A.")
    abajo = M + 10 * mm
    # la primera hoja lleva además la línea de "disponible al…"
    alto_cabecera = 27 * mm
    paginas = _componer(r, H - M - alto_cabecera - 8 * mm - abajo, H - M - alto_cabecera - abajo)
    sub = r.cliente + (f" · RIF {r.rif}" if r.rif else "")
    for k, elementos in enumerate(paginas, start=1):
        y = cabecera(c, logo, W, H, M, titulo=titulo, subtitulo=sub, fecha=fecha_corta(r.generado, hora=True),
                     nota=f"Generado por {r.generado_por}")
        if k == 1:
            c.setFillColor(GRIS)
            c.setFont("Helvetica", 8)
            c.drawString(M, y - 3 * mm, f"Material disponible en patio al {fecha_corta(r.generado, hora=True)}. "
                                        "Marque la casilla OK de cada renglón verificado en el conteo físico.")
            y -= 8 * mm
        for el in elementos:
            if el[0] == "resumen":
                y = _resumen(c, r, y)
            elif el[0] == "titulo":
                y = _titulo(c, el[1], el[2], y)
            elif el[0] == "columnas":
                y = _columnas_dibujo(c, el[1], y)
            elif el[0] == "fila":
                y = _fila(c, el[1], el[2], el[3], y)
            elif el[0] == "vacia":
                c.setFillColor(GRIS)
                c.setFont("Helvetica-Oblique", 8.5)
                c.drawString(M + 2 * mm, y - 5 * mm, "Sin material disponible en esta categoría.")
                y -= _alto_fila(el[1].tipo)
            elif el[0] == "total":
                y = _total(c, el[1], y)
            elif el[0] == "firmas":
                y = _firmas(c, y)
        pie(c, W, M, PIE, k, len(paginas))
        c.showPage()
    c.save()
    return buf.getvalue()
