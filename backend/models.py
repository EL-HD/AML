from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, text
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


class BitacoraAuditoria(Base):
    """Auditoría de accesos a módulos sensibles — Art. 19 Ley 6593."""
    __tablename__ = "BitacoraAuditoria"
    __table_args__ = {"schema": "public"}

    id              = Column("id",              UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid      = Column("licenciaid",      UUID(as_uuid=True), nullable=False)
    username        = Column("username",        String(100),        nullable=False)
    timestamp       = Column("timestamp",       DateTime,           nullable=False, default=datetime.now)
    modulo_accedido = Column("modulo_accedido", String(100),        nullable=False)
    accion          = Column("accion",          String(100),        nullable=False, default="VISUALIZACION")


# ═══════════════════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE RIESGO INSTITUCIONAL DE LD/FT
# Base legal: Art. 8-11 Decreto 15-2026 (Guatemala) — enfoque basado en riesgo
# Modelo: GAFILAT / IVE (GERILAFT App) — Identificación, Medición, Control, Monitoreo
# Todas las tablas se segmentan por licenciaid (multi-tenant: una PO por licencia).
# ═══════════════════════════════════════════════════════════════════════════

class RiesgoSegmento(Base):
    """Etapa de Identificación — Factor -> Segmento -> Variable."""
    __tablename__ = "RiesgoSegmentos"
    __table_args__ = {"schema": "public"}

    id         = Column("id",         UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid = Column("licenciaid", UUID(as_uuid=True), nullable=False, index=True)
    factor     = Column("factor",     String(60),  nullable=False)
    segmento   = Column("segmento",   String(120), nullable=False)
    variable   = Column("variable",   String(120), nullable=False)
    creado_por = Column("creado_por", String(100), nullable=False)
    creado_en  = Column("creado_en",  DateTime,    nullable=False, default=datetime.now)


class RiesgoEvento(Base):
    """Etapa de Identificación/Medición — evento de riesgo con probabilidad/impacto."""
    __tablename__ = "RiesgoEventos"
    __table_args__ = {"schema": "public"}

    id                  = Column("id",                  UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid          = Column("licenciaid",          UUID(as_uuid=True), nullable=False, index=True)
    codigo              = Column("codigo",              String(20),  nullable=False)
    nombre              = Column("nombre",              String(200), nullable=False)
    descripcion         = Column("descripcion",         String(1000), nullable=True)
    factor              = Column("factor",              String(60),  nullable=False)
    segmento_id         = Column("segmento_id",         UUID(as_uuid=True), nullable=True, index=True)
    probabilidad        = Column("probabilidad",        Integer, nullable=False)
    riesgo_operacional  = Column("riesgo_operacional",  Integer, nullable=False)
    riesgo_legal        = Column("riesgo_legal",        Integer, nullable=False)
    riesgo_reputacional = Column("riesgo_reputacional", Integer, nullable=False)
    riesgo_contagio     = Column("riesgo_contagio",     Integer, nullable=False)
    impacto             = Column("impacto",             Integer, nullable=False)
    nivel_inherente     = Column("nivel_inherente",     Integer, nullable=False)
    nivel_residual      = Column("nivel_residual",      Integer, nullable=False)
    requiere_plan_accion = Column("requiere_plan_accion", Boolean, nullable=False, default=False)
    creado_por          = Column("creado_por",          String(100), nullable=False)
    creado_en           = Column("creado_en",           DateTime, nullable=False, default=datetime.now)
    actualizado_en      = Column("actualizado_en",      DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class RiesgoControl(Base):
    """Etapa de Control — mitigador de riesgo y su ponderación (0-100)."""
    __tablename__ = "RiesgoControles"
    __table_args__ = {"schema": "public"}

    id                     = Column("id",                     UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid             = Column("licenciaid",             UUID(as_uuid=True), nullable=False, index=True)
    nombre                 = Column("nombre",                 String(150),  nullable=False)
    descripcion            = Column("descripcion",            String(1000), nullable=False)
    documentado            = Column("documentado",            Boolean, nullable=False, default=False)
    tipo_control           = Column("tipo_control",           String(20), nullable=False)
    ejecucion              = Column("ejecucion",              String(20), nullable=False)
    nivel_cumplimiento     = Column("nivel_cumplimiento",     String(20), nullable=False)
    nivel_efectividad      = Column("nivel_efectividad",      String(20), nullable=False)
    evaluado               = Column("evaluado",               Boolean, nullable=False, default=False)
    responsable_evaluacion = Column("responsable_evaluacion", String(150), nullable=True)
    fecha_evaluacion       = Column("fecha_evaluacion",       Date, nullable=True)
    ponderacion            = Column("ponderacion",            Integer, nullable=False)
    nivel_ponderacion      = Column("nivel_ponderacion",      Integer, nullable=False)
    creado_por             = Column("creado_por",             String(100), nullable=False)
    creado_en              = Column("creado_en",              DateTime, nullable=False, default=datetime.now)
    actualizado_en         = Column("actualizado_en",         DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class RiesgoEventoControl(Base):
    """Vínculo N:M entre eventos de riesgo y controles mitigadores."""
    __tablename__ = "RiesgoEventoControl"
    __table_args__ = {"schema": "public"}

    id         = Column("id",         UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid = Column("licenciaid", UUID(as_uuid=True), nullable=False, index=True)
    evento_id  = Column("evento_id",  UUID(as_uuid=True), nullable=False, index=True)
    control_id = Column("control_id", UUID(as_uuid=True), nullable=False, index=True)
    creado_en  = Column("creado_en",  DateTime, nullable=False, default=datetime.now)


class RiesgoPlanAccion(Base):
    """Etapa de Monitoreo — plan de acción para riesgo residual Medio Alto/Alto."""
    __tablename__ = "RiesgoPlanesAccion"
    __table_args__ = {"schema": "public"}

    id                = Column("id",                UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid        = Column("licenciaid",        UUID(as_uuid=True), nullable=False, index=True)
    evento_id         = Column("evento_id",         UUID(as_uuid=True), nullable=False, index=True)
    medida_propuesta  = Column("medida_propuesta",  String(1000), nullable=False)
    responsable       = Column("responsable",       String(150),  nullable=False)
    fecha_inicio      = Column("fecha_inicio",      Date, nullable=False)
    fecha_fin         = Column("fecha_fin",         Date, nullable=False)
    porcentaje_avance = Column("porcentaje_avance", Integer, nullable=False, default=0)
    creado_por        = Column("creado_por",        String(100), nullable=False)
    creado_en         = Column("creado_en",         DateTime, nullable=False, default=datetime.now)
    actualizado_en    = Column("actualizado_en",    DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
