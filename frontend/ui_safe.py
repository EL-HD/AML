"""
Utilidades para renderizar HTML en Streamlit sin riesgo de XSS (OWASP A03, S-06).

Regla del proyecto: todo valor dinámico que se interpole en un bloque con
unsafe_allow_html=True debe pasar por h() o construirse con html_block().
Las pruebas (tests/test_ui_safe.py) verifican por heurística que no existan
f-strings con unsafe_allow_html=True cuyos valores no estén escapados.
"""
from html import escape
from typing import Any

# Atributos que sí admiten HTML ya seguro (construido por componentes propios).
_SUFIJO_HTML_SEGURO = "_html"


def h(valor: Any) -> str:
    """Escapa cualquier valor para insertarlo en HTML (texto o atributo)."""
    if valor is None:
        return ""
    return escape(str(valor), quote=True)


def html_block(template: str, **valores: Any) -> str:
    """
    Rellena una plantilla str.format escapando todos los valores.
    Los argumentos cuyo nombre termina en "_html" se insertan tal cual porque
    deben venir de otro html_block/h() y ya son seguros.
    """
    seguros = {
        clave: (valor if clave.endswith(_SUFIJO_HTML_SEGURO) else h(valor))
        for clave, valor in valores.items()
    }
    return template.format(**seguros)


def attr_css_color(valor: Any, por_defecto: str = "#8b949e") -> str:
    """Valida un color CSS (hex o nombre simple) antes de usarlo en style=."""
    texto = str(valor or "").strip()
    if texto.startswith("#") and 4 <= len(texto) <= 9 and all(c in "0123456789abcdefABCDEF" for c in texto[1:]):
        return texto
    if texto.isalpha() and len(texto) <= 20:
        return texto
    return por_defecto
