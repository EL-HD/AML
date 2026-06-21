"""
mod_sesion.py — Sovereign AML Session Snapshot
Exporta e importa análisis completos en formato .saml (ZIP interno).
"""
import io
import json
import zipfile
from datetime import datetime

import pandas as pd


def _registrar_acceso_auditoria(usuario: str, licenciaid, modulo: str, accion: str = "VISUALIZACION") -> None:
    """
    Registra acceso en bitácora para cumplimiento Art. 19 Ley 6593.
    1) Escribe en st.session_state["auditoria_sesion"] (in-memory).
    2) Persiste en public."BitacoraAuditoria" (PostgreSQL).
    No interrumpe el flujo principal si la DB falla.
    """
    import streamlit as st

    # 1. Registro en memoria de sesión
    if "auditoria_sesion" not in st.session_state:
        st.session_state["auditoria_sesion"] = []
    st.session_state["auditoria_sesion"].append({
        "timestamp": datetime.now().isoformat(),
        "usuario":   usuario,
        "modulo":    modulo,
        "accion":    accion,
    })

    # 2. Persistencia en BD — Art. 19 Ley 6593
    if licenciaid is None:
        return
    try:
        import uuid as _uuid
        from backend.database import SessionLocal
        from backend import models as _models
        # Normalizar licenciaid a UUID
        lid = _uuid.UUID(str(licenciaid)) if not isinstance(licenciaid, _uuid.UUID) else licenciaid
        db = SessionLocal()
        try:
            registro = _models.BitacoraAuditoria(
                licenciaid=lid,
                username=usuario,
                modulo_accedido=modulo,
                accion=accion,
                timestamp=datetime.now(),
            )
            db.add(registro)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass  # auditoría no debe bloquear la UI

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
            "exportado_en":  datetime.now().isoformat(),
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
    Lanza ValueError si el archivo no es un .saml válido.
    """
    try:
        buf = io.BytesIO(archivo_saml.read())
        with zipfile.ZipFile(buf, mode="r") as zf:
            nombres = zf.namelist()
            _validar_estructura(nombres)

            # Transacciones
            with zf.open(_SAML_TRANSACTIONS) as f:
                df_raw = pd.read_csv(f, encoding="utf-8")

            # Configuración
            with zf.open(_SAML_CONFIG) as f:
                aml_config = json.loads(f.read().decode("utf-8"))

            # Metadatos
            with zf.open(_SAML_META) as f:
                session_meta = json.loads(f.read().decode("utf-8"))

        # Restaurar tipos correctos en config
        aml_config = _restaurar_tipos_config(aml_config)

        return df_raw, aml_config, session_meta

    except zipfile.BadZipFile:
        raise ValueError("El archivo no es un .saml válido (formato ZIP corrupto).")
    except KeyError as e:
        raise ValueError(f"Archivo .saml incompleto — falta: {e}")


# ─── helpers privados ────────────────────────────────────────────────────────

def _validar_estructura(nombres: list):
    """Valida que el ZIP contenga los archivos requeridos."""
    requeridos = {_SAML_TRANSACTIONS, _SAML_CONFIG, _SAML_META}
    faltantes = requeridos - set(nombres)
    if faltantes:
        raise ValueError(f"Archivo .saml incompleto. Faltan: {faltantes}")


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


def _restaurar_tipos_config(cfg: dict) -> dict:
    """
    Asegura que los campos de tipo bool sean bool (JSON los guarda como true/false
    pero Python los carga correctamente; esta función normaliza edge cases).
    """
    campos_bool = [
        "regla_absoluto", "regla_acumulado", "regla_perfil",
        "regla_frecuencia", "regla_smurfing", "regla_pico",
        "regla_ubicacion", "regla_feic",
    ]
    campos_int = [
        "tolerancia_perfil", "umbral_absoluto", "umbral_frecuencia",
        "umbral_smurfing", "score_critico", "monto_critico",
        "score_alto", "score_medio", "peso_absoluto", "peso_acumulado",
        "peso_perfil", "peso_frecuencia", "peso_smurfing", "peso_pico",
        "peso_pep_cpe", "peso_ubicacion", "umbral_feic",
    ]
    campos_float = ["mult_acumulado", "mult_std_pico", "w_st", "w_sc", "w_sb", "w_sn"]

    for campo in campos_bool:
        if campo in cfg:
            cfg[campo] = bool(cfg[campo])
    for campo in campos_int:
        if campo in cfg:
            cfg[campo] = int(cfg[campo])
    for campo in campos_float:
        if campo in cfg:
            cfg[campo] = float(cfg[campo])

    return cfg


def nombre_archivo_saml(nombre_original: str) -> str:
    """Genera el nombre de descarga del archivo .saml."""
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    base = nombre_original.replace(".xlsx", "").replace(".xls", "").replace(" ", "_")
    return f"sovereign_{base}_{fecha}.saml"
