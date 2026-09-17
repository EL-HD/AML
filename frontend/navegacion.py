"""
Navegación agrupada por flujo de trabajo del Oficial de Cumplimiento (U-02, U-06).

Se implementa con un st.radio por grupo (compatible con la arquitectura de
script único de app.py). Solo un radio tiene selección a la vez; el resto se
muestra sin selección (index=None). La vista activa vive en
st.session_state["nav_view"].
"""
from typing import Dict, List

import streamlit as st

from frontend import permisos
from frontend.ui_safe import h

GRUPOS: Dict[str, List[str]] = {
    "Monitoreo": ["Resumen Ejecutivo", "Casos de Alerta", "Transacciones"],
    "Investigación": ["Análisis por Cliente", "Red Transaccional"],
    "Riesgo": [
        "Matrices de Riesgo", "Riesgo Institucional LD/FT", "Imperator Diagnostics",
        "Gestión de Ubicaciones", "Acciones de Mitigación",
    ],
    "Reportería": ["Informes y Reportes"],
    "Administración": ["Configuración", "Manual de Usuario"],
}

VISTA_POR_DEFECTO = "Resumen Ejecutivo"

# Vistas que no requieren un archivo cargado
VISTAS_SIN_DATOS = {
    "Configuración", "Manual de Usuario", "Gestión de Ubicaciones",
    "Riesgo Institucional LD/FT",
}

_ALIAS = {"IMPERATOR Diagnostics": "Imperator Diagnostics"}


def todas_las_vistas() -> List[str]:
    return [v for vistas in GRUPOS.values() for v in vistas]


def _clave_radio(grupo: str) -> str:
    return "nav_radio_" + grupo.lower().replace(" ", "_")


def _vistas_visibles(grupo: str) -> List[str]:
    vistas = GRUPOS[grupo]
    if grupo == "Administración" and not permisos.puede("ver_configuracion"):
        vistas = [v for v in vistas if v != "Configuración"]
    return vistas


def _al_cambiar(grupo: str) -> None:
    seleccion = st.session_state.get(_clave_radio(grupo))
    if seleccion is None:
        return
    st.session_state["nav_view"] = seleccion
    for otro in GRUPOS:
        if otro != grupo:
            st.session_state[_clave_radio(otro)] = None


def vista_actual() -> str:
    vista = st.session_state.get("nav_view", VISTA_POR_DEFECTO)
    vista = _ALIAS.get(vista, vista)
    if vista not in todas_las_vistas():
        vista = VISTA_POR_DEFECTO
    st.session_state["nav_view"] = vista
    return vista


def render_sidebar_nav() -> str:
    """Dibuja los grupos de navegación en el sidebar y devuelve la vista activa."""
    vista = vista_actual()
    for grupo in GRUPOS:
        vistas = _vistas_visibles(grupo)
        if not vistas:
            continue
        clave = _clave_radio(grupo)
        indice = vistas.index(vista) if vista in vistas else None
        # Sincroniza el estado del widget con la vista activa (por ejemplo tras un cambio programático)
        st.session_state[clave] = vista if indice is not None else None
        st.markdown(f"<div class='sidebar-section-label'>{h(grupo)}</div>", unsafe_allow_html=True)
        st.radio(
            f"Sección {grupo}", vistas, index=indice, key=clave,
            on_change=_al_cambiar, args=(grupo,), label_visibility="collapsed",
        )
    return vista_actual()


def ir_a(vista: str) -> None:
    """Cambia la vista activa desde código (botones de estado vacío, etc.)."""
    if vista in todas_las_vistas():
        st.session_state["nav_view"] = vista
