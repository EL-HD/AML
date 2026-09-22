# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder: instala dependencias en un prefijo aislado
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# gcc es necesario solo en tiempo de compilación (psycopg2-binary, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instala dependencias de la app + supervisor en un prefijo separado
# para que Stage 2 solo copie lo necesario
# --only-binary :all: exige distribuciones ya compiladas (wheels) y evita que
# pip ejecute el setup.py de un paquete durante la construcción de la imagen
# (docker:S8541). Verificado: los 71 paquetes del árbol completo de
# dependencias publican wheel para linux x86_64 / CPython 3.11.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --only-binary :all: --prefix=/install \
        -r requirements.txt \
        supervisor

# ── Caddy (proxy inverso, T5): binario oficial verificado por checksum ───────
# Las sumas SHA-512 provienen de caddy_<versión>_checksums.txt publicado con la
# release oficial (https://github.com/caddyserver/caddy/releases). Para
# actualizar: cambiar CADDY_VERSION y las dos sumas, nada más.
ARG CADDY_VERSION=2.10.2
ARG CADDY_SHA512_AMD64=747df7ee74de188485157a383633a1a963fd9233b71fbb4a69ddcbcc589ce4e2cc82dacf5dbbe136cb51d17e14c59daeb5d9bc92487610b0f3b93680b2646546
ARG CADDY_SHA512_ARM64=6ce061a690312ab38367df3c5d5f89a2e4a263e7300d300d87356211bb81e79b15933e6d6203e03fbf26f15cc0311f264805f336147dbdd24938d84b57a4421c
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH="${TARGETARCH:-amd64}" \
    && case "$ARCH" in \
         amd64) SUMA="$CADDY_SHA512_AMD64" ;; \
         arm64) SUMA="$CADDY_SHA512_ARM64" ;; \
         *) echo "Arquitectura no soportada para Caddy: $ARCH" && exit 1 ;; \
       esac \
    && curl -fsSL --proto "=https" --tlsv1.2 --retry 3 -o /tmp/caddy.tar.gz \
        "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_${ARCH}.tar.gz" \
    && echo "${SUMA}  /tmp/caddy.tar.gz" | sha512sum -c - \
    && tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy \
    && chmod 0755 /usr/local/bin/caddy \
    && /usr/local/bin/caddy version


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime: imagen mínima y sin herramientas de compilación
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# OWASP: usuario sin privilegios (no root)
RUN groupadd --system --gid 1001 appgroup \
    && useradd --system --uid 1001 --gid appgroup \
        --no-create-home --shell /usr/sbin/nologin appuser

# Copiar paquetes Python instalados desde el builder
COPY --from=builder /install /usr/local
# Binario de Caddy verificado en el builder
COPY --from=builder /usr/local/bin/caddy /usr/local/bin/caddy

WORKDIR /app

# Copiar código fuente con ownership correcto
COPY --chown=appuser:appgroup . .

# /tmp es world-writable; aquí vivirán el caché de análisis,
# el socket de supervisord y los PID files
RUN mkdir -p /tmp/sovereign_aml_cache /tmp/caddy \
    && chown appuser:appgroup /tmp/sovereign_aml_cache /tmp/caddy

# ── Variables de entorno (valores seguros por defecto, sin secretos) ───────
# Las variables sensibles (SECRET_KEY, SESSION_SIGN_KEY, DATABASE_URL)
# DEBEN inyectarse desde Railway: NUNCA hardcodeadas aquí.
# PORT lo fija Railway; lo escucha Caddy. Streamlit (127.0.0.1:8501) y FastAPI
# (127.0.0.1:8000) son internos al contenedor.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    AUTH_API_URL=http://localhost:8000 \
    HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    MPLCONFIGDIR=/tmp/matplotlib \
    XDG_DATA_HOME=/tmp/caddy \
    XDG_CONFIG_HOME=/tmp/caddy

# Solo se expone el puerto del proxy (Caddy); Streamlit y FastAPI son internos
EXPOSE 8080

USER appuser

# Health check a través del proxy (mismo camino que usa Railway: $PORT)
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python3 -c \
        "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/_stcore/health' % os.environ.get('PORT', '8080'))" \
    || exit 1

CMD ["sh", "-c", "python scripts/db_migrate.py && exec supervisord -c /app/supervisord.conf"]
