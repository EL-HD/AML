from sqlalchemy import Column, Integer, String, Date, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from .database import Base
import uuid
from datetime import datetime

class Licencia(Base):
    __tablename__ = "Licencias"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)
    user = Column("User", String(100), nullable=False)
    name = Column("name", String(100), nullable=False)
    mail = Column("mail", String(150), unique=True, nullable=False, index=True)
    licence_id = Column("licenceid", UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    fecha_compra = Column("fechacompralicencia", Date, nullable=False)
    dias_vigencia = Column("diasvigencia", Integer, nullable=False)
    fecha_expiracion = Column("fechaexpiracion", Date, nullable=False)
    empresa = Column("empresa", String(150), nullable=False)
    password_hash = Column("passwordhash", String, nullable=False)

class BitacoraSesions(Base):
    __tablename__ = "BitacoraSesions"
    __table_args__ = {"schema": "public"}

    sessionid = Column("sessionid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    last_activity = Column("last_activity", DateTime, nullable=False, default=datetime.now)
    licenciaid = Column("licenciaid", UUID(as_uuid=True), nullable=False)
