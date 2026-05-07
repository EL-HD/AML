from pydantic import BaseModel, EmailStr, Field
from datetime import date
from uuid import UUID
from typing import Optional

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
