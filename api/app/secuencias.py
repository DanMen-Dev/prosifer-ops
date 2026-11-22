"""Ver o fijar la numeración de notas de entrega y cotizaciones.

    docker compose exec api python -m app.secuencias ver
    docker compose exec api python -m app.secuencias fijar nota_entrega 7230   # el próximo será 7231

Úsalo el día que la oficina deje de emitir notas en el Excel, con el último número que salió de ahí.
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from app.adaptadores.sql.numerador import NumeradorSql
from app.config import config
from app.db import SesionLocal


def main(argv: list[str]) -> int:
    with SesionLocal() as s:
        if len(argv) == 2 and argv[1] == "ver":
            for tipo, ultimo in s.execute(text("SELECT tipo, ultimo FROM secuencia WHERE empresa_id = :e ORDER BY tipo"),
                                          {"e": config.empresa_id}):
                print(f"{tipo}: último {ultimo}, próximo {ultimo + 1}")
            return 0
        if len(argv) == 4 and argv[1] == "fijar" and argv[3].isdigit():
            NumeradorSql(s, config.empresa_id).fijar(argv[2], int(argv[3]))
            s.commit()
            print(f"{argv[2]}: el próximo número será {int(argv[3]) + 1}")
            return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
