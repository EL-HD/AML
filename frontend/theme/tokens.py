"""
Tokens de diseño de Sovereign AML (U-01). Única fuente de colores, tipografía,
espaciado y radios. Se exponen como variables CSS (--sv-*) en styles.css y como
constantes Python para Plotly/Matplotlib y componentes.
"""

COLORES = {
    # Superficies
    "fondo": "#0f141b",
    "superficie": "#171c23",
    "superficie_alta": "#1b2027",
    "superficie_form": "#1a1f26",
    "borde": "#30353d",
    "borde_suave": "#534434",
    # Texto (contraste AA verificado en tests/test_contraste.py)
    "texto": "#dee2ed",
    "texto_fuerte": "#f0f6fc",
    "texto_secundario": "#a7b0bb",
    "texto_terciario": "#d8c3ad",
    "texto_tenue": "#b8a58e",
    "blanco": "#ffffff",
    # Marca y estados
    "acento": "#f59e0b",
    "acento_claro": "#fbbf24",
    "acento_oscuro": "#472a00",
    "info": "#3b82f6",
    "info_claro": "#7cc7ff",
    "exito": "#10b981",
    "exito_texto": "#22c55e",
    "advertencia": "#f97316",
    "advertencia_suave": "#fb923c",
    "peligro": "#ef4444",
    "peligro_suave": "#ff5a5f",
    "violeta": "#a855f7",
    "amarillo": "#eab308",
}

TIPOGRAFIA = {
    "sans": "'Manrope', sans-serif",
    "mono": "'IBM Plex Mono', monospace",
    "base": "14px",
    "minima": "12px",   # WCAG: ningún texto por debajo de 12px
    "pequena": "13px",
    "titulo": "32px",
    "seccion": "18px",
}

ESPACIADO = {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", "xl": "32px"}
RADIOS = {"none": "0px", "sm": "4px", "md": "8px"}

# Niveles de riesgo -> color (compartido por badges, tablas y gráficos)
COLOR_NIVEL = {
    "Crítico": COLORES["peligro"],
    "Critico": COLORES["peligro"],
    "Alto": COLORES["advertencia"],
    "Medio": COLORES["amarillo"],
    "Bajo": COLORES["exito_texto"],
}


def css_variables() -> str:
    """Bloque :root con todos los tokens como variables CSS."""
    lineas = [f"  --sv-{k.replace('_', '-')}: {v};" for k, v in COLORES.items()]
    lineas += [f"  --sv-font-{k}: {v};" for k, v in TIPOGRAFIA.items()]
    lineas += [f"  --sv-space-{k}: {v};" for k, v in ESPACIADO.items()]
    lineas += [f"  --sv-radius-{k}: {v};" for k, v in RADIOS.items()]
    return ":root {\n" + "\n".join(lineas) + "\n}\n"
