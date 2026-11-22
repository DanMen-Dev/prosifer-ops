"""Histórico de cotizaciones del libro Formato General Cotizaciones - Notas Entrega.

Sin base de datos. Hoja "DescargaCotizacion": una fila por cotización (de la fila 5 en adelante, la
más reciente arriba), con el número, el cliente, hasta 6 renglones (código, cantidad, unidad,
producto), la fecha ("13 de noviembre de 2026"; las más viejas no la tienen), hasta 6 abonos (fecha,
destino, monto), el precio de lista y el total de cada renglón en USD y el vendedor.

Las marcadas "ANULADA" en la columna del cliente se cargan como anuladas. Hay números repetidos de
la numeración vieja (antes de mayo de 2022): se distinguen por cliente.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import openpyxl

from importador.catalogos_excel import fecha_es, texto
from importador.existencias_excel import numero

HOJA = "DescargaCotizacion"
PRIMERA_FILA = 5
RENGLONES = (2, 7, 12, 17, 22, 27)        # cada renglón: código, cantidad, unidad, producto
COL_FECHA = 31
ABONOS = (32, 35, 38, 41, 44, 47)         # cada abono: fecha, destino, monto
COL_PRECIO, COL_TOTAL = 57, 64            # 6 columnas cada uno, un renglón por columna (USD)
COL_VENDEDOR = 92


def monto(v) -> Decimal | None:
    """Como numero(), pero acepta cero (un precio puede ser 0) y redondea el ruido de Excel."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, str):
        t = v.strip().replace(".", "").replace(",", ".") if "," in v else v.strip()
    else:
        t = repr(float(v))
    try:
        d = Decimal(t).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize()
        return Decimal(format(d, "f"))   # sin notación científica: 100, no 1E+2
    except InvalidOperation:
        return None


@dataclass
class Renglon:
    codigo: str | None
    cantidad: Decimal | None
    unidad: str | None
    descripcion: str | None
    precio: Decimal | None
    total: Decimal | None

    def como_dict(self) -> dict:
        d = {"codigo": self.codigo, "descripcion": self.descripcion or self.codigo or "—",
             "cantidad": str(self.cantidad) if self.cantidad is not None else None, "unidad": self.unidad,
             "precio_unitario": str(self.precio) if self.precio is not None else None,
             "total": str(self.total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if self.total is not None else None}
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class CotizacionHistorica:
    fila: int
    numero: str
    cliente: str | None
    fecha: dt.date | None
    anulada: bool
    renglones: list[Renglon] = field(default_factory=list)
    abonos: list[dict] = field(default_factory=list)
    vendedor: str | None = None

    @property
    def encabezado(self) -> dict:
        d = {"renglones": [r.como_dict() for r in self.renglones], "abonos": self.abonos, "vendedor": self.vendedor,
             "cliente_excel": self.cliente}
        return {k: v for k, v in d.items() if v not in (None, "")}

    @property
    def total(self) -> Decimal:
        return sum((r.total or Decimal("0") for r in self.renglones), Decimal("0"))


def _numero(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = texto(v)
    return t.upper().removeprefix("D-").strip() if t else None


def _fecha_abono(v) -> str | None:
    if isinstance(v, (dt.date, dt.datetime)):
        return (v.date() if isinstance(v, dt.datetime) else v).isoformat()
    return texto(v)


def cotizacion_de_fila(fila: int, r: tuple) -> CotizacionHistorica | None:
    r = tuple(r) + (None,) * (100 - len(r))
    num = _numero(r[0])
    if not num:
        return None
    cliente = texto(r[1])
    anulada = bool(cliente and cliente.upper().startswith("ANULAD"))
    q = CotizacionHistorica(fila, num, None if anulada else cliente, fecha_es(r[COL_FECHA]), anulada,
                            vendedor=texto(r[COL_VENDEDOR]))
    for i, o in enumerate(RENGLONES):
        codigo, cantidad, unidad, desc = texto(r[o]), r[o + 1], texto(r[o + 2]), texto(r[o + 3])
        if codigo and codigo.upper() == "CODIGO":   # plantilla sin código
            codigo = None
        cant = numero(cantidad)
        if not (codigo or desc) and cant is None:
            continue
        precio, total = monto(r[COL_PRECIO + i]), monto(r[COL_TOTAL + i])
        if total is None and precio is not None and cant is not None:
            total = cant * precio
        q.renglones.append(Renglon(codigo.upper() if codigo else None, cant, unidad, desc, precio, total))
    for o in ABONOS:
        m = monto(r[o + 2])
        if m:
            q.abonos.append({"fecha": _fecha_abono(r[o]), "destino": texto(r[o + 1]) or "—", "monto": str(m)})
    return q


def leer_hoja(filas) -> list[CotizacionHistorica]:
    return [q for i, r in enumerate(filas, start=PRIMERA_FILA) if (q := cotizacion_de_fila(i, r))]


def leer(ruta: str) -> list[CotizacionHistorica]:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    out = leer_hoja(wb[HOJA].iter_rows(min_row=PRIMERA_FILA, values_only=True))
    wb.close()
    return out


def ultima(cotizaciones: list[CotizacionHistorica]) -> int | None:
    nums = [int(q.numero) for q in cotizaciones if q.numero.isdigit()]
    return max(nums) if nums else None


if __name__ == "__main__":  # vista previa: python -m importador.cotizaciones_excel libro.xlsm
    import sys

    qs = leer(sys.argv[1])
    print(f"{len(qs)} cotizaciones; la última es la {ultima(qs)}; {sum(q.anulada for q in qs)} anuladas; "
          f"{sum(len(q.renglones) for q in qs)} renglones; {sum(q.fecha is None for q in qs)} sin fecha")
