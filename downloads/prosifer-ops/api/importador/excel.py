"""Lectura del libro Inventario_de_Bobinas.xlsm (solo lectura, sin macros).

Columnas según el libro a noviembre 2026. Si el libro cambia de columnas,
se ajusta aquí y en ningún otro lugar.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

import openpyxl


def _txt(v) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())
    return s or None


def _kg(v) -> Decimal:
    if isinstance(v, (int, float)):
        return Decimal(str(round(float(v), 3)))
    return Decimal("0")


def _num(v) -> Decimal | None:
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    try:
        return Decimal(str(v).replace(",", "."))
    except Exception:  # noqa: BLE001
        return None


def _fecha(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return None


@dataclass(frozen=True)
class Entrada:
    fila: int
    documento: str | None
    fecha: dt.date | None
    codigo_bobina: str
    codigo_producto: str | None
    tipo_acero: str | None
    descripcion: str | None
    norma: str | None
    espesor: Decimal | None
    ancho: Decimal | None
    peso: Decimal
    siderurgica: str | None
    buque: str | None
    propietario: str | None


@dataclass(frozen=True)
class Corte:
    hoja: str  # Producto (lámina) o ProductoF (slitter)
    fila: int
    ot: str | None
    codigo_bobina: str
    kg: Decimal
    fecha: dt.date | None


@dataclass(frozen=True)
class Salida:
    fila: int
    codigo_bobina: str
    kg: Decimal
    propietario: str | None
    documento: str | None
    numero: str | None
    fecha: dt.date | None


@dataclass(frozen=True)
class FilaConsolidado:
    fila: int
    codigo_bobina: str
    disponible: Decimal
    estado: str | None
    propietario: str | None


@dataclass
class Libro:
    entradas: list[Entrada]
    cortes: list[Corte]
    salidas: list[Salida]
    consolidado: list[FilaConsolidado]


def _filas(wb, hoja: str, desde: int):
    for i, r in enumerate(wb[hoja].iter_rows(min_row=desde, values_only=True), start=desde):
        yield i, r


def _col(r, i):
    return r[i] if i < len(r) else None


def leer(ruta: str) -> Libro:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    entradas = [
        Entrada(
            fila=i, documento=_txt(r[2]), fecha=_fecha(r[3]), codigo_bobina=_txt(r[5]),
            codigo_producto=_txt(r[6]), tipo_acero=_txt(r[7]), descripcion=_txt(r[8]),
            norma=_txt(r[9]), espesor=_num(r[10]), ancho=_num(r[11]), peso=_kg(r[12]),
            siderurgica=_txt(r[14]), buque=_txt(r[15]), propietario=_txt(r[16]),
        )
        for i, r in _filas(wb, "Entradas", 4) if _txt(r[5])
    ]
    cortes: list[Corte] = []
    # Producto: B=OT, C=bobina, W=kg procesado, AZ=fecha
    for i, r in _filas(wb, "Producto", 4):
        if _txt(r[2]):
            cortes.append(Corte("Producto", i, _txt(r[1]), _txt(r[2]), _kg(_col(r, 22)), _fecha(_col(r, 51))))
    # ProductoF: B=OT, C=bobina, Y=kg procesado, AA=fecha
    for i, r in _filas(wb, "ProductoF", 4):
        if _txt(r[2]):
            cortes.append(Corte("ProductoF", i, _txt(r[1]), _txt(r[2]), _kg(_col(r, 24)), _fecha(_col(r, 26))))
    # SalidasAjustadas: B=bobina, K=kg, N=propietario, O=documento, P=número, Q=fecha
    salidas = [
        Salida(i, _txt(r[1]), _kg(r[10]), _txt(r[13]), _txt(r[14]), _txt(r[15]), _fecha(r[16]))
        for i, r in _filas(wb, "SalidasAjustadas", 4) if _txt(r[1])
    ]
    # Consolidado: B=bobina, L=disponible, M=estado, N=propietario
    consolidado = [
        FilaConsolidado(i, _txt(r[1]), _kg(r[11]), _txt(r[12]), _txt(r[13]))
        for i, r in _filas(wb, "Consolidado", 4) if _txt(r[1])
    ]
    return Libro(entradas, cortes, salidas, consolidado)
