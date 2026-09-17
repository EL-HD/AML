#!/usr/bin/env bash
# ============================================================================
# railway_pull.sh — descarga un dump de la Postgres de producción (Railway)
# hacia backups/, usando un proxy TCP temporal que ya fue habilitado.
#
# Requiere UNA de estas dos formas de obtener la URL de conexión pública:
#   A) export RAILWAY_DATABASE_URL='postgresql://usuario:password@host:puerto/railway'
#      (cópiala del dashboard de Railway: servicio Postgres → Variables → DATABASE_PUBLIC_URL)
#   B) Railway CLI instalada y logueada:  brew install railway && railway login && railway link
# ============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

HOST="reseau.proxy.rlwy.net"
PORT="29108"
mkdir -p backups
OUT="backups/railway_$(date +%Y%m%d_%H%M%S).dump"

if [ -f .env.railway ]; then
    set -a
    # shellcheck disable=SC1091
    source .env.railway
    set +a
fi

URL="${RAILWAY_DATABASE_URL:-}"

if [ -z "$URL" ] && command -v railway >/dev/null 2>&1; then
    echo "[railway-pull] Consultando DATABASE_PUBLIC_URL vía Railway CLI..."
    URL="$(railway variables --service Postgres --environment production --kv 2>/dev/null \
        | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2- || true)"
fi

if [ -z "$URL" ]; then
    cat >&2 <<MSG
No se pudo obtener la URL de conexión.

Opción A: exporta la variable y vuelve a correr este script:
  export RAILWAY_DATABASE_URL='postgresql://usuario:password@${HOST}:${PORT}/railway'
  (usuario/password/nombre de la base: dashboard de Railway → Postgres → Variables)

Opción B:
  brew install railway
  railway login
  railway link            # selecciona el proyecto "Sovereign AML-V3"
  ./scripts/railway_pull.sh
MSG
    exit 1
fi

# El servidor de Railway es Postgres 18; pg_dump exige version >= la del servidor.
find_pg_dump_18() {
    for candidate in \
        "$(command -v pg_dump18 2>/dev/null || true)" \
        /opt/homebrew/opt/postgresql@18/bin/pg_dump \
        /usr/local/opt/postgresql@18/bin/pg_dump \
        /Library/PostgreSQL/18/bin/pg_dump
    do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PG_DUMP_BIN="$(find_pg_dump_18)" || {
    cat >&2 <<MSG
El servidor de Railway corre PostgreSQL 18 y tu pg_dump local es 16.x (incompatible:
pg_dump no puede ser más viejo que el servidor). Esto NO afecta tu Postgres local,
solo necesitas el cliente 18 instalado aparte:

  brew install postgresql@18

Luego vuelve a correr: ./scripts/railway_pull.sh
MSG
    exit 1
}

echo "[railway-pull] Descargando dump con $PG_DUMP_BIN (proxy temporal ${HOST}:${PORT})..."
"$PG_DUMP_BIN" "$URL" -F c --no-owner --no-privileges -f "$OUT"
echo "[railway-pull] Dump guardado en $OUT"
echo "[railway-pull] IMPORTANTE: pide que se cierre el proxy TCP público del servicio Postgres"
echo "                en Railway (Settings → Networking → Remove) — quedó abierto solo para esta descarga."
