"""
mod_sesion.py: Sovereign AML Session Snapshot
Exporta e importa análisis completos en formato .saml (ZIP interno).
"""
import io
import json
import logging
import zipfile
from datetime import datetime, timezone

import pandas as pd

from backend import auditoria
from backend.config_aml import validar_config

logger = logging.getLogger(__name__)

# Límites de importación (S-08): tamaño comprimido, descomprimido y filas.
MAX_BYTES_COMPRIMIDO = 25 * 1024 * 1024
MAX_BYTES_DESCOMPRIMIDO = 100 * 1024 * 1024
MAX_FILAS = 200_000
MAX_BYTES_JSON = 1 * 1024 * 1024


def _registrar_acceso_auditoria(usuario: str, licenciaid, modulo: str, accion: str = "VISUALIZACION") -> None:
    """
    Registra un acceso para cumplimiento del Art. 19 Ley 6593:
    1) en memoria de sesión (st.session_state["auditoria_sesion"]) y
    2) en public."BitacoraAuditoria" mediante backend.auditoria (errores registrados, nunca silenciados).
    """
    import streamlit as st

    if "auditoria_sesion" not in st.session_state:
        st.session_state["auditoria_sesion"] = []
    st.session_state["auditoria_sesion"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "usuario":   usuario,
        "modulo":    modulo,
        "accion":    accion,
    })
    if licenciaid is None:
        logger.warning("Auditoría sin licencia: usuario=%s modulo=%s accion=%s", usuario, modulo, accion)
        return
    auditoria.registrar_evento_autonomo(licenciaid, usuario, modulo, accion)


_VERSION_SAML = "1.0"
_SAML_TRANSACTIONS = "transactions.csv"
_SAML_CONFIG       = "config.json"
_SAML_META         = "session.json"


def exportar_sesion(df_raw: pd.DataFrame, aml_config: dict, nombre_original: str) -> bytes:
    """
    Empaqueta df_raw + aml_config + metadatos en un ZIP en memoria.
    Retorna los bytes del ZIP (extensión .saml para el usuario).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Transacciones raw
        csv_buf = io.StringIO()
        df_raw.to_csv(csv_buf, index=False, encoding="utf-8")
        zf.writestr(_SAML_TRANSACTIONS, csv_buf.getvalue().encode("utf-8"))

        # 2. Configuración AML
        cfg_serializable = _serializar_config(aml_config)
        zf.writestr(_SAML_CONFIG, json.dumps(cfg_serializable, ensure_ascii=False, indent=2).encode("utf-8"))

        # 3. Metadatos de sesión
        meta = {
            "version":       _VERSION_SAML,
            "nombre_archivo": nombre_original,
            "exportado_en":  datetime.now(timezone.utc).isoformat(),
            "filas":         len(df_raw),
            "columnas":      list(df_raw.columns),
        }
        zf.writestr(_SAML_META, json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))

    buf.seek(0)
    return buf.read()


def importar_sesion(archivo_saml) -> tuple:
    """
    Lee un archivo .saml (objeto file-like o UploadedFile de Streamlit).
    Retorna: (df_raw, aml_config, session_meta)
    Lanza ValueError si el archivo no es un .saml válido o supera los límites.
    """
    contenido = archivo_saml.read()
    if len(contenido) > MAX_BYTES_COMPRIMIDO:
        raise ValueError(f"El archivo supera el máximo permitido de {MAX_BYTES_COMPRIMIDO // (1024 * 1024)} MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido), mode="r") as zf:
            _validar_estructura(zf.namelist())
            _validar_tamanos(zf.infolist())

            with zf.open(_SAML_TRANSACTIONS) as f:
                df_raw = pd.read_csv(f, encoding="utf-8", nrows=MAX_FILAS + 1)
            if len(df_raw) > MAX_FILAS:
                raise ValueError(f"El archivo contiene más de {MAX_FILAS:,} filas.")

            with zf.open(_SAML_CONFIG) as f:
                aml_config = _leer_json(f, _SAML_CONFIG)
            with zf.open(_SAML_META) as f:
                session_meta = _leer_json(f, _SAML_META)
    except zipfile.BadZipFile:
        raise ValueError("El archivo no es un .saml válido (formato ZIP corrupto).")
    except KeyError as e:
        raise ValueError(f"Archivo .saml incompleto: falta: {e}")
    except (pd.errors.ParserError, UnicodeDecodeError) as e:
        raise ValueError(f"No se pudieron leer las transacciones del .saml: {e}")

    aml_config = validar_config(aml_config)
    session_meta = _sanear_meta(session_meta, len(df_raw))
    return df_raw, aml_config, session_meta


# ─── helpers privados ────────────────────────────────────────────────────────

def _validar_estructura(nombres: list):
    """Valida que el ZIP contenga los archivos requeridos."""
    requeridos = {_SAML_TRANSACTIONS, _SAML_CONFIG, _SAML_META}
    faltantes = requeridos - set(nombres)
    if faltantes:
        raise ValueError(f"Archivo .saml incompleto. Faltan: {faltantes}")


def _validar_tamanos(infos: list) -> None:
    """Verifica el tamaño declarado de cada entrada antes de descomprimir (anti zip bomb)."""
    total = 0
    for info in infos:
        if info.file_size < 0 or info.file_size > MAX_BYTES_DESCOMPRIMIDO:
            raise ValueError("El archivo .saml declara un tamaño descomprimido no permitido.")
        total += info.file_size
        if info.compress_size and info.file_size / max(info.compress_size, 1) > 200:
            raise ValueError("El archivo .saml tiene una tasa de compresión sospechosa.")
    if total > MAX_BYTES_DESCOMPRIMIDO:
        raise ValueError(f"El contenido descomprimido supera {MAX_BYTES_DESCOMPRIMIDO // (1024 * 1024)} MB.")


def _leer_json(f, nombre: str) -> dict:
    datos = f.read(MAX_BYTES_JSON + 1)
    if len(datos) > MAX_BYTES_JSON:
        raise ValueError(f"{nombre} supera el tamaño permitido.")
    try:
        valor = json.loads(datos.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError(f"{nombre} no es un JSON válido: {e}")
    if not isinstance(valor, dict):
        raise ValueError(f"{nombre} debe ser un objeto JSON.")
    return valor


def _sanear_meta(meta: dict, filas: int) -> dict:
    """Conserva solo los metadatos conocidos, con tipos y longitudes acotadas."""
    nombre = str(meta.get("nombre_archivo", "analisis.xlsx"))[:200]
    exportado = str(meta.get("exportado_en", ""))[:40]
    return {
        "version": str(meta.get("version", _VERSION_SAML))[:10],
        "nombre_archivo": nombre,
        "exportado_en": exportado,
        "filas": int(filas),
    }


def _serializar_config(cfg: dict) -> dict:
    """
    Convierte valores del config a tipos serializables en JSON.
    Específicamente: bool, int, float, list, str.
    """
    resultado = {}
    for k, v in cfg.items():
        if isinstance(v, bool):
            resultado[k] = bool(v)
        elif isinstance(v, (int, float, str, list)):
            resultado[k] = v
        else:
            resultado[k] = str(v)
    return resultado


def nombre_archivo_saml(nombre_original: str) -> str:
    """Genera el nombre de descarga del archivo .saml."""
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    base = nombre_original.replace(".xlsx", "").replace(".xls", "").replace(" ", "_")
    return f"sovereign_{base}_{fecha}.saml"
