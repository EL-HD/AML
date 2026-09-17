"""
Utilidades de base de datos para pruebas: motor SQLite en memoria con el
esquema "public" adjunto (los modelos usan schema="public").
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models


def crear_engine_pruebas():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _adjuntar_public(dbapi_conn, _record):
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS public")

    models.Base.metadata.create_all(bind=engine)
    return engine


def crear_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
