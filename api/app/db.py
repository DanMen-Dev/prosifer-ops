from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import config

engine = create_engine(config.database_url, pool_pre_ping=True)
SesionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: una transacción por petición."""
    with SesionLocal() as s:
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
