"""
Permisos de la interfaz por rol (RBAC mínimo, OWASP A01).

La autoridad final es la API (auth_api.require_role); este módulo solo decide
qué controles se muestran en Streamlit. La fuente del rol es user_data,
cargado desde la base de datos al autenticar o restaurar la sesión.
"""
from typing import Optional

import streamlit as st

ROLES = ("admin", "oficial", "analista", "auditor")

# Acción -> roles autorizados. Toda acción no listada se niega.
_MATRIZ = {
    "administrar_licencias": {"admin"},
    "configurar_parametros": {"admin", "oficial"},
    "gestionar_catalogos": {"admin", "oficial"},
    "gestionar_ubicaciones": {"admin", "oficial"},
    "editar_riesgo_ldft": {"admin", "oficial"},
    "gestionar_alertas": {"admin", "oficial", "analista"},
    "proponer_caso_sospechoso": {"admin", "oficial", "analista"},
    "aprobar_caso_sospechoso": {"admin", "oficial"},
    "cargar_listas_sancion": {"admin"},
    "gestionar_screening": {"admin", "oficial"},
    "ver_screening": {"admin", "oficial", "analista", "auditor"},
    "exportar_datos": {"admin", "oficial", "analista"},
    "ver_configuracion": {"admin", "oficial", "analista", "auditor"},
    "verificar_bitacora": {"admin", "auditor"},
    "restablecer_mfa_usuarios": {"admin"},
}

ETIQUETAS = {
    "admin": "Administrador",
    "oficial": "Oficial de Cumplimiento",
    "analista": "Analista",
    "auditor": "Auditor",
}


def rol_actual(user_data: Optional[dict] = None) -> str:
    datos = user_data if user_data is not None else (st.session_state.get("user_data") or {})
    rol = datos.get("rol") if isinstance(datos, dict) else None
    return rol if rol in ROLES else "analista"


def puede(accion: str, user_data: Optional[dict] = None) -> bool:
    """Devuelve True si el rol de la sesión está autorizado para la acción."""
    return rol_actual(user_data) in _MATRIZ.get(accion, set())


def etiqueta_rol(user_data: Optional[dict] = None) -> str:
    return ETIQUETAS.get(rol_actual(user_data), "Analista")


def aviso_solo_lectura(accion: str) -> None:
    """Mensaje estándar cuando el rol no puede modificar la sección."""
    st.info(
        f"Su rol ({etiqueta_rol()}) tiene acceso de solo lectura a esta sección. "
        "Solicite los cambios a un Oficial de Cumplimiento o Administrador."
    )


def exigir_o_avisar(accion: str) -> bool:
    """Devuelve si el rol puede `accion`; si no, muestra el aviso de solo lectura.

    Punto único para el patrón "verificar permiso y avisar" repetido en varias
    vistas (evita duplicar la pareja puede()/aviso_solo_lectura() en cada una).
    """
    permitido = puede(accion)
    if not permitido:
        aviso_solo_lectura(accion)
    return permitido
