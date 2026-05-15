"""
Script de seed para produccion. Ejecutar una sola vez via Render Jobs.
Crea los usuarios iniciales directamente en la base de datos.
"""
import os, uuid, sys
import bcrypt
from datetime import date, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL no esta configurada")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Licencia(Base):
    __tablename__ = "Licencias"
    __table_args__ = {"schema": "public"}
    id = Column(Integer, primary_key=True)
    user = Column("User", String(100), nullable=False)
    name = Column("name", String(100), nullable=False)
    mail = Column("mail", String(150), unique=True, nullable=False)
    licence_id = Column("licenceid", PGUUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    fecha_compra = Column("fechacompralicencia", Date, nullable=False)
    dias_vigencia = Column("diasvigencia", Integer, nullable=False)
    fecha_expiracion = Column("fechaexpiracion", Date, nullable=False)
    empresa = Column("empresa", String(150), nullable=False)
    password_hash = Column("passwordhash", String, nullable=False)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()

USUARIOS = [
    {
        "user": "analista_082",
        "password": "SovereignAML2025!",
        "name": "Hobed Diaz",
        "mail": "hdiazavila27@gmail.com",
        "empresa": "SOVEREIGN Intelligence",
    },
]

for u in USUARIOS:
    existing = db.query(Licencia).filter(Licencia.mail == u["mail"]).first()
    if existing:
        print(f"SKIP (ya existe): {u['user']} / {u['mail']}")
        continue

    hashed = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()
    today = date.today()
    licencia = Licencia(
        user=u["user"],
        name=u["name"],
        mail=u["mail"],
        licence_id=uuid.uuid4(),
        fecha_compra=today,
        dias_vigencia=365,
        fecha_expiracion=today + timedelta(days=365),
        empresa=u["empresa"],
        password_hash=hashed,
    )
    db.add(licencia)
    db.commit()
    print(f"OK creado: {u['user']} / {u['mail']} / pass: {u['password']}")

db.close()
print("Seed completado.")
