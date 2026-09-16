"""Genera .env local a partir de .env.example (no sobreescribe si ya existe).

DB_USER / DB_PASS quedan como placeholders: deben coincidir con la conexión
que ya usas en DBeaver/pgAdmin para tu Postgres local (no se inventan ni se
adivinan credenciales de una base de datos existente).
SECRET_KEY sí se genera de forma aleatoria y segura (uso exclusivo de JWT).
"""
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"

if env_path.exists():
    raise SystemExit(".env ya existe; no se sobreescribe.")

content = f"""# Generado por aml (scripts/generate_env.py) — variables de desarrollo LOCAL
# NUNCA subir este archivo a git (ya está en .gitignore)

# --- Base de datos PostgreSQL LOCAL (la misma que ves en DBeaver/pgAdmin) ---
# Ajusta estos 4 valores para que coincidan con tu conexión local a localhost:5432/AML
DB_USER=postgres
DB_PASS=CAMBIA_ESTO
DB_HOST=localhost
DB_PORT=5432
DB_NAME=AML

# --- Autenticación JWT (API) ---
SECRET_KEY={secrets.token_hex(32)}

# --- URL del API (Frontend Streamlit) ---
AUTH_API_URL=http://localhost:8000
"""
env_path.write_text(content, encoding="utf-8")
print(f".env generado en {env_path}")
print("IMPORTANTE: edita DB_USER/DB_PASS en .env con las credenciales reales de tu Postgres local antes de continuar.")
