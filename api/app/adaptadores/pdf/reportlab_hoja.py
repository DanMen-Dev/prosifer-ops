"""Hoja de trabajo de la OC planificada (A4 horizontal), para imprimir antes del corte.

Arriba lo que la app ya sabe (pieza, cliente, pedido, estimados); abajo casillas grandes para que el
operador anote a mano lo que sale. Después se pasa a la app en "Registrar resultados" (mismo orden
de casillas) o, más adelante, por WhatsApp leyendo el QR. Mismo estilo que la Orden de Slitter.
"""
from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, NARANJA, SUAVE, ajustar, n, qr
from app.dominio.impresion import HojaTrabajo

TITULO = {"slitter": "ORDEN DE CORTE · SLITTER", "lamina": "ORDEN DE CORTE · LAMINADORA",
          "ctf": "ORDEN DE CORTE · CTF", "maquila": "ORDEN DE MAQUILA · PERFILES"}
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _d(x) -> float:
    try:
        return float(Decimal(str(x)))
    except Exception:  # noqa: BLE001
        return 0.0


def _mm(x) -> str:
    v = _d(x)
    return n(v, 0) if v == int(v) else n(v, 2)


def _etq(c, x, y, texto, tam=7):
    c.setFillColor(GRIS)
    c.setFont("Helvetica", tam)
    c.drawString(x, y, texto.upper())


def _dato(c, x, y, etiqueta, valor, ancho, tam=11):
    _etq(c, x, y + 4.2 * mm, etiqueta)
    c.setFillColor(colors.black)
    texto = str(valor) if valor not in (None, "") else "—"
    ajustar(c, texto, "Helvetica-Bold", tam, ancho, 7)
    c.drawString(x, y, texto)


def _caja(c, x, y, w, h, titulo=None, suave=False):
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.8)
    if suave:
        c.setFillColor(SUAVE)
        c.roundRect(x, y, w, h, 2.5 * mm, stroke=1, fill=1)
    else:
        c.roundRect(x, y, w, h, 2.5 * mm, stroke=1, fill=0)
    if titulo:
        c.setFillColor(AZUL)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 3 * mm, y + h - 4.5 * mm, titulo)


def _casilla(c, x, y, w, h, etiqueta, sugerido=None):
    """Casilla blanca de borde marcado para escribir a mano."""
    c.setStrokeColor(colors.HexColor("#6F7D90"))
    c.setLineWidth(1.1)
    c.setFillColor(colors.white)
    c.rect(x, y, w, h, stroke=1, fill=1)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 6.5)
    c.drawString(x + 1.5 * mm, y + h - 3.2 * mm, etiqueta)
    if sugerido:
        c.setFillColor(colors.HexColor("#9AA6B6"))
        c.setFont("Helvetica-Oblique", 7)
        c.drawRightString(x + w - 1.5 * mm, y + 1.5 * mm, sugerido)


def _cabecera(c, h: HojaTrabajo, logo: str, W: float, H: float, m: float) -> float:
    c.drawImage(logo, m, H - m - 14 * mm, width=48 * mm, height=14 * mm, mask="auto", preserveAspectRatio=True,
                anchor="w")
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(m + 54 * mm, H - m - 7 * mm, TITULO.get(h.tipo, "ORDEN DE TRABAJO"))
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8.5)
    c.drawString(m + 54 * mm, H - m - 12.5 * mm, "Hoja de trabajo · anotar a mano lo que sale y pasar a la app en "
                 "«Registrar resultados»")
    # número, fecha y QR
    qr(c, h.qr, W - m - 24 * mm, H - m - 24 * mm, 24 * mm)
    x = W - m - 82 * mm
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(W - m - 27 * mm, H - m - 9 * mm, f"N° {h.numero}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9.5)
    f = h.fecha
    c.drawRightString(W - m - 27 * mm, H - m - 15 * mm, f"{f.day:02d} {MESES[f.month - 1]} {f.year}" if f else "")
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7)
    c.drawRightString(W - m - 27 * mm, H - m - 20 * mm, f"Planificada por {h.creado_por}"[:60])
    del x
    y = H - m - 27 * mm
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.6)
    c.line(m, y, W - m, y)
    return y - 3 * mm


def _bloque_pieza(c, h: HojaTrabajo, x, y_top, w) -> float:
    """Bobina (o fleje) que entra, con el cliente."""
    alto = 28 * mm
    _caja(c, x, y_top - alto, w, alto, "QUE ENTRA", suave=True)
    p = h.piezas[0] if h.piezas else None
    col = w / 4
    fila = y_top - 15 * mm
    _dato(c, x + 3 * mm, fila, "Cliente / dueño", h.cliente, 1.6 * col - 6 * mm, 12)
    # El código de la bobina, grande: el operador la busca en el patio con este dato
    _etq(c, x + 1.6 * col, fila + 6 * mm, "Código de la bobina (buscar en patio)")
    c.setFillColor(colors.black)
    ajustar(c, p.codigo if p else "—", "Helvetica-Bold", 22, 2.4 * col - 6 * mm, 12)
    c.drawString(x + 1.6 * col, fila - 1.5 * mm, p.codigo if p else "—")
    fila -= 10 * mm
    _dato(c, x + 3 * mm, fila, "Saldo actual", f"{n(_d(p.kg), 0)} kg" if p else "", col - 5 * mm)
    _dato(c, x + col, fila, "Espesor × ancho", f"{_mm(p.espesor_mm)} × {_mm(p.ancho_mm)} mm" if p else "",
          col - 3 * mm)
    _dato(c, x + 2 * col, fila, "Tipo / norma", f"{p.tipo_acero or '—'} · {p.norma or '—'}" if p else "", col - 3 * mm)
    _dato(c, x + 3 * col, fila, "Calidad", h.calidad or "", col - 5 * mm)
    return y_top - alto - 3 * mm


def _resultados_comunes(c, x, y_top, w, *, parcial=True) -> float:
    """Casillas que van en todas las hojas: kg procesados, scrap, paradas, horas y operador."""
    alto = 18 * mm
    etiquetas = (["Kg procesados (si es parcial)"] if parcial else []) + \
        ["Scrap (kg)", "Paradas", "Hora inicio", "Hora fin", "Operador"]
    anchos = [1.3] * (1 if parcial else 0) + [1, 0.8, 0.9, 0.9, 1.6]
    total = sum(anchos)
    xx = x
    for et, a in zip(etiquetas, anchos):
        ww = w * a / total - 2 * mm
        _casilla(c, xx, y_top - alto, ww, alto, et)
        xx += ww + 2 * mm
    return y_top - alto - 3 * mm


def _pie(c, h: HojaTrabajo, x, y_top, w, nota: str | None = None):
    alto = 26 * mm
    ancho_obs = w * 0.58
    _casilla(c, x, y_top - alto, ancho_obs, alto, "Observaciones / comentarios del operador")
    c.setStrokeColor(LINEA)
    c.setLineWidth(0.5)
    for i in range(1, 5):
        yy = y_top - alto + i * 5 * mm
        c.line(x + 2 * mm, yy, x + ancho_obs - 2 * mm, yy)
    xf = x + ancho_obs + 4 * mm
    wf = (w - ancho_obs - 4 * mm) / 2 - 2 * mm
    for i, et in enumerate(("Firma del operador", "Revisado por")):
        xx = xf + i * (wf + 4 * mm)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.7)
        c.line(xx, y_top - alto + 6 * mm, xx + wf, y_top - alto + 6 * mm)
        _etq(c, xx, y_top - alto + 2 * mm, et)
    if h.observacion:
        c.setFillColor(AZUL)
        c.setFont("Helvetica-Oblique", 8)
        ajustar(c, f"Indicaciones: {h.observacion}", "Helvetica-Oblique", 8, w * 0.4, 6)
        c.drawString(xf, y_top - 5 * mm, f"Indicaciones: {h.observacion}"[:140])
    if nota:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7)
        c.drawString(x, y_top - alto - 4 * mm, nota)


def _medida_grande(c, x, y, w, alto, titulo, valor, detalle=None):
    """Recuadro con la medida que se ajusta en la máquina (el largo), en letra grande."""
    c.setStrokeColor(NARANJA)
    c.setLineWidth(1.6)
    c.setFillColor(colors.white)
    c.roundRect(x, y, w, alto, 2.5 * mm, stroke=1, fill=1)
    c.setFillColor(NARANJA)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 3 * mm, y + alto - 5 * mm, titulo)
    c.setFillColor(colors.black)
    ajustar(c, valor, "Helvetica-Bold", 28, w - 6 * mm, 14)
    c.drawString(x + 3 * mm, y + (7.5 * mm if detalle else 5 * mm), valor)
    if detalle:
        c.setFillColor(GRIS)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 3 * mm, y + 2.5 * mm, detalle)


def _lamina(c, h: HojaTrabajo, x, y, w):
    p = h.plan
    alto = 27 * mm
    ancho_largo = 70 * mm
    w_pedido = w - ancho_largo - 3 * mm
    _caja(c, x, y - alto, w_pedido, alto, "PEDIDO")
    col = w_pedido / 4
    _dato(c, x + 3 * mm, y - 15 * mm, "Producto", p.get("descripcion"), 3 * col - 6 * mm, 15)
    _dato(c, x + 3 * col, y - 15 * mm, "Código", p.get("codigo_producto"), col - 4 * mm, 10)
    fila = y - 24 * mm
    _dato(c, x + 3 * mm, fila, "Peso teórico c/u", f"{n(_d(p.get('peso_teorico_kg')), 2)} kg", col - 6 * mm)
    est = p.get("laminas_estimadas")
    _dato(c, x + col, fila, "Láminas estimadas", f"≈ {n(est, 0)}" if est else "—", col - 4 * mm)
    _dato(c, x + 2 * col, fila, "Por atado (sugerido)", str(p.get("por_atado") or "—"), col - 4 * mm)
    _medida_grande(c, x + w_pedido + 3 * mm, y - alto, ancho_largo, alto, "LARGO A CORTAR",
                   f"{_mm(p.get('largo_mm'))} mm", f"ancho {_mm(p.get('ancho_mm'))} mm")
    y -= alto + 3 * mm

    _etq(c, x, y - 1 * mm, f"Láminas de primera por atado (sugerido: {p.get('por_atado') or '—'} por atado)", 8)
    y -= 3 * mm
    ancho_c = (w - 7 * 2 * mm) / 8
    for i in range(8):
        _casilla(c, x + i * (ancho_c + 2 * mm), y - 24 * mm, ancho_c, 24 * mm, f"Atado {i + 1}",
                 str(p.get("por_atado")) if p.get("por_atado") else None)
    y -= 27 * mm
    etiquetas = ["Total primera", "Segunda A", "Segunda B", "Segunda C", "Total láminas"]
    ancho_c = (w - 4 * 2 * mm) / 5
    for i, et in enumerate(etiquetas):
        _casilla(c, x + i * (ancho_c + 2 * mm), y - 19 * mm, ancho_c, 19 * mm, et)
    y -= 22 * mm
    return _resultados_comunes(c, x, y, w)


def _maquila(c, h: HojaTrabajo, x, y, w):
    p = h.plan
    # flejes que entran
    filas = max(len(h.piezas), 1)
    alto = 10 * mm + filas * 6 * mm
    _caja(c, x, y - alto, w, alto, f"FLEJES QUE ENTRAN · {h.cliente}", suave=True)
    cols = [("Código del fleje", 0.36), ("Espesor × ancho", 0.16), ("Saldo", 0.13), ("Kg usados si queda resto", 0.35)]
    xx = x + 3 * mm
    yy = y - 9 * mm
    for et, a in cols:
        _etq(c, xx, yy, et)
        xx += (w - 6 * mm) * a
    for i, pz in enumerate(h.piezas):
        yy = y - 14.5 * mm - i * 6 * mm
        xx = x + 3 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9.5)
        ajustar(c, pz.codigo, "Helvetica-Bold", 9.5, (w - 6 * mm) * 0.35, 6)
        c.drawString(xx, yy, pz.codigo)
        c.setFont("Helvetica", 9.5)
        c.drawString(xx + (w - 6 * mm) * 0.36, yy, f"{_mm(pz.espesor_mm)} × {_mm(pz.ancho_mm)} mm")
        c.drawString(xx + (w - 6 * mm) * 0.52, yy, f"{n(_d(pz.kg), 0)} kg")
        bx = xx + (w - 6 * mm) * 0.65
        c.setStrokeColor(colors.HexColor("#6F7D90"))
        c.setFillColor(colors.white)
        c.rect(bx, yy - 1.6 * mm, (w - 6 * mm) * 0.33, 5.2 * mm, stroke=1, fill=1)
    y -= alto + 3 * mm

    alto = 27 * mm
    ancho_largo = 70 * mm
    w_perfil = w - ancho_largo - 3 * mm
    _caja(c, x, y - alto, w_perfil, alto, "PERFIL A FABRICAR")
    col = w_perfil / 4
    _dato(c, x + 3 * mm, y - 15 * mm, "Perfil", p.get("descripcion"), 3 * col - 6 * mm, 15)
    _dato(c, x + 3 * col, y - 15 * mm, "Código", p.get("codigo_producto"), col - 4 * mm, 10)
    fila = y - 24 * mm
    _dato(c, x + 3 * mm, fila, "Peso teórico c/u",
          f"{n(_d(p.get('peso_teorico_kg')), 3)} kg" if p.get("peso_teorico_kg") else "—", col - 6 * mm)
    est = p.get("perfiles_estimados")
    _dato(c, x + col, fila, "Perfiles estimados", f"≈ {n(est, 0)}" if est else "—", col - 6 * mm)
    largo = p.get("largo_mm")
    _medida_grande(c, x + w_perfil + 3 * mm, y - alto, ancho_largo, alto, "LARGO DEL PERFIL",
                   f"{n(_d(largo) / 1000, 2)} m" if largo else "ver perfil",
                   f"{_mm(largo)} mm" if largo else None)
    y -= alto + 3 * mm

    alto_paq = 20 * mm if len(h.piezas) <= 4 else 15 * mm   # con 5 o 6 flejes todo sigue en una hoja
    _etq(c, x, y - 1 * mm, "Perfiles de primera por paquete", 8)
    y -= 3 * mm
    ancho_c = (w - 11 * 2 * mm) / 12
    for i in range(12):
        _casilla(c, x + i * (ancho_c + 2 * mm), y - alto_paq, ancho_c, alto_paq, f"Paq. {i + 1}")
    y -= alto_paq + 3 * mm
    etiquetas = ["Total primera", "Segunda A", "Segunda B", "Segunda C", "Total perfiles"]
    ancho_c = (w - 4 * 2 * mm) / 5
    for i, et in enumerate(etiquetas):
        _casilla(c, x + i * (ancho_c + 2 * mm), y - 13 * mm, ancho_c, 13 * mm, et)
    y -= 16 * mm
    return _resultados_comunes(c, x, y, w, parcial=False)


def _slitter(c, h: HojaTrabajo, x, y, w):
    p = h.plan
    cortes = p.get("cortes", [])
    filas = max(len(cortes), 1)
    alto = 11 * mm + filas * 11 * mm
    _caja(c, x, y - alto, w, alto, "CORTES PEDIDOS")
    cols = [("Pos.", 0.07), ("Ancho", 0.13), ("Rollos", 0.10), ("Ancho total", 0.13), ("Kg reales por rollo / observación", 0.57)]
    xx = x + 3 * mm
    for et, a in cols:
        _etq(c, xx, y - 9 * mm, et)
        xx += (w - 6 * mm) * a
    for i, ct in enumerate(cortes):
        yy = y - 16.5 * mm - i * 11 * mm
        xx = x + 3 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(xx, yy, str(i + 1))
        c.drawString(xx + (w - 6 * mm) * 0.07, yy, f"{_mm(ct['ancho_mm'])} mm")
        c.drawString(xx + (w - 6 * mm) * 0.20, yy, f"× {ct['rollos']}")
        c.setFont("Helvetica", 11)
        c.drawString(xx + (w - 6 * mm) * 0.30, yy, f"{_mm(_d(ct['ancho_mm']) * int(ct['rollos']))} mm")
        bx = xx + (w - 6 * mm) * 0.43
        c.setStrokeColor(colors.HexColor("#6F7D90"))
        c.setFillColor(colors.white)
        c.rect(bx, yy - 3.2 * mm, (w - 6 * mm) * 0.56, 9 * mm, stroke=1, fill=1)
    y -= alto + 2 * mm
    if p.get("scrap_ancho_mm") is not None:
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, y - 2 * mm, f"Orilla (scrap de ancho) prevista: {_mm(p['scrap_ancho_mm'])} mm")
        y -= 5 * mm
    return _resultados_comunes(c, x, y - 1 * mm, w)


def pdf_hoja(h: HojaTrabajo, logo: str) -> bytes:
    buf = io.BytesIO()
    W, H = landscape(A4)
    m = 11 * mm
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"OC {h.tipo} {h.numero} - hoja de trabajo")
    c.setAuthor("PROSIFER, C.A.")
    y = _cabecera(c, h, logo, W, H, m)
    w = W - 2 * m
    if h.tipo != "maquila":
        y = _bloque_pieza(c, h, m, y, w)
    if h.tipo in ("lamina", "ctf"):
        y = _lamina(c, h, m, y, w)
        nota = "Colocar la etiqueta de la bobina en el reverso de esta hoja · firmar y archivar"
    elif h.tipo == "maquila":
        y = _maquila(c, h, m, y, w)
        nota = "Firmar y archivar con las etiquetas de los flejes"
    else:
        y = _slitter(c, h, m, y, w)
        nota = "Colocar la etiqueta de la bobina en el reverso de esta hoja · firmar y archivar"
    _pie(c, h, m, y, w, nota)
    if h.anulada:
        c.saveState()
        c.setFillColor(colors.Color(0.78, 0.16, 0.16, alpha=0.18))
        c.setFont("Helvetica-Bold", 110)
        c.translate(W / 2, H / 2)
        c.rotate(25)
        c.drawCentredString(0, 0, "ANULADA")
        c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()
