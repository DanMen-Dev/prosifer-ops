"""Reglas de salida (doc de reglas, sección Salidas).

- Nota de entrega: total o parcial, sin límite de notas por pieza. No puede sacar
  más de lo disponible (con la tolerancia del umbral de agotado).
- Si deja un resto pequeño (menor que "resto_aviso_kg"), se avisa: suele ser una
  salida total mal escrita o un resto que habría que ajustar.
- Liberación: traspasa piezas completas; una pieza nunca tiene dos dueños.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.dominio.saldos import kg_de_unidades


class SalidaInvalida(ValueError):
    pass


@dataclass
class Linea:
    kg: Decimal
    saldo_despues: Decimal
    avisos: list[str] = field(default_factory=list)


def evaluar_linea(saldo: Decimal, kg: Decimal | None, *, umbral: Decimal = Decimal("1"),
                  resto_aviso: Decimal = Decimal("50")) -> Linea:
    if saldo <= umbral:
        raise SalidaInvalida("la pieza no tiene saldo disponible")
    if kg is None:
        kg = saldo
    if kg <= 0:
        raise SalidaInvalida("los kg a entregar deben ser mayores que cero")
    if kg > saldo + umbral:
        raise SalidaInvalida(f"se quieren entregar {kg} kg y la pieza tiene {saldo} kg")
    kg = min(kg, saldo)
    resto = saldo - kg
    avisos = []
    if umbral < resto <= resto_aviso:
        avisos.append(f"queda un resto de {resto} kg: ¿no es una salida total?")
    return Linea(kg, resto, avisos)


@dataclass
class LineaUnidades:
    unidades: int
    kg: Decimal
    saldo_despues_unidades: int
    saldo_despues_kg: Decimal
    avisos: list[str] = field(default_factory=list)


def evaluar_linea_unidades(saldo_unidades: int, saldo_kg: Decimal, unidades: int | None) -> LineaUnidades:
    """Salida de láminas, perfiles o generales: en piezas, y el kg al peso medio de la existencia."""
    if saldo_unidades <= 0:
        raise SalidaInvalida("no hay piezas disponibles")
    if unidades is None:
        unidades = saldo_unidades
    if unidades <= 0:
        raise SalidaInvalida("las piezas a entregar deben ser mayores que cero")
    if unidades > saldo_unidades:
        raise SalidaInvalida(f"se quieren entregar {unidades} piezas y hay {saldo_unidades}")
    kg = kg_de_unidades(saldo_unidades, saldo_kg, unidades)
    return LineaUnidades(unidades, kg, saldo_unidades - unidades, saldo_kg - kg)
