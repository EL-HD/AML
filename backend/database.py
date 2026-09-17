import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# A1 fix: sin contraseñas hardcodeadas: requiere env vars o DATABASE_URL completa
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "AML")

DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")


def _crear_engine(url: str):
    """
    PostgreSQL es el motor de producción. SQLite solo se admite para pruebas
    automatizadas: se adjunta un esquema "public" para que los modelos
    (schema="public") funcionen sin cambios.
    """
    if url.startswith("sqlite"):
        engine_local = create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(engine_local, "connect")
        def _adjuntar_public(dbapi_conn, _record):
            dbapi_conn.execute("ATTACH DATABASE ':memory:' AS public")

        return engine_local
    return create_engine(url, pool_pre_ping=True)


engine = _crear_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
