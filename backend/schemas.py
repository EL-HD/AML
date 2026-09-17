from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from .politica_password import validar_password
from datetime import date
from uuid import UUID
from typing import Optional, Literal

# Roles RBAC (OWASP A01). Lista cerrada: cualquier otro valor se rechaza.
Rol = Literal["admin", "oficial", "analista", "auditor"]
ROLES = ("admin", "oficial", "analista", "auditor")

class LicenciaBase(BaseModel):
    user: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    mail: EmailStr
    dias_vigencia: int = Field(..., gt=0)
    empresa: str = Field(..., max_length=150)

class LicenciaCreate(LicenciaBase):
    password: str = Field(..., min_length=12, max_length=128)
    fecha_compra: date
    fecha_expiracion: date
    licence_id: Optional[UUID] = None
    rol: Rol = "analista"

    @model_validator(mode="after")
    def _validar_politica_password(self):
        validar_password(self.password, self.user)
        return self

class LicenciaUpdate(BaseModel):
    """Campos que solo un administrador puede modificar sobre cualquier licencia."""
    model_config = ConfigDict(extra="forbid")

    user: Optional[str] = Field(None, max_length=100)
    name: Optional[str] = Field(None, max_length=100)
    mail: Optional[EmailStr] = None
    dias_vigencia: Optional[int] = Field(None, gt=0)
    fecha_expiracion: Optional[date] = None
    empresa: Optional[str] = Field(None, max_length=150)
    rol: Optional[Rol] = None

class PerfilUpdate(BaseModel):
    """Campos que cualquier usuario puede modificar sobre su propia licencia.
    Excluye fecha_expiracion, dias_vigencia, user y rol (solo admin)."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=100)
    empresa: Optional[str] = Field(None, max_length=150)

class Licencia(LicenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    licence_id: UUID
    fecha_compra: date
    fecha_expiracion: date
    rol: Rol = "analista"

class AuthRequest(BaseModel):
    username: str
    password: str
    mail: Optional[EmailStr] = None

class AuthResponse(BaseModel):
    exists: bool
    is_active: bool
    message: str
    licencia: Optional[Licencia] = None
    access_token: Optional[str] = None
    session_id: Optional[str] = None
    # MFA (T6): si mfa_requerido, solo se entrega mfa_token (5 min, un solo uso) para
    # canjearlo en /auth/mfa/verificar; licencia, access_token y session_id vienen vacíos.
    mfa_requerido: bool = False
    mfa_token: Optional[str] = None
    # Política MFA_ENFORCE: el usuario entró pero debe enrolar antes de usar el sistema.
    mfa_enrolamiento_pendiente: bool = False


class MfaVerificarRequest(BaseModel):
    mfa_token: str = Field(..., min_length=20, max_length=2048)
    codigo: str = Field(..., min_length=6, max_length=16)


class MfaCodigoRequest(BaseModel):
    codigo: str = Field(..., min_length=6, max_length=16)


class MfaEstado(BaseModel):
    disponible: bool
    activo: bool
    obligatorio: bool
    enrolamiento_pendiente: bool
    codigos_restantes: int = 0
    enrolado_en: Optional[str] = None


class MfaEnrolamiento(BaseModel):
    secreto: str
    secreto_bloques: str
    uri: str
    emisor: str
    cuenta: str


class MfaCodigosRecuperacion(BaseModel):
    codigos_recuperacion: list[str]
    mensaje: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    session_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE RIESGO INSTITUCIONAL DE LD/FT (Art. 8-11 Decreto 15-2026 /
# modelo GAFILAT-IVE). Listas cerradas (Literal) para evitar valores arbitrarios
# en campos que alimentan el motor de cálculo: validación explícita (OWASP A03).
# ═══════════════════════════════════════════════════════════════════════════

FactorLDFT = Literal[
    "Clientes", "Productos y Servicios", "Canales de Distribución", "Ubicación Geográfica"
]
TipoControlLDFT = Literal["Preventivo", "Detectivo", "Correctivo"]
EjecucionControlLDFT = Literal["Automático", "Semiautomático", "Manual"]
NivelCualitativoLDFT = Literal["Bueno", "Adecuado", "Mejorable", "Deficiente"]


class RiesgoSegmentoCreate(BaseModel):
    factor: FactorLDFT
    segmento: str = Field(..., min_length=2, max_length=120)
    variable: str = Field(..., min_length=2, max_length=120)


class RiesgoSegmento(RiesgoSegmentoCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    creado_por: str
    creado_en: date


class RiesgoEventoCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=200)
    descripcion: Optional[str] = Field(None, max_length=1000)
    factor: FactorLDFT
    segmento_id: Optional[UUID] = None
    probabilidad: int = Field(..., ge=1, le=4)
    riesgo_operacional: int = Field(..., ge=1, le=4)
    riesgo_legal: int = Field(..., ge=1, le=4)
    riesgo_reputacional: int = Field(..., ge=1, le=4)
    riesgo_contagio: int = Field(..., ge=1, le=4)


class RiesgoControlCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=150)
    descripcion: str = Field(..., min_length=3, max_length=1000)
    documentado: bool
    tipo_control: TipoControlLDFT
    ejecucion: EjecucionControlLDFT
    nivel_cumplimiento: NivelCualitativoLDFT
    nivel_efectividad: NivelCualitativoLDFT
    evaluado: bool = False
    responsable_evaluacion: Optional[str] = Field(None, max_length=150)
    fecha_evaluacion: Optional[date] = None


class RiesgoPlanAccionCreate(BaseModel):
    medida_propuesta: str = Field(..., min_length=3, max_length=1000)
    responsable: str = Field(..., min_length=2, max_length=150)
    fecha_inicio: date
    fecha_fin: date
    porcentaje_avance: int = Field(0, ge=0, le=100)

    @model_validator(mode="after")
    def _validar_fechas(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("La fecha de finalización no puede ser anterior a la fecha de inicio.")
        return self
