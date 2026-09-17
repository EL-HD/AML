"""
Utilidades de base de datos para pruebas. Reutiliza el motor de backend.database
(SQLite en memoria cuando DATABASE_URL=sqlite://, fijado en tests/conftest.py).
"""
from backend import models
from backend.database import SessionLocal, engine


def crear_engine_pruebas():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine


def crear_session_factory(_engine=None):
    return SessionLocal
