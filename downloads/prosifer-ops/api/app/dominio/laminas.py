"""Reglas de la orden de corte a lámina: laminadora y CTF (doc de reglas, Órdenes de trabajo).

- Entra una bobina (o un fleje, en la CTF) y salen láminas de un largo y un ancho.
- Las láminas de primera se cuentan por atados (hasta 8, como el Excel); cada atado lleva su
  etiqueta. Las de segunda se cuentan aparte en A, B y C.
- Total o parcial: en el parcial se indican los kg procesados y la bobina sigue con el resto.
- Peso real de cada lámina = (kg procesados − scrap) ÷ láminas producidas. Así el balance de
  kg cuadra siempre (decisión del 10 nov 2026). Se compara con el peso teórico
  (espesor × ancho × largo × 7,85) y se avisa si difieren más de la tolerancia (5 %).
- El ancho de la lámina no puede pasar el de la bobina.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.dominio.slitter import ABREVIATURA_TIPO

MAX_ATADOS = 8
DENSIDAD_KG_DM3 = Decimal("7.85")
MIL = Decimal("0.001")
CLASES = ("1", "A", "B", "C")


class CorteLaminaInvalido(ValueError):
    pass


@dataclass
class Grupo:
    clase: str                    # "1" primera; "A", "B", "C" segunda
    unidades: int
    kg: Decimal


@dataclass
class PlanLamina:
    consumido: Decimal
    scrap_kg: Decimal
    largo_mm: Decimal
    ancho_mm: Decimal
    total_laminas: int
    kg_por_lamina: Decimal
    kg_teorico_por_lamina: Decimal
    diferencia_teorico: Decimal          # fracción: 0.05 = 5 %
    grupos: list[Grupo]
    kg_atados: list[Decimal]
    avisos: list[str] = field(default_factory=list)

    @property
    def producido(self) -> Decimal:
        return sum((g.kg for g in self.grupos), Decimal("0"))


def _r(x: Decimal) -> Decimal:
    return x.quantize(MIL, rounding=ROUND_HALF_UP)


def peso_teorico(espesor: Decimal, ancho: Decimal, largo: Decimal) -> Decimal:
    return _r(espesor * ancho * largo * DENSIDAD_KG_DM3 / 1_000_000)


def planificar(*, espesor: Decimal, ancho_pieza: Decimal, consumido: Decimal, largo_mm: Decimal,
               ancho_mm: Decimal | None, atados: list[int], segundas: dict[str, int],
               scrap_kg: Decimal = Decimal("0"), tolerancia: Decimal = Decimal("0.05"),
               tolerancia_ancho_mm: Decimal = Decimal("2")) -> PlanLamina:
    if not espesor or not ancho_pieza:
        raise CorteLaminaInvalido("la pieza no tiene espesor o ancho registrado; corrígelo en su ficha")
    if consumido <= 0:
        raise CorteLaminaInvalido("el peso a procesar debe ser mayor que cero")
    if largo_mm <= 0:
        raise CorteLaminaInvalido("indica el largo de la lámina")
    ancho = ancho_mm or ancho_pieza
    if ancho > ancho_pieza + tolerancia_ancho_mm:
        raise CorteLaminaInvalido(f"la lámina de {ancho} mm no sale de una pieza de {ancho_pieza} mm de ancho")
    if len(atados) > MAX_ATADOS:
        raise CorteLaminaInvalido(f"máximo {MAX_ATADOS} atados por orden")
    if any(a <= 0 for a in atados):
        raise CorteLaminaInvalido("cada atado lleva al menos una lámina")
    if any(clase not in ("A", "B", "C") or n < 0 for clase, n in segundas.items()):
        raise CorteLaminaInvalido("las segundas se cuentan en A, B y C, con cantidades positivas")
    if scrap_kg < 0 or scrap_kg >= consumido:
        raise CorteLaminaInvalido("el scrap debe ser menor que lo procesado")

    cantidades = {"1": sum(atados), **{c: segundas.get(c, 0) for c in ("A", "B", "C")}}
    total = sum(cantidades.values())
    if total <= 0:
        raise CorteLaminaInvalido("indica cuántas láminas salieron")

    neto = consumido - scrap_kg
    por_lamina = _r(neto / total)
    teorico = peso_teorico(espesor, ancho, largo_mm)
    diferencia = abs(por_lamina - teorico) / teorico if teorico else Decimal("0")

    # Cada grupo al peso real; el último grupo con láminas absorbe el redondeo para que cuadre.
    grupos = [Grupo(c, cantidades[c], _r(por_lamina * cantidades[c])) for c in CLASES if cantidades[c]]
    grupos[-1].kg = _r(neto - sum((g.kg for g in grupos[:-1]), Decimal("0")))
    kg_atados = [_r(por_lamina * a) for a in atados]

    avisos = []
    if diferencia > tolerancia:
        avisos.append(f"cada lámina pesa {por_lamina} kg y la teórica es {teorico} kg: difieren "
                      f"{diferencia * 100:.1f} % (límite {tolerancia * 100:.0f} %). Revisa el conteo o el scrap")
    if ancho_pieza - ancho > tolerancia_ancho_mm:
        avisos.append(f"la lámina ({ancho} mm) es más angosta que la pieza ({ancho_pieza} mm): el recorte va al scrap")
    return PlanLamina(consumido, _r(scrap_kg), largo_mm, ancho, total, por_lamina, teorico, diferencia, grupos,
                      kg_atados, avisos)


def _num(x: Decimal) -> str:
    return f"{x.normalize():f}".replace(".", ",")


def descripcion_lamina(tipo_codigo: str, espesor: Decimal, ancho: Decimal, largo: Decimal) -> str:
    """Lamina L.F. 1,10mm x 1250mm x 2400mm, con el espesor que se le pase (real o ya redondeado)."""
    e = f"{espesor:.2f}".replace(".", ",")
    return f"Lamina {ABREVIATURA_TIPO.get(tipo_codigo, tipo_codigo)} {e}mm x {_num(ancho)}mm x {_num(largo)}mm"


def calidad_de(clase: str, calidad_primera: str | None) -> str:
    return calidad_primera or "1er" if clase == "1" else f"2da-{clase}"


def codigo_atado(codigo_producto: str, codigo_pieza: str, numero_ot: int, atado: int) -> str:
    """Lo que lleva la etiqueta y su QR: producto / bobina madre / orden / atado."""
    return f"{codigo_producto} / {codigo_pieza} / OC{numero_ot} / AT{atado}"
