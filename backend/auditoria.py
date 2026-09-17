"""
Bitácora de auditoría (Art. 19 Ley 6593, OWASP A09).

Punto único para registrar eventos de seguridad y de negocio en
public."BitacoraAuditoria". Nunca interrumpe el flujo principal, pero tampoco
silencia errores: cada fallo se registra con logger.exception y se cuenta.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from . import models

logger = logging.getLogger(__name__)

# Acciones normalizadas (texto libre permitido, pero se recomienda usar estas)
LOGIN_OK = "LOGIN_OK"
LOGIN_FALLIDO = "LOGIN_FALLIDO"
LOGOUT = "LOGOUT"
EXPORTACION = "EXPORTACION"
IMPORTACION = "IMPORTACION"
CAMBIO_CONFIG = "CAMBIO_CONFIG"
CAMBIO_ESTADO_CASO = "CAMBIO_ESTADO_CASO"
VISUALIZACION = "VISUALIZACION"
MODULO_AUTENTICACION = "Autenticación"

fallos_registro = 0


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalizar_uuid(valor) -> Optional[uuid.UUID]:
    if isinstance(valor, uuid.UUID):
        return valor
    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError, AttributeError):
        return None


def registrar_evento(db, licenciaid, username: str, modulo: str, accion: str = VISUALIZACION) -> bool:
    """Inserta un evento usando la sesión db recibida. Devuelve True si se persistió."""
    global fallos_registro
    lid = _normalizar_uuid(licenciaid)
    if lid is None:
        logger.warning("Auditoría omitida: licenciaid inválido (usuario=%s, modulo=%s, accion=%s)",
                       username, modulo, accion)
        return False
    try:
        db.add(models.BitacoraAuditoria(
            licenciaid=lid,
            username=str(username or "desconocido")[:100],
            modulo_accedido=str(modulo)[:100],
            accion=str(accion)[:100],
            timestamp=ahora_utc(),
        ))
        db.commit()
        return True
    except SQLAlchemyError:
        fallos_registro += 1
        db.rollback()
        logger.exception("No se pudo registrar el evento de auditoría (fallos acumulados=%d).",
                         fallos_registro)
        return False


def registrar_evento_autonomo(licenciaid, username: str, modulo: str, accion: str = VISUALIZACION) -> bool:
    """Igual que registrar_evento pero abre y cierra su propia sesión de BD."""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        return registrar_evento(db, licenciaid, username, modulo, accion)
    finally:
        db.close()
