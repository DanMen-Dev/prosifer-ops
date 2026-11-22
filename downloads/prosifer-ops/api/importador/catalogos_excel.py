"""Clientes y productos del libro Formato_General_Cotizaciones_-_Notas_Entrega.xlsm.

Solo lectura y sin base de datos, para probarlo con el libro real o con filas armadas a mano.
Hojas a noviembre 2026:
- "Lista de Clientes": encabezado en la fila 4 (NOMBRE, DIRECCION, Estado, Rif, Telefono,
  Forma de pago, Vendedor, Ciudad, fecha de alta, Correo).
- "Lista Productos": encabezado en la fila 4 (Ref, PRODUCTO, CODIGO, ..., Peso (kg)); las
  columnas de medidas vienen vacías porque las medidas ya están en el código.

Reglas:
- Un cliente repetido (el mismo nombre sin puntos, tildes ni mayúsculas) se une en uno: vale el
  primero y se completan sus datos vacíos con los del repetido.
- Dos nombres distintos con el mismo RIF NO se unen (puede ser un nombre comercial o un RIF mal
  copiado): se cargan los dos y se avisa para que la oficina lo revise.
- Un código de producto repetido con otro nombre es un error del libro: se carga el primero
  y se informa el resto para que la oficina asigne el código correcto.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field, fields, replace
from decimal import Decimal, InvalidOperation

import openpyxl

HOJA_CLIENTES = "Lista de Clientes"
HOJA_PRODUCTOS = "Lista Productos"
PRIMERA_FILA = 5

MESES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
     "noviembre", "diciembre"], start=1)}
VENDEDOR_BASURA = {"columna2", "columna4"}


@dataclass(frozen=True)
class Cliente:
    fila: int
    nombre: str
    direccion: str | None = None
    estado_region: str | None = None
    rif: str | None = None
    telefono: str | None = None
    forma_pago: str | None = None
    vendedor: str | None = None
    ciudad: str | None = None
    cliente_desde: dt.date | None = None
    correo: str | None = None


@dataclass(frozen=True)
class Producto:
    fila: int
    codigo: str
    nombre: str
    peso_unitario_kg: Decimal | None


@dataclass
class Catalogos:
    clientes: list[Cliente] = field(default_factory=list)
    productos: list[Producto] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def texto(v) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())
    s = s.strip(" ,;")
    return s or None


def clave_nombre(nombre: str) -> str:
    """'Inversiones Delta, C.A. ' e 'Inversiones DELTA, C.A.' dan la misma clave; 'León' y 'Leon' también."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sin_tildes.lower())


def clave_rif(rif: str | None) -> str | None:
    """'J-10000002-8', 'J 100000028' y 'j-10.000.002-8' dan 'J100000028'."""
    if not rif:
        return None
    k = re.sub(r"[^A-Z0-9]", "", rif.upper())
    return k if len(k) >= 6 else None


def fecha_es(v) -> dt.date | None:
    """'19 de marzo de 2025' (como lo escribe el libro) o una fecha de Excel."""
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    t = texto(v)
    if not t:
        return None
    m = re.fullmatch(r"(\d{1,2}) de ([a-záéíóú]+) de (\d{4})", t.lower())
    if not m or m.group(2) not in MESES:
        return None
    try:
        return dt.date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


def peso(v) -> Decimal | None:
    """Acepta 49.2, 49 y '49,20'. Cero o vacío = sin peso."""
    if v is None or v == "":
        return None
    t = str(v).strip()
    if isinstance(v, str) and "," in t:  # formato venezolano: 1.234,56
        t = t.replace(".", "").replace(",", ".")
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    d = d.quantize(Decimal("0.0001"))
    return d if d > 0 else None


def _vendedor(v) -> str | None:
    t = texto(v)
    if not t or t.lower() in VENDEDOR_BASURA:
        return None
    return t.rstrip(".")  # 'R.O.' y 'R.O' son el mismo


def _forma_pago(v) -> str | None:
    t = texto(v)
    return t.capitalize() if t else None


def cliente_de_fila(fila: int, r: tuple) -> Cliente | None:
    r = tuple(r) + (None,) * (10 - len(r))
    nombre = texto(r[0])
    if not nombre:
        return None
    rif = texto(r[3])
    return Cliente(fila, nombre, direccion=texto(r[1]), estado_region=texto(r[2]),
                   rif=rif.upper() if rif else None, telefono=texto(r[4]), forma_pago=_forma_pago(r[5]),
                   vendedor=_vendedor(r[6]), ciudad=texto(r[7]), cliente_desde=fecha_es(r[8]),
                   correo=(texto(r[9]) or "").lower() or None)


def producto_de_fila(fila: int, r: tuple) -> Producto | None:
    r = tuple(r) + (None,) * (9 - len(r))
    codigo, nombre = texto(r[2]), texto(r[1])
    if not codigo or not nombre:
        return None
    return Producto(fila, codigo.upper(), nombre, peso(r[8]))


def completar(base: Cliente, otro: Cliente) -> Cliente:
    """Llena los campos vacíos de base con los de otro."""
    cambios = {f.name: getattr(otro, f.name) for f in fields(Cliente)
               if f.name not in ("fila", "nombre") and getattr(base, f.name) is None and getattr(otro, f.name)}
    return replace(base, **cambios)


def unir_clientes(filas: list[Cliente], avisos: list[str]) -> list[Cliente]:
    unidos: list[Cliente] = []
    por_nombre: dict[str, int] = {}
    por_rif: dict[str, Cliente] = {}
    for c in filas:
        kn = clave_nombre(c.nombre)
        i = por_nombre.get(kn)
        if i is not None:
            avisos.append(f"Clientes fila {c.fila}: «{c.nombre}» repite la fila {unidos[i].fila}; se unen")
            unidos[i] = completar(unidos[i], c)
            continue
        kr = clave_rif(c.rif)
        if kr and kr in por_rif:
            otro = por_rif[kr]
            avisos.append(f"Clientes fila {c.fila}: «{c.nombre}» tiene el mismo RIF {c.rif} que «{otro.nombre}» "
                          f"(fila {otro.fila}); se cargan los dos, revisar")
        elif kr:
            por_rif[kr] = c
        unidos.append(c)
        por_nombre[kn] = len(unidos) - 1
    return unidos


def depurar_productos(filas: list[Producto], avisos: list[str]) -> list[Producto]:
    vistos: dict[str, Producto] = {}
    for p in filas:
        previo = vistos.get(p.codigo)
        if previo is None:
            vistos[p.codigo] = p
        elif clave_nombre(previo.nombre) != clave_nombre(p.nombre):
            avisos.append(f"Productos fila {p.fila}: el código {p.codigo} ya es de «{previo.nombre}» "
                          f"(fila {previo.fila}); «{p.nombre}» no se carga hasta que tenga su propio código")
    return list(vistos.values())


def construir(clientes: list[Cliente], productos: list[Producto]) -> Catalogos:
    avisos: list[str] = []
    return Catalogos(unir_clientes(clientes, avisos), depurar_productos(productos, avisos), avisos)


def leer(ruta: str) -> Catalogos:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    clientes = [c for i, r in enumerate(wb[HOJA_CLIENTES].iter_rows(min_row=PRIMERA_FILA, values_only=True),
                                        start=PRIMERA_FILA) if (c := cliente_de_fila(i, r))]
    productos = [p for i, r in enumerate(wb[HOJA_PRODUCTOS].iter_rows(min_row=PRIMERA_FILA, values_only=True),
                                         start=PRIMERA_FILA) if (p := producto_de_fila(i, r))]
    wb.close()
    return construir(clientes, productos)


if __name__ == "__main__":  # vista previa sin base de datos
    import sys

    cat = leer(sys.argv[1])
    print(f"{len(cat.clientes)} clientes y {len(cat.productos)} productos")
    for a in cat.avisos:
        print(" -", a)
