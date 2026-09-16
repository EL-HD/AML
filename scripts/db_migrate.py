"""
Runner de migraciones — idempotente.
1) Crea las tablas ORM (backend/models.py) si no existen.
2) Aplica migrations/*.sql pendientes, en orden, registrando cada archivo
   aplicado en public.schema_migrations para no repetirlo.

Uso: python scripts/db_migrate.py
"""
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


def apply_sql_migrations():
    with engine.begin() as conn:
        ensure_tracking_table(conn)
        done = applied_migrations(conn)
        pending = sorted(f for f in MIGRATIONS_DIR.glob("*.sql") if f.name not in done)
        if not pending:
            print("-> Sin migraciones SQL pendientes.")
            return
        for f in pending:
            print(f"-> Aplicando migración: {f.name}")
            conn.execute(text(f.read_text(encoding="utf-8")))
            conn.execute(
                text("INSERT INTO public.schema_migrations (filename) VALUES (:f)"),
                {"f": f.name},
            )


def main():
    print("== Tablas ORM (backend/models.py) ==")
    models.Base.metadata.create_all(bind=engine)
    print("== Migraciones SQL (migrations/*.sql) ==")
    apply_sql_migrations()
    print("Migraciones al día.")


if __name__ == "__main__":
    main()
