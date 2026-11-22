"""Histórico de notas de entrega del libro Formato General Cotizaciones - Notas Entrega.

Sin base de datos. Hoja "DescargaNotaEntrega": una fila por NE (de la fila 5 en adelante),
con el número, el cliente, hasta 6 renglones (código, cantidad, unidad, producto, peso del
renglón), la fecha ("06 de noviembre de 2026" o fecha de Excel), la nota de salida, el
conductor, la placa y la masa total.

Solo consulta y respaldo: estas NE no mueven inventario (el saldo de apertura ya las descuenta).
Las NE marcadas "ANULADA" en la columna del cliente se cargan como anuladas.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

import openpyxl

from importador.catalogos_excel import fecha_es, texto
from importador.existencias_excel import numero

HOJA = "DescargaNotaEntrega"
PRIMERA_FILA = 5
RENGLONES = (2, 7, 12, 17, 22, 27)       # cada renglón: código, cantidad, unidad, producto, peso
COL_FECHA, COL_SALIDA, COL_CONDUCTOR, COL_PLACA, COL_MASA = 32, 33, 34, 35, 36


@dataclass
class Renglon:
    posicion: int
    codigo: str | None
    cantidad: Decimal | None
    unidad: str | None
    descripcion: str | None
    kg: Decimal | None


@dataclass
class NotaHistorica:
    fila: int
    numero: str
    cliente: str | None
    fecha: dt.date | None
    anulada: bool
    renglones: list[Renglon] = field(default_factory=list)
    nota_salida: str | None = None
    conductor: str | None = None
    placa: str | None = None
    masa_total: Decimal | None = None
    fecha_excel: dt.date | None = None      # la fecha tal como estaba, si hubo que corregirla

    @property
    def encabezado(self) -> dict | None:
        """Lo que la NE impresa muestra abajo y en el recuadro del cliente."""
        d = {"nota_salida": self.nota_salida, "chofer": self.conductor, "placa": self.placa}
        d = {k: v for k, v in d.items() if v}
        return d or None

    @property
    def observacion(self) -> str | None:
        partes = [f"Fecha corregida (el Excel decía {self.fecha_excel:%d/%m/%Y})" if self.fecha_excel else None,
                  f"Nota de salida {self.nota_salida}" if self.nota_salida else None,
                  f"Conductor {self.conductor}" if self.conductor else None,
                  f"Placa {self.placa}" if self.placa else None]
        partes = [p for p in partes if p]
        return " · ".join(partes) or None


def _numero_ne(v) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = texto(v)
    return t.upper() if t else None


def _entero_texto(v) -> str | None:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return texto(v)


def nota_de_fila(fila: int, r: tuple) -> NotaHistorica | None:
    r = tuple(r) + (None,) * (40 - len(r))
    num = _numero_ne(r[0])
    if not num:
        return None
    cliente = texto(r[1])
    anulada = bool(cliente and cliente.upper().startswith("ANULAD"))
    nota = NotaHistorica(fila, num, None if anulada else cliente, fecha_es(r[COL_FECHA]), anulada,
                         nota_salida=_entero_texto(r[COL_SALIDA]), conductor=texto(r[COL_CONDUCTOR]),
                         placa=texto(r[COL_PLACA]), masa_total=numero(r[COL_MASA]))
    for i, o in enumerate(RENGLONES, start=1):
        codigo, cantidad, unidad, desc, kg = (r[o], r[o + 1], r[o + 2], r[o + 3], r[o + 4])
        codigo, desc = texto(codigo), texto(desc)
        cant = numero(cantidad)
        if not (codigo or desc) and cant is None:
            continue
        nota.renglones.append(Renglon(i, codigo.upper() if codigo else None, cant, texto(unidad), desc, numero(kg)))
    return nota


PRIMER_ANO = 2012


def _posible(f: dt.date | None, hoy: dt.date) -> bool:
    return f is not None and dt.date(PRIMER_ANO, 1, 1) <= f <= hoy


def _con_ano(f: dt.date, ano: int) -> dt.date | None:
    try:
        return f.replace(year=ano)
    except ValueError:      # 29 de febrero
        return None


def corregir_fechas(notas: list[NotaHistorica], hoy: dt.date | None = None) -> list[NotaHistorica]:
    """Arregla fechas imposibles del Excel (año 0202, 2004, 2029, 2034…; o futuras).

    Las NE van en orden: la fecha correcta queda entre la de la NE anterior y la siguiente.
    Primero se prueba el mismo día y mes con el año de las vecinas; si no cae entre ellas, se usa
    la fecha de la NE anterior. La fecha original queda en fecha_excel.
    """
    hoy = hoy or dt.date.today()
    numeradas = sorted((n for n in notas if n.numero.isdigit()), key=lambda n: int(n.numero))
    for i, n in enumerate(numeradas):
        if n.fecha is None or _posible(n.fecha, hoy):
            continue
        antes = next((m.fecha for m in reversed(numeradas[:i]) if _posible(m.fecha, hoy)), None)
        despues = next((m.fecha for m in numeradas[i + 1:] if _posible(m.fecha, hoy)), None)
        anos = {f.year for f in (antes, despues) if f}
        candidatas = [c for a in sorted(anos) if (c := _con_ano(n.fecha, a))
                      and (antes is None or c >= antes) and (despues is None or c <= despues)]
        nueva = candidatas[0] if candidatas else (antes or despues)
        if nueva:
            n.fecha_excel, n.fecha = n.fecha, nueva
    return notas


def leer_hoja(filas, hoy: dt.date | None = None) -> list[NotaHistorica]:
    return corregir_fechas([n for i, r in enumerate(filas, start=PRIMERA_FILA) if (n := nota_de_fila(i, r))], hoy)


def leer(ruta: str) -> list[NotaHistorica]:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    notas = leer_hoja(wb[HOJA].iter_rows(min_row=PRIMERA_FILA, values_only=True))
    wb.close()
    return notas


def ultima(notas: list[NotaHistorica]) -> int | None:
    """La NE de número más alto (sin las que llevan letra, como 1371-A)."""
    nums = [int(n.numero) for n in notas if n.numero.isdigit()]
    return max(nums) if nums else None


if __name__ == "__main__":  # vista previa: python -m importador.ne_historico_excel libro.xlsm
    import sys

    notas = leer(sys.argv[1])
    print(f"{len(notas)} notas de entrega; la última es la {ultima(notas)}; "
          f"{sum(n.anulada for n in notas)} anuladas; {sum(len(n.renglones) for n in notas)} renglones")
