"""
Componentes de interfaz reutilizables (U-01). Todos escapan sus valores con
ui_safe.h, por lo que pueden recibir texto proveniente del usuario o del Excel.
"""
from typing import Optional

import streamlit as st

from frontend.theme.tokens import COLOR_NIVEL, COLORES
from frontend.ui_safe import h, html_block

_TONOS = {"amber", "red", "blue", "green", "violet", "orange"}

_ESTADOS = {
    "ok": ("badge-ok", "Activo"),
    "activo": ("badge-ok", "Activo"),
    "inactivo": ("badge-off", "Inactivo"),
    "alerta": ("badge-warn", "Alerta"),
    "critico": ("badge-danger", "Crítico"),
    "info": ("badge-info", "Información"),
}


def _render(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


def kpi_card(label: str, value, sub: Optional[str] = None, tone: str = "amber",
             font_size: Optional[int] = None) -> str:
    """Tarjeta de indicador. Devuelve el HTML (para componer) y no lo renderiza."""
    tono = tone if tone in _TONOS else "amber"
    estilo = f' style="font-size:{int(font_size)}px;"' if font_size else ""
    sub_html = f'<div class="metric-sub">{h(sub)}</div>' if sub else ""
    return html_block(
        '<div class="metric-card {tono}"><div class="metric-number"{estilo_html}>{valor}</div>'
        '<div class="metric-label">{label}</div>{sub_html}</div>',
        tono=tono, estilo_html=estilo, valor=value, label=label, sub_html=sub_html,
    )


def kpi(label: str, value, sub: Optional[str] = None, tone: str = "amber") -> None:
    _render(kpi_card(label, value, sub, tone))


def section_title(texto: str) -> None:
    _render(html_block('<div class="section-title">{texto}</div>', texto=texto))


def page_header(titulo: str, descripcion: Optional[str] = None) -> None:
    desc_html = f'<p class="page-header-desc">{h(descripcion)}</p>' if descripcion else ""
    _render(html_block(
        '<div class="page-header"><h2 class="page-header-title">{titulo}</h2>{desc_html}</div>',
        titulo=titulo, desc_html=desc_html,
    ))


def info_panel(texto: str, titulo: Optional[str] = None, tipo: str = "info") -> None:
    """Panel informativo. tipo: info | warning."""
    clase = "warning-box" if tipo == "warning" else "info-box"
    titulo_html = f"<strong>{h(titulo)}</strong>: " if titulo else ""
    _render(html_block('<div class="{clase}">{titulo_html}{texto}</div>',
                       clase=clase, titulo_html=titulo_html, texto=texto))


def status_badge(estado: str, texto: Optional[str] = None) -> str:
    """Insignia de estado con texto visible (el estado no se comunica solo con color)."""
    clase, etiqueta = _ESTADOS.get(str(estado).lower(), ("badge-info", str(estado)))
    return html_block('<span class="badge {clase}">{texto}</span>', clase=clase, texto=texto or etiqueta)


_TONO_POR_COLOR = {
    COLORES["peligro"]: "tone-danger",
    COLORES["advertencia"]: "tone-warn",
    COLORES["amarillo"]: "tone-yellow",
    COLORES["exito_texto"]: "tone-ok",
    COLORES["exito"]: "tone-green",
    COLORES["info"]: "tone-info",
    COLORES["violeta"]: "tone-violet",
    COLORES["acento"]: "tone-accent",
    COLORES["texto_secundario"]: "tone-muted",
    COLORES["texto_fuerte"]: "tone-strong",
    COLORES["blanco"]: "tone-white",
    COLORES["info_claro"]: "tone-sky",
    # Colores heredados que se alinean al token accesible más cercano
    "#8b949e": "tone-muted",
    "#2ecc71": "tone-ok",
    "#e74c3c": "tone-danger",
}


def tone_class(color: Optional[str], por_defecto: str = "tone-muted") -> str:
    """
    Clase de tono (.tone-*) para un color de token. Sustituye los style= inline
    con colores dinámicos: el componente lee --sv-tone desde styles.css.
    Un color desconocido cae en `por_defecto` (nunca se emite el valor crudo).
    """
    return _TONO_POR_COLOR.get(str(color or "").strip().lower(), por_defecto)


def tone_nivel(nivel: str) -> str:
    """Clase de tono para un nivel de riesgo (Crítico, Alto, Medio, Bajo)."""
    return tone_class(COLOR_NIVEL.get(str(nivel)), "tone-muted")


def nivel_badge(nivel: str) -> str:
    """Insignia de nivel de riesgo (Crítico, Alto, Medio, Bajo) con color y texto."""
    return html_block('<span class="badge badge-tone {tono}">{nivel}</span>',
                      tono=tone_nivel(nivel), nivel=nivel)


def empty_state(titulo: str, descripcion: str, accion: Optional[str] = None) -> None:
    """Estado vacío con guía de siguiente paso."""
    accion_html = f'<div class="empty-state-action">{h(accion)}</div>' if accion else ""
    _render(html_block(
        '<div class="empty-state"><div class="empty-state-title">{titulo}</div>'
        '<div class="empty-state-desc">{descripcion}</div>{accion_html}</div>',
        titulo=titulo, descripcion=descripcion, accion_html=accion_html,
    ))


def moneda_actual() -> str:
    """Código de moneda configurado (GTQ o USD)."""
    cfg = st.session_state.get("aml_config") or {}
    moneda = cfg.get("moneda", "GTQ") if isinstance(cfg, dict) else "GTQ"
    return moneda if moneda in ("GTQ", "USD") else "GTQ"


def simbolo_moneda(moneda: Optional[str] = None) -> str:
    return "US$" if (moneda or moneda_actual()) == "USD" else "Q"


def etiqueta_monto(texto: str = "Monto") -> str:
    """Etiqueta de columna o eje con la moneda configurada, por ejemplo 'Monto (Q)'."""
    return f"{texto} ({simbolo_moneda()})"


def nombre_moneda(moneda: Optional[str] = None) -> str:
    """Nombre largo de la moneda de trabajo, por ejemplo 'GTQ (Quetzales)'."""
    return "USD (Dólares)" if (moneda or moneda_actual()) == "USD" else "GTQ (Quetzales)"


# Umbral RTE del Art. 31 Ley 6593: monto normativo fijado en dólares.
UMBRAL_RTE_USD = 10_000
UMBRAL_RTE_TEXTO = f"USD {UMBRAL_RTE_USD:,}"


def texto_moneda_normativa() -> str:
    """
    Aclaración para informes: distingue la moneda de trabajo (configurable, en
    la que se expresan los montos) del umbral normativo RTE, que la ley fija en USD.
    """
    return (
        f"Moneda de trabajo: {nombre_moneda()}. Los montos de este documento se expresan en esa moneda. "
        f"El umbral de reporte de transacciones en efectivo del Art. 31 Ley 6593 ({UMBRAL_RTE_TEXTO}) "
        "es un monto normativo fijado en dólares y se compara contra su equivalente en la moneda de trabajo."
    )


def fmt_moneda(valor, decimales: int = 0, moneda: Optional[str] = None) -> str:
    """Formato único de moneda (U-08). Usa la moneda configurada (GTQ por defecto)."""
    simbolo = simbolo_moneda(moneda)
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return f"{simbolo}0"
    return f"{simbolo}{numero:,.{decimales}f}"


def regla_titulo(nombre: str, activa: bool) -> None:
    """Título de regla con estado en texto (ACTIVA / DESACTIVADA)."""
    estado = "ACTIVA" if activa else "DESACTIVADA"
    _render(html_block(
        '<div class="section-title">{nombre} &nbsp;<span class="section-badge">{estado}</span></div>',
        nombre=nombre, estado=estado,
    ))


def spec_card(descripcion_html: str, variable: str, logica: str, acento: Optional[str] = None,
              etiqueta_variable: str = "Variable IMPERATOR", etiqueta_logica: str = "Lógica Algebraica",
              impacto_titulo: Optional[str] = None, impacto_html: Optional[str] = None) -> None:
    """
    Ficha de especificación técnica de una regla. descripcion_html e impacto_html
    deben ser HTML constante del código (no datos de usuario); el resto se escapa.
    """
    tono = f" {tone_class(acento)}" if acento else ""
    clase_punto = f' class="pulse-dot spec-dot-tone{tono}"' if acento else ' class="pulse-dot"'
    clase_borde = f' class="spec-impact spec-impact-tone{tono}"' if acento else ' class="spec-impact"'
    impacto = ""
    if impacto_html:
        impacto = html_block(
            '<div{clase_html}><div class="spec-impact-title">{titulo}</div>'
            '<div class="spec-impact-body">{cuerpo_html}</div></div>',
            clase_html=clase_borde, titulo=impacto_titulo or "IMPACTO AL MODIFICAR", cuerpo_html=impacto_html,
        )
    _render(html_block(
        '<div class="spec-card">'
        '<div class="spec-kicker"><span{punto_html}></span> ESPECIFICACIÓN TÉCNICA</div>'
        '<div class="spec-desc">{descripcion_html}</div>'
        '<div class="spec-grid">'
        '<div class="spec-cell"><div class="spec-cell-label">{etiqueta_variable}</div><div class="spec-cell-value">{variable}</div></div>'
        '<div class="spec-cell"><div class="spec-cell-label">{etiqueta_logica}</div><div class="spec-cell-value">{logica}</div></div>'
        '</div>{impacto_html}</div>',
        punto_html=clase_punto, descripcion_html=descripcion_html, variable=variable, logica=logica,
        etiqueta_variable=etiqueta_variable, etiqueta_logica=etiqueta_logica, impacto_html=impacto,
    ))


def regla_kpi(valor, etiqueta: str, peso, activa: bool, tone: Optional[str] = None) -> None:
    """Tarjeta compacta de umbral actual + peso en score para el panel de configuración.
    Si peso no es numérico se muestra como texto descriptivo (por ejemplo un código de acción)."""
    tono = tone if (tone and activa) else ("amber" if activa else "blue")
    sub = f"Peso en score: {peso} pts" if isinstance(peso, (int, float)) else str(peso)
    _render(html_block(
        '<div class="metric-card {tono} compact"><div class="metric-number">{valor}</div>'
        '<div class="metric-label">{etiqueta}</div>'
        '<div class="metric-sub"><strong>{sub}</strong></div></div>',
        tono=tono, valor=valor, etiqueta=etiqueta, sub=sub,
    ))
