#!/usr/bin/env bash
# Prepara la vitrina pública en tu Ubuntu y la sube a prosifer-ops.
# Uso:
#   bash preparar-vitrina.sh /ruta/a/prosifer-app
set -euo pipefail

SRC="${1:-}"
if [[ -z "$SRC" || ! -d "$SRC" ]]; then
  echo "Uso: bash preparar-vitrina.sh /ruta/a/prosifer-app"
  exit 1
fi

WORK="$HOME/prosifer-ops-build"
PUBLIC_REPO="https://github.com/DanMen-Dev/prosifer-ops.git"

rm -rf "$WORK"
mkdir -p "$WORK"
# copia el código sin .git / basura local
rsync -a --exclude '.git' --exclude '.env' --exclude 'datos' --exclude 'node_modules' \
  --exclude '__pycache__' --exclude '.venv' --exclude 'dist' --exclude '*.xlsx' --exclude '*.xlsm' \
  "$SRC"/ "$WORK"/

cd "$WORK"

python3 - <<'PY'
from pathlib import Path
import re

root = Path('.')
replacements = [
    ("Hierros y Materiales del Sur, C.A.", "Aceros del Valle, C.A."),
    ("Hierros y Materiales del Sur", "Aceros del Valle"),
    ("cliente@hyms", "cliente@acerosvalle"),
    ("compras@hyms.com", "compras@acerosvalle.test"),
    ("no de Hierros", "no de Aceros"),
    ('startswith("Hierros")', 'startswith("Aceros")'),
    ("Materiales Sidelven C.A.", "Laminados Norte, C.A."),
    ("Metalurgica La Triunfadora, C.A. ", "Metalurgica Aurora, C.A. "),
    ("Metalurgica La Triunfadora, C.A.", "Metalurgica Aurora, C.A."),
    ("Ventas@Triunfadora.com", "ventas@aurora-demo.test"),
    ("ventas@triunfadora.com", "ventas@aurora-demo.test"),
    ("Sector Bajos de Guataparo, Tocuyito, Carabobo", "Zona Industrial Demo Norte"),
    ("Tocuyito", "Ciudad Demo"),
    ("Inversiones J.N.G. C.A.", "Inversiones Delta, C.A."),
    ("Inversiones JNG, C.A.", "Inversiones DELTA, C.A."),
    ("Leonardo León", "Carlos Rivera"),
    ("Leonardo Leon", "Carlos Rivera"),
    ("Construganga, C.A.", "Constructora Horizonte, C.A."),
    ("Suministros Metalurgicos Valencia, C.A.", "Suministros Metalicos Centro, C.A."),
    ("Sumametales, C.A.", "Metales Unidos, C.A."),
    ("Induferca, C.A", "Industrias Ferreas, C.A"),
    ("J-29762192-0", "J-10000001-0"),
    ("j-29762192-0", "j-10000001-0"),
    ("J-29367916-8", "J-10000002-8"),
    ("J-40982592-2", "J-10000003-2"),
    ("J 40982592 2", "J 10000003 2"),
    ("J-410883723", "J-10000004-9"),
    ("0414-3477462", "0414-0000001"),
    ("0414-5247336", "0414-0000002"),
    ('""""Hierros y Materiales del Sur, C.A." y "Hierros y Materiales del Sur" son el mismo tercero."""',
     '""""Aceros del Valle, C.A." y "Aceros del Valle" son el mismo tercero."""'),
    ("RIF_PROSIFER = \"J-29615614-0\"", "RIF_PROSIFER = \"J-00000000-0\""),
    ("DIRECCION_FISCAL = \"Calle San José, Galpón Nro. 92-30, El Socorro, Valencia, Edo. Carabobo\"",
     "DIRECCION_FISCAL = \"Av. Industrial Demo 100, Zona Franca, Ciudad Demo\""),
    ("PLANTA = \"PLANTA: Sector Ind. El Socorro, Calle San José, Galpón N° 92-30. Valencia, Carabobo\"",
     "PLANTA = \"PLANTA: Parque Industrial Demo, Calle 1, Galpón N° 10. Ciudad Demo\""),
    ("CONTACTO = \"Teléfonos: 0416-644.72.00 / 0414-421.89.03 · Email: ventasprosifer@gmail.com\"",
     "CONTACTO = \"Teléfonos: 0000-000.00.00 · Email: demo@prosifer-ops.test\""),
    ("Registrada en app.prosifer.com por", "Registrada en Prosifer Ops por"),
    ('assert ce.clave_rif("j-29.367.916-8") == "J293679168"',
     'assert ce.clave_rif("j-10.000.002-8") == "J100000028"'),
]
exts = {'.py', '.ts', '.tsx', '.md', '.yml', '.yaml', '.txt', '.ini', '.json', '.css', '.html', '.example', '.mako'}
skip = {'.git', 'node_modules', '__pycache__', '.venv', 'dist', 'datos'}
n = 0
for path in root.rglob('*'):
    if not path.is_file() or any(p in skip for p in path.parts):
        continue
    if path.suffix.lower() not in exts and path.name not in {'.env.example', '.gitignore'}:
        continue
    text = path.read_text(encoding='utf-8')
    orig = text
    for a, b in replacements:
        text = text.replace(a, b)
    if text != orig:
        path.write_text(text, encoding='utf-8')
        n += 1
print(f"Sanitizados {n} archivos")
PY

# repo público
if [[ ! -d "$HOME/prosifer-ops/.git" ]]; then
  git clone "$PUBLIC_REPO" "$HOME/prosifer-ops"
fi

rsync -a --delete --exclude '.git' "$WORK"/ "$HOME/prosifer-ops"/
cd "$HOME/prosifer-ops"
git add .
git status
echo
echo "Revisa el status. Si se ve bien:"
echo "  cd ~/prosifer-ops"
echo "  git commit -m 'Initial public showcase: Prosifer Ops (sanitized)'"
echo "  git push -u origin main"
