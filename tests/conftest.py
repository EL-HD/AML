"""
Configuración común de pruebas de Sovereign AML.

Reglas:
- Las pruebas no tocan PostgreSQL real: usan SQLite en memoria con un esquema
  "public" adjunto, de modo que los modelos (schema="public") funcionen sin cambios.
- Las variables de entorno sensibles se fijan a valores de prueba antes de importar
  la aplicación, porque auth_api valida su presencia al cargar.
- Las pruebas se escriben con unittest (compatibles con pytest) para poder
  ejecutarse con `python -m unittest discover tests` en entornos sin pytest.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SECRET_KEY", "clave-de-prueba-secret-key-0123456789abcdef")
os.environ.setdefault("SESSION_SIGN_KEY", "clave-de-prueba-session-sign-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_ISSUER", "sovereign-aml-test")
os.environ.setdefault("JWT_AUDIENCE", "sovereign-aml-app")
os.environ.setdefault("CACHE_ENCRYPTION_SALT", "sal-de-prueba")
