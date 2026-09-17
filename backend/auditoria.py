"""
Bitácora de auditoría (Art. 19 Ley 6593, OWASP A09).

Punto único para registrar eventos de seguridad y de negocio en
public."BitacoraAuditoria". Nunca interrumpe el flujo principal, pero tampoco
silencia errores: cada fallo se registra con logger.exception y se cuenta.

Bitácora a prueba de alteraciones (T4 Fase 2, migración 006):
- Cada registro es un eslabón: seq correlativo por licencia, hash_prev (hash del
  eslabón anterior, 64 ceros en el primero) y hash sobre la serialización
  canónica (JSON con claves ordenadas: v, licenciaid, seq, hash_prev, timestamp
  ISO UTC con microsegundos, usuario, modulo, accion).
- Algoritmo: SHA-256; si la variable AUDIT_HMAC_KEY está definida se usa
  HMAC-SHA256 con esa clave (hash_alg = 'hmac-sha256'). Trade-off: sin clave,
  quien tenga acceso de escritura a la base y logre desactivar los triggers
  podría recalcular toda la cadena; con clave necesita además el secreto de la
  aplicación. Sin clave la cadena sigue detectando alteraciones accidentales o
  hechas sin recalcular. La verificación acepta eslabones sha256 anteriores al
  primer eslabón HMAC (rotación), pero nunca un retroceso a sha256 después.
- Concurrencia: en PostgreSQL, pg_advisory_xact_lock por licencia dentro de la
  transacción del insert; en otros motores (SQLite en pruebas), un cerrojo de
  proceso por licencia. En ambos casos UNIQUE (licenciaid, seq) impide la
  bifurcación y se reintenta ante colisión.
- El cálculo del hash vive únicamente aquí (calcular_hash); la base de datos
  solo valida la estructura del eslabón (trigger de la migración 006).
"""
import hashlib
import hmac
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
VERIFICACION_BITACORA = "VERIFICACION_BITACORA"
VISUALIZACION = "VISUALIZACION"
MODULO_AUTENTICACION = "Autenticación"
MODULO_INTEGRIDAD = "Integridad de Bitácora"

VERSION_CANONICA = 1
HASH_GENESIS = "0" * 64
ALG_SHA256 = "sha256"
ALG_HMAC = "hmac-sha256"
VARIABLE_HMAC = "AUDIT_HMAC_KEY"
_REINTENTOS_COLISION = 3

fallos_registro = 0

# Cerrojos de proceso por licencia (motores sin advisory locks, p. ej. SQLite)
_cerrojos_guard = threading.Lock()
_cerrojos: Dict[str, threading.Lock] = {}


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalizar_uuid(valor) -> Optional[uuid.UUID]:
    if isinstance(valor, uuid.UUID):
        return valor
    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError, AttributeError):
        return None


# ── Serialización canónica y hash (único punto de cálculo) ───────────────

def clave_hmac() -> Optional[bytes]:
    """Clave HMAC configurada (None si la variable no existe o está vacía)."""
    valor = os.getenv(VARIABLE_HMAC, "").strip()
    return valor.encode("utf-8") if valor else None


def timestamp_canonico(marca: datetime) -> str:
    """ISO 8601 en UTC con microsegundos. Un datetime sin zona se asume UTC
    (así se almacena en la base). Independiente de la zona de la sesión."""
    if marca.tzinfo is None:
        marca = marca.replace(tzinfo=timezone.utc)
    return marca.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def serializacion_canonica(licenciaid, seq: int, hash_prev: str, timestamp: datetime,
                           usuario: str, modulo: str, accion: str) -> bytes:
    documento = {
        "v": VERSION_CANONICA,
        "licenciaid": str(licenciaid),
        "seq": int(seq),
        "hash_prev": hash_prev,
        "timestamp": timestamp_canonico(timestamp),
        "usuario": usuario,
        "modulo": modulo,
        "accion": accion,
    }
    return json.dumps(documento, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def calcular_hash(licenciaid, seq: int, hash_prev: str, timestamp: datetime, usuario: str,
                  modulo: str, accion: str, alg: str = ALG_SHA256, clave: Optional[bytes] = None) -> str:
    """Hash hexadecimal (64) del eslabón. alg = sha256 | hmac-sha256 (requiere clave)."""
    datos = serializacion_canonica(licenciaid, seq, hash_prev, timestamp, usuario, modulo, accion)
    if alg == ALG_HMAC:
        if not clave:
            raise ValueError("hmac-sha256 requiere clave")
        return hmac.new(clave, datos, hashlib.sha256).hexdigest()
    if alg != ALG_SHA256:
        raise ValueError(f"Algoritmo de hash desconocido: {alg}")
    return hashlib.sha256(datos).hexdigest()


def _hash_registro(registro: models.BitacoraAuditoria, clave: Optional[bytes]) -> str:
    return calcular_hash(registro.licenciaid, registro.seq, registro.hash_prev, registro.timestamp,
                         registro.username, registro.modulo_accedido, registro.accion,
                         registro.hash_alg, clave)


# ── Bloqueo por licencia ─────────────────────────────────────────────────

def _clave_advisory(lid: uuid.UUID) -> int:
    """Entero de 64 bits con signo derivado del UUID (clave de pg_advisory_xact_lock)."""
    return int.from_bytes(hashlib.sha256(lid.bytes).digest()[:8], "big", signed=True)


def _es_postgresql(db) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except (AttributeError, SQLAlchemyError):
        return False


def _cerrojo_proceso(lid: uuid.UUID) -> threading.Lock:
    with _cerrojos_guard:
        return _cerrojos.setdefault(str(lid), threading.Lock())


def _ultimo_eslabon(db, lid: uuid.UUID):
    return (
        db.query(models.BitacoraAuditoria.seq, models.BitacoraAuditoria.hash)
        .filter(models.BitacoraAuditoria.licenciaid == lid, models.BitacoraAuditoria.seq.isnot(None))
        .order_by(models.BitacoraAuditoria.seq.desc())
        .first()
    )


def _insertar_eslabon(db, lid: uuid.UUID, username: str, modulo: str, accion: str) -> None:
    """Calcula y persiste el siguiente eslabón dentro de la transacción actual."""
    if _es_postgresql(db):
        # La zona UTC de la transacción garantiza que el valor almacenado (sea la
        # columna TIMESTAMP o TIMESTAMPTZ) coincida con el timestamp hasheado.
        db.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        db.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": _clave_advisory(lid)})
    ultimo = _ultimo_eslabon(db, lid)
    seq = (ultimo.seq + 1) if ultimo is not None else 1
    hash_prev = ultimo.hash if ultimo is not None else HASH_GENESIS
    clave = clave_hmac()
    alg = ALG_HMAC if clave else ALG_SHA256
    marca = ahora_utc()
    db.add(models.BitacoraAuditoria(
        licenciaid=lid, username=username, modulo_accedido=modulo, accion=accion, timestamp=marca,
        seq=seq, hash_prev=hash_prev, hash_alg=alg,
        hash=calcular_hash(lid, seq, hash_prev, marca, username, modulo, accion, alg, clave),
    ))
    db.commit()


def registrar_evento(db, licenciaid, username: str, modulo: str, accion: str = VISUALIZACION) -> bool:
    """Inserta un evento encadenado usando la sesión db recibida. Devuelve True si se persistió."""
    global fallos_registro
    lid = _normalizar_uuid(licenciaid)
    if lid is None:
        logger.warning("Auditoría omitida: licenciaid inválido (usuario=%s, modulo=%s, accion=%s)",
                       username, modulo, accion)
        return False
    username = str(username or "desconocido")[:100]
    modulo = str(modulo)[:100]
    accion = str(accion)[:100]
    cerrojo = None if _es_postgresql(db) else _cerrojo_proceso(lid)
    for intento in range(1, _REINTENTOS_COLISION + 1):
        try:
            if cerrojo is not None:
                with cerrojo:
                    _insertar_eslabon(db, lid, username, modulo, accion)
            else:
                _insertar_eslabon(db, lid, username, modulo, accion)
            return True
        except IntegrityError:
            db.rollback()
            if intento < _REINTENTOS_COLISION:
                logger.warning("Colisión de seq en la bitácora (licencia=%s, intento %d): se reintenta.", lid, intento)
                continue
            fallos_registro += 1
            logger.exception("No se pudo registrar el evento de auditoría tras %d colisiones (fallos acumulados=%d).",
                             _REINTENTOS_COLISION, fallos_registro)
            return False
        except SQLAlchemyError:
            fallos_registro += 1
            db.rollback()
            logger.exception("No se pudo registrar el evento de auditoría (fallos acumulados=%d).",
                             fallos_registro)
            return False
    return False


def registrar_evento_autonomo(licenciaid, username: str, modulo: str, accion: str = VISUALIZACION) -> bool:
    """Igual que registrar_evento pero abre y cierra su propia sesión de BD."""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        return registrar_evento(db, licenciaid, username, modulo, accion)
    finally:
        db.close()


# ── Verificación de la cadena ────────────────────────────────────────────

ESTADO_OK = "OK"
ESTADO_ROTO = "ROTO"
ESTADO_NO_VERIFICABLE = "NO_VERIFICABLE"


@dataclass
class ResultadoVerificacion:
    licenciaid: str
    integra: bool
    total_eslabones: int = 0
    verificados: int = 0
    pre_cadena: int = 0
    primer_seq_roto: Optional[int] = None
    motivo: str = ""
    hmac_configurado: bool = False
    ultimo_seq: Optional[int] = None
    ultimo_hash: Optional[str] = None
    detalle: List[dict] = field(default_factory=list)

    def resumen(self) -> Dict[str, str]:
        """Pares etiqueta/valor listos para la UI o exportación."""
        return {
            "Licencia": self.licenciaid,
            "Resultado": "Íntegra" if self.integra else "Rota",
            "Eslabones encadenados": str(self.total_eslabones),
            "Eslabones verificados": str(self.verificados),
            "Registros pre-cadena (anteriores a la migración 006)": str(self.pre_cadena),
            "Primer seq roto": "" if self.primer_seq_roto is None else str(self.primer_seq_roto),
            "Motivo": self.motivo,
            "HMAC configurado": "Sí" if self.hmac_configurado else "No",
            "Último seq": "" if self.ultimo_seq is None else str(self.ultimo_seq),
            "Último hash": self.ultimo_hash or "",
        }


def _iterar_cadena(db, lid: uuid.UUID) -> Iterator[models.BitacoraAuditoria]:
    consulta = (
        db.query(models.BitacoraAuditoria)
        .filter(models.BitacoraAuditoria.licenciaid == lid, models.BitacoraAuditoria.seq.isnot(None))
        .order_by(models.BitacoraAuditoria.seq.asc())
    )
    return consulta.yield_per(500)


def _fila_detalle(registro: models.BitacoraAuditoria, estado: str, motivo: str = "") -> dict:
    return {
        "seq": registro.seq,
        "timestamp": timestamp_canonico(registro.timestamp),
        "usuario": registro.username,
        "modulo": registro.modulo_accedido,
        "accion": registro.accion,
        "hash_alg": registro.hash_alg,
        "hash_prev": registro.hash_prev,
        "hash": registro.hash,
        "estado": estado,
        "motivo": motivo,
    }


def _motivo_eslabon(registro: models.BitacoraAuditoria, esperado_seq: int, esperado_prev: str,
                    hmac_visto: bool, clave: Optional[bytes]) -> Optional[str]:
    """Devuelve el motivo de ruptura de un eslabón o None si es válido."""
    if registro.seq != esperado_seq:
        if registro.seq > esperado_seq:
            return f"Hueco en la secuencia: se esperaba seq {esperado_seq} y se encontró {registro.seq} (posible borrado)"
        return f"Secuencia repetida o fuera de orden: seq {registro.seq} tras {esperado_seq - 1}"
    if registro.hash_prev != esperado_prev:
        return "hash_prev no coincide con el hash del eslabón anterior (inserción fuera de orden o alteración)"
    if registro.hash_alg not in (ALG_SHA256, ALG_HMAC):
        return f"Algoritmo desconocido: {registro.hash_alg}"
    if registro.hash_alg == ALG_SHA256 and hmac_visto:
        return "Retroceso de HMAC a SHA-256 después de un eslabón HMAC (posible recálculo sin clave)"
    if registro.hash_alg == ALG_HMAC and not clave:
        return ESTADO_NO_VERIFICABLE
    if _hash_registro(registro, clave) != registro.hash:
        return "El hash no corresponde al contenido del registro (campo alterado)"
    return None


def verificar_cadena(db, licenciaid, incluir_detalle: bool = True) -> ResultadoVerificacion:
    """Recorre la cadena de una licencia y devuelve íntegra/rota con el primer seq roto y el motivo.

    Solo se detiene en el primer eslabón roto para el veredicto, pero el detalle
    incluye todos los eslabones con su estado (los posteriores a la ruptura se
    marcan como no verificados) para el reporte exportable.
    """
    lid = _normalizar_uuid(licenciaid)
    if lid is None:
        raise ValueError("licenciaid inválido")
    clave = clave_hmac()
    resultado = ResultadoVerificacion(licenciaid=str(lid), integra=True, hmac_configurado=bool(clave))
    resultado.pre_cadena = (
        db.query(models.BitacoraAuditoria)
        .filter(models.BitacoraAuditoria.licenciaid == lid, models.BitacoraAuditoria.seq.is_(None))
        .count()
    )
    esperado_seq, esperado_prev, hmac_visto = 1, HASH_GENESIS, False
    for registro in _iterar_cadena(db, lid):
        resultado.total_eslabones += 1
        if not resultado.integra:
            if incluir_detalle:
                resultado.detalle.append(_fila_detalle(registro, "NO_VERIFICADO", "Posterior a la primera ruptura"))
            continue
        motivo = _motivo_eslabon(registro, esperado_seq, esperado_prev, hmac_visto, clave)
        if motivo == ESTADO_NO_VERIFICABLE:
            resultado.integra = False
            resultado.primer_seq_roto = registro.seq
            resultado.motivo = (f"El eslabón {registro.seq} usa HMAC y {VARIABLE_HMAC} no está configurada: "
                                "no es posible verificarlo")
            if incluir_detalle:
                resultado.detalle.append(_fila_detalle(registro, ESTADO_NO_VERIFICABLE, resultado.motivo))
            continue
        if motivo is not None:
            resultado.integra = False
            resultado.primer_seq_roto = registro.seq
            resultado.motivo = motivo
            if incluir_detalle:
                resultado.detalle.append(_fila_detalle(registro, ESTADO_ROTO, motivo))
            continue
        resultado.verificados += 1
        hmac_visto = hmac_visto or registro.hash_alg == ALG_HMAC
        esperado_seq, esperado_prev = registro.seq + 1, registro.hash
        resultado.ultimo_seq, resultado.ultimo_hash = registro.seq, registro.hash
        if incluir_detalle:
            resultado.detalle.append(_fila_detalle(registro, ESTADO_OK))
    if resultado.integra:
        resultado.motivo = ("Cadena íntegra" if resultado.total_eslabones else "Sin eslabones encadenados todavía")
    return resultado
