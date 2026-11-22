"""Reglas de existencia: la existencia es la suma de movimientos de cada pieza.

Este módulo no depende de la base de datos: lo usan el servicio de inventario
(al registrar cada movimiento) y el importador (para la prueba de paridad).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

UMBRAL_AGOTADO_KG = Decimal("1")  # parámetro "umbral_agotado_kg"

# tipo de movimiento -> signo esperado del kg
TIPOS_MOVIMIENTO = {
    "entrada": +1,
    "produccion": +1,
    "consumo": -1,
    "salida": -1,
    "liberacion": 0,
    "ajuste": 0,  # puede ser + o -
}


class MovimientoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Resultado:
    saldo_kg: Decimal
    estado: str


def estado_para(saldo: Decimal, umbral: Decimal = UMBRAL_AGOTADO_KG) -> str:
    return "disponible" if saldo > umbral else "agotado"


def aplicar(saldo: Decimal, tipo: str, kg: Decimal, *, umbral: Decimal = UMBRAL_AGOTADO_KG,
            permitir_negativo: bool = False) -> Resultado:
    """Devuelve el saldo después del movimiento o rechaza si deja la pieza en negativo."""
    if tipo not in TIPOS_MOVIMIENTO:
        raise MovimientoInvalido(f"tipo de movimiento desconocido: {tipo}")
    signo = TIPOS_MOVIMIENTO[tipo]
    if signo > 0 and kg < 0 or signo < 0 and kg > 0:
        raise MovimientoInvalido(f"el kg de un movimiento '{tipo}' debe tener signo {'+' if signo > 0 else '-'}")
    if tipo == "liberacion" and kg != 0:
        raise MovimientoInvalido("una liberación no cambia el peso")
    nuevo = saldo + kg
    if nuevo < -umbral and not permitir_negativo:
        raise MovimientoInvalido(f"saldo insuficiente: hay {saldo} kg y se intenta mover {-kg} kg")
    return Resultado(nuevo, estado_para(nuevo, umbral))


def diferencia_corte(consumido: Decimal, producido: Decimal, scrap: Decimal) -> Decimal:
    """Fracción de diferencia entre lo consumido y lo producido + scrap (aviso si > 5 %)."""
    if consumido <= 0:
        return Decimal("0")
    return abs(consumido - producido - scrap) / consumido


# --- Existencias en piezas (láminas, perfiles, generales) ---------------------

@dataclass(frozen=True)
class ResultadoUnidades:
    unidades: int          # piezas que mueve el movimiento, con signo
    kg: Decimal            # kg que mueve el movimiento, con signo
    saldo_unidades: int
    saldo_kg: Decimal
    estado: str


def kg_de_unidades(saldo_unidades: int, saldo_kg: Decimal, unidades: int) -> Decimal:
    """Kg de las piezas que salen, al peso medio de lo que hay. Si salen todas, sale todo el kg.

    Así el kg nunca queda con restos por redondeo cuando la existencia llega a cero.
    """
    if saldo_unidades <= 0:
        raise MovimientoInvalido("no hay piezas en existencia")
    if unidades >= saldo_unidades:
        return saldo_kg
    return (saldo_kg * unidades / saldo_unidades).quantize(Decimal("0.001"))


def aplicar_unidades(saldo_unidades: int, saldo_kg: Decimal, tipo: str, unidades: int,
                     kg: Decimal | None = None) -> ResultadoUnidades:
    """Mueve piezas. Si no se da el kg, sale al peso medio (kg_de_unidades).

    Las entradas y producciones traen su kg; las salidas y consumos lo calculan.
    Un ajuste puede traer las dos cosas (por ejemplo, al anular una nota de entrega).
    """
    if tipo not in TIPOS_MOVIMIENTO or tipo == "liberacion":
        raise MovimientoInvalido(f"movimiento '{tipo}' no aplica a existencias en piezas")
    signo = TIPOS_MOVIMIENTO[tipo]
    if unidades == 0:
        raise MovimientoInvalido("el movimiento debe mover al menos una pieza")
    if signo > 0 and unidades < 0 or signo < 0 and unidades > 0:
        raise MovimientoInvalido(f"las piezas de un movimiento '{tipo}' deben ser {'positivas' if signo > 0 else 'negativas'}")
    nuevo_u = saldo_unidades + unidades
    if nuevo_u < 0:
        raise MovimientoInvalido(f"hay {saldo_unidades} piezas y se intenta sacar {-unidades}")
    if kg is None:
        if unidades > 0:
            raise MovimientoInvalido("una entrada de piezas necesita su peso")
        kg = -kg_de_unidades(saldo_unidades, saldo_kg, -unidades)
    if (kg < 0) != (unidades < 0) and kg != 0:
        raise MovimientoInvalido("piezas y kg deben ir en el mismo sentido")
    if nuevo_u == 0:
        kg = -saldo_kg  # sin piezas no queda peso: sale todo el kg que había
    nuevo_kg = saldo_kg + kg
    if nuevo_u > 0 and nuevo_kg <= 0:
        raise MovimientoInvalido("el peso quedaría en cero con piezas en existencia")
    return ResultadoUnidades(unidades, kg, nuevo_u, nuevo_kg, "disponible" if nuevo_u > 0 else "agotado")
