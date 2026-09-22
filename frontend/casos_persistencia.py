"""
casos_persistencia.py: puente entre la sesión Streamlit y backend.casos_alerta.

Responsabilidades:
  * Calcular (y memorizar en sesión) el hash del lote cargado.
  * Rehidratar los estados persistidos sobre el DataFrame `casos` de la sesión,
    para que Casos de Alerta, Resumen Ejecutivo y Reportes vean el mismo estado.
  * Exponer la identidad de sesión (licencia, usuario, rol) desde el servidor.
"""
import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from backend import casos_alerta
from backend.database import SessionLocal
from frontend import permisos

logger = logging.getLogger(__name__)

_CLAVE_HASH = "lote_hash"
_CLAVE_HASH_ORIGEN = "lote_hash_origen"


def identidad_sesion() -> tuple:
    """(licenciaid, usuario, rol) desde la sesión autenticada (server-trusted)."""
    ud = st.session_state.get("user_data") or {}
    return ud.get("licence_id"), ud.get("user", "desconocido"), permisos.rol_actual(ud)


def hash_lote_sesion():
    """Hash del lote de `data_raw`; se memoriza mientras el DataFrame sea el mismo objeto."""
    df_raw = st.session_state.get("data_raw")
    if df_raw is None:
        return None
    origen = id(df_raw)
    if st.session_state.get(_CLAVE_HASH_ORIGEN) == origen and st.session_state.get(_CLAVE_HASH):
        return st.session_state[_CLAVE_HASH]
    hash_lote = casos_alerta.calcular_hash_lote(df_raw)
    st.session_state[_CLAVE_HASH] = hash_lote
    st.session_state[_CLAVE_HASH_ORIGEN] = origen
    return hash_lote


def olvidar_hash_lote() -> None:
    for clave in (_CLAVE_HASH, _CLAVE_HASH_ORIGEN):
        st.session_state.pop(clave, None)


def rehidratar_estados(casos) -> int:
    """Aplica sobre `casos` los estados guardados para (licencia, lote). Devuelve filas actualizadas."""
    casos_alerta.asegurar_columnas_estado(casos)
    licenciaid, _usuario, _rol = identidad_sesion()
    hash_lote = hash_lote_sesion()
    if not licenciaid or not hash_lote:
        return 0
    db = SessionLocal()
    try:
        registros = casos_alerta.listar_casos_lote(db, licenciaid, hash_lote)
        return casos_alerta.rehidratar_dataframe(casos, registros)
    except SQLAlchemyError:
        logger.exception("No se pudieron rehidratar los estados de casos de alerta.")
        st.warning("No se pudieron cargar los estados guardados de los casos. Se muestran los valores calculados.")
        return 0
    finally:
        db.close()
