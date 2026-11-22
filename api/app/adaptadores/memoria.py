"""Adaptador en memoria de la unidad de trabajo. Sirve para probar los casos de uso sin
PostgreSQL: mismas reglas, datos en diccionarios. No bloquea ni persiste."""
from __future__ import annotations

import copy
import datetime as dt
import itertools

from app.dominio import entidades as e


class _Tabla:
    def __init__(self):
        self.filas: dict[int, object] = {}
        self._ids = itertools.count(1)

    def nuevo_id(self) -> int:
        return next(self._ids)


class PiezasMem:
    def __init__(self, u: "UnidadMemoria"):
        self.u, self.t = u, _Tabla()

    def _leer(self, p: e.Pieza) -> e.Pieza:
        p = copy.deepcopy(p)
        t = self.u.terceros.filas.get(p.propietario_id)
        p.propietario_nombre = t.nombre if t else ""
        tipo = next((x for x in self.u.catalogos.tipos.values() if x.id == p.tipo_acero_id), None)
        p.tipo_acero_codigo, p.tipo_acero_nombre = (tipo.codigo, tipo.nombre) if tipo else (None, None)
        n = self.u.catalogos.normas.get(p.norma_id) if p.norma_id else None
        p.norma_nombre = n.nombre if n else None
        return p

    def obtener(self, id_, *, bloquear=False):
        p = self.t.filas.get(id_)
        return self._leer(p) if p else None

    def obtener_varias(self, ids, *, bloquear=False):
        return {i: self._leer(self.t.filas[i]) for i in sorted(ids) if i in self.t.filas}

    def id_por_codigo(self, tipo, codigo, *, excluir_id=None):
        return next((p.id for p in self.t.filas.values() if p.tipo == tipo and not p.anulada and p.id != excluir_id
                     and p.saldo_unidades is None and p.codigo_fisico.upper() == codigo.upper()), None)

    def existencia(self, tipo, codigo, propietario_id, *, bloquear=False):
        p = next((p for p in self.t.filas.values() if p.tipo == tipo and not p.anulada and p.saldo_unidades is not None
                  and p.codigo_fisico.upper() == codigo.upper() and p.propietario_id == propietario_id), None)
        return self._leer(p) if p else None

    def existencias_de(self, propietario_id, tipo):
        return [self._leer(p) for p in self.t.filas.values() if p.tipo == tipo and not p.anulada
                and p.saldo_unidades is not None and p.propietario_id == propietario_id]

    def producidas_por(self, orden_id):
        return [self._leer(p) for p in self.t.filas.values() if p.orden_trabajo_id == orden_id]

    def agregar(self, p):
        p.id = self.t.nuevo_id()
        self.t.filas[p.id] = copy.deepcopy(p)
        leida = self._leer(p)
        p.propietario_nombre, p.tipo_acero_codigo = leida.propietario_nombre, leida.tipo_acero_codigo
        p.tipo_acero_nombre, p.norma_nombre = leida.tipo_acero_nombre, leida.norma_nombre
        return p

    def guardar(self, p):
        self.t.filas[p.id] = copy.deepcopy(p)


class MovimientosMem:
    def __init__(self):
        self.t = _Tabla()

    def agregar(self, mv):
        mv.id = self.t.nuevo_id()
        mv.creado_en = dt.datetime.now(dt.timezone.utc)
        self.t.filas[mv.id] = copy.deepcopy(mv)
        return mv

    def por_clave(self, clave):
        return next((copy.deepcopy(m) for m in self.t.filas.values() if m.clave_idempotencia == clave), None)

    def por_documento(self, documento_id):
        return [copy.deepcopy(m) for m in self.t.filas.values() if m.documento_id == documento_id]

    def contar(self, pieza_id, *, excepto_tipo=None):
        return sum(1 for m in self.t.filas.values() if m.pieza_id == pieza_id and m.tipo != excepto_tipo)

    def de_pieza(self, pieza_id):
        return [copy.deepcopy(m) for m in self.t.filas.values() if m.pieza_id == pieza_id]

    def revertidos(self, ids):
        return {m.revierte_id for m in self.t.filas.values() if m.revierte_id in set(ids)}


class DocumentosMem:
    def __init__(self):
        self.t = _Tabla()

    def agregar(self, d):
        d.id = self.t.nuevo_id()
        self.t.filas[d.id] = copy.deepcopy(d)
        return d

    def obtener(self, id_):
        d = self.t.filas.get(id_)
        return copy.deepcopy(d) if d else None

    def guardar(self, d):
        self.t.filas[d.id] = copy.deepcopy(d)

    def por_clave(self, clave):
        return next((copy.deepcopy(d) for d in self.t.filas.values() if d.clave_idempotencia == clave), None)

    def numero_en_uso(self, tipo, numero):
        return any(d.tipo == tipo and d.numero == numero and not d.anulado for d in self.t.filas.values())

    def correcciones(self, documento_id):
        return [copy.deepcopy(d) for d in self.t.filas.values() if d.documento_origen_id == documento_id]

    def abiertos(self, tipo):
        return [copy.deepcopy(d) for d in self.t.filas.values()
                if d.tipo == tipo and d.estado == "pendiente" and not d.anulado]

    def agregar_lineas(self, documento_id, lineas):
        self.renglones = getattr(self, "renglones", {})
        self.renglones.setdefault(documento_id, []).extend(copy.deepcopy(lineas))

    def lineas(self, documento_id):
        return copy.deepcopy(getattr(self, "renglones", {}).get(documento_id, []))

    def con_referencia_abono(self, tipo, referencia):
        ref = referencia.strip().upper()
        return next((copy.deepcopy(d) for d in self.t.filas.values() if d.tipo == tipo and any(
            (a.get("referencia") or "").strip().upper() == ref for a in (d.encabezado or {}).get("abonos", []))), None)


class OrdenesMem:
    def __init__(self, u: "UnidadMemoria"):
        self.u, self.t = u, _Tabla()

    def _leer(self, o):
        o = copy.deepcopy(o)
        t = self.u.terceros.filas.get(o.propietario_id)
        o.propietario_nombre = t.nombre if t else ""
        return o

    def agregar(self, o):
        o.id = self.t.nuevo_id()
        self.t.filas[o.id] = copy.deepcopy(o)
        return o

    def obtener(self, id_):
        o = self.t.filas.get(id_)
        return self._leer(o) if o else None

    def guardar(self, o):
        self.t.filas[o.id] = copy.deepcopy(o)

    def por_clave(self, clave):
        return next((self._leer(o) for o in self.t.filas.values() if o.clave_idempotencia == clave), None)

    def ultimo_numero(self, tipo):
        return max((o.numero for o in self.t.filas.values() if o.tipo == tipo), default=0)

    def numero_en_uso(self, tipo, numero):
        return any(o.tipo == tipo and o.numero == numero and o.estado not in ("anulada", "ejecutada")
                   for o in self.t.filas.values())

    def planificadas(self):
        return [self._leer(o) for o in self.t.filas.values() if o.estado == "planificada"]


class TercerosMem:
    def __init__(self):
        self.filas: dict[int, e.Tercero] = {}

    def nuevo(self, nombre: str) -> e.Tercero:
        t = e.Tercero(len(self.filas) + 1, nombre)
        self.filas[t.id] = t
        return t

    def obtener(self, id_):
        return self.filas.get(id_)


class CatalogosMem:
    def __init__(self):
        self.tipos = {c: e.TipoAcero(i, c, n) for i, (c, n) in enumerate(
            [("HP", "LAM FRIO"), ("HN", "LAM CALI"), ("GV", "LAM GALV"), ("ES", "LAM ESTR"), ("PP", "LAM PREP"),
             ("AL", "ALUMINIO")], start=1)}
        self.normas: dict[int, e.Norma] = {}
        self.productos: dict[str, e.ProductoCatalogo] = {}

    def tipo_por_codigo(self, codigo):
        return self.tipos.get(codigo)

    def norma(self, id_):
        return self.normas.get(id_)

    def producto(self, codigo):
        return self.productos.get(codigo.strip().upper())


class ParametrosMem:
    def __init__(self):
        self.valores: dict[str, str] = {}

    def valor(self, clave, por_defecto, fecha=None):
        return self.valores.get(clave, por_defecto)


class AuditoriaMem:
    def __init__(self):
        self.registros: list[tuple] = []

    def registrar(self, tabla, registro_id, campo, antes, despues, *, usuario, origen):
        self.registros.append((tabla, registro_id, campo, antes, despues, usuario, origen))


class NumeradorMem:
    def __init__(self, inicial: dict[str, int] | None = None):
        self.ultimos = dict(inicial or {})

    def siguiente(self, tipo):
        self.ultimos[tipo] = self.ultimos.get(tipo, 0) + 1
        return self.ultimos[tipo]

    def ver_siguiente(self, tipo):
        return self.ultimos.get(tipo, 0) + 1


class ArchivosMem:
    def __init__(self):
        self.archivos: dict[tuple, bytes] = {}

    def guardar(self, ref_tabla, ref_id, nombre, contenido, *, tipo_mime, usuario):
        self.archivos[(ref_tabla, ref_id, nombre)] = contenido
        return len(self.archivos)

    def buscar(self, ref_tabla, ref_id, nombre):
        return self.archivos.get((ref_tabla, ref_id, nombre))


class UnidadMemoria:
    """Implementa app.puertos.UnidadDeTrabajo en memoria."""

    def __init__(self, empresa_id: int = 1):
        self.empresa_id = empresa_id
        self.terceros = TercerosMem()
        self.catalogos = CatalogosMem()
        self.piezas = PiezasMem(self)
        self.movimientos = MovimientosMem()
        self.documentos = DocumentosMem()
        self.ordenes = OrdenesMem(self)
        self.parametros = ParametrosMem()
        self.auditoria = AuditoriaMem()
        self.numerador = NumeradorMem({"nota_entrega": 7224, "cotizacion": 2938})
        self.archivos = ArchivosMem()
