"""Carga las existencias de láminas, perfiles o productos generales desde su libro.

    python -m importador.cargar_existencias lamina  /datos/Inventario_de_Laminas.xlsm             # vista previa
    python -m importador.cargar_existencias lamina  /datos/Inventario_de_Laminas.xlsm --cargar    # guarda
    python -m importador.cargar_existencias perfil  /datos/Inventario_de_Perfiles.xlsm --cargar
    python -m importador.cargar_existencias general /datos/Inventario_de_Productos_Generales.xlsm --cargar

Para refrescar con un libro más nuevo (antes de estrenar la app), --reemplazar borra lo cargado
de ese tipo y lo vuelve a cargar. Se niega si alguna de esas existencias ya tiene movimientos
hechos en la app (NE, OC, ajustes): ahí ya no se reemplaza, se ajusta.

    python -m importador.cargar_existencias lamina /datos/Inventario_de_Laminas.xlsm --cargar --reemplazar

Cada código y dueño entra como una existencia en piezas con un movimiento de entrada
(origen "importacion"), por el mismo caso de uso que usa la pantalla. Se niega si ese
tipo ya tiene existencias en la base, para no cargar dos veces.

Peso por pieza: el del libro; si falta, el del catálogo de productos; si falta y es una
lámina, el teórico (espesor × ancho × largo × 7,85). Si no hay ninguno, la fila no se
carga y se informa.
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal

from sqlalchemy import delete, func, select

from app import modelos as m
from app.adaptadores.sql.repositorios import UnidadSql
from app.config import config
from app.db import SesionLocal
from app.dominio import codigos
from app.dominio.entidades import Documento
from app.servicios import inventario
from importador import existencias_excel as xe
from importador.cargar import Cache

USUARIO = "importador"


def borrar_cargado(s, tipo: str, empresa_id: int) -> int:
    """Borra las existencias de un tipo cargadas desde el Excel, si la app todavía no las movió."""
    ids = list(s.scalars(select(m.Pieza.id).where(m.Pieza.empresa_id == empresa_id, m.Pieza.tipo == tipo,
                                                   m.Pieza.saldo_unidades.is_not(None))))
    if not ids:
        return 0
    usadas = s.scalar(select(func.count(m.Movimiento.id)).where(
        m.Movimiento.pieza_id.in_(ids), m.Movimiento.origen != "importacion"))
    if usadas:
        raise SystemExit(f"No se reemplaza: hay {usadas} movimientos hechos en la app sobre existencias de tipo "
                         f"{tipo}. Desde aquí se corrige con ajustes, no recargando.")
    docs = set(s.scalars(select(m.Movimiento.documento_id).where(m.Movimiento.pieza_id.in_(ids),
                                                                  m.Movimiento.documento_id.is_not(None))))
    s.execute(delete(m.Movimiento).where(m.Movimiento.pieza_id.in_(ids)))
    s.execute(delete(m.Auditoria).where(m.Auditoria.tabla == "pieza", m.Auditoria.registro_id.in_(ids)))
    s.execute(delete(m.Pieza).where(m.Pieza.id.in_(ids)))
    for d in docs:
        if not s.scalar(select(func.count(m.Movimiento.id)).where(m.Movimiento.documento_id == d)):
            s.execute(delete(m.Documento).where(m.Documento.id == d, m.Documento.origen == "importacion",
                                                m.Documento.tipo == "entrada"))
    s.flush()
    return len(ids)


def cargar(s, libro: xe.LibroExistencias, empresa_id: int, *, nombre_libro: str) -> tuple[dict, list[str]]:
    avisos: list[str] = []
    ya = s.scalar(select(func.count(m.Pieza.id)).where(
        m.Pieza.empresa_id == empresa_id, m.Pieza.tipo == libro.tipo, m.Pieza.anulada.is_(False),
        m.Pieza.saldo_unidades.is_not(None)))
    if ya:
        raise SystemExit(f"Ya hay {ya} existencias de tipo {libro.tipo} en la base: no se carga dos veces. "
                         f"Para refrescarlas con un libro más nuevo agrega --reemplazar.")
    cache = Cache(s, empresa_id)
    duenos = {d: cache.tercero(d) for d in libro.duenos}
    s.flush()
    productos = {p.codigo.upper(): p for p in s.scalars(select(m.Producto).where(m.Producto.empresa_id == empresa_id))}

    uow = UnidadSql(s, empresa_id)
    hoy = dt.date.today()
    doc = uow.documentos.agregar(Documento(
        None, "entrada", numero=f"Importación {nombre_libro}", fecha=hoy, observacion="Saldo inicial desde el Excel",
        origen="importacion", creado_por=USUARIO))
    cargado: dict[str, int] = {}
    for f in libro.filas:
        peso = f.peso_unitario_kg
        if peso is None and f.codigo in productos and productos[f.codigo].peso_unitario_kg:
            peso = productos[f.codigo].peso_unitario_kg
        if peso is None and libro.tipo == "lamina":
            peso = xe.peso_teorico_lamina(f)
            if peso:
                avisos.append(f"{f.codigo}: sin peso en el libro, se usa el teórico {peso} kg por pieza")
        if not peso:
            avisos.append(f"{f.codigo}: NO se carga, no tiene peso por pieza ni en el libro ni en el catálogo "
                          f"({sum(f.por_dueno.values())} piezas)")
            continue
        peso = peso.quantize(Decimal("0.0001"))
        tipo_acero_id = norma_id = None
        try:
            t = cache.tipos.get(codigos.codigo_tipo(f.tipo_acero)) if f.tipo_acero else None
            tipo_acero_id = t.id if t else None
        except codigos.CodigoInvalido:
            avisos.append(f"{f.codigo}: tipo de acero desconocido {f.tipo_acero!r}")
        n = cache.norma(f.norma)
        if n is not None:
            s.flush()
            norma_id = n.id
        for dueno, piezas in f.por_dueno.items():
            prod = inventario.ProductoEnExistencia(
                libro.tipo, f.codigo, f.descripcion[:200], duenos[dueno].id, calidad=(f.calidad or None) and f.calidad[:10],
                tipo_acero_id=tipo_acero_id, norma_id=norma_id, espesor_mm=f.espesor_mm, ancho_mm=f.ancho_mm,
                largo_mm=f.largo_mm)
            inventario.sumar_existencia(uow, prod, piezas, (peso * piezas).quantize(Decimal("0.001")),
                                        tipo_mov="entrada", usuario=USUARIO, origen="importacion", fecha=hoy,
                                        documento_id=doc.id, observacion=f"{nombre_libro}, fila {f.fila}")
            cargado[dueno] = cargado.get(dueno, 0) + piezas
    return cargado, avisos


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in xe.COLUMNAS:
        print(__doc__)
        return 2
    tipo, ruta = argv[0], argv[1]
    libro = xe.leer(tipo, ruta)
    print("\n".join(xe.informe(libro)))
    nombre = ruta.rsplit("/", 1)[-1]
    with SesionLocal() as s:
        if "--reemplazar" in argv:
            print(f"Se reemplazan {borrar_cargado(s, tipo, config.empresa_id)} existencias de tipo {tipo} ya cargadas.")
        cargado, avisos = cargar(s, libro, config.empresa_id, nombre_libro=nombre)
        for a in avisos:
            print(" -", a)
        errores = xe.paridad(libro, cargado)
        print("Paridad por dueño:", "OK" if not errores else "DIFERENCIAS")
        for e in errores:
            print("   ", e)
        if "--cargar" in argv:
            s.commit()
            print(f"Guardado: {sum(cargado.values())} piezas.")
        else:
            s.rollback()
            print("Vista previa: no se guardó nada. Agrega --cargar para guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
