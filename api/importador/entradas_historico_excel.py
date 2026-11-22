"""Histórico de entradas de material de los libros Inventario de Láminas e Inventario de Productos Generales.

Sin base de datos. Cada libro guarda sus entradas en dos hojas que se alternan:
"Entradas_Lam_Almacen_Otras" y "Entradas_Lam_Almacen_Otras_Def" (se leen las dos). Fila 2: títulos;
fila 3: "INICIO"; desde la fila 4, un renglón por producto que entró:

    PROPIETARIO | CODIGO | DESCRIPCION | TIPO | NORMA | ESPESOR | ANCHO | LARGO | CALIDAD | TOTAL | FECHA |
    DOCUMENTO | NUMERO | NOMBRE DOCUMENTO | PESO (KG) (láminas: peso por pieza) o PRODUCTO (generales)

Los renglones de un mismo documento (dueño + nombre del documento + fecha) forman una entrada.
Solo consulta: no mueven inventario (el saldo de apertura ya los incluye).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

import openpyxl

from importador.catalogos_excel import fecha_es, texto
from importador.existencias_excel import numero

HOJAS = ("Entradas_Lam_Almacen_Otras", "Entradas_Lam_Almacen_Otras_Def")
PRIMERA_FILA = 4
(C_DUENO, C_CODIGO, C_DESC, C_TIPO, C_NORMA, C_ESP, C_ANCHO, C_LARGO, C_CAL, C_TOTAL, C_FECHA,
 C_DOC, C_NUM, C_NOMBRE_DOC, C_PESO) = range(15)


@dataclass
class Renglon:
    posicion: int
    codigo: str | None
    descripcion: str | None
    cantidad: Decimal | None
    kg: Decimal | None
    peso_unitario: Decimal | None    # del libro de láminas; en generales se toma del catálogo al cargar


@dataclass
class EntradaHistorica:
    libro: str
    hoja: str
    fila: int                        # primera fila del documento en la hoja
    propietario: str | None
    documento: str                   # "Nota de Entrega Nro.20102026"
    fecha: dt.date | None
    renglones: list[Renglon] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def clave(self) -> tuple:
        return ((self.propietario or "").lower(), self.documento.lower(), self.fecha)


def _documento(tipo, numero_doc, nombre) -> str | None:
    if isinstance(numero_doc, float) and numero_doc.is_integer():
        numero_doc = int(numero_doc)
    n = texto(nombre)
    if n:
        return n
    partes = [texto(tipo), texto(numero_doc)]
    return " ".join(p for p in partes if p) or None


def leer(ruta: str, hoy: dt.date | None = None) -> list[EntradaHistorica]:
    hoy = hoy or dt.date.today()
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    libro = ruta.rsplit("/", 1)[-1]
    entradas: dict[tuple, EntradaHistorica] = {}
    for hoja in HOJAS:
        if hoja not in wb.sheetnames:
            continue
        ws = wb[hoja]
        con_peso = texto(ws.cell(2, C_PESO + 1).value or "") or ""
        peso_por_pieza = "PESO" in con_peso.upper()
        for i, r in enumerate(ws.iter_rows(min_row=PRIMERA_FILA, values_only=True), start=PRIMERA_FILA):
            r = tuple(r) + (None,) * (15 - len(r))
            codigo, desc = texto(r[C_CODIGO]), texto(r[C_DESC])
            if not codigo and not desc:
                continue
            if (codigo or "").upper() == "INICIO":
                continue
            documento = _documento(r[C_DOC], r[C_NUM], r[C_NOMBRE_DOC]) or "Sin documento"
            fecha = fecha_es(r[C_FECHA])
            dueno = texto(r[C_DUENO])
            e = EntradaHistorica(libro, hoja, i, dueno, documento, fecha)
            e = entradas.setdefault(e.clave, e)
            if fecha and fecha > hoy and not e.avisos:
                e.avisos.append(f"fecha {fecha:%d/%m/%Y} en el futuro (¿error de tipeo?)")
            cant = numero(r[C_TOTAL])
            peso = numero(r[C_PESO]) if peso_por_pieza else None
            e.renglones.append(Renglon(len(e.renglones) + 1, codigo, desc, cant,
                                       (cant * peso).quantize(Decimal("0.001")) if cant and peso else None, peso))
    wb.close()
    return sorted(entradas.values(), key=lambda e: (e.fecha or dt.date.min, e.documento))
