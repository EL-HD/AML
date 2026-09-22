"""
screening_repo.py: persistencia y flujo de revisión del screening de sanciones.

Complementa backend/screening.py (motor puro). Aquí viven:
  * Carga de listas (solo admin): parseo validado, versión, hash SHA-256,
    desactivación de la versión anterior de la misma fuente y auditoría.
  * Construcción del índice de búsqueda a partir de las listas activas
    (cacheado por proceso mientras no cambie el conjunto de listas activas).
  * Ejecución del screening para una licencia: crea coincidencias nuevas y
    conserva las ya revisadas (clave única licencia + cliente + entrada).
  * Decisión humana (admin/oficial) con fundamento obligatorio, historial
    append-only (ScreeningDecisiones) y evento en BitacoraAuditoria. Una
    coincidencia confirmada se vincula al Caso de Alerta del lote (T1) cuando
    el cliente pertenece al análisis cargado.

Seguridad (OWASP A01/A03): toda consulta de coincidencias filtra por
licenciaid; rol y usuario llegan desde la sesión autenticada del servidor.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import insert
from sqlalchemy.orm import Session

from . import auditoria, casos_alerta, models, screening

ESTADOS = models.ESTADOS_COINCIDENCIA
ESTADO_PENDIENTE, ESTADO_DESCARTADA, ESTADO_CONFIRMADA = ESTADOS

ROLES_CARGA = frozenset({"admin"})
ROLES_REVISION = frozenset({"admin", "oficial"})
ROLES_LECTURA = frozenset({"admin", "oficial", "analista", "auditor"})

ORIGEN_CLIENTE = "Cliente"
ORIGEN_DESTINO = "Cliente_Destino"
ORIGENES = (ORIGEN_CLIENTE, ORIGEN_DESTINO)

MODULO_AUDITORIA = "Listas de Sanciones"
CARGA_LISTA_SANCION = "CARGA_LISTA_SANCION"
EJECUCION_SCREENING = "EJECUCION_SCREENING"
DECISION_SCREENING = "DECISION_SCREENING"

MIN_CARACTERES_FUNDAMENTO = 10
MAX_CARACTERES_FUNDAMENTO = 4000
MAX_CONSULTAS_POR_EJECUCION = 20000
COLUMNA_SENAL = "Screening_Sanciones"
SENAL_SIN = "Sin coincidencia"

_cache_indice: Dict[Tuple[str, ...], screening.IndiceScreening] = {}


class ErrorScreeningRepo(ValueError):
    """Regla de negocio incumplida."""


class PermisoScreeningDenegado(ErrorScreeningRepo):
    """Rol no autorizado."""


def _as_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ErrorScreeningRepo("Identificador inválido.") from exc


def _usuario(usuario) -> str:
    texto = casos_alerta.normalizar_usuario(usuario)
    if not texto:
        raise ErrorScreeningRepo("Usuario de sesión no identificado.")
    return texto


def _validar_fundamento(fundamento) -> str:
    texto = re.sub(r"\s+", " ", str(fundamento or "")).strip()
    if len(texto) < MIN_CARACTERES_FUNDAMENTO:
        raise ErrorScreeningRepo(
            f"El fundamento de la decisión es obligatorio: mínimo {MIN_CARACTERES_FUNDAMENTO} caracteres."
        )
    if len(texto) > MAX_CARACTERES_FUNDAMENTO:
        raise ErrorScreeningRepo(f"El fundamento supera los {MAX_CARACTERES_FUNDAMENTO} caracteres.")
    return texto


# ── Listas ───────────────────────────────────────────────────────────────

def listas_activas(db: Session) -> List[models.ListaSancion]:
    return (
        db.query(models.ListaSancion)
        .filter(models.ListaSancion.activa.is_(True))
        .order_by(models.ListaSancion.fuente)
        .all()
    )


def listar_listas(db: Session, limite: int = 50) -> List[models.ListaSancion]:
    return (
        db.query(models.ListaSancion)
        .order_by(models.ListaSancion.cargada_en.desc())
        .limit(max(1, min(int(limite), 500)))
        .all()
    )


def cargar_lista(db: Session, fuente: str, nombre_archivo: str, principal: bytes, usuario: str, rol: str,
                 licenciaid=None, secundario: Optional[bytes] = None, origen: str = "carga_manual",
                 version: Optional[str] = None) -> models.ListaSancion:
    """Parsea, valida y persiste una lista; desactiva la versión anterior de la misma fuente."""
    if rol not in ROLES_CARGA:
        raise PermisoScreeningDenegado("Solo un Administrador puede cargar listas de sanciones.")
    if fuente not in screening.FUENTES:
        raise ErrorScreeningRepo("Fuente de lista desconocida.")
    if origen not in ("carga_manual", "descarga_oficial"):
        raise ErrorScreeningRepo("Origen de carga desconocido.")
    usuario_n = _usuario(usuario)
    resultado = screening.parsear_por_fuente(fuente, principal, secundario)
    duplicada = (
        db.query(models.ListaSancion)
        .filter(models.ListaSancion.fuente == fuente, models.ListaSancion.hash_sha256 == resultado.hash_sha256,
                models.ListaSancion.activa.is_(True))
        .first()
    )
    if duplicada is not None:
        raise ErrorScreeningRepo("Esta versión de la lista (mismo SHA-256) ya está cargada y activa.")

    ahora = models.ahora_utc()
    version_txt = re.sub(r"\s+", " ", str(version or ahora.strftime("%Y-%m-%dT%H:%M:%SZ"))).strip()[:60]
    db.query(models.ListaSancion).filter(
        models.ListaSancion.fuente == fuente, models.ListaSancion.activa.is_(True)
    ).update({models.ListaSancion.activa: False}, synchronize_session=False)

    lista = models.ListaSancion(
        fuente=fuente, version=version_txt, nombre_archivo=str(nombre_archivo)[:255],
        hash_sha256=resultado.hash_sha256, cantidad_entradas=len(resultado.entradas),
        filas_rechazadas=resultado.filas_rechazadas, origen=origen, activa=True,
        cargada_por=usuario_n, cargada_en=ahora,
    )
    db.add(lista)
    db.flush()
    filas = [
        {
            "id": uuid.uuid4(), "lista_id": lista.id, "fuente": fuente, "referencia": e.referencia[:60],
            "nombre": e.nombre[:300], "nombre_normalizado": screening.normalizar_nombre(e.nombre)[:300],
            "tipo": (e.tipo or None), "programa": (e.programa or None), "nacionalidad": (e.nacionalidad or None),
            "alias_json": json.dumps(list(e.alias), ensure_ascii=False),
        }
        for e in resultado.entradas
    ]
    for inicio in range(0, len(filas), 2000):
        db.execute(insert(models.ListaSancionEntrada), filas[inicio:inicio + 2000])
    db.commit()
    db.refresh(lista)
    _cache_indice.clear()
    # Las listas son globales; el evento se registra bajo la licencia del administrador que las cargó.
    auditoria.registrar_evento(db, licenciaid, usuario_n, MODULO_AUDITORIA,
                               f"{CARGA_LISTA_SANCION}:{fuente}:{len(resultado.entradas)}")
    return lista


def _entradas_de(db: Session, listas: Iterable[models.ListaSancion]) -> List[screening.EntradaLista]:
    ids = [l.id for l in listas]
    if not ids:
        return []
    salida = []
    consulta = db.query(models.ListaSancionEntrada).filter(models.ListaSancionEntrada.lista_id.in_(ids))
    for fila in consulta.yield_per(2000):
        try:
            alias = tuple(str(a) for a in json.loads(fila.alias_json or "[]"))
        except (TypeError, ValueError):
            alias = ()
        salida.append(screening.EntradaLista(
            fuente=fila.fuente, referencia=fila.referencia, nombre=fila.nombre, tipo=fila.tipo or "",
            programa=fila.programa or "", nacionalidad=fila.nacionalidad or "", alias=alias,
            id_entrada=str(fila.id),
        ))
    return salida


def construir_indice(db: Session) -> Tuple[screening.IndiceScreening, List[models.ListaSancion]]:
    """Índice sobre las listas activas; se cachea por proceso mientras no cambien."""
    listas = listas_activas(db)
    clave = tuple(sorted(str(l.id) for l in listas))
    indice = _cache_indice.get(clave)
    if indice is None:
        indice = screening.IndiceScreening(_entradas_de(db, listas))
        _cache_indice.clear()
        _cache_indice[clave] = indice
    return indice, listas


# ── Ejecución ────────────────────────────────────────────────────────────

def _limpiar_consulta(nombre) -> str:
    texto = re.sub(r"\s+", " ", str(nombre if nombre is not None else "")).strip()
    if texto.lower() in ("", "nan", "none", "nat"):
        return ""
    return texto[:200]


def ejecutar_screening(db: Session, licenciaid, consultas: Iterable[Tuple[str, str]], usuario: str, rol: str,
                       umbral: float = screening.UMBRAL_POR_DEFECTO, hash_lote: Optional[str] = None) -> dict:
    """Evalúa (nombre, origen) contra las listas activas y persiste coincidencias nuevas.

    Devuelve un resumen: consultas, coincidencias, nuevas, existentes, listas y segundos.
    """
    if rol not in ROLES_REVISION:
        raise PermisoScreeningDenegado("Solo un Oficial de Cumplimiento o Administrador puede ejecutar el screening.")
    lid = _as_uuid(licenciaid)
    usuario_n = _usuario(usuario)
    umbral = screening.validar_umbral(umbral)
    if hash_lote is not None and not re.fullmatch(r"[0-9a-f]{64}", str(hash_lote)):
        raise ErrorScreeningRepo("hash_lote inválido.")
    inicio = time.perf_counter()
    indice, listas = construir_indice(db)
    if not listas:
        raise ErrorScreeningRepo("No hay listas de sanciones activas. Un Administrador debe cargarlas.")
    lista_por_fuente = {l.fuente: l for l in listas}

    pendientes: Dict[Tuple[str, str], str] = {}
    for nombre, origen in consultas:
        texto = _limpiar_consulta(nombre)
        if not texto or origen not in ORIGENES:
            continue
        clave_n = screening.normalizar_nombre(texto)
        if clave_n and clave_n not in pendientes:
            pendientes[clave_n] = (texto, origen)
        if len(pendientes) >= MAX_CONSULTAS_POR_EJECUCION:
            break

    existentes = {
        (c.cliente_normalizado, str(c.entrada_id))
        for c in db.query(models.ScreeningCoincidencia.cliente_normalizado, models.ScreeningCoincidencia.entrada_id)
        .filter(models.ScreeningCoincidencia.licenciaid == lid)
    }
    nuevas: List[dict] = []
    total = 0
    ahora = models.ahora_utc()
    for clave_n, (texto, origen) in pendientes.items():
        for coincidencia in indice.buscar(texto, umbral):
            total += 1
            if coincidencia.id_entrada is None or (clave_n, coincidencia.id_entrada) in existentes:
                continue
            existentes.add((clave_n, coincidencia.id_entrada))
            nuevas.append({
                "id": uuid.uuid4(), "licenciaid": lid, "cliente": texto, "cliente_normalizado": clave_n[:300],
                "origen": origen, "hash_lote": hash_lote, "lista_id": lista_por_fuente[coincidencia.fuente].id,
                "entrada_id": uuid.UUID(coincidencia.id_entrada), "fuente": coincidencia.fuente,
                "referencia": coincidencia.referencia[:60], "nombre_lista": coincidencia.nombre_lista[:300],
                "alias_coincidente": (coincidencia.alias_coincidente or None),
                "puntaje": float(coincidencia.puntaje), "motivo": coincidencia.motivo[:300],
                "estado": ESTADO_PENDIENTE, "fundamento": "", "detectado_por": usuario_n,
                "detectado_en": ahora, "actualizado_en": ahora,
            })
    for i in range(0, len(nuevas), 1000):
        db.execute(insert(models.ScreeningCoincidencia), nuevas[i:i + 1000])
    db.commit()
    auditoria.registrar_evento(db, lid, usuario_n, MODULO_AUDITORIA, f"{EJECUCION_SCREENING}:{len(nuevas)}")
    return {
        "consultas": len(pendientes), "coincidencias": total, "nuevas": len(nuevas),
        "existentes": total - len(nuevas), "listas": [l.fuente for l in listas],
        "segundos": round(time.perf_counter() - inicio, 3), "umbral": umbral,
    }


# ── Consultas (siempre por licenciaid) ────────────────────────────────────

def listar_coincidencias(db: Session, licenciaid, estado: Optional[str] = None,
                         limite: int = 500) -> List[models.ScreeningCoincidencia]:
    consulta = db.query(models.ScreeningCoincidencia).filter(
        models.ScreeningCoincidencia.licenciaid == _as_uuid(licenciaid)
    )
    if estado is not None:
        if estado not in ESTADOS:
            raise ErrorScreeningRepo("Estado desconocido.")
        consulta = consulta.filter(models.ScreeningCoincidencia.estado == estado)
    return (
        consulta.order_by(models.ScreeningCoincidencia.puntaje.desc(), models.ScreeningCoincidencia.cliente)
        .limit(max(1, min(int(limite), 5000)))
        .all()
    )


def obtener_coincidencia(db: Session, licenciaid, coincidencia_id) -> Optional[models.ScreeningCoincidencia]:
    return (
        db.query(models.ScreeningCoincidencia)
        .filter(models.ScreeningCoincidencia.id == _as_uuid(coincidencia_id),
                models.ScreeningCoincidencia.licenciaid == _as_uuid(licenciaid))
        .first()
    )


def historial_decisiones(db: Session, licenciaid, coincidencia_id) -> List[models.ScreeningDecision]:
    return (
        db.query(models.ScreeningDecision)
        .filter(models.ScreeningDecision.coincidencia_id == _as_uuid(coincidencia_id),
                models.ScreeningDecision.licenciaid == _as_uuid(licenciaid))
        .order_by(models.ScreeningDecision.registrado_en, models.ScreeningDecision.id)
        .all()
    )


def coincidencias_cliente(db: Session, licenciaid, cliente) -> List[models.ScreeningCoincidencia]:
    clave = screening.normalizar_nombre(_limpiar_consulta(cliente))
    if not clave:
        return []
    return (
        db.query(models.ScreeningCoincidencia)
        .filter(models.ScreeningCoincidencia.licenciaid == _as_uuid(licenciaid),
                models.ScreeningCoincidencia.cliente_normalizado == clave[:300])
        .order_by(models.ScreeningCoincidencia.puntaje.desc())
        .all()
    )


def senales_por_cliente(db: Session, licenciaid) -> Dict[str, str]:
    """cliente_normalizado -> 'Confirmada' | 'Pendiente' (las descartadas no generan señal)."""
    senales: Dict[str, str] = {}
    filas = (
        db.query(models.ScreeningCoincidencia.cliente_normalizado, models.ScreeningCoincidencia.estado)
        .filter(models.ScreeningCoincidencia.licenciaid == _as_uuid(licenciaid),
                models.ScreeningCoincidencia.estado != ESTADO_DESCARTADA)
    )
    for cliente_n, estado in filas:
        if estado == ESTADO_CONFIRMADA or cliente_n not in senales:
            senales[cliente_n] = estado
    return senales


def marcar_dataframe(casos, senales: Dict[str, str]) -> int:
    """Añade/actualiza in situ la columna Screening_Sanciones en el DataFrame de casos."""
    if COLUMNA_SENAL not in casos.columns:
        casos[COLUMNA_SENAL] = SENAL_SIN
    if "Cliente" not in casos.columns or not senales:
        return 0
    marcadas = 0
    for idx, cliente in casos["Cliente"].items():
        senal = senales.get(screening.normalizar_nombre(_limpiar_consulta(cliente)))
        if senal:
            casos.at[idx, COLUMNA_SENAL] = senal
            marcadas += 1
    return marcadas


# ── Decisión humana ──────────────────────────────────────────────────────

def decidir(db: Session, licenciaid, coincidencia_id, nuevo_estado: str, fundamento, usuario: str, rol: str,
            hash_lote: Optional[str] = None, score_max=None, nivel_riesgo=None) -> models.ScreeningCoincidencia:
    """Descarta o confirma una coincidencia con fundamento obligatorio y traza completa."""
    if rol not in ROLES_REVISION:
        raise PermisoScreeningDenegado("Solo un Oficial de Cumplimiento o Administrador puede decidir sobre coincidencias.")
    if nuevo_estado not in (ESTADO_DESCARTADA, ESTADO_CONFIRMADA):
        raise ErrorScreeningRepo("La decisión debe ser Descartada o Confirmada.")
    lid = _as_uuid(licenciaid)
    usuario_n = _usuario(usuario)
    texto = _validar_fundamento(fundamento)
    coincidencia = obtener_coincidencia(db, lid, coincidencia_id)
    if coincidencia is None:
        raise ErrorScreeningRepo("La coincidencia no existe o no pertenece a su licencia.")
    if coincidencia.estado == nuevo_estado:
        raise ErrorScreeningRepo("La coincidencia ya se encuentra en ese estado.")

    estado_anterior = coincidencia.estado
    ahora = models.ahora_utc()
    coincidencia.estado = nuevo_estado
    coincidencia.fundamento = texto
    coincidencia.revisor = usuario_n
    coincidencia.revisado_en = ahora
    coincidencia.actualizado_en = ahora
    lote = hash_lote or coincidencia.hash_lote
    if nuevo_estado == ESTADO_CONFIRMADA and lote and coincidencia.origen == ORIGEN_CLIENTE:
        caso = casos_alerta.obtener_o_crear_caso(
            db, lid, lote, coincidencia.cliente, usuario_n, rol, score_max=score_max, nivel_riesgo=nivel_riesgo,
        )
        coincidencia.caso_id = caso.id
    db.add(models.ScreeningDecision(
        licenciaid=lid, coincidencia_id=coincidencia.id, estado_anterior=estado_anterior,
        estado_nuevo=nuevo_estado, fundamento=texto, revisor=usuario_n, rol=rol, registrado_en=ahora,
    ))
    db.commit()
    db.refresh(coincidencia)
    auditoria.registrar_evento(db, lid, usuario_n, MODULO_AUDITORIA,
                               f"{DECISION_SCREENING}:{estado_anterior}->{nuevo_estado}")
    return coincidencia


def resumen_estados(db: Session, licenciaid) -> Dict[str, int]:
    conteo = {e: 0 for e in ESTADOS}
    for c in listar_coincidencias(db, licenciaid, limite=5000):
        conteo[c.estado] = conteo.get(c.estado, 0) + 1
    return conteo


def formato_fecha(valor: Optional[datetime]) -> str:
    return valor.strftime("%Y-%m-%d %H:%M") if isinstance(valor, datetime) else "--"
