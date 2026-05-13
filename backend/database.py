import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Lee la variable DATABASE_URL del entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Si no existe (ej. en local), usa un valor por defecto
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:h_y%2B%2CcRs5eSAG2z@db.sbeipaftiyfvhxnixrxe.supabase.co:5432/postgres"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
