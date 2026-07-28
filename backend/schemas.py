from pydantic import BaseModel, EmailStr, Field, model_validator
from datetime import date
from uuid import UUID
from typing import Optional, Literal

class LicenciaBase(BaseModel):
    user: str = Field(..., max_length=100)
    name: str = Field(..., max_length=100)
    mail: EmailStr
    dias_vigencia: int = Field(..., gt=0)
    empresa: str = Field(..., max_length=150)

class LicenciaCreate(LicenciaBase):
    password: str = Field(..., min_length=8)
    fecha_compra: date
    fecha_expiracion: date
    licence_id: Optional[UUID] = None

class LicenciaUpdate(BaseModel):
    user: Optional[str] = None
    name: Optional[str] = None
    mail: Optional[EmailStr] = None
    dias_vigencia: Optional[int] = None
    fecha_expiracion: Optional[date] = None
    empresa: Optional[str] = None

class Licencia(LicenciaBase):
    id: int
    licence_id: UUID
    fecha_compra: date
    fecha_expiracion: date

    class Config:
        from_attributes = True

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

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    session_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# ADMINISTRACIÓN DE RIESGO INSTITUCIONAL DE LD/FT (Art. 8-11 Decreto 15-2026 /
# modelo GAFILAT-IVE). Listas cerradas (Literal) para evitar valores arbitrarios
# en campos que alimentan el motor de cálculo — validación explícita (OWASP A03).
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
    id: UUID
    creado_por: str
    creado_en: date

    class Config:
        from_attributes = True


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
