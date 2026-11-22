"""Qué perfil sale de un fleje: el "desarrollo" (ancho del fleje), el material y el espesor.

Reglas sacadas de las entradas de perfiles del Excel (EntradasPER) y de lo que contó Daniel el
11 nov 2026: un fleje de 90 mm L.C. de 1,90 mm en adelante va a vigueta; de 90 mm L.F. delgado
(0,85–1,10) a romanilla. Son sugerencias: la asistente ratifica o elige otro perfil del catálogo.
Si un ancho nuevo aparece con frecuencia, se agrega aquí.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction


@dataclass(frozen=True)
class Desarrollo:
    familia: str                       # clave del generador
    nombre: str                        # cómo se muestra la sugerencia
    materiales: tuple[str, ...]
    ancho_min: Decimal
    ancho_max: Decimal
    espesor_min: Decimal = Decimal("0")
    espesor_max: Decimal = Decimal("99")
    largo_mm: Decimal = Decimal("6000")
    datos: dict = field(default_factory=dict)   # subtipo, medidas fijas del perfil


D = Decimal
DESARROLLOS: tuple[Desarrollo, ...] = (
    Desarrollo("perfil_vigueta", "Vigueta 2'' x 1''", ("HN",), D(85), D(95), D("1.5"),
               datos={"medida1": Fraction(2), "medida2": Fraction(1)}),
    Desarrollo("perfil_romanilla", "Romanilla", ("HP", "GV"), D(85), D(95), D(0), D("1.49")),
    Desarrollo("perfil_onge", "Onge 1 1/4''", ("HN", "HP", "GV"), D(110), D(118), datos={"medida1": Fraction(5, 4)}),
    Desarrollo("perfil_guia_sm", "Guía Santa María 1'' x 2''", ("HN", "HP"), D(120), D(130)),
    Desarrollo("perfil_omega", "Omega 60mm", ("HN", "HP", "GV"), D(150), D(158)),
    Desarrollo("perfil_onge", "Onge 2''", ("HN", "HP", "GV"), D(158), D(165), datos={"medida1": Fraction(2)}),
    Desarrollo("perfil_hoja_sm", "Hoja Santa María", ("HP", "GV", "AL"), D(170), D(185), largo_mm=D(6100)),
    Desarrollo("perfil_marco", "Marco de Ventana B10", ("HP", "GV"), D(195), D(205), largo_mm=D(5150),
               datos={"subtipo": "Ventana", "base": 10}),
    Desarrollo("perfil_marco", "Marco de Puerta B10", ("HP", "GV"), D(210), D(226), largo_mm=D(5150),
               datos={"subtipo": "Puerta", "base": 10}),
    Desarrollo("perfil_marco", "Marco de Ventana B12", ("HP", "GV"), D(220), D(242), largo_mm=D(5150),
               datos={"subtipo": "Ventana", "base": 12}),
    Desarrollo("perfil_marco", "Marco de Puerta B12", ("HP", "GV"), D(234), D(242), largo_mm=D(5150),
               datos={"subtipo": "Puerta", "base": 12}),
    Desarrollo("perfil_marco", "Marco de Ventana B15", ("HP", "GV"), D(234), D(242), largo_mm=D(5150),
               datos={"subtipo": "Ventana", "base": 15}),
    Desarrollo("perfil_marco", "Marco de Puerta B15", ("HP", "GV"), D(258), D(272), largo_mm=D(5150),
               datos={"subtipo": "Puerta", "base": 15}),
)


def para_fleje(material: str | None, espesor: Decimal | None, ancho: Decimal | None) -> list[Desarrollo]:
    """Los perfiles que suelen salir de un fleje así, del más ajustado al ancho al menos."""
    if not (material and espesor and ancho):
        return []
    candidatos = [d for d in DESARROLLOS if material in d.materiales and d.ancho_min <= ancho <= d.ancho_max
                  and d.espesor_min <= espesor <= d.espesor_max]
    centro = lambda d: abs((d.ancho_min + d.ancho_max) / 2 - ancho)  # noqa: E731
    return sorted(candidatos, key=centro)
