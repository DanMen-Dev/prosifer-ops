"""Reglas de la orden de corte en slitter (doc de reglas, sección Órdenes de trabajo).

- Hasta 6 cortes por pasada más el scrap (la posición 7 del Excel).
- Cada corte tiene un ancho y un número de rollos; cada rollo es una pieza (fleje).
- Si no se indica el peso de un corte, se reparte el peso consumido según el ancho:
  kg del corte = consumido × (ancho × rollos) ÷ ancho de la bobina. Es lo que hace el Excel.
- El peso del corte se reparte por igual entre sus rollos; el último absorbe el redondeo.
- La suma de anchos no puede pasar el ancho de la bobina (más una tolerancia).
- Si consumido y producido + scrap difieren más de la tolerancia (5 %), se avisa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

MAX_CORTES = 6
MAX_ROLLOS = 15  # posiciones A..O del Excel
LETRAS = "ABCDEFGHIJKLMNO"
MIL = Decimal("0.001")


class CorteInvalido(ValueError):
    pass


@dataclass(frozen=True)
class CorteIn:
    ancho_mm: Decimal
    rollos: int
    kg: Decimal | None = None
    calidad: str | None = None


@dataclass
class CortePlan:
    posicion: int
    ancho_mm: Decimal
    rollos: int
    kg: Decimal
    kg_rollos: list[Decimal]
    calidad: str | None


@dataclass
class PlanSlitter:
    consumido: Decimal
    cortes: list[CortePlan]
    scrap_ancho_mm: Decimal
    scrap_kg: Decimal
    producido: Decimal
    diferencia: Decimal          # fracción, 0.05 = 5 %
    ancho_usado_mm: Decimal
    avisos: list[str] = field(default_factory=list)


def _r(x: Decimal) -> Decimal:
    return x.quantize(MIL, rounding=ROUND_HALF_UP)


def repartir(total: Decimal, partes: int) -> list[Decimal]:
    base = _r(total / partes)
    pesos = [base] * partes
    pesos[-1] = _r(total - base * (partes - 1))
    return pesos


def planificar(ancho_bobina: Decimal, consumido: Decimal, cortes: list[CorteIn], *,
               scrap_ancho_mm: Decimal = Decimal("0"), scrap_kg: Decimal | None = None,
               tolerancia: Decimal = Decimal("0.05"), tolerancia_ancho_mm: Decimal = Decimal("2")) -> PlanSlitter:
    if not cortes:
        raise CorteInvalido("indica al menos un corte")
    if len(cortes) > MAX_CORTES:
        raise CorteInvalido(f"máximo {MAX_CORTES} cortes por orden (más el scrap)")
    if ancho_bobina is None or ancho_bobina <= 0:
        raise CorteInvalido("la bobina no tiene ancho registrado; corrígelo en su ficha antes de cortar")
    if consumido <= 0:
        raise CorteInvalido("el peso a procesar debe ser mayor que cero")
    for c in cortes:
        if c.ancho_mm <= 0:
            raise CorteInvalido("cada corte necesita un ancho mayor que cero")
        if not 1 <= c.rollos <= MAX_ROLLOS:
            raise CorteInvalido(f"cada corte lleva entre 1 y {MAX_ROLLOS} rollos")
        if c.kg is not None and c.kg <= 0:
            raise CorteInvalido("el peso de un corte debe ser mayor que cero")

    ancho_usado = sum((c.ancho_mm * c.rollos for c in cortes), Decimal("0")) + scrap_ancho_mm
    if ancho_usado > ancho_bobina + tolerancia_ancho_mm:
        raise CorteInvalido(
            f"los cortes suman {ancho_usado} mm y la bobina mide {ancho_bobina} mm")

    avisos: list[str] = []
    if ancho_bobina - ancho_usado > tolerancia_ancho_mm:
        avisos.append(f"quedan {ancho_bobina - ancho_usado} mm del ancho sin asignar (¿falta el scrap?)")

    plan_cortes = []
    for i, c in enumerate(cortes, start=1):
        kg = _r(c.kg if c.kg is not None else consumido * c.ancho_mm * c.rollos / ancho_bobina)
        plan_cortes.append(CortePlan(i, c.ancho_mm, c.rollos, kg, repartir(kg, c.rollos), c.calidad))
    s_kg = _r(scrap_kg if scrap_kg is not None else consumido * scrap_ancho_mm / ancho_bobina)
    producido = sum((c.kg for c in plan_cortes), Decimal("0"))
    diferencia = abs(consumido - producido - s_kg) / consumido
    if diferencia > tolerancia:
        avisos.append(
            f"lo producido ({producido} kg) más el scrap ({s_kg} kg) difiere {diferencia * 100:.1f} % "
            f"de lo consumido ({consumido} kg); el límite es {tolerancia * 100:.0f} %")
    return PlanSlitter(consumido, plan_cortes, scrap_ancho_mm, s_kg, producido, diferencia, ancho_usado, avisos)


ABREVIATURA_TIPO = {"HP": "L.F.", "HN": "L.C.", "GV": "Galv.", "ES": "Estr.", "PP": "Prepint.", "AL": "Alum."}


def descripcion_fleje(tipo_codigo: str, espesor: Decimal, ancho: Decimal) -> str:
    e = f"{espesor:.2f}".replace(".", ",")   # bobinas y flejes llevan el espesor real (11 nov 2026)
    a = ancho.normalize()
    a_txt = f"{a:f}".replace(".", ",")
    return f"Fleje {ABREVIATURA_TIPO.get(tipo_codigo, tipo_codigo)} {e}mm x {a_txt}mm"


def codigo_rollo(codigo_producto: str, codigo_bobina: str, numero_ot: int, posicion: int, rollo: int) -> str:
    """Código físico de cada rollo: producto / bobina madre / orden / corte-rollo."""
    return f"{codigo_producto} / {codigo_bobina} / OC{numero_ot} / {posicion}-{LETRAS[rollo - 1]}"
