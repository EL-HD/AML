"""
MFA TOTP por usuario (T6 Fase 2, OWASP A07): enrolamiento, verificación,
códigos de recuperación, restablecimiento y política de obligatoriedad.

- Secreto cifrado en reposo con Fernet (cryptography) y la clave MFA_ENCRYPTION_KEY.
  Sin clave válida no se puede enrolar ni verificar códigos TOTP (fail-closed);
  los códigos de recuperación, que solo viven como hashes, siguen funcionando para
  que un usuario ya enrolado pueda entrar y un administrador restablecer.
- Anti-replay: se persiste el último contador aceptado por usuario.
- Sesión MFA: `MfaUsuario.sesion_mfa` guarda el sessionid que superó el segundo
  factor. `sesion_autorizada` es el único punto que decide si una sesión creada
  por contraseña puede usarse: lo consultan la API (get_current_user) y la
  restauración de sesión de Streamlit, de modo que un token de restauración o un
  JWT nunca sirven para saltarse el MFA.
- Política: MFA_ENFORCE=true vuelve obligatorio el MFA para admin y oficial; un
  usuario de esos roles sin enrolar solo puede completar el enrolamiento.
- Toda acción queda en BitacoraAuditoria: MFA_OK, MFA_FALLIDO, MFA_ENROLADO,
  MFA_RECUPERACION, MFA_RESTABLECIDO (módulo "Autenticación").
"""
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import List, Optional

from cryptography.fernet import Fernet, InvalidToken

from . import auditoria, models, totp

logger = logging.getLogger(__name__)

VARIABLE_CLAVE = "MFA_ENCRYPTION_KEY"
VARIABLE_ENFORCE = "MFA_ENFORCE"
ROLES_MFA_OBLIGATORIO = frozenset({"admin", "oficial"})
MENSAJE_SIN_CLAVE = (
    "MFA no disponible: la variable MFA_ENCRYPTION_KEY no está configurada o no es una clave Fernet válida."
)
_aviso_clave_emitido = False


class MfaError(ValueError):
    """Error de negocio del MFA con mensaje apto para el usuario."""


@dataclass
class EstadoMfa:
    disponible: bool          # hay clave de cifrado válida
    activo: bool              # el usuario tiene MFA confirmado
    obligatorio: bool         # la política exige MFA para su rol
    enrolamiento_pendiente: bool  # obligatorio y no activo
    codigos_restantes: int = 0
    enrolado_en: Optional[str] = None

    def como_dict(self) -> dict:
        return {
            "disponible": self.disponible, "activo": self.activo, "obligatorio": self.obligatorio,
            "enrolamiento_pendiente": self.enrolamiento_pendiente,
            "codigos_restantes": self.codigos_restantes, "enrolado_en": self.enrolado_en,
        }


# ── Configuración ────────────────────────────────────────────────────────

def cifrador() -> Optional[Fernet]:
    """Fernet con MFA_ENCRYPTION_KEY, o None si la clave falta o es inválida (fail-closed)."""
    global _aviso_clave_emitido
    clave = os.getenv(VARIABLE_CLAVE, "").strip()
    if clave:
        try:
            return Fernet(clave.encode("ascii"))
        except (ValueError, TypeError):
            logger.error("%s no es una clave Fernet válida (44 caracteres base64 url-safe).", VARIABLE_CLAVE)
            return None
    if not _aviso_clave_emitido:
        logger.warning("%s ausente: el enrolamiento MFA queda deshabilitado.", VARIABLE_CLAVE)
        _aviso_clave_emitido = True
    return None


def mfa_disponible() -> bool:
    return cifrador() is not None


def mfa_obligatorio_para(rol: Optional[str]) -> bool:
    """MFA_ENFORCE=true exige MFA a admin y oficial. Por defecto false (no bloquea el despliegue)."""
    valor = os.getenv(VARIABLE_ENFORCE, "false").strip().lower()
    return valor in ("1", "true", "yes", "si", "sí") and (rol or "") in ROLES_MFA_OBLIGATORIO


def cifrar_secreto(secreto_b32: str) -> str:
    f = cifrador()
    if f is None:
        raise MfaError(MENSAJE_SIN_CLAVE)
    return f.encrypt(secreto_b32.encode("ascii")).decode("ascii")


def descifrar_secreto(secreto_cifrado: str) -> Optional[str]:
    """None si no hay clave o el texto cifrado no corresponde a la clave actual."""
    f = cifrador()
    if f is None:
        return None
    try:
        return f.decrypt(secreto_cifrado.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, TypeError):
        logger.error("Secreto MFA no descifrable: la clave MFA_ENCRYPTION_KEY cambió o el registro está dañado.")
        return None


# ── Utilidades internas ──────────────────────────────────────────────────

def _lid(licenciaid) -> uuid.UUID:
    try:
        return licenciaid if isinstance(licenciaid, uuid.UUID) else uuid.UUID(str(licenciaid))
    except (ValueError, TypeError, AttributeError) as exc:
        raise MfaError("Identificador de licencia inválido.") from exc


def _sid(session_id) -> Optional[uuid.UUID]:
    try:
        return session_id if isinstance(session_id, uuid.UUID) else uuid.UUID(str(session_id))
    except (ValueError, TypeError, AttributeError):
        return None


def _auditar(db, licencia, accion: str) -> None:
    auditoria.registrar_evento(db, licencia.licence_id, licencia.user,
                               auditoria.MODULO_AUTENTICACION, accion)


def _cargar_hashes(registro: models.MfaUsuario) -> List[str]:
    try:
        datos = json.loads(registro.codigos_recuperacion or "[]")
    except ValueError:
        return []
    return [str(x) for x in datos] if isinstance(datos, list) else []


def obtener(db, licenciaid) -> Optional[models.MfaUsuario]:
    return db.query(models.MfaUsuario).filter(models.MfaUsuario.licenciaid == _lid(licenciaid)).first()


def esta_activo(db, licenciaid) -> bool:
    registro = obtener(db, licenciaid)
    return bool(registro and registro.activo)


def estado(db, licencia) -> EstadoMfa:
    registro = obtener(db, licencia.licence_id)
    activo = bool(registro and registro.activo)
    obligatorio = mfa_obligatorio_para(getattr(licencia, "rol", None))
    return EstadoMfa(
        disponible=mfa_disponible(), activo=activo, obligatorio=obligatorio,
        enrolamiento_pendiente=obligatorio and not activo,
        codigos_restantes=int(registro.codigos_restantes) if activo else 0,
        enrolado_en=registro.enrolado_en.isoformat() if (activo and registro.enrolado_en) else None,
    )


def enrolamiento_pendiente(db, licencia) -> bool:
    """True si la política exige MFA al rol y el usuario aún no lo tiene activo."""
    return mfa_obligatorio_para(getattr(licencia, "rol", None)) and not esta_activo(db, licencia.licence_id)


# ── Sesión ───────────────────────────────────────────────────────────────

def sesion_autorizada(db, licencia, session_id) -> bool:
    """
    Decide si una sesión (creada al validar la contraseña) puede usarse.
    Sin MFA activo: sí. Con MFA activo: solo si es la sesión que superó el segundo
    factor. Lo usan get_current_user (API) y la restauración de sesión (Streamlit).
    """
    registro = obtener(db, licencia.licence_id)
    if registro is None or not registro.activo:
        return True
    sid = _sid(session_id)
    return sid is not None and registro.sesion_mfa == sid


def _marcar_sesion(db, registro: models.MfaUsuario, session_id) -> None:
    registro.sesion_mfa = _sid(session_id)
    registro.actualizado_en = models.ahora_utc()


# ── Enrolamiento ─────────────────────────────────────────────────────────

def iniciar_enrolamiento(db, licencia) -> dict:
    """
    Genera un secreto nuevo (cifrado en BD, inactivo hasta confirmar) y devuelve
    el material para el autenticador: secreto, bloques y URI otpauth.
    Un usuario con MFA activo debe restablecerlo (con código) antes de re-enrolar.
    """
    if not mfa_disponible():
        raise MfaError(MENSAJE_SIN_CLAVE)
    registro = obtener(db, licencia.licence_id)
    if registro is not None and registro.activo:
        raise MfaError("El MFA ya está activo. Para cambiar de dispositivo primero restablézcalo con un código válido.")
    secreto = totp.generar_secreto()
    if registro is None:
        registro = models.MfaUsuario(licenciaid=_lid(licencia.licence_id), usuario=str(licencia.user)[:100])
        db.add(registro)
    registro.usuario = str(licencia.user)[:100]
    registro.secreto_cifrado = cifrar_secreto(secreto)
    registro.activo = False
    registro.enrolado_en = None
    registro.ultimo_contador = 0
    registro.codigos_recuperacion = "[]"
    registro.codigos_restantes = 0
    registro.sesion_mfa = None
    registro.actualizado_en = models.ahora_utc()
    db.commit()
    return {
        "secreto": secreto,
        "secreto_bloques": totp.secreto_en_bloques(secreto),
        "uri": totp.uri_otpauth(secreto, str(licencia.user)),
        "emisor": totp.EMISOR_POR_DEFECTO,
        "cuenta": str(licencia.user),
    }


def confirmar_enrolamiento(db, licencia, codigo: str, session_id=None) -> List[str]:
    """
    Activa el MFA si `codigo` es válido para el secreto pendiente. Devuelve los
    códigos de recuperación en claro (única vez); en BD solo quedan sus hashes.
    """
    registro = obtener(db, licencia.licence_id)
    if registro is None or registro.activo:
        raise MfaError("No hay un enrolamiento pendiente. Inicie el enrolamiento primero.")
    secreto = descifrar_secreto(registro.secreto_cifrado)
    if secreto is None:
        raise MfaError(MENSAJE_SIN_CLAVE)
    contador = totp.verificar_totp(secreto, codigo, ultimo_contador=registro.ultimo_contador)
    if contador is None:
        _auditar(db, licencia, auditoria.MFA_FALLIDO)
        raise MfaError("Código incorrecto. Verifique la hora del dispositivo e intente de nuevo.")
    codigos = totp.generar_codigos_recuperacion()
    registro.codigos_recuperacion = json.dumps([totp.hash_codigo_recuperacion(c) for c in codigos])
    registro.codigos_restantes = len(codigos)
    registro.ultimo_contador = contador
    registro.activo = True
    registro.enrolado_en = models.ahora_utc()
    _marcar_sesion(db, registro, session_id)
    db.commit()
    _auditar(db, licencia, auditoria.MFA_ENROLADO)
    return codigos


# ── Verificación en el login ─────────────────────────────────────────────

def verificar(db, licencia, codigo: str, session_id) -> bool:
    """
    Segundo factor del login: acepta un código TOTP (6 dígitos) o un código de
    recuperación (XXXXX-XXXXX, un solo uso). Si es válido marca `session_id`
    como sesión autenticada con MFA. Audita MFA_OK / MFA_RECUPERACION / MFA_FALLIDO.
    """
    registro = obtener(db, licencia.licence_id)
    if registro is None or not registro.activo:
        raise MfaError("El usuario no tiene MFA activo.")
    codigo_n = totp.normalizar_codigo(codigo)
    if totp.es_formato_totp(codigo_n):
        exito = _verificar_totp(db, registro, codigo_n)
        accion = auditoria.MFA_OK
    elif totp.es_formato_recuperacion(codigo_n):
        exito = _consumir_recuperacion(registro, codigo_n)
        accion = auditoria.MFA_RECUPERACION
    else:
        exito, accion = False, auditoria.MFA_FALLIDO
    if exito:
        _marcar_sesion(db, registro, session_id)
        db.commit()
        _auditar(db, licencia, accion)
        return True
    db.rollback()
    _auditar(db, licencia, auditoria.MFA_FALLIDO)
    return False


def _verificar_totp(db, registro: models.MfaUsuario, codigo_n: str) -> bool:
    secreto = descifrar_secreto(registro.secreto_cifrado)
    if secreto is None:
        return False
    contador = totp.verificar_totp(secreto, codigo_n, ultimo_contador=registro.ultimo_contador)
    if contador is None:
        return False
    registro.ultimo_contador = contador
    return True


def _consumir_recuperacion(registro: models.MfaUsuario, codigo_n: str) -> bool:
    """Recorre todos los hashes (sin cortar antes) y elimina el que coincide."""
    hashes = _cargar_hashes(registro)
    indice = None
    for i, h in enumerate(hashes):
        if totp.verificar_codigo_recuperacion(codigo_n, h) and indice is None:
            indice = i
    if indice is None:
        return False
    del hashes[indice]
    registro.codigos_recuperacion = json.dumps(hashes)
    registro.codigos_restantes = len(hashes)
    return True


# ── Restablecimiento ─────────────────────────────────────────────────────

def restablecer_propio(db, licencia, codigo: str) -> None:
    """El propio usuario retira su MFA presentando un código válido (TOTP o recuperación)."""
    registro = obtener(db, licencia.licence_id)
    if registro is None or not registro.activo:
        raise MfaError("El usuario no tiene MFA activo.")
    codigo_n = totp.normalizar_codigo(codigo)
    valido = False
    if totp.es_formato_totp(codigo_n):
        valido = _verificar_totp(db, registro, codigo_n)
    elif totp.es_formato_recuperacion(codigo_n):
        valido = _consumir_recuperacion(registro, codigo_n)
    if not valido:
        db.rollback()
        _auditar(db, licencia, auditoria.MFA_FALLIDO)
        raise MfaError("Código incorrecto: no se restableció el MFA.")
    db.delete(registro)
    db.commit()
    _auditar(db, licencia, f"{auditoria.MFA_RESTABLECIDO}:propio")


def restablecer_por_admin(db, admin, objetivo) -> None:
    """
    Un administrador retira el MFA de otro usuario (p. ej. dispositivo perdido sin
    códigos de recuperación). Nunca el propio: para eso se exige un código.
    Queda auditado en la bitácora del administrador y en la del usuario afectado.
    """
    if getattr(admin, "rol", None) != "admin":
        raise MfaError("Solo un administrador puede restablecer el MFA de otro usuario.")
    if str(admin.licence_id) == str(objetivo.licence_id):
        raise MfaError("No puede restablecer su propio MFA por esta vía: use un código válido.")
    registro = obtener(db, objetivo.licence_id)
    if registro is None:
        raise MfaError("El usuario no tiene MFA configurado.")
    db.delete(registro)
    db.commit()
    detalle = f"{auditoria.MFA_RESTABLECIDO}:admin={str(admin.user)[:40]}"
    _auditar(db, objetivo, detalle)
    _auditar(db, admin, f"{auditoria.MFA_RESTABLECIDO}:usuario={str(objetivo.user)[:40]}")
