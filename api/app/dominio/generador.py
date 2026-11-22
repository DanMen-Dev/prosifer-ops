"""Generador de códigos y nombres de productos (la app es la ley; decidido el 10 nov 2026).

Parte del Generador Lista Costos JADEL, que Prosifer y HierroEnLinea ya usan, y corrige sus
inconsistencias para los productos nuevos.

Código largo (30 caracteres) para lo que no es lámina, bobina, fleje ni perfil:

    TUB 000 HP E090 A00015 A00005 L06000
     |   |   |   |    |      |      +- largo en mm (en mallas, m²)
     |   |   |   |    |      +- medida 2
     |   |   |   |    +- medida 1
     |   |   |   +- espesor o diámetro (4 caracteres)
     |   |   +- material: HN caliente, HP frío, GV galvanizado
     |   +- subtipo: 000, VNT, CRT, S60, IPE, TRK, PRD, EST…
     +- familia: TUB, ANG, PLT, VIG, CST, ALA, BRD, BCD, MLL, CER

Espesor (4 caracteres):
    menos de 10 mm      E + centésimas de mm         2,50 mm -> E250
    10 mm o más         centésimas de mm, sin la E   12 mm   -> 1200
    pulgadas            F + milésimas de pulgada     3/16''  -> F188
    no aplica                                                   E000
Medidas (A + 5 dígitos):
    milímetros          tal cual                     100 mm  -> A00100
    pulgadas            el decimal sin "0," ni ceros 1 1/2'' -> A00015, 3/4'' -> A00075, 2'' -> A00002

Código corto (como ya usa la app):
    LAM + material + espesor (3) + ancho (4) + largo (4)    LAMHN20012502400
    BOB / FLE + material (2) + espesor (3) + ancho (4)       FLEHP0900268
    PER + material + forma + medidas                         PERHNVIG2256000, PERHPP150905150
Segunda calidad: -A, -B o -C en el código y (2A), (2B) o (2C) en el nombre.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from app.dominio.codigos import ancho_codigo

CERO = Decimal("0")


class GeneradorInvalido(ValueError):
    pass


# --------------------------------------------------------------------- medidas

@dataclass(frozen=True)
class Medida:
    valor: Fraction            # en mm o en pulgadas
    pulgadas: bool = False

    @staticmethod
    def mm(v) -> "Medida":
        return Medida(Fraction(str(v).replace(",", ".")))

    @staticmethod
    def pulg(v) -> "Medida":
        return Medida(_fraccion(v), True)

    @property
    def en_mm(self) -> Decimal:
        f = self.valor * Fraction(254, 10) if self.pulgadas else self.valor
        return Decimal(f.numerator) / Decimal(f.denominator)

    def texto(self, decimales: int | None = None) -> str:
        """1 1/2'' · 100mm · 2,50mm"""
        if self.pulgadas:
            return f"{_pulgadas_texto(self.valor)}''"
        d = Decimal(self.valor.numerator) / Decimal(self.valor.denominator)
        if decimales is not None:
            return f"{d:.{decimales}f}".replace(".", ",") + "mm"
        return _num(d) + "mm"


def _fraccion(v) -> Fraction:
    """'1 1/2', '1-1/2', '3/4', '2', 1.5 -> Fraction."""
    if isinstance(v, Fraction):
        return v
    if isinstance(v, (int, Decimal, float)):
        return Fraction(str(v))
    t = str(v).strip().replace("''", "").replace('"', "").replace("-", " ").replace(",", ".")
    total = Fraction(0)
    for parte in t.split():
        total += Fraction(parte)
    if total <= 0:
        raise GeneradorInvalido(f"medida inválida: {v!r}")
    return total


def _pulgadas_texto(f: Fraction) -> str:
    entero, resto = divmod(f.numerator, f.denominator)
    frac = Fraction(resto, f.denominator)
    if not frac:
        return str(entero)
    return f"{entero} {frac.numerator}/{frac.denominator}" if entero else f"{frac.numerator}/{frac.denominator}"


def _num(d: Decimal) -> str:
    d = d.normalize()
    return f"{d:f}".replace(".", ",")


def _redondo(d: Decimal | Fraction) -> int:
    if isinstance(d, Fraction):
        d = Decimal(d.numerator) / Decimal(d.denominator)
    return int(d.to_integral_value(rounding=ROUND_HALF_UP))


def slot_espesor(m: Medida | None) -> str:
    if m is None:
        return "E000"
    if m.pulgadas:
        milesimas = _redondo(m.valor * 1000)
        if not 0 < milesimas < 1000:
            raise GeneradorInvalido(f"espesor en pulgadas fuera de rango: {m.texto()}")
        return f"F{milesimas:03d}"
    centesimas = _redondo(m.en_mm * 100)
    if centesimas <= 0 or centesimas >= 10000:
        raise GeneradorInvalido(f"espesor fuera de rango: {m.texto()}")
    return f"E{centesimas:03d}" if centesimas < 1000 else f"{centesimas:04d}"


def slot_medida(m: Medida | None, letra: str = "A") -> str:
    if m is None:
        return f"{letra}00000"
    if m.pulgadas:
        d = Decimal(m.valor.numerator) / Decimal(m.valor.denominator)
        txt = f"{d.normalize():f}"
        if txt.startswith("0."):
            txt = txt[2:]
        digitos = txt.replace(".", "")
    else:
        digitos = str(_redondo(m.en_mm))
    if len(digitos) > 5:
        raise GeneradorInvalido(f"medida fuera de rango: {m.texto()}")
    return f"{letra}{digitos.zfill(5)}"


def slot_largo(mm: Decimal | int | None) -> str:
    return slot_medida(Medida.mm(mm) if mm else None, "L")


# --------------------------------------------------------------------- materiales

# material del nombre -> (código, texto en el nombre)
MATERIALES = {
    "HP": ("HP", "L.F."),
    "HN": ("HN", "L.C."),
    "GV": ("GV", "Galv."),
    "AL": ("AL", "Aluminio"),
    "PP": ("PP", "PP"),
    "EST": ("EST", "Est HN"),
}
_ALIAS_MATERIAL = {
    "L.F.": "HP", "LF": "HP", "L.F": "HP", "FRIO": "HP",
    "L.C.": "HN", "LC": "HN", "L.C": "HN", "CALIENTE": "HN", "H.N.": "HN", "HN": "HN",
    "GALV.": "GV", "GALV": "GV", "GV": "GV", "GALVANIZADO": "GV", "GALVANIZADA": "GV",
    "ALUMINIO": "AL", "AL": "AL", "ALU": "AL",
    "PP": "PP", "PREPINTADA": "PP",
    "EST": "EST",
}


def material(texto: str) -> str:
    m = _ALIAS_MATERIAL.get(texto.strip().upper())
    if not m:
        raise GeneradorInvalido(f"material desconocido: {texto!r}")
    return m


# --------------------------------------------------------------------- producto

@dataclass
class Producto:
    """Lo que hace falta para armar código y nombre."""
    familia: str                       # clave de FAMILIAS
    material: str = "HN"
    subtipo: str | None = None         # VNT, IPE, S60, P/V (marcos)…
    espesor: Medida | None = None      # o diámetro
    medida1: Medida | None = None
    medida2: Medida | None = None
    largo_mm: Decimal | None = None    # en mallas: m²
    segunda: str | None = None         # A, B o C
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    tipo: str = "mm"                   # mm, pulgadas, mm_o_pulgadas, opcion, numero
    opciones: tuple[str, ...] = ()
    obligatorio: bool = True


@dataclass(frozen=True)
class Familia:
    clave: str
    nombre: str
    prefijo: str
    materiales: tuple[str, ...]
    campos: tuple[Campo, ...]


TIPOS_VIGA = ("IPE", "IPN", "HEA", "UPL", "UPE", "CP")
CAMPO_LARGO = Campo("largo_mm", "Largo (mm)", "numero")

FAMILIAS: dict[str, Familia] = {f.clave: f for f in (
    Familia("tubo", "Tubo cuadrado o rectangular", "TUB", ("HP", "HN", "GV"), (
        Campo("medida1", "Lado 1", "mm_o_pulgadas"), Campo("medida2", "Lado 2", "mm_o_pulgadas"),
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("tubo_redondo", "Tubo redondo", "TUB", ("HP", "HN", "GV"), (
        Campo("medida1", "Diámetro", "mm_o_pulgadas"), Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("tubo_ventilacion", "Tubo de ventilación", "TUB", ("HN",), (
        Campo("medida1", "Diámetro", "pulgadas"), Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("tubo_cerca", "Tubo para cerca", "TUB", ("GV",), (
        Campo("medida1", "Diámetro", "pulgadas"), Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("angulo", "Ángulo", "ANG", ("HN",), (
        Campo("medida1", "Ala", "mm_o_pulgadas"), Campo("espesor", "Espesor", "mm_o_pulgadas"), CAMPO_LARGO)),
    Familia("pletina", "Pletina", "PLT", ("HN",), (
        Campo("medida2", "Ancho", "mm_o_pulgadas"), Campo("espesor", "Espesor", "mm_o_pulgadas"), CAMPO_LARGO)),
    Familia("pletina_perforada", "Pletina perforada", "PLT", ("HN",), (
        Campo("subtipo", "Agujero", "opcion", ("Redonda", "Cuadrada")), Campo("medida1", "Agujero", "pulgadas"),
        Campo("medida2", "Ancho", "pulgadas"), Campo("espesor", "Espesor", "pulgadas"), CAMPO_LARGO)),
    Familia("viga", "Viga", "VIG", ("HN",), (
        Campo("subtipo", "Tipo", "opcion", TIPOS_VIGA), Campo("medida1", "Altura (mm)"), CAMPO_LARGO)),
    Familia("cabilla", "Cabilla estriada", "CST", ("HN",), (
        Campo("subtipo", "Grado", "opcion", ("S40", "S60")), Campo("espesor", "Diámetro", "mm_o_pulgadas"),
        CAMPO_LARGO)),
    Familia("alambron", "Alambrón", "ALA", ("HN",), (
        Campo("subtipo", "Superficie", "opcion", ("Estriado", "Liso")), Campo("espesor", "Diámetro (mm)"),
        Campo("largo_mm", "Largo (mm, vacío = por rollo)", "numero", obligatorio=False))),
    Familia("barra_redonda", "Barra redonda (lisa)", "BRD", ("HN",), (
        Campo("espesor", "Diámetro", "mm_o_pulgadas"), CAMPO_LARGO)),
    Familia("barra_cuadrada", "Barra cuadrada", "BCD", ("HN",), (
        Campo("espesor", "Lado", "mm_o_pulgadas"), CAMPO_LARGO)),
    Familia("malla_truckson", "Malla Truckson", "MLL", ("HN",), (
        Campo("medida1", "Abertura", "pulgadas"), Campo("espesor", "Alambre (mm)"),
        Campo("largo_mm", "Rollo (m²)", "numero"))),
    Familia("cercha", "Cercha", "CER", ("HN",), (
        Campo("medida1", "Altura (mm)"), CAMPO_LARGO)),
    Familia("lamina", "Lámina", "LAM", ("HP", "HN", "GV", "EST", "AL", "PP"), (
        Campo("espesor", "Espesor (mm)"), Campo("medida1", "Ancho (mm)"), CAMPO_LARGO)),
    Familia("bobina", "Bobina", "BOB", ("HP", "HN", "GV", "AL", "PP"), (
        Campo("espesor", "Espesor (mm)"), Campo("medida1", "Ancho (mm)"))),
    Familia("fleje", "Fleje", "FLE", ("HP", "HN", "GV", "AL", "PP"), (
        Campo("espesor", "Espesor (mm)"), Campo("medida1", "Ancho (mm)"))),
    Familia("perfil_vigueta", "Perfil vigueta", "PER", ("HN", "HP", "GV"), (
        Campo("medida1", "Alto", "pulgadas"), Campo("medida2", "Ancho", "pulgadas"),
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("perfil_marco", "Perfil marco de puerta o ventana", "PER", ("HP", "GV"), (
        Campo("subtipo", "Marco", "opcion", ("Puerta", "Ventana")), Campo("medida1", "Base (B10, B12, B15…)", "numero"),
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("perfil_hoja_sm", "Perfil hoja Santa María", "PER", ("HP", "GV", "AL"), (
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("perfil_guia_sm", "Perfil guía Santa María", "PER", ("HN", "HP"), (
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("perfil_onge", "Perfil onge", "PER", ("HN", "HP", "GV"), (
        Campo("medida1", "Medida", "opcion", ("1 1/4", "2")), Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("perfil_omega", "Perfil omega 60mm", "PER", ("HN", "HP", "GV"), (
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
    Familia("perfil_romanilla", "Perfil romanilla", "PER", ("HP", "GV"), (
        Campo("espesor", "Espesor (mm)"), CAMPO_LARGO)),
)}

# Onge: la medida en pulgadas va como 2 dígitos en el código (PERHNO14…, PERHNO20…)
ONGE = {Fraction(5, 4): "14", Fraction(2): "20"}


# --------------------------------------------------------------------- código y nombre

def _mat_nombre(m: str) -> str:
    return MATERIALES[m][1]


def _mat_perfil(m: str) -> str:
    """En los perfiles el material va sin puntos: LC, LF, GV, AL."""
    return {"HN": "LC", "HP": "LF"}.get(m, m)


def _segunda(codigo: str, nombre: str, p: Producto) -> tuple[str, str]:
    if p.segunda:
        if p.segunda not in ("A", "B", "C"):
            raise GeneradorInvalido(f"segunda calidad desconocida: {p.segunda}")
        return f"{codigo}-{p.segunda}", f"{nombre} (2{p.segunda})"
    return codigo, nombre


def _largo_mm(p: Producto) -> str:
    return f"{_redondo(p.largo_mm)}mm" if p.largo_mm else ""


def _largo_mts(p: Producto) -> str:
    return f"{Decimal(p.largo_mm) / 1000:.2f}".replace(".", ",") + "mts"


def _d3(m: Medida) -> str:
    """Espesor en centésimas para los códigos cortos: 3 dígitos; 4 desde 10 mm (LAMHN100012002400)."""
    n = _redondo(m.en_mm * 100)
    if not 0 < n < 10000:
        raise GeneradorInvalido(f"espesor fuera de rango: {m.texto()}")
    return f"{n:03d}" if n < 1000 else f"{n:04d}"


def _d4(v) -> str:
    n = _redondo(Decimal(str(v)))
    if not 0 < n < 10000:
        raise GeneradorInvalido(f"medida fuera de rango: {v}")
    return f"{n:04d}"


def _esp_nombre(m: Medida) -> str:
    """Espesor como se nombra: el que se indica, con dos decimales (2,50mm), o en pulgadas.
    Bobinas y flejes llevan el real; láminas y perfiles el real o el comercial si se eligió redondear
    (y entonces el código también va redondeado)."""
    if m.pulgadas:
        return m.texto()
    return f"{m.en_mm:.2f}".replace(".", ",") + "mm"


def _largo_codigo(p: Producto) -> str:
    return slot_largo(p.largo_mm)


def generar(p: Producto) -> tuple[str, str]:
    """(código, nombre) según la regla de la familia."""
    f = FAMILIAS.get(p.familia)
    if f is None:
        raise GeneradorInvalido(f"familia desconocida: {p.familia}")
    if p.material not in f.materiales:
        raise GeneradorInvalido(f"{f.nombre}: material {p.material} no previsto ({', '.join(f.materiales)})")
    for c in f.campos:
        valor = p.subtipo if c.clave == "subtipo" else getattr(p, c.clave)
        if c.obligatorio and not valor:
            raise GeneradorInvalido(f"{f.nombre}: falta {c.etiqueta.lower()}")
    m = p.material
    k = p.familia

    if k in ("tubo", "tubo_redondo", "tubo_ventilacion", "tubo_cerca"):
        sub = {"tubo": "000", "tubo_redondo": "RED", "tubo_ventilacion": "VNT", "tubo_cerca": "CRT"}[k]
        codigo = f"TUB{sub}{m}{slot_espesor(p.espesor)}{slot_medida(p.medida1)}{slot_medida(p.medida2)}{_largo_codigo(p)}"
        if k == "tubo":
            nombre = f"Tubo {_mat_nombre(m)} {p.medida1.texto()} x {p.medida2.texto()} x {_esp_nombre(p.espesor)} x {_largo_mm(p)}"
        elif k == "tubo_redondo":
            nombre = f"Tubo Redondo {_mat_nombre(m)} {p.medida1.texto()} x {_esp_nombre(p.espesor)} x {_largo_mm(p)}"
        elif k == "tubo_ventilacion":
            nombre = f"Tubo Ventilacion L.C. {p.medida1.texto()} x {_esp_nombre(p.espesor)} x {_largo_mm(p)}"
        else:
            nombre = f"Tubo Para Cerca Galv. {p.medida1.texto()} x {_esp_nombre(p.espesor)} x {_largo_mm(p)}"
    elif k == "angulo":
        codigo = f"ANG000{m}{slot_espesor(p.espesor)}{slot_medida(p.medida1)}{slot_medida(p.medida1)}{_largo_codigo(p)}"
        nombre = f"Angulo {p.medida1.texto()} x {p.medida1.texto()} x {_esp_nombre(p.espesor)} x {_largo_mm(p)}"
    elif k == "pletina":
        codigo = f"PLT000{m}{slot_espesor(p.espesor)}{slot_medida(None)}{slot_medida(p.medida2)}{_largo_codigo(p)}"
        nombre = f"Pletina {p.medida2.texto()} x {_esp_nombre(p.espesor)} x {_largo_mm(p)}"
    elif k == "pletina_perforada":
        forma = (p.subtipo or "Redonda").capitalize()
        sub = "PRD" if forma == "Redonda" else "PCD"
        codigo = f"PLT{sub}{m}{slot_espesor(p.espesor)}{slot_medida(p.medida1)}{slot_medida(p.medida2)}{_largo_codigo(p)}"
        nombre = (f"Pletina Perforada {forma} {p.medida1.texto()} - {p.medida2.texto()} x {_esp_nombre(p.espesor)}"
                  f" x {_largo_mm(p)}")
    elif k == "viga":
        tipo = (p.subtipo or "").upper()
        if tipo not in TIPOS_VIGA:
            raise GeneradorInvalido(f"tipo de viga desconocido: {p.subtipo}")
        sub = "VCP" if tipo == "CP" else tipo
        codigo = f"VIG{sub}{m}E000{slot_medida(p.medida1)}{slot_medida(None)}{_largo_codigo(p)}"
        nombre = f"Viga {tipo} {p.medida1.texto()} x {_largo_mm(p)}"
    elif k == "cabilla":
        grado = (p.subtipo or "").upper()
        if grado not in ("S40", "S60"):
            raise GeneradorInvalido("la cabilla lleva grado S40 o S60")
        codigo = f"CST{grado}{m}{slot_espesor(p.espesor)}{slot_medida(None)}{slot_medida(None)}{_largo_codigo(p)}"
        nombre = f"Cabilla Estriada {p.espesor.texto()} x {_largo_mm(p)} {grado}"
    elif k == "alambron":
        sup = (p.subtipo or "Estriado").capitalize()
        sub = "EST" if sup == "Estriado" else "LIS"
        codigo = f"ALA{sub}{m}{slot_espesor(p.espesor)}{slot_medida(None)}{slot_medida(None)}{_largo_codigo(p)}"
        cola = f"x {_largo_mm(p)}" if p.largo_mm else "Por Rollo"
        nombre = f"Alambron {sup} {_esp_nombre(p.espesor)} {cola}"
    elif k in ("barra_redonda", "barra_cuadrada"):
        pre, forma = ("BRD", "Redonda") if k == "barra_redonda" else ("BCD", "Cuadrada")
        codigo = f"{pre}000{m}{slot_espesor(p.espesor)}{slot_medida(None)}{slot_medida(None)}{_largo_codigo(p)}"
        nombre = f"Barra {forma} {p.espesor.texto(2) if not p.espesor.pulgadas else p.espesor.texto()} x {_largo_mm(p)}"
    elif k == "malla_truckson":
        codigo = f"MLLTRK{m}{slot_espesor(p.espesor)}{slot_medida(p.medida1)}{slot_medida(p.medida1)}{_largo_codigo(p)}"
        nombre = (f"Malla Truckson {p.medida1.texto()} x {p.medida1.texto()} x {_esp_nombre(p.espesor)}"
                  f" x {_redondo(p.largo_mm)}mts2")
    elif k == "cercha":
        alto = _redondo(p.medida1.en_mm)
        sub = f"C{alto // 10:02d}"
        codigo = f"CER{sub}{m}E000{slot_medida(p.medida1)}{slot_medida(None)}{_largo_codigo(p)}"
        nombre = f"Cercha C-{alto // 10} {alto}mm x {_largo_mm(p)}"
    elif k == "lamina":
        codigo = f"LAM{m}{_d3(p.espesor)}{_d4(p.medida1.en_mm)}{_d4(p.largo_mm)}"
        nombre = (f"Lamina {_mat_nombre(m)} {_esp_nombre(p.espesor)} x {_num(p.medida1.en_mm)}mm"
                  f" x {_num(Decimal(p.largo_mm))}mm")
    elif k in ("bobina", "fleje"):
        pre = "BOB" if k == "bobina" else "FLE"
        codigo = f"{pre}{m}{_d3(p.espesor)}{ancho_codigo(p.medida1.en_mm)}"
        nombre = f"{'Bobina' if k == 'bobina' else 'Fleje'} {_mat_nombre(m)} {_esp_nombre(p.espesor)} x {_num(p.medida1.en_mm)}mm"
    elif k == "perfil_vigueta":
        codigo = f"PER{m}VIG{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = (f"Perfil {_mat_perfil(m)} Vigueta {p.medida1.texto()} x {p.medida2.texto()}"
                  f" x {_esp_nombre(p.espesor)} x {_largo_mts(p)}")
    elif k == "perfil_marco":
        tipo = (p.subtipo or "").capitalize()
        if tipo not in ("Puerta", "Ventana"):
            raise GeneradorInvalido("el marco es de puerta o de ventana")
        base = _redondo(p.medida1.valor)
        codigo = f"PER{m}{tipo[0]}{base:02d}{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = (f"Perfil {_mat_perfil(m)} Marco de {tipo} B{base} x {_esp_nombre(p.espesor)}"
                  f" x {_largo_mts(p)}")
    elif k == "perfil_hoja_sm":
        codigo = f"PER{m}HSM{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = f"Perfil {_mat_perfil(m)} Hoja Santa Maria x {_esp_nombre(p.espesor)} x {_largo_mts(p)}"
    elif k == "perfil_guia_sm":
        codigo = f"PER{m}GUI{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = (f"Perfil {_mat_perfil(m)} Guia Sta Maria 1'' x 2'' x {_esp_nombre(p.espesor)}"
                  f" x {_largo_mts(p)}")
    elif k == "perfil_onge":
        med = p.medida1 if isinstance(p.medida1, Medida) else Medida.pulg(p.medida1 or "")
        cod = ONGE.get(med.valor)
        if cod is None:
            raise GeneradorInvalido(f"onge de {med.texto()} sin código conocido (1 1/4'' o 2'')")
        codigo = f"PER{m}O{cod}{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = f"Perfil {_mat_perfil(m)} Onge {med.texto()} x {_esp_nombre(p.espesor)} x {_largo_mts(p)}"
    elif k == "perfil_omega":
        codigo = f"PER{m}OME{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = f"Perfil {_mat_perfil(m)} Omega 60mm x {_esp_nombre(p.espesor)} x {_largo_mts(p)}"
    elif k == "perfil_romanilla":
        codigo = f"PER{m}ROM{_d3(p.espesor)}{_d4(p.largo_mm)}"
        nombre = f"Perfil {_mat_perfil(m)} Romanilla {_esp_nombre(p.espesor)} x {_largo_mts(p)}"
    else:  # pragma: no cover - toda familia de FAMILIAS tiene su regla
        raise GeneradorInvalido(f"sin regla para {k}")
    return _segunda(codigo, re.sub(r"\s+", " ", nombre).strip(), p)


# --------------------------------------------------------------------- leer un nombre existente

_INVISIBLES = {**{c: " " for c in range(0x2000, 0x200B)}, **dict.fromkeys(range(0x200B, 0x2010)),
               0xFEFF: None, 0x00A0: " "}


def limpiar(nombre: str) -> str:
    t = unicodedata.normalize("NFC", nombre or "").translate(_INVISIBLES)
    t = t.replace("”", "''").replace('"', "''").replace("´´", "''").replace("’’", "''")
    return re.sub(r"\s+", " ", t).strip()


_PULG = r"(\d+(?:[ -]\d+/\d+)?|\d+/\d+)(?:'')?"
_NUM = r"(\d+(?:[.,]\d+)?)"


def _med(texto: str) -> Medida:
    """'1 1/2''' -> pulgadas; '100mm' o '2,50' -> mm."""
    t = texto.strip()
    if t.endswith("mm"):
        return Medida.mm(t[:-2])
    if "''" in t or "/" in t:
        return Medida.pulg(t)
    return Medida.mm(t)


def _med_pulg_o_mm(texto: str, por_defecto_pulgadas: bool) -> Medida:
    t = texto.strip()
    if t.endswith("mm"):
        return Medida.mm(t[:-2])
    if "''" in t or "/" in t or por_defecto_pulgadas:
        return Medida.pulg(t)
    return Medida.mm(t)


def _miles(texto: str) -> str:
    """'2.400' (punto de miles en una medida en mm) -> '2400'."""
    return texto.replace(".", "") if re.fullmatch(r"\d{1,3}\.\d{3}", texto) else texto


def _largo(texto: str) -> Decimal:
    """'6000mm' -> 6000; '6,00mts' -> 6000; '6M' -> 6000."""
    t = texto.strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(mm|mts|mt|m|mtrs)?", t)
    if not m:
        raise GeneradorInvalido(f"largo ilegible: {texto!r}")
    v = Decimal(m.group(1).replace(",", "."))
    return v if (m.group(2) == "mm" or (m.group(2) is None and v >= 100)) else v * 1000


def leer(nombre: str) -> Producto | None:
    """Saca familia, material y medidas de un nombre de la app. None si no sigue una regla conocida."""
    t = limpiar(nombre)
    segunda = None
    if (ms := re.search(r"\s*\(2([ABC])\)$", t)):
        segunda, t = ms.group(1), t[:ms.start()]
    try:
        p = _leer(t)
    except (GeneradorInvalido, ValueError, ZeroDivisionError):
        return None
    if p is not None:
        p.segunda = segunda
    return p


def _leer(t: str) -> Producto | None:  # noqa: C901 - una rama por familia, a propósito
    x = r"\s*x\s*"
    if (m := re.fullmatch(rf"Tubo (L\.F\.|L\.C\.|Galv\.) {_PULG}(mm)?{x}{_PULG}(mm)?{x}{_NUM}mm{x}(\S+)", t, re.I)):
        mm = bool(m.group(3) or m.group(5))
        return Producto("tubo", material(m.group(1)), espesor=Medida.mm(m.group(6)),
                        medida1=_med_pulg_o_mm(m.group(2) + ("mm" if m.group(3) else ""), not mm),
                        medida2=_med_pulg_o_mm(m.group(4) + ("mm" if m.group(5) else ""), not mm),
                        largo_mm=_largo(m.group(7)))
    if (m := re.fullmatch(rf"Tubo Redondo (L\.F\.|L\.C\.|Galv\.) {_PULG}{x}{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("tubo_redondo", material(m.group(1)), medida1=Medida.pulg(m.group(2)),
                        espesor=Medida.mm(m.group(3)), largo_mm=_largo(m.group(4)))
    if (m := re.fullmatch(rf"Tubo Ventilacion L\.C\.(?: H\.?N\.?)? {_PULG}{x}{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("tubo_ventilacion", "HN", medida1=Medida.pulg(m.group(1)), espesor=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Tubo (?:Para )?Cerca Galv\.? {_PULG}{x}{_NUM}(?:mm)?{x}(\S+?)(?: P CERCAS)?", t, re.I)):
        return Producto("tubo_cerca", "GV", medida1=Medida.pulg(m.group(1)), espesor=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Angulo {_NUM}mm{x}{_NUM}mm{x}{_NUM}mm{x}(\S+)", t, re.I)):
        if m.group(1) != m.group(2):
            return None
        return Producto("angulo", "HN", medida1=Medida.mm(m.group(1)), espesor=Medida.mm(m.group(3)),
                        largo_mm=_largo(m.group(4)))
    if (m := re.fullmatch(rf"Pletina Perforada (Redonda|Cuadrada) {_PULG}\s*-\s*{_PULG}{x}{_PULG}{x}(\S+)", t, re.I)):
        return Producto("pletina_perforada", "HN", subtipo=m.group(1).capitalize(), medida1=Medida.pulg(m.group(2)),
                        medida2=Medida.pulg(m.group(3)), espesor=Medida.pulg(m.group(4)), largo_mm=_largo(m.group(5)))
    if (m := re.fullmatch(rf"Pletina {_PULG}{x}{_PULG}{x}(\S+)", t, re.I)):
        return Producto("pletina", "HN", medida2=Medida.pulg(m.group(1)), espesor=Medida.pulg(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Viga (IPE|IPN|HEA|UPL|UPE|CP) {_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("viga", "HN", subtipo=m.group(1).upper(), medida1=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"(?:Cabilla|Barra) Estriada {_PULG}(mm)?{x}(\S+) (S40|S60)", t, re.I)):
        diam = Medida.mm(m.group(1)) if m.group(2) else _med(m.group(1))
        return Producto("cabilla", "HN", subtipo=m.group(4).upper(), espesor=diam, largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Alambron (Estriado|Liso) {_NUM}mm (?:x (\S+)|Por Rollo)", t, re.I)):
        return Producto("alambron", "HN", subtipo=m.group(1).capitalize(), espesor=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)) if m.group(3) else None)
    if (m := re.fullmatch(rf"Barra (Redonda|Cuadrada) {_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("barra_redonda" if m.group(1).lower() == "redonda" else "barra_cuadrada", "HN",
                        espesor=Medida.mm(m.group(2)), largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Malla Truckson {_PULG}{x}{_PULG}{x}{_NUM}mm{x}(\d+)\s*mts2", t, re.I)):
        if Medida.pulg(m.group(1)) != Medida.pulg(m.group(2)):
            return None
        return Producto("malla_truckson", "HN", medida1=Medida.pulg(m.group(1)), espesor=Medida.mm(m.group(3)),
                        largo_mm=Decimal(m.group(4)))
    if (m := re.fullmatch(rf"Cercha C-\d+ {_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("cercha", "HN", medida1=Medida.mm(m.group(1)), largo_mm=_largo(m.group(2)))
    if (m := re.fullmatch(rf"Lamina (L\.F\.|L\.C\.|Galv\.|Aluminio|Est HN|PP) {_NUM}mm{x}{_NUM}mm{x}{_NUM}mm", t, re.I)):
        mat = "EST" if m.group(1).upper() == "EST HN" else material(m.group(1))
        return Producto("lamina", mat, espesor=Medida.mm(m.group(2)), medida1=Medida.mm(_miles(m.group(3))),
                        largo_mm=Decimal(_miles(m.group(4)).replace(",", ".")))
    if (m := re.fullmatch(rf"(Bobina|Fleje) (L\.F\.?|L\.C\.?|Galv\.|GV|Aluminio) {_NUM}mm{x}{_NUM}\s*mm", t, re.I)):
        mat = m.group(2).rstrip(".") + ("." if m.group(2).upper().startswith("L.") else "")
        return Producto(m.group(1).lower(), material(mat), espesor=Medida.mm(m.group(3)),
                        medida1=Medida.mm(m.group(4)))
    if (m := re.fullmatch(rf"Perfil (LC|LF|GV) Vigueta {_PULG}{x}{_PULG}{x}{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("perfil_vigueta", material(m.group(1)), medida1=Medida.pulg(m.group(2)),
                        medida2=Medida.pulg(m.group(3)), espesor=Medida.mm(m.group(4)), largo_mm=_largo(m.group(5)))
    if (m := re.fullmatch(rf"Perfil (LF|GV) Marco de (Puerta|Ventana) B(\d+){x}{_NUM}mm{x}(\S+)", t, re.I)):
        largo = _largo(m.group(5))
        if not largo:
            return None
        return Producto("perfil_marco", material(m.group(1)), subtipo=m.group(2).capitalize(),
                        medida1=Medida.mm(m.group(3)), espesor=Medida.mm(m.group(4)), largo_mm=largo)
    if (m := re.fullmatch(rf"Perfil (LF|GV|AL) Hoja Santa Maria x {_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("perfil_hoja_sm", material(m.group(1)), espesor=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Perfil (LC|LF|GV) Onge {_PULG}{x}{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("perfil_onge", material(m.group(1)), medida1=Medida.pulg(m.group(2)),
                        espesor=Medida.mm(m.group(3)), largo_mm=_largo(m.group(4)))
    if (m := re.fullmatch(rf"Perfil (LC|LF|GV) Omega 60mm{x}{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("perfil_omega", material(m.group(1)), espesor=Medida.mm(m.group(2)), largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Perfil (LF|GV) Romanilla (?:x )?{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("perfil_romanilla", material(m.group(1)), espesor=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    if (m := re.fullmatch(rf"Perfil (LC|LF) Guia Sta Maria 1''{x}2''{x}{_NUM}mm{x}(\S+)", t, re.I)):
        return Producto("perfil_guia_sm", material(m.group(1)), espesor=Medida.mm(m.group(2)),
                        largo_mm=_largo(m.group(3)))
    return None


# --------------------------------------------------------------------- comparar con la app

@dataclass
class FilaComparacion:
    estado: str                 # igual, cambia_codigo, cambia_nombre, cambian_ambos, sin_regla, choque
    familia: str | None
    codigo_actual: str
    nombre_actual: str
    codigo_nuevo: str | None = None
    nombre_nuevo: str | None = None
    nota: str = ""


ORDEN_ESTADOS = ("cambia_codigo", "cambian_ambos", "choque", "cambia_nombre", "sin_regla", "igual")


def comparar(productos: list[tuple[str, str]]) -> list[FilaComparacion]:
    """Para cada (código, nombre) de la app: qué código y nombre le da la regla nueva."""
    filas: list[FilaComparacion] = []
    for codigo, nombre in productos:
        codigo = (codigo or "").strip().upper()
        p = leer(nombre)
        if p is None:
            filas.append(FilaComparacion("sin_regla", None, codigo, nombre, nota="el nombre no sigue una regla conocida"))
            continue
        try:
            c_nuevo, n_nuevo = generar(p)
        except GeneradorInvalido as exc:
            filas.append(FilaComparacion("sin_regla", p.familia, codigo, nombre, nota=str(exc)))
            continue
        cambia_c = c_nuevo != codigo
        cambia_n = n_nuevo != limpiar(nombre) or n_nuevo != nombre
        estado = ("cambian_ambos" if cambia_c and cambia_n else "cambia_codigo" if cambia_c
                  else "cambia_nombre" if cambia_n else "igual")
        filas.append(FilaComparacion(estado, p.familia, codigo, nombre, c_nuevo, n_nuevo))
    # Choques: dos productos que terminarían con el mismo código, o uno que pisa a otro que no cambia.
    finales: dict[str, list[FilaComparacion]] = {}
    for f in filas:
        finales.setdefault(f.codigo_nuevo or f.codigo_actual, []).append(f)
    for codigo, grupo in finales.items():
        if len(grupo) > 1:
            for f in grupo:
                if f.estado != "igual":
                    f.estado = "choque"
                    otros = ", ".join(g.codigo_actual for g in grupo if g is not f)
                    f.nota = f"terminaría con el código {codigo}, igual que {otros}"
    return filas
