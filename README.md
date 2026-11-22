# Prosifer Ops

**Manufacturing operations for steel coil inventory, slitting, sheet/profile production, and delivery notes.**

Showcase (public) of a system that replaced Excel+VBA workbooks with a live inventory: every movement updates stock in the same transaction—no “consolidar” step.

> This repository is a **sanitized portfolio build**. Client/company PII from production was removed or replaced with demo data. The private production repo stays private.

## Live demo

- URL: https://demo-prosifer.brecha-cero.com/
- Usuario: `socio@demo.test`
- Clave: `DemoProsifer1`

Datos ficticios (`python -m app.demo sembrar`). Deploy en Hetzner: ver [`deploy/DEPLOY-HETZNER.md`](deploy/DEPLOY-HETZNER.md).

---

## Problema que resuelve

En un patio de acero (bobinas, flejes, láminas, perfiles) el inventario vivía en libros Excel con VBA. Había que consolidar, los cortes no cuadraban con facilidad y las notas de entrega / órdenes de corte eran frágiles.

**Prosifer Ops** modela las reglas de negocio reales:

- Entrada de bobinas con código de producto (`BOBHP0901220`), rechazo de códigos repetidos y avisos de peso fuera de rango
- Orden de corte en **slitter** (hijos fleje, scrap, tolerancia 5 %, hoja a escala + etiquetas QR)
- Corte a **lámina** y **maquila de perfiles** con balance de peso real vs teórico
- **Notas de entrega**, liberaciones, correcciones y anulaciones con roles
- Conteos físicos de patio con flujo pendiente → ajuste
- Importador Excel con **prueba de paridad** contra el consolidado histórico
- Roles: socio / asistente / cliente (+ API key para integraciones / n8n)

---

## Stack

| Pieza | Tecnología |
| --- | --- |
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, ReportLab |
| Web | React 19, TypeScript, Vite, nginx |
| DB | PostgreSQL 16 |
| Ops | Docker Compose, GitHub Actions CI |

Arquitectura **hexagonal** (`dominio` → `servicios` → `puertos` → adaptadores SQL/PDF/memoria). Los tests de casos de uso corren en memoria sin Postgres.

```
api/app/
  dominio/      reglas puras (códigos, saldos, slitter, salidas…)
  servicios/    casos de uso
  puertos.py    contratos
  adaptadores/  sql/, pdf/, memoria.py
  rutas/        FastAPI
web/src/paginas/  inventario, cortes, salidas, portal cliente…
```

---

## Levantar en local

```bash
cp .env.example .env
# edita POSTGRES_PASSWORD y PROSIFER_API_KEY

docker compose up -d --build
curl -s http://127.0.0.1:8110/api/salud   # {"ok":true}

# primer usuario (pide la clave en consola)
docker compose exec api python -m app.usuarios crear \
  --correo socio@demo.test --nombre "Socio Demo" --rol socio

# datos de demostración (clientes y bobinas ficticios)
docker compose exec api python -m app.demo sembrar
```

- API docs: http://127.0.0.1:8110/api/docs  
- Web: http://127.0.0.1:8111  

Clave de API de ejemplo (la de `.env`): header `X-Api-Key`.

---

## Pruebas

```bash
cd api
pip install -r requirements-dev.txt
pytest -q
```

CI (`.github/workflows/ci.yml`) corre pytest con Postgres de servicio y `npm run build` del frontend.

---

## Qué hay / qué no hay en esta vitrina

| Incluido | No incluido (a propósito) |
| --- | --- |
| Código de API + web + tests | Dumps de Postgres / Excel reales |
| Seed demo con terceros ficticios | RIF, teléfonos y correos de clientes reales |
| Docker + CI | Secrets de producción / `.env` |
| Documentación para reclutadores | Módulos VBA originales (siguen en el flujo privado) |

Los Excel de importación van en `datos/` (gitignored). En producción se montan solo en el VPS.

---

## Cómo se construyó

1. Reglas de negocio sacadas del Excel/VBA y de la operación diaria  
2. Núcleo de dominio testeable sin base de datos  
3. Adaptadores SQL + PDF + importador  
4. UI por roles (planta + portal cliente)  
5. Deploy con Docker en VPS  

Siguiente en el roadmap privado: liberaciones por piezas / Losacero, portal de OT, reportes de almacenaje.

---

## Licencia / uso

Código publicado como portafolio. Marca y logo de demostración; no es un dump de la operación real.
