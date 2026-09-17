"""
Caché temporal del análisis en disco, ligado al tenant y cifrado (hallazgo S-03).

- Nombre de archivo: <licence_id>_<cache_id>.saml; solo se carga si el licence_id
  autenticado coincide con el del archivo (evita IDOR entre tenants).
- Contenido cifrado con Fernet (AES-128-CBC + HMAC) usando una clave derivada de
  SESSION_SIGN_KEY y CACHE_ENCRYPTION_SALT (PBKDF2-HMAC-SHA256).
- Permisos 0o600 y TTL igual al tiempo de sesión.
- Fail-closed: sin clave de firma no se persiste nada.
"""
import base64
import hashlib
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from backend.session_token import clave_firma

logger = logging.getLogger(__name__)

CACHE_DIR = Path(tempfile.gettempdir()) / "sovereign_aml_cache"
TTL_SEGUNDOS = 30 * 60
_PATRON_UUID = re.compile(r"[a-f0-9-]{36}")
_ITERACIONES_PBKDF2 = 200_000
_clave_fernet_cache: dict = {}


def uuid_seguro(valor) -> Optional[str]:
    """Devuelve el valor solo si tiene forma de UUID (evita path traversal)."""
    valor = str(valor or "").lower()
    return valor if _PATRON_UUID.fullmatch(valor) else None


def _clave_fernet() -> Optional[Fernet]:
    clave = clave_firma()
    if clave is None:
        return None
    sal = os.getenv("CACHE_ENCRYPTION_SALT", "sovereign-aml-cache").encode("utf-8")
    indice = (clave, sal)
    if indice not in _clave_fernet_cache:
        derivada = hashlib.pbkdf2_hmac("sha256", clave, sal, _ITERACIONES_PBKDF2, dklen=32)
        _clave_fernet_cache.clear()
        _clave_fernet_cache[indice] = Fernet(base64.urlsafe_b64encode(derivada))
    return _clave_fernet_cache[indice]


def ruta_cache(licence_id, cache_id) -> Optional[Path]:
    lid = uuid_seguro(licence_id)
    cid = uuid_seguro(cache_id)
    if not lid or not cid:
        return None
    return CACHE_DIR / f"{lid}_{cid}.saml"


def _expirado(ruta: Path) -> bool:
    return time.time() - ruta.stat().st_mtime > TTL_SEGUNDOS


def guardar(licence_id, cache_id, contenido: bytes) -> bool:
    """Cifra y guarda el contenido. Devuelve False si no se pudo persistir."""
    fernet = _clave_fernet()
    ruta = ruta_cache(licence_id, cache_id)
    if fernet is None or ruta is None:
        return False
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(".tmp")
        with os.fdopen(os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            f.write(fernet.encrypt(contenido))
        os.replace(temporal, ruta)
        os.chmod(ruta, 0o600)
        return True
    except OSError:
        logger.exception("No se pudo escribir el caché de análisis.")
        return False


def cargar(licence_id, cache_id) -> Optional[bytes]:
    """Devuelve el contenido descifrado o None (ausente, expirado, ajeno o corrupto)."""
    fernet = _clave_fernet()
    ruta = ruta_cache(licence_id, cache_id)
    if fernet is None or ruta is None or not ruta.exists():
        return None
    try:
        if _expirado(ruta):
            ruta.unlink()
            return None
        contenido = fernet.decrypt(ruta.read_bytes())
        ruta.touch()
        return contenido
    except InvalidToken:
        logger.warning("Caché de análisis con firma inválida; se descarta.")
        eliminar(licence_id, cache_id)
        return None
    except OSError:
        logger.exception("No se pudo leer el caché de análisis.")
        return None


def eliminar(licence_id, cache_id) -> None:
    ruta = ruta_cache(licence_id, cache_id)
    if ruta is None or not ruta.exists():
        return
    try:
        ruta.unlink()
    except OSError:
        logger.exception("No se pudo eliminar el caché de análisis.")


def limpiar_expirados() -> int:
    """Elimina archivos vencidos de todos los tenants. Devuelve cuántos borró."""
    borrados = 0
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for ruta in CACHE_DIR.glob("*.saml"):
            try:
                if _expirado(ruta):
                    ruta.unlink()
                    borrados += 1
            except OSError:
                logger.exception("No se pudo limpiar %s", ruta.name)
    except OSError:
        logger.exception("No se pudo acceder al directorio de caché.")
    return borrados
