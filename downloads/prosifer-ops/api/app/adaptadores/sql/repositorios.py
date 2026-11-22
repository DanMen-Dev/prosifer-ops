"""Adaptador PostgreSQL de los repositorios y la unidad de trabajo.

Traduce entre las entidades del dominio (app.dominio.entidades) y las tablas
(app.modelos). La transacción la abre y la cierra quien crea la sesión
(la dependencia `sesion` de FastAPI): aquí solo se hace flush.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import fields

from sqlalchemy import String, cast, func, select, text
from sqlalchemy.orm import Session

from app import modelos as m
from app.adaptadores.sql.archivos import AlmacenSql
from app.adaptadores.sql.numerador import NumeradorSql
from app.dominio import entidades as e

CAMPOS_PIEZA = [f.name for f in fields(e.Pieza)
                if f.name not in ("propietario_nombre", "tipo_acero_codigo", "tipo_acero_nombre", "norma_nombre")]
CAMPOS_MOV = [f.name for f in fields(e.Movimiento) if f.name != "creado_en"]
CAMPOS_DOC = [f.name for f in fields(e.Documento)]
CAMPOS_OT = [f.name for f in fields(e.OrdenTrabajo) if f.name != "propietario_nombre"]


def a_pieza(r: m.Pieza) -> e.Pieza:
    p = e.Pieza(**{c: getattr(r, c) for c in CAMPOS_PIEZA})
    p.propietario_nombre = r.propietario.nombre if r.propietario else ""
    if r.tipo_acero:
        p.tipo_acero_codigo, p.tipo_acero_nombre = r.tipo_acero.codigo, r.tipo_acero.nombre
    p.norma_nombre = r.norma.nombre if r.norma else None
    return p


def a_movimiento(r: m.Movimiento) -> e.Movimiento:
    mv = e.Movimiento(**{c: getattr(r, c) for c in CAMPOS_MOV})
    mv.creado_en = r.creado_en
    return mv


def a_documento(r: m.Documento) -> e.Documento:
    return e.Documento(**{c: getattr(r, c) for c in CAMPOS_DOC})


def a_orden(r: m.OrdenTrabajo) -> e.OrdenTrabajo:
    o = e.OrdenTrabajo(**{c: getattr(r, c) for c in CAMPOS_OT})
    o.propietario_nombre = r.propietario.nombre if r.propietario else ""
    return o


def _copiar(origen, destino, campos: list[str]) -> None:
    for c in campos:
        if c != "id":
            setattr(destino, c, getattr(origen, c))


class _Base:
    def __init__(self, s: Session, empresa_id: int):
        self.s, self.e = s, empresa_id


class PiezasSql(_Base):
    def _consulta(self, bloquear: bool):
        q = select(m.Pieza).where(m.Pieza.empresa_id == self.e)
        # FOR UPDATE OF pieza: las tablas unidas (dueño, tipo, norma) no se bloquean.
        return q.with_for_update(of=m.Pieza) if bloquear else q

    def obtener(self, id_: int, *, bloquear: bool = False) -> e.Pieza | None:
        r = self.s.scalar(self._consulta(bloquear).where(m.Pieza.id == id_))
        return a_pieza(r) if r else None

    def obtener_varias(self, ids: list[int], *, bloquear: bool = False) -> dict[int, e.Pieza]:
        filas = self.s.scalars(self._consulta(bloquear).where(m.Pieza.id.in_(ids)).order_by(m.Pieza.id))
        return {r.id: a_pieza(r) for r in filas}

    def id_por_codigo(self, tipo: str, codigo: str, *, excluir_id: int | None = None) -> int | None:
        q = select(m.Pieza.id).where(m.Pieza.empresa_id == self.e, m.Pieza.tipo == tipo,
                                     func.upper(m.Pieza.codigo_fisico) == codigo.upper(), m.Pieza.anulada.is_(False),
                                     m.Pieza.saldo_unidades.is_(None))
        if excluir_id is not None:
            q = q.where(m.Pieza.id != excluir_id)
        return self.s.scalar(q.limit(1))

    def existencia(self, tipo: str, codigo: str, propietario_id: int, *, bloquear: bool = False) -> e.Pieza | None:
        r = self.s.scalar(self._consulta(bloquear).where(
            m.Pieza.tipo == tipo, func.upper(m.Pieza.codigo_fisico) == codigo.upper(),
            m.Pieza.propietario_id == propietario_id, m.Pieza.anulada.is_(False), m.Pieza.saldo_unidades.is_not(None)))
        return a_pieza(r) if r else None

    def existencias_de(self, propietario_id: int, tipo: str) -> list[e.Pieza]:
        return [a_pieza(r) for r in self.s.scalars(self._consulta(False).where(
            m.Pieza.tipo == tipo, m.Pieza.propietario_id == propietario_id, m.Pieza.anulada.is_(False),
            m.Pieza.saldo_unidades.is_not(None)).order_by(m.Pieza.id))]

    def producidas_por(self, orden_id: int) -> list[e.Pieza]:
        return [a_pieza(r) for r in self.s.scalars(
            select(m.Pieza).where(m.Pieza.orden_trabajo_id == orden_id).order_by(m.Pieza.id))]

    def agregar(self, p: e.Pieza) -> e.Pieza:
        r = m.Pieza(empresa_id=self.e)
        _copiar(p, r, CAMPOS_PIEZA)
        self.s.add(r)
        self.s.flush()
        self.s.refresh(r)
        nueva = a_pieza(r)
        p.id = nueva.id
        p.propietario_nombre, p.tipo_acero_codigo = nueva.propietario_nombre, nueva.tipo_acero_codigo
        p.tipo_acero_nombre, p.norma_nombre = nueva.tipo_acero_nombre, nueva.norma_nombre
        return p

    def guardar(self, p: e.Pieza) -> None:
        r = self.s.get(m.Pieza, p.id)
        _copiar(p, r, CAMPOS_PIEZA)
        self.s.flush()


class MovimientosSql(_Base):
    def agregar(self, mv: e.Movimiento) -> e.Movimiento:
        r = m.Movimiento(empresa_id=self.e)
        _copiar(mv, r, CAMPOS_MOV)
        self.s.add(r)
        self.s.flush()
        mv.id, mv.creado_en = r.id, r.creado_en
        return mv

    def por_clave(self, clave: str) -> e.Movimiento | None:
        r = self.s.scalar(select(m.Movimiento).where(m.Movimiento.empresa_id == self.e,
                                                     m.Movimiento.clave_idempotencia == clave))
        return a_movimiento(r) if r else None

    def por_documento(self, documento_id: int) -> list[e.Movimiento]:
        return [a_movimiento(r) for r in self.s.scalars(
            select(m.Movimiento).where(m.Movimiento.documento_id == documento_id).order_by(m.Movimiento.id))]

    def revertidos(self, ids: list[int]) -> set[int]:
        if not ids:
            return set()
        return set(self.s.scalars(select(m.Movimiento.revierte_id).where(m.Movimiento.revierte_id.in_(ids))))

    def contar(self, pieza_id: int, *, excepto_tipo: str | None = None) -> int:
        q = select(func.count(m.Movimiento.id)).where(m.Movimiento.pieza_id == pieza_id)
        if excepto_tipo:
            q = q.where(m.Movimiento.tipo != excepto_tipo)
        return self.s.scalar(q) or 0


class DocumentosSql(_Base):
    def agregar(self, d: e.Documento) -> e.Documento:
        r = m.Documento(empresa_id=self.e)
        _copiar(d, r, CAMPOS_DOC)
        self.s.add(r)
        self.s.flush()
        d.id = r.id
        return d

    def obtener(self, id_: int) -> e.Documento | None:
        r = self.s.get(m.Documento, id_)
        return a_documento(r) if r and r.empresa_id == self.e else None

    def guardar(self, d: e.Documento) -> None:
        r = self.s.get(m.Documento, d.id)
        _copiar(d, r, CAMPOS_DOC)
        self.s.flush()

    def por_clave(self, clave: str) -> e.Documento | None:
        r = self.s.scalar(select(m.Documento).where(m.Documento.empresa_id == self.e,
                                                    m.Documento.clave_idempotencia == clave))
        return a_documento(r) if r else None

    def numero_en_uso(self, tipo: str, numero: str) -> bool:
        return self.s.scalar(select(m.Documento.id).where(
            m.Documento.empresa_id == self.e, m.Documento.tipo == tipo, m.Documento.numero == numero,
            m.Documento.anulado.is_(False)).limit(1)) is not None

    def correcciones(self, documento_id: int) -> list[e.Documento]:
        return [a_documento(r) for r in self.s.scalars(
            select(m.Documento).where(m.Documento.documento_origen_id == documento_id).order_by(m.Documento.id))]

    def abiertos(self, tipo: str) -> list[e.Documento]:
        return [a_documento(r) for r in self.s.scalars(
            select(m.Documento).where(m.Documento.empresa_id == self.e, m.Documento.tipo == tipo,
                                      m.Documento.estado == "pendiente", m.Documento.anulado.is_(False))
            .order_by(m.Documento.id))]

    def agregar_lineas(self, documento_id: int, lineas: list[dict]) -> None:
        inicio = self.s.scalar(select(func.count(m.DocumentoLinea.id)).where(
            m.DocumentoLinea.documento_id == documento_id)) or 0
        for k, x in enumerate(lineas, start=inicio + 1):
            self.s.add(m.DocumentoLinea(documento_id=documento_id, posicion=k, codigo=x.get("codigo"),
                                        descripcion=x.get("descripcion"), cantidad=x.get("cantidad"),
                                        unidad=x.get("unidad"), kg=x.get("kg")))
        self.s.flush()

    def con_referencia_abono(self, tipo: str, referencia: str) -> e.Documento | None:
        ref = referencia.strip().upper()
        candidatos = self.s.scalars(select(m.Documento).where(
            m.Documento.empresa_id == self.e, m.Documento.tipo == tipo,
            func.upper(cast(m.Documento.encabezado, String)).contains(ref)))
        for r in candidatos:   # el filtro de texto acota; aquí se confirma que es la referencia de un abono
            if any((a.get("referencia") or "").strip().upper() == ref for a in (r.encabezado or {}).get("abonos", [])):
                return a_documento(r)
        return None

    def lineas(self, documento_id: int) -> list[dict]:
        return [{"codigo": r.codigo, "descripcion": r.descripcion, "cantidad": r.cantidad, "unidad": r.unidad, "kg": r.kg}
                for r in self.s.scalars(select(m.DocumentoLinea).where(m.DocumentoLinea.documento_id == documento_id)
                                        .order_by(m.DocumentoLinea.posicion))]


class OrdenesSql(_Base):
    def agregar(self, o: e.OrdenTrabajo) -> e.OrdenTrabajo:
        r = m.OrdenTrabajo(empresa_id=self.e)
        _copiar(o, r, CAMPOS_OT)
        self.s.add(r)
        self.s.flush()
        o.id = r.id
        return o

    def obtener(self, id_: int) -> e.OrdenTrabajo | None:
        r = self.s.get(m.OrdenTrabajo, id_)
        return a_orden(r) if r and r.empresa_id == self.e else None

    def guardar(self, o: e.OrdenTrabajo) -> None:
        r = self.s.get(m.OrdenTrabajo, o.id)
        _copiar(o, r, CAMPOS_OT)
        self.s.flush()

    def por_clave(self, clave: str) -> e.OrdenTrabajo | None:
        r = self.s.scalar(select(m.OrdenTrabajo).where(m.OrdenTrabajo.empresa_id == self.e,
                                                       m.OrdenTrabajo.clave_idempotencia == clave))
        return a_orden(r) if r else None

    def ultimo_numero(self, tipo: str) -> int:
        # Dos órdenes del mismo tipo creadas a la vez (p. ej. un lote de Prosi) leían el mismo máximo y salían con
        # el mismo número. El candado (por empresa y tipo, hasta el commit) hace que la segunda espere a la primera.
        if self.s.get_bind().dialect.name == "postgresql":
            self.s.execute(text("select pg_advisory_xact_lock(cast(:a as integer), hashtext(:b))"),
                           {"a": self.e, "b": f"orden_trabajo:{tipo}"})
        return self.s.scalar(select(func.max(m.OrdenTrabajo.numero)).where(
            m.OrdenTrabajo.empresa_id == self.e, m.OrdenTrabajo.tipo == tipo)) or 0

    def numero_en_uso(self, tipo: str, numero: int) -> bool:
        """Un número lo ocupa una orden viva; una planificada ya ejecutada lo comparte con su resultado."""
        return self.s.scalar(select(m.OrdenTrabajo.id).where(
            m.OrdenTrabajo.empresa_id == self.e, m.OrdenTrabajo.tipo == tipo, m.OrdenTrabajo.numero == numero,
            m.OrdenTrabajo.estado.not_in(("anulada", "ejecutada"))).limit(1)) is not None

    def planificadas(self) -> list[e.OrdenTrabajo]:
        return [a_orden(r) for r in self.s.scalars(select(m.OrdenTrabajo).where(
            m.OrdenTrabajo.empresa_id == self.e, m.OrdenTrabajo.estado == "planificada").order_by(m.OrdenTrabajo.id))]


class TercerosSql(_Base):
    def obtener(self, id_: int) -> e.Tercero | None:
        r = self.s.get(m.Tercero, id_)
        return e.Tercero(r.id, r.nombre) if r and r.empresa_id == self.e else None


class CatalogosSql(_Base):
    def tipo_por_codigo(self, codigo: str) -> e.TipoAcero | None:
        r = self.s.scalar(select(m.TipoAcero).where(m.TipoAcero.empresa_id == self.e, m.TipoAcero.codigo == codigo))
        return e.TipoAcero(r.id, r.codigo, r.nombre) if r else None

    def norma(self, id_: int) -> e.Norma | None:
        r = self.s.get(m.Norma, id_)
        return e.Norma(r.id, r.nombre) if r and r.empresa_id == self.e else None

    def producto(self, codigo: str) -> e.ProductoCatalogo | None:
        r = self.s.scalar(select(m.Producto).where(m.Producto.empresa_id == self.e, m.Producto.activo.is_(True),
                                                   func.upper(m.Producto.codigo) == codigo.strip().upper()))
        return e.ProductoCatalogo(r.id, r.codigo, r.nombre, r.peso_unitario_kg) if r else None


class ParametrosSql(_Base):
    def valor(self, clave: str, por_defecto: str, fecha: dt.date | None = None) -> str:
        v = self.s.scalar(select(m.Parametro.valor).where(
            m.Parametro.empresa_id == self.e, m.Parametro.clave == clave,
            m.Parametro.vigente_desde <= (fecha or dt.date.today())).order_by(m.Parametro.vigente_desde.desc()).limit(1))
        return v if v is not None else por_defecto


class AuditoriaSql(_Base):
    def registrar(self, tabla: str, registro_id: int, campo: str, antes: str | None, despues: str | None, *,
                  usuario: str, origen: str) -> None:
        self.s.add(m.Auditoria(empresa_id=self.e, tabla=tabla, registro_id=registro_id, campo=campo, antes=antes,
                               despues=despues, usuario=usuario, origen=origen))
        self.s.flush()


class UnidadSql:
    """Implementa app.puertos.UnidadDeTrabajo sobre una sesión de SQLAlchemy."""

    def __init__(self, s: Session, empresa_id: int):
        self.empresa_id = empresa_id
        self.sesion = s
        self.piezas = PiezasSql(s, empresa_id)
        self.movimientos = MovimientosSql(s, empresa_id)
        self.documentos = DocumentosSql(s, empresa_id)
        self.ordenes = OrdenesSql(s, empresa_id)
        self.terceros = TercerosSql(s, empresa_id)
        self.catalogos = CatalogosSql(s, empresa_id)
        self.parametros = ParametrosSql(s, empresa_id)
        self.auditoria = AuditoriaSql(s, empresa_id)
        self.numerador = NumeradorSql(s, empresa_id)
        self.archivos = AlmacenSql(s, empresa_id)
