"""El núcleo (dominio, servicios, puertos) no depende de la base de datos ni de la web.

Si esta prueba falla, alguien importó SQLAlchemy, FastAPI o los modelos de tablas dentro del
núcleo: esa dependencia va en un adaptador (app/adaptadores) y entra por un puerto.
"""
import ast
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app"
NUCLEO = [RAIZ / "dominio", RAIZ / "servicios", RAIZ / "puertos.py", RAIZ / "errores.py"]
PROHIBIDOS = ("sqlalchemy", "fastapi", "app.modelos", "app.db", "app.adaptadores", "app.rutas")


def _archivos():
    for ruta in NUCLEO:
        yield from ([ruta] if ruta.is_file() else sorted(ruta.rglob("*.py")))


def test_nucleo_sin_infraestructura():
    malos = []
    for archivo in _archivos():
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            nombres = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres = [nodo.module] + [f"{nodo.module}.{a.name}" for a in nodo.names]
            for n in nombres:
                if n.startswith(PROHIBIDOS) or n in ("app.modelos", "app.db"):
                    malos.append(f"{archivo.relative_to(RAIZ.parent)}: {n}")
    assert not malos, "el núcleo importa infraestructura:\n" + "\n".join(malos)
