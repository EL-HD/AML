"""
Configuración del motor AML: valores por defecto y validación con lista blanca.

AmlConfig (Pydantic, extra="forbid") es la única fuente de verdad sobre qué
claves existen y en qué rangos. Se usa al importar un archivo .saml o un JSON
de configuración, evitando asignación masiva de claves desconocidas (S-08).
No modifica la lógica de scoring (backend/procesador.py), solo valida entradas.
"""
from typing import List

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_UBICACIONES = 500
MAX_LARGO_UBICACION = 120


class AmlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tolerancia_perfil: int = Field(15, ge=0, le=100)
    umbral_absoluto: int = Field(20000, ge=1000, le=10_000_000)
    mult_acumulado: float = Field(2.0, ge=1.0, le=10.0)
    umbral_frecuencia: int = Field(5, ge=1, le=500)
    umbral_smurfing: int = Field(5, ge=2, le=50)
    mult_std_pico: float = Field(2.0, ge=0.5, le=5.0)
    score_critico: int = Field(8, ge=1, le=30)
    monto_critico: int = Field(30000, ge=1000, le=10_000_000)
    score_alto: int = Field(5, ge=1, le=30)
    score_medio: int = Field(3, ge=1, le=30)
    peso_absoluto: int = Field(3, ge=0, le=10)
    peso_acumulado: int = Field(2, ge=0, le=10)
    peso_perfil: int = Field(1, ge=0, le=10)
    peso_frecuencia: int = Field(1, ge=0, le=10)
    peso_smurfing: int = Field(3, ge=0, le=10)
    peso_pico: int = Field(2, ge=0, le=10)
    regla_absoluto: bool = True
    regla_acumulado: bool = True
    regla_perfil: bool = True
    regla_frecuencia: bool = True
    regla_smurfing: bool = True
    regla_pico: bool = True
    regla_ubicacion: bool = True
    peso_pep_cpe: int = Field(2, ge=0, le=10)
    peso_ubicacion: int = Field(2, ge=0, le=10)
    w_st: float = Field(0.40, ge=0.0, le=1.0)
    w_sc: float = Field(0.25, ge=0.0, le=1.0)
    w_sb: float = Field(0.20, ge=0.0, le=1.0)
    w_sn: float = Field(0.15, ge=0.0, le=1.0)
    ubicaciones_manuales: List[str] = Field(
        default_factory=lambda: ["Huehuetenango", "San Marcos", "Izabal", "Petén", "Escuintla"]
    )
    regla_feic: bool = True
    umbral_feic: int = Field(45000, ge=1000, le=500_000)
    moneda: str = Field("GTQ", pattern=r"^(GTQ|USD)$")

    @field_validator("ubicaciones_manuales")
    @classmethod
    def _validar_ubicaciones(cls, valor):
        if len(valor) > MAX_UBICACIONES:
            raise ValueError(f"Demasiadas ubicaciones (máximo {MAX_UBICACIONES}).")
        limpias = []
        for item in valor:
            texto = str(item).strip()
            if not texto or len(texto) > MAX_LARGO_UBICACION:
                raise ValueError("Cada ubicación debe tener entre 1 y 120 caracteres.")
            limpias.append(texto)
        return limpias


def config_por_defecto() -> dict:
    return AmlConfig().model_dump()


def _mensaje_validacion(error: ValidationError) -> str:
    partes = []
    for err in error.errors():
        campo = ".".join(str(p) for p in err.get("loc", ())) or "configuración"
        partes.append(f"{campo}: {err.get('msg')}")
    return "; ".join(partes[:6])


def validar_config(datos: dict) -> dict:
    """
    Valida un diccionario contra AmlConfig. Claves desconocidas y valores fuera
    de rango lanzan ValueError con un mensaje legible. Devuelve el dict completo
    (con defaults para las claves ausentes).
    """
    if not isinstance(datos, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    try:
        return AmlConfig.model_validate(datos).model_dump()
    except ValidationError as exc:
        raise ValueError(f"Configuración inválida: {_mensaje_validacion(exc)}") from exc
