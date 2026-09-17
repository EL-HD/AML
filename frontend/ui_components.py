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


def nivel_badge(nivel: str) -> str:
    """Insignia de nivel de riesgo (Crítico, Alto, Medio, Bajo) con color y texto."""
    color = COLOR_NIVEL.get(str(nivel), COLORES["texto_secundario"])
    return html_block('<span class="badge" style="border-color:{color};color:{color};">{nivel}</span>',
                      color=color, nivel=nivel)


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
    estilo_punto = f' style="background:{h(acento)}; box-shadow:0 0 10px {h(acento)};"' if acento else ""
    estilo_borde = f' style="border-left-color:{h(acento)};"' if acento else ""
    impacto = ""
    if impacto_html:
        impacto = html_block(
            '<div class="spec-impact"{borde_html}><div class="spec-impact-title">{titulo}</div>'
            '<div class="spec-impact-body">{cuerpo_html}</div></div>',
            borde_html=estilo_borde, titulo=impacto_titulo or "IMPACTO AL MODIFICAR", cuerpo_html=impacto_html,
        )
    _render(html_block(
        '<div class="spec-card">'
        '<div class="spec-kicker"><span class="pulse-dot"{punto_html}></span> ESPECIFICACIÓN TÉCNICA</div>'
        '<div class="spec-desc">{descripcion_html}</div>'
        '<div class="spec-grid">'
        '<div class="spec-cell"><div class="spec-cell-label">{etiqueta_variable}</div><div class="spec-cell-value">{variable}</div></div>'
        '<div class="spec-cell"><div class="spec-cell-label">{etiqueta_logica}</div><div class="spec-cell-value">{logica}</div></div>'
        '</div>{impacto_html}</div>',
        punto_html=estilo_punto, descripcion_html=descripcion_html, variable=variable, logica=logica,
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
