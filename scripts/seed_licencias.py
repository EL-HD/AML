"""
seed_licencias.py: Crea o restablece licencias (usuarios) base del sistema.

Uso: se ejecuta una sola vez como preDeployCommand en Railway (o manualmente
con `python -m scripts.seed_licencias` desde la raíz del repo, con las
variables de entorno correspondientes ya cargadas).

Seguridad (OWASP A02 - Cryptographic Failures / A07 - Auth Failures):
- Ninguna contraseña se hardcodea en este archivo ni se registra en logs.
  Cada usuario a crear/restablecer lee su contraseña desde una variable de
  entorno (convención: SEED_<USERNAME_EN_MAYUSCULAS>_PASSWORD).
- El hash se genera con bcrypt.gensalt() (backend.crud.get_password_hash),
  el mismo mecanismo que usa el resto del sistema: sin duplicar lógica.
- Operación idempotente: si la licencia ya existe (por mail, columna única),
  se actualiza en vez de duplicarse; si no existe, se crea.
- Falla explícitamente (exit code 1) si falta una variable de entorno
  requerida, en vez de omitir el usuario silenciosamente.
"""
import os
import sys
import uuid
from datetime import date, timedelta

from backend import crud, schemas
from backend.database import SessionLocal

# Metadata no sensible de cada licencia a garantizar. La contraseña de cada
# una se toma de la variable de entorno SEED_<USER>_PASSWORD (no de aquí).
LICENCIAS_BASE = [
    {
        "user": "admin",
        "name": "Administrador",
        "mail": "hdiazavila27@gmail.com",
        "empresa": "Sovereign AML",
        "dias_vigencia": 3650,  # ~10 años
    },
    {
        "user": "invitado",
        "name": "Usuario Invitado",
        "mail": "invitado@sovereign-aml.com",
        "empresa": "Sovereign AML - Demo",
        "dias_vigencia": 365,  # 1 año
    },
]


def _password_env_var(username: str) -> str:
    return f"SEED_{username.upper()}_PASSWORD"


def _leer_password(username: str) -> str:
    env_var = _password_env_var(username)
    password = os.environ.get(env_var)
    if not password:
        raise RuntimeError(
            f"Falta la variable de entorno {env_var}. "
            f"Configúrela antes de ejecutar este script."
        )
    return password


def upsert_licencia(db, config: dict) -> str:
    """Crea la licencia si no existe (por mail, columna única) o restablece
    su contraseña y vigencia si ya existe. Devuelve 'creada' o 'actualizada'.
    """
    password = _leer_password(config["user"])
    hoy = date.today()
    fecha_expiracion = hoy + timedelta(days=config["dias_vigencia"])

    existente = crud.get_licencia_by_mail(db, mail=config["mail"])
    if existente:
        existente.user = config["user"]
        existente.name = config["name"]
        existente.empresa = config["empresa"]
        existente.dias_vigencia = config["dias_vigencia"]
        existente.fecha_compra = hoy
        existente.fecha_expiracion = fecha_expiracion
        existente.password_hash = crud.get_password_hash(password)
        db.commit()
        return "actualizada"

    nueva = schemas.LicenciaCreate(
        user=config["user"],
        name=config["name"],
        mail=config["mail"],
        dias_vigencia=config["dias_vigencia"],
        empresa=config["empresa"],
        password=password,
        fecha_compra=hoy,
        fecha_expiracion=fecha_expiracion,
        licence_id=uuid.uuid4(),
    )
    crud.create_licencia(db, licencia=nueva)
    return "creada"


def main() -> int:
    db = SessionLocal()
    try:
        for config in LICENCIAS_BASE:
            try:
                resultado = upsert_licencia(db, config)
                print(f"[seed_licencias] Licencia '{config['user']}' {resultado} correctamente.")
            except RuntimeError as e:
                print(f"[seed_licencias] ERROR con '{config['user']}': {e}", file=sys.stderr)
                return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
