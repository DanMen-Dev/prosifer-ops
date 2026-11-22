"""Existencias de láminas, perfiles y productos generales desde sus libros de Excel.

Sin base de datos. La fuente es la hoja "Consolidado_Item_Cliente" de cada libro: una
fila por código y una columna por dueño con las piezas disponibles (entradas menos notas
de entrega), que es lo que la oficina consulta como "disponible por cliente".

    Inventario_de_Laminas.xlsm              -> lamina
    Inventario_de_Perfiles.xlsm             -> perfil
    Inventario_de_Productos_Generales.xlsm  -> general

Reglas:
- Se cargan las celdas positivas: N piezas del código C del dueño D.
- Las celdas negativas (más notas de entrega que entradas para ese dueño) NO se cargan:
  se listan para que la oficina las resuelva con un conteo físico. Casi siempre es una
  NE cargada a otro dueño del mismo código.
- La prueba de paridad compara, por dueño, las piezas positivas del libro con lo cargado.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import openpyxl

from importador.catalogos_excel import texto

HOJA = "Consolidado_Item_Cliente"


@dataclass(frozen=True)
class Columnas:
    codigo: int
    descripcion: int
    tipo_acero: int
    norma: int
    espesor: int
    ancho: int
    largo: int
    calidad: int
    peso: int
    primer_dueno: int
    largo_en_metros: bool = False


COLUMNAS = {
    "lamina": Columnas(1, 2, 3, 4, 5, 6, 7, 8, 9, 11),
    "general": Columnas(1, 2, 3, 4, 5, 6, 7, 8, 9, 11),
    "perfil": Columnas(2, 3, 4, 5, 6, 7, 8, 10, 9, 17, largo_en_metros=True),
}


@dataclass
class FilaExistencia:
    fila: int
    codigo: str
    descripcion: str
    tipo_acero: str | None
    norma: str | None
    espesor_mm: Decimal | None
    ancho_mm: Decimal | None
    largo_mm: Decimal | None
    calidad: str | None
    peso_unitario_kg: Decimal | None
    por_dueno: dict[str, int] = field(default_factory=dict)      # solo positivos


@dataclass
class Negativo:
    fila: int
    codigo: str
    dueno: str
    piezas: int


@dataclass
class LibroExistencias:
    tipo: str
    filas: list[FilaExistencia]
    negativos: list[Negativo]
    duenos: list[str]

    def piezas_por_dueno(self) -> dict[str, int]:
        t: dict[str, int] = defaultdict(int)
        for f in self.filas:
            for d, n in f.por_dueno.items():
                t[d] += n
        return dict(t)

    @property
    def total_piezas(self) -> int:
        return sum(self.piezas_por_dueno().values())


def numero(v) -> Decimal | None:
    """49.2, '49,20' o '1,40' -> Decimal; vacío, texto o cero -> None."""
    if v is None or v == "" or isinstance(v, (bool, dt.date)):
        return None
    t = str(v).strip()
    if isinstance(v, str):
        t = t.replace(".", "").replace(",", ".") if "," in t else t
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return d if d > 0 else None


def _largo(v, en_metros: bool) -> Decimal | None:
    d = numero(v)
    if d is None:
        return None
    # Los perfiles traen el largo en metros (5,15); la app lo guarda en mm como el resto.
    return (d * 1000).quantize(Decimal("1")) if en_metros and d < 100 else d


def leer_hoja(tipo: str, filas: list[tuple]) -> LibroExistencias:
    c = COLUMNAS[tipo]
    encabezado = filas[1]
    duenos: list[tuple[int, str]] = []
    for i in range(c.primer_dueno, len(encabezado)):
        nombre = texto(encabezado[i])
        if not nombre:
            break
        duenos.append((i, nombre))
    salida: list[FilaExistencia] = []
    negativos: list[Negativo] = []
    for n, r in enumerate(filas[3:], start=4):
        r = tuple(r) + (None,) * (len(encabezado) - len(r))
        codigo = texto(r[c.codigo])
        if not codigo:
            continue
        codigo = codigo.upper()
        f = FilaExistencia(
            fila=n, codigo=codigo, descripcion=texto(r[c.descripcion]) or codigo, tipo_acero=texto(r[c.tipo_acero]),
            norma=texto(r[c.norma]), espesor_mm=numero(r[c.espesor]),
            ancho_mm=numero(r[c.ancho]) if tipo == "lamina" else None,
            largo_mm=_largo(r[c.largo], c.largo_en_metros), calidad=texto(r[c.calidad]),
            peso_unitario_kg=numero(r[c.peso]))
        for i, dueno in duenos:
            v = r[i]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v == 0:
                continue
            piezas = int(round(v))
            if piezas > 0:
                f.por_dueno[dueno] = f.por_dueno.get(dueno, 0) + piezas
            elif piezas < 0:
                negativos.append(Negativo(n, codigo, dueno, piezas))
        if f.por_dueno:
            salida.append(f)
    return LibroExistencias(tipo, salida, negativos, [d for _, d in duenos])


def leer(tipo: str, ruta: str) -> LibroExistencias:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    filas = list(wb[HOJA].iter_rows(values_only=True))
    wb.close()
    return leer_hoja(tipo, filas)


DENSIDAD_KG_DM3 = Decimal("7.85")


def peso_teorico_lamina(f: FilaExistencia) -> Decimal | None:
    """Espesor × ancho × largo × 7,85 kg/dm³, para las filas de láminas sin peso en el libro."""
    if not (f.espesor_mm and f.ancho_mm and f.largo_mm):
        return None
    return (f.espesor_mm * f.ancho_mm * f.largo_mm * DENSIDAD_KG_DM3 / 1_000_000).quantize(Decimal("0.0001"))


def paridad(libro: LibroExistencias, cargado: dict[str, int]) -> list[str]:
    """Piezas por dueño: libro (celdas positivas) contra lo cargado."""
    errores = []
    for dueno, n in libro.piezas_por_dueno().items():
        if cargado.get(dueno, 0) != n:
            errores.append(f"{dueno}: libro {n} piezas, cargado {cargado.get(dueno, 0)}")
    return errores


def informe(libro: LibroExistencias) -> list[str]:
    lineas = [f"{libro.tipo}: {len(libro.filas)} códigos con existencia, {libro.total_piezas} piezas"]
    for d, n in sorted(libro.piezas_por_dueno().items(), key=lambda x: -x[1]):
        lineas.append(f"   {d}: {n} piezas")
    if libro.negativos:
        lineas.append(f"   {len(libro.negativos)} celdas negativas NO se cargan (revisar con conteo físico):")
        for x in libro.negativos:
            lineas.append(f"     fila {x.fila} {x.codigo} · {x.dueno}: {x.piezas}")
    return lineas


if __name__ == "__main__":  # vista previa sin base de datos: python -m importador.existencias_excel lamina libro.xlsm
    import sys

    print("\n".join(informe(leer(sys.argv[1], sys.argv[2]))))
