"""
Carga de estilos del sistema de diseño (una sola vez por render).

- styles.css: tema global (tokens en :root, sidebar, tarjetas, tablas).
- login.css: ajustes exclusivos de la pantalla de acceso.
"""
from pathlib import Path

import streamlit as st

from .tokens import css_variables

_DIR = Path(__file__).resolve().parent


@st.cache_data(show_spinner=False)
def _leer_css(nombre: str) -> str:
    return (_DIR / nombre).read_text(encoding="utf-8")


def cargar_estilos(*archivos: str) -> None:
    """Inyecta :root con tokens y los archivos CSS indicados (por defecto styles.css)."""
    nombres = archivos or ("styles.css",)
    css = css_variables() + "\n".join(_leer_css(n) for n in nombres)
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)
