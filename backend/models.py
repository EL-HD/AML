from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Float, text
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, event
from sqlalchemy import Uuid as UUID  # tipo genérico: UUID nativo en PostgreSQL, CHAR(32) en SQLite (pruebas)
from .database import Base
import uuid
from datetime import datetime, timezone


def ahora_utc() -> datetime:
    """Marca de tiempo con zona horaria UTC para toda bitácora (trazabilidad forense)."""
    return datetime.now(timezone.utc)

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
    rol = Column("rol", String(20), nullable=False, default="analista", server_default="analista")

class BitacoraSesions(Base):
    __tablename__ = "BitacoraSesions"
    __table_args__ = {"schema": "public"}

    sessionid = Column("sessionid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    last_activity = Column("last_activity", DateTime, nullable=False, default=ahora_utc)
    licenciaid = Column("licenciaid", UUID(as_uuid=True), nullable=False)


class BitacoraAuditoria(Base):
    """Auditoría de accesos a módulos sensibles: Art. 19 Ley 6593."""
    __tablename__ = "BitacoraAuditoria"
    __table_args__ = {"schema": "public"}

    id              = Column("id",              UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid      = Column("licenciaid",      UUID(as_uuid=True), nullable=False)
    username        = Column("username",        String(100),        nullable=False)
    timestamp       = Column("timestamp",       DateTime,           nullable=False, default=ahora_utc)
    modulo_accedido = Column("modulo_accedido", String(100),        nullable=False)
    accion          = Column("accion",          String(100),        nullable=False, default="VISUALIZACION")


# ═══════════════════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE RIESGO INSTITUCIONAL DE LD/FT
# Base legal: Art. 8-11 Decreto 15-2026 (Guatemala): enfoque basado en riesgo
# Modelo: GAFILAT / IVE (GERILAFT App): Identificación, Medición, Control, Monitoreo
# Todas las tablas se segmentan por licenciaid (multi-tenant: una PO por licencia).
# ═══════════════════════════════════════════════════════════════════════════

class RiesgoSegmento(Base):
    """Etapa de Identificación: Factor -> Segmento -> Variable."""
    __tablename__ = "RiesgoSegmentos"
    __table_args__ = {"schema": "public"}

    id         = Column("id",         UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid = Column("licenciaid", UUID(as_uuid=True), nullable=False, index=True)
    factor     = Column("factor",     String(60),  nullable=False)
    segmento   = Column("segmento",   String(120), nullable=False)
    variable   = Column("variable",   String(120), nullable=False)
    creado_por = Column("creado_por", String(100), nullable=False)
    creado_en  = Column("creado_en",  DateTime,    nullable=False, default=ahora_utc)


class RiesgoEvento(Base):
    """Etapa de Identificación/Medición: evento de riesgo con probabilidad/impacto."""
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
    creado_en           = Column("creado_en",           DateTime, nullable=False, default=ahora_utc)
    actualizado_en      = Column("actualizado_en",      DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)


class RiesgoControl(Base):
    """Etapa de Control: mitigador de riesgo y su ponderación (0-100)."""
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
    creado_en              = Column("creado_en",              DateTime, nullable=False, default=ahora_utc)
    actualizado_en         = Column("actualizado_en",         DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)


class RiesgoEventoControl(Base):
    """Vínculo N:M entre eventos de riesgo y controles mitigadores."""
    __tablename__ = "RiesgoEventoControl"
    __table_args__ = {"schema": "public"}

    id         = Column("id",         UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid = Column("licenciaid", UUID(as_uuid=True), nullable=False, index=True)
    evento_id  = Column("evento_id",  UUID(as_uuid=True), nullable=False, index=True)
    control_id = Column("control_id", UUID(as_uuid=True), nullable=False, index=True)
    creado_en  = Column("creado_en",  DateTime, nullable=False, default=ahora_utc)


class RiesgoPlanAccion(Base):
    """Etapa de Monitoreo: plan de acción para riesgo residual Medio Alto/Alto."""
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
    creado_en         = Column("creado_en",         DateTime, nullable=False, default=ahora_utc)
    actualizado_en    = Column("actualizado_en",    DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)


# ═══════════════════════════════════════════════════════════════════════════
# CATÁLOGOS GLOBALES: REPORTES REGULATORIOS IVE (RTS/RTE)
# Base legal: normativa IVE vigente para el RTS, Art. 30-31 Ley 6593.
# Tablas de referencia compartidas por TODAS las licencias (sin licenciaid):
# el código oficial es la clave primaria, son de solo lectura para las PO y
# solo se actualizan cuando la IVE publica un catálogo nuevo o revisado.
# ═══════════════════════════════════════════════════════════════════════════

class CatalogoActivoMixin:
    """
    Columna compartida por todos los catálogos globales del RTS: permite
    inactivar una entrada (p. ej. una moneda o país retirado del catálogo
    oficial) sin eliminarla, preservando la integridad referencial con
    datos históricos que ya la usaron. Se reutiliza vía mixin para no
    repetir la misma columna en las 10 tablas.
    """
    activo = Column("activo", Boolean, nullable=False, default=True, server_default=text("true"))


class CatDepartamento(CatalogoActivoMixin, Base):
    """Departamentos de Guatemala (catálogo oficial IVE)."""
    __tablename__ = "CatDepartamentos"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(2), primary_key=True)
    nombre = Column("nombre", String(100), nullable=False)


class CatMunicipio(CatalogoActivoMixin, Base):
    """Municipios de Guatemala, vinculados a su departamento (catálogo oficial IVE)."""
    __tablename__ = "CatMunicipios"
    __table_args__ = {"schema": "public"}

    codigo               = Column("codigo",               String(4), primary_key=True)
    nombre               = Column("nombre",               String(100), nullable=False)
    departamento_codigo  = Column("departamento_codigo",  String(2), nullable=False, index=True)


class CatPais(CatalogoActivoMixin, Base):
    """Catálogo de países (catálogo oficial IVE)."""
    __tablename__ = "CatPaises"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(2), primary_key=True)
    nombre = Column("nombre", String(150), nullable=False)


class CatMoneda(CatalogoActivoMixin, Base):
    """Catálogo de monedas (catálogo oficial IVE)."""
    __tablename__ = "CatMonedas"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(3), primary_key=True)
    nombre = Column("nombre", String(100), nullable=False)


class CatTipoCanal(CatalogoActivoMixin, Base):
    """Tipo de canal transaccional: Módulo 4 del RTS."""
    __tablename__ = "CatTipoCanal"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(3), primary_key=True)
    nombre = Column("nombre", String(100), nullable=False)


class CatTipoInstrumento(CatalogoActivoMixin, Base):
    """Tipo de instrumento de integración: Módulo 4 del RTS."""
    __tablename__ = "CatTipoInstrumento"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(3), primary_key=True)
    nombre = Column("nombre", String(100), nullable=False)


class CatTipoProductoOficial(CatalogoActivoMixin, Base):
    """Tipo de producto o servicio según nomenclatura oficial IVE: Módulo 2 del RTS."""
    __tablename__ = "CatTipoProductoOficial"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(3), primary_key=True)
    nombre = Column("nombre", String(100), nullable=False)


class CatTipoIdentificacion(CatalogoActivoMixin, Base):
    """Tipo de identificación de persona: Módulo 2 del RTS."""
    __tablename__ = "CatTipoIdentificacion"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(1), primary_key=True)
    nombre = Column("nombre", String(100), nullable=False)


class CatMotivoInvolucramiento(CatalogoActivoMixin, Base):
    """Motivo de involucramiento de una persona en el RTS: Módulo 2."""
    __tablename__ = "CatMotivoInvolucramiento"
    __table_args__ = {"schema": "public"}

    codigo = Column("codigo", String(20), primary_key=True)
    nombre = Column("nombre", String(150), nullable=False)


class CatTipoReporte(CatalogoActivoMixin, Base):
    """Tipos de reporte/informe que puede generar el sistema (alimenta ReporteGenerado, fase 2)."""
    __tablename__ = "CatTipoReporte"
    __table_args__ = {"schema": "public"}

    codigo         = Column("codigo",         String(30), primary_key=True)
    nombre         = Column("nombre",         String(150), nullable=False)
    es_regulatorio = Column("es_regulatorio", Boolean, nullable=False, default=False)
    articulo_legal = Column("articulo_legal", String(100), nullable=True)


# ═══════════════════════════════════════════════════════════════════════════
# CASOS DE ALERTA PERSISTENTES (ciclo Inusual -> Sospechosa)
# Base legal: Art. 29 (examen y fundamento), Art. 30 (RTS) y Art. 34
# (conservación de registros, mínimo 5 años) Ley 6593. Segmentación por
# licenciaid (multi-tenant). La clave estable del caso se documenta en
# backend/casos_alerta.py (clave_caso = SHA-256 de licencia|lote|cliente).
# ═══════════════════════════════════════════════════════════════════════════

ESTADOS_CASO = (
    "Inusual_Pendiente",       # Detectado por IMPERATOR, sin examinar
    "Inusual_Examinada",       # Examinada por analista, no escalada
    "Sospechosa_Propuesta",    # Analista propone RTS: pendiente de aprobación (cuatro ojos)
    "Sospechosa_Confirmada",   # Aprobada por oficial/admin distinto del proponente: requiere RTS (Art. 30)
    "Descartada",              # Falso positivo documentado
)


class CasoAlerta(Base):
    """Estado vigente de un caso de alerta (cliente dentro de un lote analizado)."""
    __tablename__ = "CasosAlerta"
    __table_args__ = (
        UniqueConstraint("licenciaid", "clave_caso", name="uq_casosalerta_licencia_clave"),
        Index("idx_casosalerta_licencia_lote", "licenciaid", "hash_lote"),
        CheckConstraint(
            "estado IN ('Inusual_Pendiente','Inusual_Examinada','Sospechosa_Propuesta',"
            "'Sospechosa_Confirmada','Descartada')",
            name="casosalerta_estado_check",
        ),
        {"schema": "public"},
    )

    id              = Column("id",              UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid      = Column("licenciaid",      UUID(as_uuid=True), nullable=False, index=True)
    clave_caso      = Column("clave_caso",      String(64),  nullable=False)
    hash_lote       = Column("hash_lote",       String(64),  nullable=False)
    cliente         = Column("cliente",         String(200), nullable=False)
    nombre_archivo  = Column("nombre_archivo",  String(255), nullable=True)
    estado          = Column("estado",          String(40),  nullable=False, default="Inusual_Pendiente")
    fundamento      = Column("fundamento",      String(4000), nullable=False, default="")
    score_max       = Column("score_max",       Float, nullable=True)
    nivel_riesgo    = Column("nivel_riesgo",    String(30),  nullable=True)
    propuesto_por   = Column("propuesto_por",   String(100), nullable=True)
    propuesto_en    = Column("propuesto_en",    DateTime, nullable=True)
    aprobado_por    = Column("aprobado_por",    String(100), nullable=True)
    aprobado_en     = Column("aprobado_en",     DateTime, nullable=True)
    fecha_clasificacion_sospechosa = Column("fecha_clasificacion_sospechosa", Date, nullable=True)
    creado_por      = Column("creado_por",      String(100), nullable=False)
    creado_en       = Column("creado_en",       DateTime, nullable=False, default=ahora_utc)
    actualizado_por = Column("actualizado_por", String(100), nullable=False)
    actualizado_en  = Column("actualizado_en",  DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)


class CasoAlertaHistorial(Base):
    """Historial append-only de cambios de estado (nunca se actualiza ni se borra)."""
    __tablename__ = "CasosAlertaHistorial"
    __table_args__ = (
        Index("idx_casosalertahist_licencia_caso", "licenciaid", "caso_id"),
        {"schema": "public"},
    )

    id              = Column("id",              UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    licenciaid      = Column("licenciaid",      UUID(as_uuid=True), nullable=False, index=True)
    caso_id         = Column("caso_id",         UUID(as_uuid=True), nullable=False, index=True)
    estado_anterior = Column("estado_anterior", String(40),  nullable=True)
    estado_nuevo    = Column("estado_nuevo",    String(40),  nullable=False)
    accion          = Column("accion",          String(40),  nullable=False)
    fundamento      = Column("fundamento",      String(4000), nullable=False, default="")
    usuario         = Column("usuario",         String(100), nullable=False)
    rol             = Column("rol",             String(20),  nullable=False)
    registrado_en   = Column("registrado_en",   DateTime, nullable=False, default=ahora_utc)


class HistorialInmutableError(RuntimeError):
    """Se lanza al intentar modificar o borrar registros protegidos por retención."""


@event.listens_for(CasoAlertaHistorial, "before_update")
def _historial_sin_update(mapper, connection, target):  # noqa: ARG001
    raise HistorialInmutableError("CasosAlertaHistorial es append-only: no se permite actualizar.")


@event.listens_for(CasoAlertaHistorial, "before_delete")
def _historial_sin_delete(mapper, connection, target):  # noqa: ARG001
    raise HistorialInmutableError("CasosAlertaHistorial es append-only: no se permite borrar.")


@event.listens_for(CasoAlerta, "before_delete")
def _caso_sin_delete(mapper, connection, target):  # noqa: ARG001
    raise HistorialInmutableError("CasosAlerta tiene retención mínima de 5 años (Art. 34 Ley 6593): no se permite borrar.")
