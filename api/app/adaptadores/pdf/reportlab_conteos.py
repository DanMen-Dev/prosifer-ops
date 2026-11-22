"""Resumen de conteos físicos en patio (auditorías), carta vertical: una fila por conteo con la fecha, el producto,
lo que había en el sistema, el ajuste (+/-) y lo que quedó. Sirve para mandarlo al grupo cuando el chat se hizo
largo. Los códigos se omiten (ocupan mucho); la descripción basta para el patio."""
from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.adaptadores.pdf.reportlab_reporte_salidas import _cortar, _fecha_larga
from app.adaptadores.pdf.reportlab_slitter import AZUL, GRIS, LINEA, LOGO, SUAVE, n
from app.esquemas import ConteoOut

FILAS_POR_HOJA = 36
ALTO_FILA = 5.6 * mm
ESTADO = {"cuadra": "Cuadra", "ajustado": "Ajustado", "pendiente": "Pendiente", "descartado": "Descartado"}
VERDE = colors.HexColor("#2E7D4F")
ROJO = colors.HexColor("#C0392B")


def _cant(v: Decimal, unidad: str, signo: bool = False) -> str:
    x = float(v)
    texto = n(x, 0 if unidad == "pzas" else 1) + ("" if unidad == "pzas" else " kg")
    return ("+" + texto) if signo and x > 0 else texto


def despues(c: ConteoOut) -> Decimal:
    """Lo que quedó en el sistema tras el conteo: lo contado si cuadró o se ajustó; si no, lo de antes."""
    return c.contado if c.estado in ("cuadra", "ajustado") else c.sistema


def _columnas(con_cliente: bool) -> tuple:
    # (título, ancho en mm, alineación)
    producto = 66 if con_cliente else 100
    cols = [("Fecha", 18, "c")] + ([("Cliente", 34, "l")] if con_cliente else []) + [
        ("Producto", producto, "l"), ("Antes\n(pzas)", 17, "r"), ("Ajuste\n(+/-)", 17, "r"),
        ("Después\n(pzas)", 18, "r"), ("Estado", 22, "c")]
    return tuple(cols)


def pdf_conteos(conteos: list[ConteoOut], *, tercero: str | None, desde: dt.date | None, hasta: dt.date | None,
                ahora: dt.datetime | None = None) -> bytes:
    buf = io.BytesIO()
    W, H = LETTER
    m = 12 * mm
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle("Resumen de conteos en patio" + (f" {tercero}" if tercero else ""))
    ahora = ahora or dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))   # hora de Venezuela
    generado = ahora.strftime("%d/%m/%Y %I:%M %p")
    filas = sorted(conteos, key=lambda x: ((x.propietario or "") if not tercero else "", x.fecha, x.descripcion or x.codigo,
                                          x.id or 0))
    con_cliente = not tercero
    cols = _columnas(con_cliente)
    fechas = sorted(x.fecha for x in filas)
    ini, fin = desde or (fechas[0] if fechas else None), hasta or (fechas[-1] if fechas else None)
    hojas = max(1, -(-(len(filas) + 3) // FILAS_POR_HOJA))

    def cabecera() -> float:
        c.drawImage(LOGO, m, H - m - 14 * mm, width=48 * mm, height=14 * mm, mask="auto", preserveAspectRatio=True,
                    anchor="w")
        c.setFillColor(AZUL)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(m + 52 * mm, H - m - 6 * mm, "Resumen de conteos en patio (auditorías)")
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(m + 52 * mm, H - m - 11 * mm, _cortar(tercero or "Todos los clientes", "Helvetica-Bold", 9.5, 80 * mm))
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawRightString(W - m - 34 * mm, H - m - 6 * mm, "Desde:")
        c.drawRightString(W - m - 34 * mm, H - m - 11 * mm, "Hasta:")
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(W - m, H - m - 6 * mm, _fecha_larga(ini))
        c.drawRightString(W - m, H - m - 11 * mm, _fecha_larga(fin))
        y = H - m - 19 * mm
        c.setFillColor(AZUL)
        c.rect(m, y - 9 * mm, W - 2 * m, 9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 7.5)
        x = m
        for titulo, ancho, _ in cols:
            lineas = titulo.split("\n")
            for k, ln in enumerate(lineas):
                c.drawCentredString(x + ancho * mm / 2, y - 3.6 * mm - k * 3.2 * mm + (len(lineas) - 1) * 1.2 * mm, ln)
            x += ancho * mm
        return y - 9 * mm

    for hoja in range(hojas):
        y = cabecera()
        trozo = filas[hoja * FILAS_POR_HOJA:(hoja + 1) * FILAS_POR_HOJA]
        for k, f in enumerate(trozo):
            if k % 2:
                c.setFillColor(SUAVE)
                c.rect(m, y - ALTO_FILA, W - 2 * m, ALTO_FILA, stroke=0, fill=1)
            dif = f.diferencia if f.estado == "ajustado" else Decimal("0")
            valores = [f"{f.fecha:%d/%m/%Y}"] + ([f.propietario or ""] if con_cliente else []) + [
                f.descripcion or f.codigo, _cant(f.sistema, f.unidad),
                "—" if f.estado == "cuadra" else (f"({_cant(f.diferencia, f.unidad, True)})" if f.estado != "ajustado"
                                                  else _cant(dif, f.unidad, True)),
                _cant(despues(f), f.unidad), ESTADO.get(f.estado, f.estado)]
            x = m
            yy = y - ALTO_FILA + 1.9 * mm
            for (titulo, ancho, al), v in zip(cols, valores):
                w = ancho * mm
                color = colors.black
                if titulo.startswith("Ajuste") and f.estado != "cuadra":
                    color = GRIS if f.estado != "ajustado" else (ROJO if f.diferencia < 0 else VERDE)
                if titulo == "Estado" and f.estado == "pendiente":
                    color = ROJO
                c.setFillColor(color)
                c.setFont("Helvetica-Bold" if titulo.startswith("Después") else "Helvetica", 7.5)
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
            cuenta = {e: sum(1 for x in filas if x.estado == e) for e in ESTADO}
            menos = sum(-x.diferencia for x in filas if x.estado == "ajustado" and x.unidad == "pzas" and x.diferencia < 0)
            mas = sum(x.diferencia for x in filas if x.estado == "ajustado" and x.unidad == "pzas" and x.diferencia > 0)
            c.setFillColor(AZUL)
            c.setFont("Helvetica-Bold", 9)
            if not filas:
                c.drawString(m, y - 6 * mm, "Sin conteos en el período.")
            else:
                pl = lambda k, uno, varios: f"{k} {uno if k == 1 else varios}"   # noqa: E731
                partes = [pl(cuenta["cuadra"], "cuadra", "cuadran"), pl(cuenta["ajustado"], "ajustado", "ajustados")]
                if mas or menos:
                    partes[-1] += " (" + ", ".join(x for x in (f"+{n(float(mas))} pzas" if mas else "",
                                                               f"-{n(float(menos))} pzas" if menos else "") if x) + ")"
                if cuenta["pendiente"]:
                    partes.append(pl(cuenta["pendiente"], "pendiente", "pendientes"))
                if cuenta["descartado"]:
                    partes.append(pl(cuenta["descartado"], "descartado", "descartados"))
                c.drawString(m, y - 6 * mm, f"{pl(len(filas), 'conteo', 'conteos')}: " + ", ".join(partes) + ".")
                c.setFillColor(GRIS)
                c.setFont("Helvetica", 7.5)
                c.drawString(m, y - 11 * mm, "Antes: lo que decía el sistema al contar. Después: lo que quedó en el sistema "
                             "(lo contado si cuadró o se ajustó). Un ajuste entre paréntesis está pendiente o se descartó.")
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7)
        c.drawString(m, m - 2 * mm, f"Fecha y hora del reporte: {generado}")
        c.drawRightString(W - m, m - 2 * mm, f"Página {hoja + 1} de {hojas}")
        c.showPage()
    c.save()
    return buf.getvalue()
