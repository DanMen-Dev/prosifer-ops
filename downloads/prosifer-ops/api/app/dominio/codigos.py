"""Reglas de codificación de productos (ver doc de reglas, sección Catálogos).

Código de producto = prefijo + tipo (2 letras) + espesor (3 dígitos, centésimas de mm)
+ ancho (4 dígitos, mm) [+ largo (4 dígitos, mm) en láminas].

    BOBHP0901220      bobina laminada en frío 0,90 x 1220
    FLEHP0900268      fleje 0,90 x 268
    LAMHP11012502400  lámina 1,10 x 1250 x 2400
"""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

PREFIJOS = {"bobina": "BOB", "fleje": "FLE", "lamina": "LAM"}

# Segunda calidad: el código lleva -A, -B o -C y la descripción (2A), (2B) o (2C).
SEGUNDAS = ("A", "B", "C")

# Nombre del tipo de acero en los libros -> código de 2 letras (decidido 8 nov 2026).
TIPOS_ACERO = {
    "LAM FRIO": "HP",
    "LAM CALI": "HN",
    "LAM GALV": "GV",
    "LAM ESTR": "ES",
    "LAM PREP": "PP",
    "ALUMINIO": "AL",
}
# Códigos viejos que usaban los libros de láminas y se normalizan al importar.
EQUIVALENCIAS_TIPO = {"EST": "ES", "ALU": "AL"}

# Espesor real -> espesor comercial con el que se nombra el producto.
ESPESOR_COMERCIAL = {
    Decimal("0.58"): Decimal("0.60"),
    Decimal("0.68"): Decimal("0.70"),
    Decimal("0.88"): Decimal("0.90"),
    Decimal("1.08"): Decimal("1.10"),
    Decimal("1.90"): Decimal("2.00"),
    Decimal("2.90"): Decimal("3.00"),
}


class CodigoInvalido(ValueError):
    pass


def _dec(valor) -> Decimal:
    try:
        return Decimal(str(valor).replace(",", "."))
    except Exception as exc:  # noqa: BLE001
        raise CodigoInvalido(f"número inválido: {valor!r}") from exc


def codigo_tipo(tipo: str) -> str:
    """Acepta el nombre del libro (LAM FRIO) o el código (HP, EST...)."""
    t = (tipo or "").strip().upper()
    if t in TIPOS_ACERO:
        return TIPOS_ACERO[t]
    t = EQUIVALENCIAS_TIPO.get(t, t)
    if t in TIPOS_ACERO.values():
        return t
    raise CodigoInvalido(f"tipo de acero desconocido: {tipo!r}")


def espesor_comercial(espesor) -> Decimal:
    e = _dec(espesor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ESPESOR_COMERCIAL.get(e, e)


def _digitos(valor: Decimal, ancho: int, nombre: str) -> str:
    n = int(valor.to_integral_value(rounding=ROUND_HALF_UP))
    if n <= 0 or len(str(n)) > ancho:
        raise CodigoInvalido(f"{nombre} fuera de rango para el código: {valor}")
    return str(n).zfill(ancho)


def ancho_codigo(ancho) -> str:
    """Ancho en mm con 4 dígitos; si tiene decimales van tras una D: 38,1 -> 0038D1, 19,05 -> 0019D05.
    Así 38 y 38,1 no comparten código (decidido el 10 nov 2026)."""
    a = _dec(ancho).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero, frac = divmod(a, 1)
    if entero <= 0 and not frac:
        raise CodigoInvalido(f"ancho fuera de rango para el código: {ancho}")
    base = str(int(entero)).zfill(4)
    if len(base) > 4:
        raise CodigoInvalido(f"ancho fuera de rango para el código: {ancho}")
    decimales = f"{frac:.2f}"[2:].rstrip("0")
    return f"{base}D{decimales}" if decimales else base


def codigo_producto(tipo_pieza: str, tipo_acero: str, espesor, ancho, largo=None) -> str:
    if tipo_pieza not in PREFIJOS:
        raise CodigoInvalido(f"sin regla de código para {tipo_pieza!r}")
    e = _digitos(_dec(espesor) * 100, 3, "espesor")
    a = ancho_codigo(ancho)
    codigo = f"{PREFIJOS[tipo_pieza]}{codigo_tipo(tipo_acero)}{e}{a}"
    if tipo_pieza == "lamina":
        if largo is None:
            raise CodigoInvalido("la lámina necesita largo")
        codigo += _digitos(_dec(largo), 4, "largo")
    return codigo


def tipo_pieza_por_codigo(codigo_producto: str | None) -> str:
    """Las entradas del libro mezclan bobinas y flejes reingresados."""
    c = (codigo_producto or "").strip().upper()
    if c.startswith("FLE"):
        return "fleje"
    if c.startswith("LAM"):
        return "lamina"
    return "bobina"


def medidas_lamina(codigo: str) -> tuple[str, Decimal, Decimal, Decimal] | None:
    """LAMHP11012502400(-A) -> ('HP', 1.10, 1250, 2400). None si el código no sigue la regla.

    Lámina Est lleva 3 letras (LAMEST…) y desde 10 mm el espesor va en 4 dígitos (LAMHN100012002400)."""
    m = re.fullmatch(r"LAM([A-Z]{2,3}?)(\d{3,4})(\d{4})(\d{4})(?:-[ABC])?", (codigo or "").strip().upper())
    if not m:
        return None
    return m.group(1), Decimal(m.group(2)) / 100, Decimal(m.group(3)), Decimal(m.group(4))


# Productos del catálogo que no llevan existencia: salen en la NE solo para dejar registro del peso
# (scrap, chatarra, recortes fuera de medida…). No exigen stock de ningún cliente ni mueven inventario.
SIN_EXISTENCIA = {"MATERIALESIRREG": "Material de Medidas Irregulares"}


def sin_existencia(codigo: str | None) -> bool:
    return (codigo or "").strip().upper() in SIN_EXISTENCIA


def tipo_existencia_por_codigo(codigo: str) -> str:
    """LAM… lámina, PER… perfil; el resto (tubos, vigas, electrodos…) es producto general."""
    c = (codigo or "").strip().upper()
    if c.startswith("LAM"):
        return "lamina"
    if c.startswith("PER"):
        return "perfil"
    return "general"


def codigo_segunda(codigo: str, clase: str) -> str:
    """Código de la segunda calidad A, B o C de un producto de primera."""
    if clase not in SEGUNDAS:
        raise CodigoInvalido(f"clase de segunda desconocida: {clase!r}")
    return f"{codigo}-{clase}"


def descripcion_segunda(descripcion: str, clase: str) -> str:
    return f"{descripcion} (2{clase})"


# Categorías del reporte mensual de salidas (servicio de descarga-carga): se excluyen por categoría.
CATEGORIAS_SALIDA = {"bobina": "Bobinas", "fleje": "Flejes", "lamina": "Láminas", "perfil": "Perfiles",
                     "general": "Productos generales", "irregular": "Medidas irregulares"}


def categoria_salida(tipo_pieza: str | None, codigo: str | None, descripcion: str | None) -> str:
    """Categoría de un renglón de una NE: por el tipo de la pieza (NE de la app) o, en el histórico del
    Excel, por el código del catálogo (LAM…, PER…, FLE…, BOB…) o la primera palabra de la descripción."""
    c = (codigo or "").strip().upper()
    if c in SIN_EXISTENCIA:
        return "irregular"
    if tipo_pieza in CATEGORIAS_SALIDA:
        return tipo_pieza
    for prefijo, cat in (("BOB", "bobina"), ("FLE", "fleje"), ("LAM", "lamina"), ("PER", "perfil")):
        if c.startswith(prefijo):
            return cat
    palabra = (descripcion or "").strip().lower().split(" ")[0] if descripcion else ""
    for inicio, cat in (("bobina", "bobina"), ("fleje", "fleje"), ("lamina", "lamina"), ("lámina", "lamina"),
                        ("perfil", "perfil"), ("material", "irregular")):
        if palabra.startswith(inicio):
            return cat
    return "general"



def prefijo_automatico(nombre: str) -> str:
    """Las tres primeras letras de la primera palabra del nombre, sin acentos: "Puerta Metálica…" -> "PUE"."""
    plano = unicodedata.normalize("NFD", nombre or "").encode("ascii", "ignore").decode().upper()
    palabra = next((w for w in re.split(r"[^A-Z]+", plano) if w), "")
    return (palabra[:3] or "PRD").ljust(3, "X")


def codigo_automatico(nombre: str, existentes: set[str] | list[str]) -> str:
    """Código para un producto sin familia: prefijo del nombre + correlativo de 4 cifras (PUE0001, PUE0002…).
    El nombre lleva el detalle; el código solo tiene que ser único y corto."""
    prefijo = prefijo_automatico(nombre)
    patron = re.compile(rf"^{prefijo}(\d{{4}})$")
    usados = [int(m.group(1)) for c in existentes if (m := patron.match((c or "").upper()))]
    return f"{prefijo}{(max(usados) if usados else 0) + 1:04d}"
