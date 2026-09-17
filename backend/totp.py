"""
TOTP (RFC 6238) y HOTP (RFC 4226) con biblioteca estándar, más códigos de
recuperación de un solo uso (T6 Fase 2, OWASP A07).

Diseño:
- HMAC-SHA1, 6 dígitos, paso de 30 segundos (parámetros por defecto de los
  autenticadores: Google Authenticator, Microsoft Authenticator, Authy, 1Password).
- La verificación acepta una ventana de +-1 paso (tolerancia de reloj) y
  devuelve el contador coincidente para que el llamador lo persista y rechace
  cualquier contador igual o anterior (anti-replay: un código solo sirve una vez).
- Toda comparación de códigos y hashes usa hmac.compare_digest (tiempo constante).
- Los códigos de recuperación se guardan hasheados con PBKDF2-HMAC-SHA256 y sal
  aleatoria por código (formato autodescriptivo: pbkdf2_sha256$iteraciones$sal$hash).
- No se usa ninguna dependencia externa: hmac, hashlib, struct, base64, secrets.
"""
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from typing import List, Optional
from urllib.parse import quote

DIGITOS = 6
PASO_SEGUNDOS = 30
VENTANA = 1
BYTES_SECRETO = 20  # 160 bits, recomendación de RFC 4226 sección 4
EMISOR_POR_DEFECTO = "Sovereign AML"

CODIGOS_RECUPERACION = 10
_ALFABETO_RECUPERACION = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I
_LONGITUD_RECUPERACION = 10
_ITERACIONES_PBKDF2 = 60_000
_ALG_RECUPERACION = "pbkdf2_sha256"
_RE_TOTP = re.compile(r"^\d{6}$")
_RE_RECUPERACION = re.compile(r"^[A-Z2-9]{10}$")


# ── Secretos ─────────────────────────────────────────────────────────────

def generar_secreto(longitud_bytes: int = BYTES_SECRETO) -> str:
    """Secreto aleatorio en Base32 sin relleno (formato que aceptan los autenticadores)."""
    if longitud_bytes < 16:
        raise ValueError("El secreto TOTP debe tener al menos 128 bits.")
    return base64.b32encode(secrets.token_bytes(longitud_bytes)).decode("ascii").rstrip("=")


def decodificar_secreto(secreto_b32: str) -> bytes:
    """Decodifica Base32 (tolera minúsculas, espacios y ausencia de relleno)."""
    limpio = re.sub(r"[\s-]", "", str(secreto_b32 or "")).upper()
    if not limpio or re.search(r"[^A-Z2-7]", limpio):
        raise ValueError("Secreto TOTP inválido.")
    limpio += "=" * (-len(limpio) % 8)
    try:
        return base64.b32decode(limpio)
    except (ValueError, TypeError) as exc:
        raise ValueError("Secreto TOTP inválido.") from exc


def secreto_en_bloques(secreto_b32: str, tamano: int = 4) -> str:
    """Presenta el secreto en bloques de 4 para el ingreso manual en el autenticador."""
    limpio = re.sub(r"\s", "", str(secreto_b32 or "")).upper()
    return " ".join(limpio[i:i + tamano] for i in range(0, len(limpio), tamano))


def uri_otpauth(secreto_b32: str, cuenta: str, emisor: str = EMISOR_POR_DEFECTO) -> str:
    """URI otpauth:// (formato de Google Authenticator) para QR o ingreso manual."""
    etiqueta = quote(f"{emisor}:{cuenta}", safe="")
    return (
        f"otpauth://totp/{etiqueta}?secret={secreto_b32}&issuer={quote(emisor, safe='')}"
        f"&algorithm=SHA1&digits={DIGITOS}&period={PASO_SEGUNDOS}"
    )


# ── HOTP / TOTP ──────────────────────────────────────────────────────────

def hotp(secreto: bytes, contador: int, digitos: int = DIGITOS) -> str:
    """RFC 4226: truncamiento dinámico de HMAC-SHA1 sobre el contador (8 bytes big-endian)."""
    if contador < 0:
        raise ValueError("El contador HOTP no puede ser negativo.")
    resumen = hmac.new(secreto, struct.pack(">Q", contador), hashlib.sha1).digest()
    desplazamiento = resumen[-1] & 0x0F
    codigo = struct.unpack(">I", resumen[desplazamiento:desplazamiento + 4])[0] & 0x7FFFFFFF
    return str(codigo % (10 ** digitos)).zfill(digitos)


def contador_totp(momento: Optional[float] = None, paso: int = PASO_SEGUNDOS) -> int:
    momento = time.time() if momento is None else momento
    return int(momento // paso)


def totp(secreto_b32: str, momento: Optional[float] = None, paso: int = PASO_SEGUNDOS,
         digitos: int = DIGITOS) -> str:
    """RFC 6238: HOTP sobre el contador de tiempo T = floor(unix / paso)."""
    return hotp(decodificar_secreto(secreto_b32), contador_totp(momento, paso), digitos)


def es_formato_totp(codigo: str) -> bool:
    return bool(_RE_TOTP.match(normalizar_codigo(codigo)))


def normalizar_codigo(codigo: str) -> str:
    return re.sub(r"[\s-]", "", str(codigo or "")).upper()


def verificar_totp(secreto_b32: str, codigo: str, momento: Optional[float] = None,
                   ventana: int = VENTANA, ultimo_contador: Optional[int] = None) -> Optional[int]:
    """
    Verifica un código TOTP en la ventana [-ventana, +ventana] pasos.
    Devuelve el contador que coincidió (para persistirlo como anti-replay) o None.
    Cualquier contador menor o igual a `ultimo_contador` se rechaza aunque el código
    sea correcto: un código aceptado no vuelve a servir dentro de su vigencia.
    Recorre toda la ventana sin salir antes (tiempo constante respecto a la posición).
    """
    codigo_n = normalizar_codigo(codigo)
    if not _RE_TOTP.match(codigo_n):
        return None
    try:
        secreto = decodificar_secreto(secreto_b32)
    except ValueError:
        return None
    ventana = max(0, min(int(ventana), 2))
    actual = contador_totp(momento)
    coincidencia: Optional[int] = None
    for desplazamiento in range(-ventana, ventana + 1):
        candidato = actual + desplazamiento
        if candidato < 0:
            continue
        iguales = hmac.compare_digest(hotp(secreto, candidato), codigo_n)
        if iguales and (ultimo_contador is None or candidato > ultimo_contador) and coincidencia is None:
            coincidencia = candidato
    return coincidencia


# ── Códigos de recuperación ──────────────────────────────────────────────

def generar_codigos_recuperacion(cantidad: int = CODIGOS_RECUPERACION) -> List[str]:
    """Códigos de un solo uso con formato XXXXX-XXXXX (alfabeto sin caracteres ambiguos)."""
    codigos: List[str] = []
    while len(codigos) < cantidad:
        crudo = "".join(secrets.choice(_ALFABETO_RECUPERACION) for _ in range(_LONGITUD_RECUPERACION))
        codigo = f"{crudo[:5]}-{crudo[5:]}"
        if codigo not in codigos:
            codigos.append(codigo)
    return codigos


def es_formato_recuperacion(codigo: str) -> bool:
    return bool(_RE_RECUPERACION.match(normalizar_codigo(codigo)))


def hash_codigo_recuperacion(codigo: str, sal: Optional[bytes] = None,
                             iteraciones: int = _ITERACIONES_PBKDF2) -> str:
    """PBKDF2-HMAC-SHA256 con sal aleatoria de 16 bytes; formato autodescriptivo."""
    sal = sal if sal is not None else secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac("sha256", normalizar_codigo(codigo).encode("ascii"), sal, iteraciones)
    return f"{_ALG_RECUPERACION}${iteraciones}${sal.hex()}${derivado.hex()}"


def verificar_codigo_recuperacion(codigo: str, hash_guardado: str) -> bool:
    """Comparación en tiempo constante contra un hash almacenado."""
    partes = str(hash_guardado or "").split("$")
    if len(partes) != 4 or partes[0] != _ALG_RECUPERACION:
        return False
    try:
        iteraciones = int(partes[1])
        sal = bytes.fromhex(partes[2])
        esperado = bytes.fromhex(partes[3])
    except ValueError:
        return False
    if iteraciones < 10_000 or iteraciones > 1_000_000 or len(sal) < 8:
        return False
    codigo_n = normalizar_codigo(codigo)
    if not _RE_RECUPERACION.match(codigo_n):
        return False
    derivado = hashlib.pbkdf2_hmac("sha256", codigo_n.encode("ascii"), sal, iteraciones)
    return hmac.compare_digest(derivado, esperado)
