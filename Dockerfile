# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — builder: instala dependencias en un prefijo aislado
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
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
        -r requirements.txt \
        supervisor


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime: imagen mínima y sin herramientas de compilación
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# OWASP: usuario sin privilegios (no root)
RUN groupadd --system --gid 1001 appgroup \
    && useradd --system --uid 1001 --gid appgroup \
        --no-create-home --shell /usr/sbin/nologin appuser

# Copiar paquetes Python instalados desde el builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copiar código fuente con ownership correcto
COPY --chown=appuser:appgroup . .

# /tmp es world-writable; aquí vivirán el caché de análisis,
# el socket de supervisord y los PID files
RUN mkdir -p /tmp/sovereign_aml_cache \
    && chown appuser:appgroup /tmp/sovereign_aml_cache

# ── Variables de entorno (valores seguros por defecto, sin secretos) ───────
# Las variables sensibles (SECRET_KEY, SESSION_SIGN_KEY, DATABASE_URL)
# DEBEN inyectarse desde Railway — NUNCA hardcodeadas aquí.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8501 \
    AUTH_API_URL=http://localhost:8000 \
    HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    MPLCONFIGDIR=/tmp/matplotlib

# Solo se expone el puerto de Streamlit; FastAPI es interno (127.0.0.1:8000)
EXPOSE 8501

USER appuser

# Health check sobre el endpoint interno de Streamlit
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python3 -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" \
    || exit 1

CMD ["supervisord", "-c", "/app/supervisord.conf"]
