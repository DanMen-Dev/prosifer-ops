"""Catálogo de productos: lo que se cotiza y se despacha."""
from __future__ import annotations

import dataclasses
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import modelos as m
from app.adaptadores.sql import crud
from app.db import sesion
from app.dominio import codigos, desarrollos
from app.dominio import generador as gen
from app.esquemas import (
    CambioProducto, GenerarProductoIn, PerfilSugerido, ProductoGenerado, ProductoIn, ProductoOut, VariantesEspesor,
    VariantesEspesorIn,
)
from app.seguridad import Actor, actor, editor

ruta = APIRouter(prefix="/api/productos", tags=["productos"])


@ruta.get("", response_model=list[ProductoOut])
def listar(q: str | None = Query(default=None, description="Busca en el código y en el nombre"),
           incluir_inactivos: bool = False, limite: int = Query(default=200, ge=1, le=2000),
           s: Session = Depends(sesion), a: Actor = Depends(actor)):
    # el cliente también lo consulta (solo activos) para autocompletar sus avisos de entrada
    consulta = select(m.Producto).where(m.Producto.empresa_id == a.empresa_id)
    if not incluir_inactivos or a.cliente is not None:
        consulta = consulta.where(m.Producto.activo.is_(True))
    if a.cliente is not None:   # el cliente no anuncia productos sin existencia (medidas irregulares)
        consulta = consulta.where(func.upper(m.Producto.codigo).not_in(list(codigos.SIN_EXISTENCIA)))
    for palabra in (q or "").split():  # cada palabra debe aparecer: "lamina 3,00 2400"
        patron = f"%{palabra}%"
        consulta = consulta.where(or_(m.Producto.codigo.ilike(patron), m.Producto.nombre.ilike(patron)))
    return s.scalars(consulta.order_by(m.Producto.nombre).limit(limite)).all()


@ruta.get("/familias", summary="Familias del generador de códigos: campos y materiales de cada una")
def familias(a: Actor = Depends(editor)) -> list[dict]:
    return [{"clave": f.clave, "nombre": f.nombre, "prefijo": f.prefijo,
             "materiales": [{"codigo": c, "nombre": gen.MATERIALES[c][1]} for c in f.materiales],
             "campos": [{"clave": c.clave, "etiqueta": c.etiqueta, "tipo": c.tipo, "opciones": list(c.opciones),
                         "obligatorio": c.obligatorio} for c in f.campos]}
            for f in gen.FAMILIAS.values()]


def _medida(texto: str | None, tipo: str) -> gen.Medida | None:
    if not texto or not texto.strip():
        return None
    t = texto.strip()
    if tipo == "pulgadas" or (tipo == "mm_o_pulgadas" and ("/" in t or "''" in t or '"' in t)):
        return gen.Medida.pulg(t)
    return gen.Medida.mm(t.lower().removesuffix("mm"))


@ruta.post("/generar", response_model=ProductoGenerado,
           summary="Arma código y nombre con la regla de la familia y dice si ya existe (no guarda nada)")
def generar(datos: GenerarProductoIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    f = gen.FAMILIAS.get(datos.familia)
    if f is None:
        raise HTTPException(422, f"familia desconocida: {datos.familia}")
    tipos = {c.clave: c.tipo for c in f.campos}
    try:
        p = gen.Producto(
            datos.familia, datos.material.upper(), subtipo=datos.subtipo,
            espesor=_medida(datos.espesor, tipos.get("espesor", "mm")),
            medida1=_medida(datos.medida1, "pulgadas" if tipos.get("medida1") == "opcion" else tipos.get("medida1", "mm")),
            medida2=_medida(datos.medida2, tipos.get("medida2", "mm")),
            largo_mm=datos.largo_mm, segunda=datos.segunda)
        codigo, nombre = gen.generar(p)
    except (gen.GeneradorInvalido, ValueError, ZeroDivisionError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _generado(s, a.empresa_id, codigo, nombre)


def _generado(s: Session, empresa_id: int, codigo: str, nombre: str) -> ProductoGenerado:
    existente = s.scalar(select(m.Producto).where(m.Producto.empresa_id == empresa_id, m.Producto.codigo == codigo))
    return ProductoGenerado(codigo=codigo, nombre=nombre,
                            existente=ProductoOut.model_validate(existente) if existente else None)


@ruta.get("/espesor-comercial", summary="Espesor con el que se vende (0,58 -> 0,60), para preguntar si se redondea")
def espesor_comercial(mm: Decimal = Query(gt=0, lt=100), a: Actor = Depends(editor)) -> dict:
    real = mm.quantize(Decimal("0.01"))
    comercial = codigos.espesor_comercial(real)
    return {"real": str(real), "comercial": str(comercial), "difiere": comercial != real}


@ruta.get("/sugerir-perfil", response_model=list[PerfilSugerido],
          summary="Perfiles que suelen salir de un fleje (por ancho, material y espesor), para que la asistente ratifique")
def sugerir_perfil(pieza_id: int, s: Session = Depends(sesion), a: Actor = Depends(actor)):
    pieza = s.get(m.Pieza, pieza_id)
    # el cliente también la usa al precargar su orden de maquila, solo con sus flejes
    if pieza is None or pieza.empresa_id != a.empresa_id or (a.cliente is not None and pieza.propietario_id != a.cliente):
        raise HTTPException(404, "pieza inexistente")
    material = pieza.tipo_acero.codigo if pieza.tipo_acero else None
    real = (pieza.espesor_mm or Decimal("0")).quantize(Decimal("0.01"))
    comercial = codigos.espesor_comercial(real) if real else None
    salida: list[PerfilSugerido] = []
    for d in desarrollos.para_fleje(material, real, pieza.ancho_mm):
        base = gen.Producto(d.familia, material, subtipo=d.datos.get("subtipo"), largo_mm=d.largo_mm,
                            medida1=gen.Medida(d.datos["medida1"], True) if "medida1" in d.datos else
                            (gen.Medida.mm(d.datos["base"]) if "base" in d.datos else None),
                            medida2=gen.Medida(d.datos["medida2"], True) if "medida2" in d.datos else None)
        try:
            c_r, n_r = gen.generar(dataclasses.replace(base, espesor=gen.Medida.mm(real)))
            opcion_c = None
            if comercial and comercial != real:
                c_c, n_c = gen.generar(dataclasses.replace(base, espesor=gen.Medida.mm(comercial)))
                opcion_c = _generado(s, a.empresa_id, c_c, n_c)
        except gen.GeneradorInvalido:
            continue
        salida.append(PerfilSugerido(nombre=d.nombre, espesor_real=real,
                                     espesor_comercial=comercial if comercial != real else None,
                                     real=_generado(s, a.empresa_id, c_r, n_r), comercial=opcion_c))
    return salida


@ruta.post("/variantes-espesor", response_model=VariantesEspesor,
           summary="El producto con el espesor real del material y con el comercial, para preguntar si se redondea")
def variantes_espesor(datos: VariantesEspesorIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    """Maquila (y cualquier transformación): si el fleje es de 0,58 mm, el perfil puede llevar 0,58 o 0,60.
    Si se redondea, se redondean el nombre y el código, para distinguirlo del que no se redondea."""
    base = s.scalar(select(m.Producto).where(m.Producto.empresa_id == a.empresa_id,
                                             m.Producto.codigo == datos.codigo.strip().upper()))
    if base is None:
        raise HTTPException(404, "ese producto no está en el catálogo")
    p = gen.leer(base.nombre)
    if p is None:
        raise HTTPException(422, "el nombre de ese producto no sigue una regla conocida: elige el código a mano")
    real = datos.espesor_mm.quantize(Decimal("0.01"))
    comercial = codigos.espesor_comercial(real)
    try:
        c_real, n_real = gen.generar(dataclasses.replace(p, espesor=gen.Medida.mm(real)))
        opcion_comercial = None
        if comercial != real:
            c_com, n_com = gen.generar(dataclasses.replace(p, espesor=gen.Medida.mm(comercial)))
            opcion_comercial = _generado(s, a.empresa_id, c_com, n_com)
    except gen.GeneradorInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    return VariantesEspesor(espesor_real=real, espesor_comercial=comercial if comercial != real else None,
                            real=_generado(s, a.empresa_id, c_real, n_real), comercial=opcion_comercial)


@ruta.post("", response_model=ProductoOut, status_code=201)
def crear(datos: ProductoIn, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    """Sin código, la app asigna uno: prefijo del nombre + correlativo (PUE0001…). Sirve para lo que no tiene
    familia en el generador (puertas, accesorios): el nombre lleva el detalle."""
    nombre = " ".join(datos.nombre.split())
    codigo = (datos.codigo or "").strip().upper()
    if codigo and len(codigo) < 3:
        raise HTTPException(422, "el código debe tener al menos 3 caracteres (o déjalo vacío y la app lo asigna)")
    if codigo:
        p = m.Producto(empresa_id=a.empresa_id, codigo=codigo, nombre=nombre, peso_unitario_kg=datos.peso_unitario_kg)
        s.add(p)
        try:
            s.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "ya existe un producto con ese código") from exc
        return p
    prefijo = codigos.prefijo_automatico(nombre)
    if s.get_bind().dialect.name == "postgresql":     # dos altas a la vez no toman el mismo correlativo
        s.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"producto:{a.empresa_id}:{prefijo}"))))
    usados = s.scalars(select(m.Producto.codigo).where(m.Producto.empresa_id == a.empresa_id,
                                                        m.Producto.codigo.like(f"{prefijo}%"))).all()
    p = m.Producto(empresa_id=a.empresa_id, codigo=codigos.codigo_automatico(nombre, set(usados)), nombre=nombre,
                   peso_unitario_kg=datos.peso_unitario_kg)
    s.add(p)
    s.flush()
    return p


@ruta.patch("/{id_}", response_model=ProductoOut)
def editar(id_: int, datos: CambioProducto, s: Session = Depends(sesion), a: Actor = Depends(editor)):
    """El código no se cambia: lo usan los documentos ya emitidos. Un código equivocado se desactiva y se crea otro."""
    p = s.get(m.Producto, id_)
    if p is None or p.empresa_id != a.empresa_id:
        raise HTTPException(404, "no existe")
    crud.editar(s, a.empresa_id, p, datos.model_dump(exclude_unset=True), tabla="producto",
                usuario=a.usuario, origen=a.origen)
    return p
