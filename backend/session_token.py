"""
Tokens firmados para restaurar la sesión de Streamlit tras una recarga del navegador.

Diseño (OWASP A07, hallazgos S-01 y S-02 del plan 2026-09):
- HMAC-SHA256 con la clave SESSION_SIGN_KEY (obligatoria, 32+ caracteres).
- Fail-closed: sin clave válida no se firma ni se verifica nada.
- El payload solo transporta identificadores (lid = licence_id, sid = session_id),
  nunca datos del usuario; estos se recargan desde la base de datos al restaurar.
- Campos iat/exp (máximo 30 minutos) y nonce aleatorio para evitar replay indefinido.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

logger = logging.getLogger(__name__)

RESTORE_TTL_SECONDS = 30 * 60
LONGITUD_MINIMA_CLAVE = 32
_CAMPOS_REQUERIDOS = ("lid", "sid", "iat", "exp", "nonce")
_aviso_clave_emitido = False


def clave_firma() -> Optional[bytes]:
    """Devuelve la clave de firma o None si no está configurada o es débil."""
    global _aviso_clave_emitido
    clave = os.getenv("SESSION_SIGN_KEY", "")
    if len(clave) >= LONGITUD_MINIMA_CLAVE:
        return clave.encode("utf-8")
    if not _aviso_clave_emitido:
        logger.warning(
            "SESSION_SIGN_KEY ausente o menor de %d caracteres: la restauración de sesión "
            "queda deshabilitada (fail-closed).", LONGITUD_MINIMA_CLAVE,
        )
        _aviso_clave_emitido = True
    return None


def _b64e(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def _b64d(texto: str) -> bytes:
    relleno = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode((texto + relleno).encode("ascii"))


def _firma(clave: bytes, cuerpo: str) -> str:
    return _b64e(hmac.new(clave, cuerpo.encode("ascii"), hashlib.sha256).digest())


def firmar_restauracion(licence_id, session_id, ahora: Optional[float] = None,
                        ttl_segundos: int = RESTORE_TTL_SECONDS) -> Optional[str]:
    """Genera un token firmado. Devuelve None si no hay clave (fail-closed)."""
    clave = clave_firma()
    if clave is None or not licence_id or not session_id:
        return None
    ttl = max(1, min(int(ttl_segundos), RESTORE_TTL_SECONDS))
    emitido = int(ahora if ahora is not None else time.time())
    payload = {
        "lid": str(licence_id),
        "sid": str(session_id),
        "iat": emitido,
        "exp": emitido + ttl,
        "nonce": secrets.token_hex(8),
    }
    cuerpo = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{cuerpo}.{_firma(clave, cuerpo)}"


def verificar_restauracion(token: str, ahora: Optional[float] = None) -> Optional[dict]:
    """
    Verifica firma, estructura y vigencia. Devuelve el payload o None.
    Nunca acepta tokens sin firma.
    """
    clave = clave_firma()
    if clave is None or not isinstance(token, str) or len(token) > 2048:
        return None
    partes = token.split(".")
    if len(partes) != 2 or not partes[0] or not partes[1]:
        return None
    cuerpo, firma = partes
    if not hmac.compare_digest(firma, _firma(clave, cuerpo)):
        return None
    try:
        payload = json.loads(_b64d(cuerpo).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or any(c not in payload for c in _CAMPOS_REQUERIDOS):
        return None
    if not isinstance(payload["iat"], int) or not isinstance(payload["exp"], int):
        return None
    momento = ahora if ahora is not None else time.time()
    if payload["exp"] <= momento or payload["exp"] - payload["iat"] > RESTORE_TTL_SECONDS:
        return None
    if payload["iat"] > momento + 60:
        return None
    return payload
