"""
casos_alerta.py: persistencia y ciclo de vida de los Casos de Alerta.

Base legal: Art. 29 (examen y fundamento), Art. 30 (RTS) y Art. 34 (conservación
de registros, mínimo 5 años) de la Ley 6593 (Guatemala). Recomendación 20 GAFI.

Clave estable del caso
----------------------
Un caso se identifica de forma determinista, sin depender de la sesión ni del
nombre del archivo, por la tripleta (licencia, lote, cliente):

  * hash_lote  = SHA-256 del contenido canónico del lote de transacciones
                 (columnas ordenadas alfabéticamente, filas ordenadas, todo
                 como texto, CSV UTF-8). Dos archivos con las mismas
                 transacciones producen el mismo hash aunque cambie el nombre
                 o el orden de las filas.
  * cliente    = identificador del cliente normalizado (recortado, sin espacios
                 repetidos, mayúsculas).
  * clave_caso = SHA-256 hex de "licenciaid|hash_lote|cliente".

La restricción UNIQUE (licenciaid, clave_caso) garantiza un solo registro por
caso y, al recargar el mismo lote, permite rehidratar el estado guardado.

Flujo de cuatro ojos (segregación de funciones)
----------------------------------------------
  * Cualquier rol operativo (admin, oficial, analista) examina, descarta o
    PROPONE "Sospechosa_Propuesta" con fundamento.
  * Solo admin u oficial APRUEBA "Sospechosa_Confirmada", y nunca quien propuso.
  * "Sospechosa_Confirmada" es terminal: el RTS se emite en Reportes.
  * El auditor solo observa.

Seguridad (OWASP A01/A03): toda consulta filtra por licenciaid y usa el ORM
con parámetros ligados. El licenciaid, usuario y rol provienen siempre de la
sesión autenticada en el servidor, nunca de campos editables.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from . import auditoria, models

ESTADOS = models.ESTADOS_CASO
ESTADO_INICIAL = "Inusual_Pendiente"
ESTADO_PROPUESTA = "Sospechosa_Propuesta"
ESTADO_CONFIRMADA = "Sospechosa_Confirmada"

ROLES_OPERATIVOS = frozenset({"admin", "oficial", "analista"})
ROLES_APROBACION = frozenset({"admin", "oficial"})

ACCION_CLASIFICAR = "CLASIFICAR"
ACCION_PROPONER = "PROPONER_SOSPECHOSA"
ACCION_APROBAR = "APROBAR_SOSPECHOSA"
ACCION_RECHAZAR = "RECHAZAR_PROPUESTA"
ACCION_CREAR = "CREAR"

MODULO_AUDITORIA = "Casos de Alerta"
MIN_CARACTERES_FUNDAMENTO = 10
MAX_CARACTERES_FUNDAMENTO = 4000
MAX_CARACTERES_CLIENTE = 200

# Transiciones permitidas: estado actual -> estados destino.
TRANSICIONES = {
    "Inusual_Pendiente":    {"Inusual_Examinada", "Sospechosa_Propuesta", "Descartada"},
    "Inusual_Examinada":    {"Sospechosa_Propuesta", "Descartada"},
    "Descartada":           {"Inusual_Examinada", "Sospechosa_Propuesta"},
    "Sospechosa_Propuesta": {"Inusual_Examinada", "Descartada", "Sospechosa_Confirmada"},
    "Sospechosa_Confirmada": set(),
}


class ErrorCasoAlerta(ValueError):
    """Regla de negocio incumplida (estado, fundamento, transición)."""


class PermisoCasoDenegado(ErrorCasoAlerta):
    """El rol o el usuario no está autorizado para la transición solicitada."""


# ── Utilidades de identidad ──────────────────────────────────────────────

def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def normalizar_usuario(usuario) -> str:
    return re.sub(r"\s+", " ", str(usuario or "")).strip().lower()[:100]


def normalizar_cliente(cliente) -> str:
    texto = re.sub(r"\s+", " ", str(cliente if cliente is not None else "")).strip().upper()
    if not texto:
        raise ErrorCasoAlerta("El identificador de cliente está vacío.")
    return texto[:MAX_CARACTERES_CLIENTE]


def calcular_hash_lote(df) -> str:
    """SHA-256 del lote en forma canónica (independiente de nombre y orden de filas)."""
    canon = df.astype(str)
    canon = canon.reindex(sorted(canon.columns, key=str), axis=1)
    if len(canon.columns) > 0:
        canon = canon.sort_values(by=list(canon.columns), kind="mergesort")
    csv = canon.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(csv.encode("utf-8")).hexdigest()


def clave_caso(licenciaid, hash_lote: str, cliente: str) -> str:
    base = f"{_as_uuid(licenciaid)}|{hash_lote}|{normalizar_cliente(cliente)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _validar_hash(hash_lote: str) -> str:
    if not isinstance(hash_lote, str) or not re.fullmatch(r"[0-9a-f]{64}", hash_lote):
        raise ErrorCasoAlerta("hash_lote inválido: se espera SHA-256 hexadecimal.")
    return hash_lote


def _validar_fundamento(fundamento, estado_destino: str) -> str:
    texto = re.sub(r"\s+", " ", str(fundamento or "")).strip()
    if len(texto) > MAX_CARACTERES_FUNDAMENTO:
        raise ErrorCasoAlerta(f"El fundamento supera los {MAX_CARACTERES_FUNDAMENTO} caracteres.")
    if estado_destino != ESTADO_INICIAL and len(texto) < MIN_CARACTERES_FUNDAMENTO:
        raise ErrorCasoAlerta(
            f"El fundamento del examen es obligatorio (Art. 29 Ley 6593): mínimo {MIN_CARACTERES_FUNDAMENTO} caracteres."
        )
    return texto


# ── Consultas (siempre filtradas por licenciaid) ─────────────────────────

def listar_casos_lote(db: Session, licenciaid, hash_lote: str) -> list:
    return (
        db.query(models.CasoAlerta)
        .filter(
            models.CasoAlerta.licenciaid == _as_uuid(licenciaid),
            models.CasoAlerta.hash_lote == _validar_hash(hash_lote),
        )
        .order_by(models.CasoAlerta.cliente)
        .all()
    )


def obtener_caso(db: Session, licenciaid, caso_id) -> Optional[models.CasoAlerta]:
    return (
        db.query(models.CasoAlerta)
        .filter(models.CasoAlerta.id == _as_uuid(caso_id), models.CasoAlerta.licenciaid == _as_uuid(licenciaid))
        .first()
    )


def obtener_caso_por_clave(db: Session, licenciaid, hash_lote: str, cliente) -> Optional[models.CasoAlerta]:
    return (
        db.query(models.CasoAlerta)
        .filter(
            models.CasoAlerta.licenciaid == _as_uuid(licenciaid),
            models.CasoAlerta.clave_caso == clave_caso(licenciaid, _validar_hash(hash_lote), cliente),
        )
        .first()
    )


def historial_caso(db: Session, licenciaid, caso_id) -> list:
    return (
        db.query(models.CasoAlertaHistorial)
        .filter(
            models.CasoAlertaHistorial.caso_id == _as_uuid(caso_id),
            models.CasoAlertaHistorial.licenciaid == _as_uuid(licenciaid),
        )
        .order_by(models.CasoAlertaHistorial.registrado_en, models.CasoAlertaHistorial.id)
        .all()
    )


# ── Escritura ────────────────────────────────────────────────────────────

def _registrar_historial(db: Session, caso: models.CasoAlerta, estado_anterior, accion: str,
                         fundamento: str, usuario: str, rol: str) -> None:
    db.add(models.CasoAlertaHistorial(
        licenciaid=caso.licenciaid,
        caso_id=caso.id,
        estado_anterior=estado_anterior,
        estado_nuevo=caso.estado,
        accion=accion,
        fundamento=fundamento,
        usuario=usuario[:100],
        rol=rol,
        registrado_en=models.ahora_utc(),
    ))


def obtener_o_crear_caso(db: Session, licenciaid, hash_lote: str, cliente, usuario: str, rol: str,
                         score_max=None, nivel_riesgo=None, nombre_archivo=None) -> models.CasoAlerta:
    """Devuelve el caso persistido; si no existe lo crea en estado inicial."""
    if rol not in ROLES_OPERATIVOS:
        raise PermisoCasoDenegado("Su rol no puede gestionar casos de alerta.")
    existente = obtener_caso_por_clave(db, licenciaid, hash_lote, cliente)
    if existente:
        return existente
    usuario_n = normalizar_usuario(usuario)
    caso = models.CasoAlerta(
        licenciaid=_as_uuid(licenciaid),
        clave_caso=clave_caso(licenciaid, hash_lote, cliente),
        hash_lote=hash_lote,
        cliente=normalizar_cliente(cliente),
        nombre_archivo=(str(nombre_archivo)[:255] if nombre_archivo else None),
        estado=ESTADO_INICIAL,
        fundamento="",
        score_max=(float(score_max) if score_max is not None else None),
        nivel_riesgo=(str(nivel_riesgo)[:30] if nivel_riesgo else None),
        creado_por=usuario_n,
        creado_en=models.ahora_utc(),
        actualizado_por=usuario_n,
        actualizado_en=models.ahora_utc(),
    )
    db.add(caso)
    db.flush()
    _registrar_historial(db, caso, None, ACCION_CREAR, "", usuario_n, rol)
    db.commit()
    db.refresh(caso)
    return caso


def transiciones_permitidas(caso: models.CasoAlerta, usuario: str, rol: str) -> list:
    """Estados destino que `usuario` con `rol` puede aplicar al caso (para la UI)."""
    if rol not in ROLES_OPERATIVOS:
        return []
    destinos = []
    for destino in ESTADOS:
        try:
            _validar_transicion(caso, destino, normalizar_usuario(usuario), rol)
        except ErrorCasoAlerta:
            continue
        destinos.append(destino)
    return destinos


def _validar_transicion(caso: models.CasoAlerta, destino: str, usuario_n: str, rol: str) -> str:
    """Devuelve la acción de historial o lanza ErrorCasoAlerta/PermisoCasoDenegado."""
    if destino not in ESTADOS:
        raise ErrorCasoAlerta(f"Estado desconocido: {destino}")
    if rol not in ROLES_OPERATIVOS:
        raise PermisoCasoDenegado("Su rol no puede clasificar casos de alerta.")
    if destino == caso.estado:
        raise ErrorCasoAlerta("El caso ya se encuentra en ese estado.")
    if destino not in TRANSICIONES.get(caso.estado, set()):
        raise ErrorCasoAlerta(f"Transición no permitida: {caso.estado} -> {destino}.")
    if destino == ESTADO_CONFIRMADA:
        if rol not in ROLES_APROBACION:
            raise PermisoCasoDenegado("Solo un Oficial de Cumplimiento o Administrador puede confirmar una operación sospechosa.")
        if normalizar_usuario(caso.propuesto_por) == usuario_n:
            raise PermisoCasoDenegado("Principio de cuatro ojos: quien propuso el caso no puede aprobarlo.")
        return ACCION_APROBAR
    if caso.estado == ESTADO_PROPUESTA:
        es_proponente = normalizar_usuario(caso.propuesto_por) == usuario_n
        if rol not in ROLES_APROBACION and not es_proponente:
            raise PermisoCasoDenegado("Solo el proponente o un Oficial/Administrador puede retirar una propuesta.")
        return ACCION_RECHAZAR
    if destino == ESTADO_PROPUESTA:
        return ACCION_PROPONER
    return ACCION_CLASIFICAR


def cambiar_estado(db: Session, licenciaid, caso_id, nuevo_estado: str, fundamento,
                   usuario: str, rol: str) -> models.CasoAlerta:
    """Aplica una transición de estado con validación, historial y auditoría."""
    caso = obtener_caso(db, licenciaid, caso_id)
    if caso is None:
        raise ErrorCasoAlerta("El caso no existe o no pertenece a su licencia.")
    usuario_n = normalizar_usuario(usuario)
    if not usuario_n:
        raise ErrorCasoAlerta("Usuario de sesión no identificado.")
    accion = _validar_transicion(caso, nuevo_estado, usuario_n, rol)
    texto = _validar_fundamento(fundamento, nuevo_estado)

    estado_anterior = caso.estado
    ahora = models.ahora_utc()
    caso.estado = nuevo_estado
    caso.fundamento = texto
    caso.actualizado_por = usuario_n
    caso.actualizado_en = ahora
    if accion == ACCION_PROPONER:
        caso.propuesto_por = usuario_n
        caso.propuesto_en = ahora
        caso.aprobado_por = None
        caso.aprobado_en = None
    elif accion == ACCION_APROBAR:
        caso.aprobado_por = usuario_n
        caso.aprobado_en = ahora
        caso.fecha_clasificacion_sospechosa = ahora.date()
    elif accion == ACCION_RECHAZAR:
        caso.aprobado_por = None
        caso.aprobado_en = None
    _registrar_historial(db, caso, estado_anterior, accion, texto, usuario_n, rol)
    db.commit()
    db.refresh(caso)
    auditoria.registrar_evento(
        db, licenciaid, usuario_n, MODULO_AUDITORIA,
        f"{auditoria.CAMBIO_ESTADO_CASO}:{estado_anterior}->{nuevo_estado}",
    )
    return caso


# ── Rehidratación en el DataFrame de casos ───────────────────────────────

COLUMNAS_ESTADO = ("Estado_Alerta", "Fundamento_Examen", "Fecha_Clasificacion_Sospechosa")


def asegurar_columnas_estado(casos) -> None:
    """Crea in situ las columnas del ciclo de vida si el DataFrame no las trae."""
    if "Estado_Alerta" not in casos.columns:
        casos["Estado_Alerta"] = ESTADO_INICIAL
    if "Fundamento_Examen" not in casos.columns:
        casos["Fundamento_Examen"] = ""
    if "Fecha_Clasificacion_Sospechosa" not in casos.columns:
        casos["Fecha_Clasificacion_Sospechosa"] = None


def rehidratar_dataframe(casos, registros: Iterable[models.CasoAlerta]) -> int:
    """Copia in situ el estado persistido sobre el DataFrame `casos` (por cliente).

    Devuelve el número de filas actualizadas. Se modifica el mismo objeto para que
    Resumen Ejecutivo y Reportes (que leen `casos` desde la sesión) vean el estado.
    """
    asegurar_columnas_estado(casos)
    if "Cliente" not in casos.columns or len(casos) == 0:
        return 0
    por_cliente = {r.cliente: r for r in registros}
    if not por_cliente:
        return 0
    if casos["Fecha_Clasificacion_Sospechosa"].dtype != object:
        casos["Fecha_Clasificacion_Sospechosa"] = casos["Fecha_Clasificacion_Sospechosa"].astype(object)
    actualizadas = 0
    for idx, cliente in casos["Cliente"].items():
        try:
            registro = por_cliente.get(normalizar_cliente(cliente))
        except ErrorCasoAlerta:
            registro = None
        if registro is None:
            continue
        casos.at[idx, "Estado_Alerta"] = registro.estado
        casos.at[idx, "Fundamento_Examen"] = registro.fundamento or ""
        fecha = registro.fecha_clasificacion_sospechosa
        casos.at[idx, "Fecha_Clasificacion_Sospechosa"] = fecha if isinstance(fecha, date) else None
        actualizadas += 1
    return actualizadas
