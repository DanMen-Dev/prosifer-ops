"""Reglas de la maquila de perfiles (doc de reglas, Órdenes de trabajo).

- Entran hasta 6 flejes del mismo dueño (el cliente de la maquila); cada uno total o con los kg
  que se procesan.
- Sale un perfil (Vigueta, Marco de Puerta B15, Omega…) elegido del catálogo: la primera por
  paquetes (hasta 12, como el Excel) y la segunda en A, B y C (código -A/-B/-C, nombre (2A)…).
- Peso real de cada perfil = (kg procesados − scrap) ÷ perfiles producidos, para que el balance
  cuadre; se compara con el peso teórico del catálogo y se avisa si difieren más del 5 %.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.dominio.laminas import CLASES, Grupo

MAX_FLEJES = 6
MAX_PAQUETES = 12
MIL = Decimal("0.001")


class MaquilaInvalida(ValueError):
    pass


@dataclass
class PlanMaquila:
    consumido: Decimal
    scrap_kg: Decimal
    total: int
    kg_por_pieza: Decimal
    kg_teorico: Decimal | None
    diferencia_teorico: Decimal | None
    grupos: list[Grupo]
    kg_paquetes: list[Decimal]
    avisos: list[str] = field(default_factory=list)

    @property
    def producido(self) -> Decimal:
        return sum((g.kg for g in self.grupos), Decimal("0"))


def _r(x: Decimal) -> Decimal:
    return x.quantize(MIL, rounding=ROUND_HALF_UP)


def planificar(*, consumido: Decimal, paquetes: list[int], segundas: dict[str, int], peso_teorico: Decimal | None,
               scrap_kg: Decimal = Decimal("0"), tolerancia: Decimal = Decimal("0.05")) -> PlanMaquila:
    if consumido <= 0:
        raise MaquilaInvalida("el peso a procesar debe ser mayor que cero")
    if len(paquetes) > MAX_PAQUETES:
        raise MaquilaInvalida(f"máximo {MAX_PAQUETES} paquetes por orden")
    if any(p <= 0 for p in paquetes):
        raise MaquilaInvalida("cada paquete lleva al menos un perfil")
    if any(c not in ("A", "B", "C") or n < 0 for c, n in segundas.items()):
        raise MaquilaInvalida("las segundas se cuentan en A, B y C, con cantidades positivas")
    if scrap_kg < 0 or scrap_kg >= consumido:
        raise MaquilaInvalida("el scrap debe ser menor que lo procesado")
    cantidades = {"1": sum(paquetes), **{c: segundas.get(c, 0) for c in ("A", "B", "C")}}
    total = sum(cantidades.values())
    if total <= 0:
        raise MaquilaInvalida("indica cuántos perfiles salieron")
    neto = consumido - scrap_kg
    por_pieza = _r(neto / total)
    grupos = [Grupo(c, cantidades[c], _r(por_pieza * cantidades[c])) for c in CLASES if cantidades[c]]
    grupos[-1].kg = _r(neto - sum((g.kg for g in grupos[:-1]), Decimal("0")))
    avisos = []
    diferencia = None
    if peso_teorico:
        diferencia = abs(por_pieza - peso_teorico) / peso_teorico
        if diferencia > tolerancia:
            avisos.append(f"cada perfil pesa {por_pieza} kg y el teórico es {peso_teorico} kg: difieren "
                          f"{diferencia * 100:.1f} % (límite {tolerancia * 100:.0f} %). Revisa el conteo o el scrap")
    else:
        avisos.append("el perfil no tiene peso teórico en el catálogo: no se puede comparar el peso por pieza")
    return PlanMaquila(consumido, _r(scrap_kg), total, por_pieza, peso_teorico, diferencia, grupos,
                       [_r(por_pieza * p) for p in paquetes], avisos)


def codigo_paquete(codigo_producto: str, numero_ot: int, paquete: int) -> str:
    """Lo que lleva la etiqueta y su QR: perfil / orden / paquete."""
    return f"{codigo_producto} / OC{numero_ot} / PQ{paquete}"
