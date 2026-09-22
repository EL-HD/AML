"""
Runner de migraciones — idempotente.
1) Crea las tablas ORM (backend/models.py) si no existen.
2) Aplica migrations/*.sql pendientes, en orden, registrando cada archivo
   aplicado en public.schema_migrations para no repetirlo.

Uso: python scripts/db_migrate.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from backend import models  # noqa: E402
from backend.database import engine  # noqa: E402

MIGRATIONS_DIR = ROOT / "migrations"


def ensure_tracking_table(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS public.schema_migrations (
            filename   TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


def applied_migrations(conn):
    rows = conn.execute(text("SELECT filename FROM public.schema_migrations"))
    return {row[0] for row in rows}


def ejecutar_sql_literal(conn, sql: str) -> None:
    """Ejecuta SQL de migración tal cual, sin sustitución de parámetros.

    Se usa el cursor DBAPI directamente y se invoca execute(sql) con un único
    argumento. Motivos explícitos:

    1) SQLAlchemy.exec_driver_sql(sql) entrega a psycopg2 un diccionario vacío
       como parámetros. Al detectar "%" en el SQL, psycopg2 intenta interpolar
       y rechaza ese tipo con:
           TypeError: sqlalchemy.cyextension.immutabledict.immutabledict
                      is not a sequence
       Las migraciones contienen "%" legítimo como marcador de PL/pgSQL en
       RAISE EXCEPTION (004, 005, 006), de modo que el fallo es inevitable por
       esa vía.
    2) Con execute(sql) de un solo argumento, psycopg2 no realiza ninguna
       interpolación: ni "%" ni ":algo" se interpretan como parámetro.

    El cursor pertenece a la conexión de la transacción abierta por
    engine.begin(), por lo que el commit y el rollback siguen gobernados por
    ese bloque: no se introduce una transacción paralela.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("ejecutar_sql_literal recibió SQL vacío o de tipo inválido.")
    cursor = conn.connection.cursor()
    try:
        cursor.execute(sql)
    finally:
        cursor.close()


def apply_sql_migrations():
    with engine.begin() as conn:
        ensure_tracking_table(conn)
        done = applied_migrations(conn)
        pending = sorted(f for f in MIGRATIONS_DIR.glob("*.sql") if f.name not in done)
        if not pending:
            print("-> Sin migraciones SQL pendientes.")
            return
        for f in pending:
            print(f"-> Aplicando migración: {f.name}", flush=True)
            ejecutar_sql_literal(conn, f.read_text(encoding="utf-8"))
            conn.execute(
                text("INSERT INTO public.schema_migrations (filename) VALUES (:f)"),
                {"f": f.name},
            )


def _usuarios_bootstrap_admin() -> list:
    """Lee BOOTSTRAP_ADMIN_USERS (lista separada por comas) y valida cada nombre."""
    crudo = os.getenv("BOOTSTRAP_ADMIN_USERS", "")
    usuarios = [u.strip() for u in crudo.split(",") if u.strip()]
    for usuario in usuarios:
        if len(usuario) > 100:
            raise ValueError("BOOTSTRAP_ADMIN_USERS contiene un usuario de más de 100 caracteres.")
    return usuarios


def bootstrap_admins():
    """Asigna rol admin a los usuarios indicados. Idempotente y explícito."""
    usuarios = _usuarios_bootstrap_admin()
    if not usuarios:
        print("-> BOOTSTRAP_ADMIN_USERS vacío: no se asigna rol admin automáticamente.")
        return
    with engine.begin() as conn:
        for usuario in usuarios:
            resultado = conn.execute(
                text('UPDATE public."Licencias" SET rol = :rol WHERE "User" = :u AND rol <> :rol'),
                {"rol": "admin", "u": usuario},
            )
            print(f"-> Rol admin para '{usuario}': {resultado.rowcount} fila(s) actualizada(s).")


def main():
    print("== Tablas ORM (backend/models.py) ==")
    models.Base.metadata.create_all(bind=engine)
    print("== Migraciones SQL (migrations/*.sql) ==")
    apply_sql_migrations()
    print("== Bootstrap de administradores ==")
    bootstrap_admins()
    print("Migraciones al día.")


if __name__ == "__main__":
    main()
