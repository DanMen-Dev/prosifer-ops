"""Edición directa de registros de catálogo (tipos de acero, normas, terceros, usuarios).

Son mantenimientos sin reglas de inventario, así que viven en el adaptador SQL; cada
cambio queda en la auditoría igual que en el núcleo.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import modelos as m


def editar(s: Session, empresa_id: int, objeto, cambios: dict, *, tabla: str, usuario: str,
           origen: str) -> list[str]:
    cambiados = []
    for campo, nuevo in cambios.items():
        viejo = getattr(objeto, campo)
        if viejo == nuevo:
            continue
        setattr(objeto, campo, nuevo)
        s.add(m.Auditoria(empresa_id=empresa_id, tabla=tabla, registro_id=objeto.id, campo=campo,
                          antes=None if viejo is None else str(viejo),
                          despues=None if nuevo is None else str(nuevo), usuario=usuario, origen=origen))
        cambiados.append(campo)
    s.flush()
    return cambiados
