"""Prueba de paridad: compara la existencia calculada con la hoja Consolidado.

Uso:
    python -m importador.paridad /ruta/Inventario_de_Bobinas.xlsm

Termina con código 0 si el inventario disponible (piezas, kg y dueño)
coincide con el Consolidado; 1 si no.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from decimal import Decimal

from importador import excel, reglas

TOLERANCIA_KG = Decimal("1")


def comparar(libro: excel.Libro, plan: reglas.Plan) -> dict:
    por_codigo = defaultdict(list)
    for f in libro.consolidado:
        por_codigo[reglas.clave(f.codigo_bobina)].append(f)

    ultima_salida = {}
    for s in libro.salidas:  # la hoja guarda las salidas de la más nueva a la más vieja
        ultima_salida.setdefault(reglas.clave(s.codigo_bobina), s)

    diferencias = []
    disp_libro = [f for f in libro.consolidado if f.estado == "Disponible"]
    disp_nuevo = [p for p in plan.piezas.values() if p.estado == "disponible"]
    for k, p in plan.piezas.items():
        filas = por_codigo.get(k, [])
        if not filas:
            diferencias.append((p.entrada.codigo_bobina, "no está en Consolidado", p.saldo, None))
            continue
        # Las entradas duplicadas aparecen dos veces en el Consolidado: basta con que una coincida.
        if not any(abs(f.disponible - p.saldo) <= TOLERANCIA_KG for f in filas):
            diferencias.append((p.entrada.codigo_bobina, "kg", p.saldo, [f.disponible for f in filas]))
        elif p.estado == "disponible" and not any(
                reglas.clave(f.propietario) == reglas.clave(p.propietario) for f in filas):
            # El libro pone como dueño a quien figure en la última salida, aunque sea una nota
            # de entrega o una fila sin datos. La regla nueva solo cambia el dueño con una liberación.
            ultima = ultima_salida.get(k)
            tipo = "dueño (regla vieja)" if ultima is not None and any(
                reglas.clave(f.propietario) == reglas.clave(ultima.propietario) for f in filas) else "dueño"
            diferencias.append((p.entrada.codigo_bobina, tipo, p.propietario, [f.propietario for f in filas]))

    return {
        "piezas": len(plan.piezas),
        "disponibles_libro": (len(disp_libro), sum(f.disponible for f in disp_libro)),
        "disponibles_nuevo": (len(disp_nuevo), sum(p.saldo for p in disp_nuevo)),
        "diferencias": diferencias,
        "incidencias": plan.incidencias,
    }


def _kg(x: Decimal) -> str:
    return f"{x:,.0f}".replace(",", ".")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    libro = excel.leer(argv[1])
    plan = reglas.construir(libro)
    r = comparar(libro, plan)
    nl, kl = r["disponibles_libro"]
    nn, kn = r["disponibles_nuevo"]
    print(f"Piezas importadas: {r['piezas']}")
    print(f"Disponible según Consolidado: {nl} piezas, {_kg(kl)} kg")
    print(f"Disponible según la app:      {nn} piezas, {_kg(kn)} kg")
    print(f"\nDiferencias: {len(r['diferencias'])}")
    for d in r["diferencias"]:
        print("  ", d)
    tipos = Counter(i.tipo for i in r["incidencias"])
    print(f"\nIncidencias para revisar: {dict(tipos)}")
    for i in r["incidencias"]:
        print(f"   [{i.tipo}] {i.codigo}: {i.detalle}")
    kg_ok = nl == nn and abs(kl - kn) <= TOLERANCIA_KG and not [
        d for d in r["diferencias"] if d[1] in ("kg", "no está en Consolidado")]
    por_revisar = [d for d in r["diferencias"] if d[1] == "dueño"]
    print("\nExistencia (piezas y kg): " + ("PARIDAD OK" if kg_ok else "CON DIFERENCIAS"))
    print(f"Dueños por revisar a mano: {len(por_revisar)}")
    return 0 if kg_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
