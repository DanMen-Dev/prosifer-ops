# Deploy demo · Hetzner

URL objetivo: **https://demo-prosifer.brecha-cero.com/**

La UI habla con `/api` en el mismo host. El nginx del contenedor `web` reenvía `/api` al contenedor `api`. Caddy solo publica el puerto web en HTTPS.

## 1. DNS

En el DNS de `brecha-cero.com`:

| Tipo | Nombre | Valor |
| --- | --- | --- |
| A | `demo-prosifer` | IP pública del VPS Hetzner |

Espera a que resuelva:

```bash
dig +short demo-prosifer.brecha-cero.com
```

## 2. En el VPS

```bash
# dependencias
sudo apt update
sudo apt install -y git docker.io docker-compose-v2 caddy
sudo usermod -aG docker $USER   # luego cierra sesión y vuelve a entrar

# código
sudo mkdir -p /opt/prosifer-ops
sudo chown $USER:$USER /opt/prosifer-ops
cd /opt/prosifer-ops
git clone https://github.com/DanMen-Dev/prosifer-ops.git .
mkdir -p datos

cp .env.example .env
nano .env
```

Contenido sugerido de `.env` (cambia las claves):

```env
POSTGRES_PASSWORD=pon-una-clave-larga-aqui
PROSIFER_API_KEY=otra-clave-larga-distinta
PROSIFER_PUERTO=8110
PROSIFER_PUERTO_WEB=8111
PROSIFER_CORS=https://demo-prosifer.brecha-cero.com
PROSIFER_SECRETO=otra-cadena-larga-de-sesion
```

```bash
docker compose up -d --build
curl -s http://127.0.0.1:8110/api/salud
curl -s http://127.0.0.1:8111/api/salud

docker compose exec api python -m app.demo sembrar
```

Usuario demo (también queda en el README):

- correo: `socio@demo.test`
- clave: `DemoProsifer1`

## 3. Caddy (HTTPS)

```bash
sudo cp /opt/prosifer-ops/deploy/Caddyfile /etc/caddy/Caddyfile
# Si ya tienes otros sitios en Caddy, pega solo el bloque demo-prosifer
# dentro de tu Caddyfile existente en lugar de sobrescribir.

sudo systemctl reload caddy
sudo systemctl status caddy
curl -I https://demo-prosifer.brecha-cero.com/
curl -s https://demo-prosifer.brecha-cero.com/api/salud
```

Abre el navegador: https://demo-prosifer.brecha-cero.com/

## 4. Actualizar la demo

```bash
cd /opt/prosifer-ops
git pull
docker compose up -d --build
docker compose exec api python -m app.demo sembrar
```

## 5. Resetear datos demo

```bash
cd /opt/prosifer-ops
docker compose down -v    # borra el volumen de Postgres
docker compose up -d --build
docker compose exec api python -m app.demo sembrar
```

## Firewall

Puertos públicos: **80** y **443** (Caddy).  
**No** abras 8110/8111 a internet (quedan en `127.0.0.1`).
