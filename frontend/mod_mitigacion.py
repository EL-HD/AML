import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from frontend.mod_utils import plotly_dark_layout

# ═══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO DE ACCIONES DE MITIGACIÓN — RBA (GAFI) + ISO 31000 + COSO ERM
# ═══════════════════════════════════════════════════════════════════════════════

_CATALOGO = {
    "Preventivas": [
        {"accion": "Bloqueo temporal de cuenta",   "codigo": "P-01", "norma": "ISO 31000 §6.4"},
        {"accion": "Rechazo de transacción",        "codigo": "P-02", "norma": "GAFI Rec. 16"},
        {"accion": "Limitación de montos",          "codigo": "P-03", "norma": "GAFI Rec. 1 / RBA"},
    ],
    "Correctivas": [
        {"accion": "DDA - Debida Diligencia Ampliada",  "codigo": "C-01", "norma": "GAFI Rec. 10/12"},
        {"accion": "Solicitud de documentación",    "codigo": "C-02", "norma": "ISO 31000 §8.5"},
        {"accion": "Revisión manual por analista",  "codigo": "C-03", "norma": "COSO ERM Pilar 4"},
    ],
    "Regulatorias": [
        {"accion": "Generación de RTS/RTI",         "codigo": "R-01", "norma": "GAFI Rec. 20"},
        {"accion": "Escalamiento a Cumplimiento",   "codigo": "R-02", "norma": "ISO 31000 §6.6"},
    ],
    "Estratégicas": [
        {"accion": "Ajuste de perfil del cliente",  "codigo": "E-01", "norma": "COSO ERM Obj. 2"},
        {"accion": "Reclasificación de segmento",   "codigo": "E-02", "norma": "RBA GAFI §2"},
        {"accion": "Restricción de productos",       "codigo": "E-03", "norma": "ISO 31000 §6.4.3"},
    ],
    "Formularios KYC": [
        {"accion": "Actualizar FEIS a FEIC (Formulario Electrónico de Información del Cliente)",
         "codigo": "F-01", "norma": "GAFI Rec. 10 / KYC"},
    ],
}

_COLOR_CAT = {
    "Preventivas":   "#ef4444",
    "Correctivas":   "#f97316",
    "Regulatorias":  "#eab308",
    "Estratégicas":  "#3b82f6",
    "Formularios KYC": "#a855f7",
}


def _texto_seguro(valor):
    """Escapa texto dinámico para evitar que el HTML se renderice como contenido."""
    if pd.isna(valor):
        return "—"
    return html.escape(str(valor))

def _determinar_acciones(row, cfg=None):
    """
    Determina las acciones de mitigación según el nivel de riesgo,
    score y factores agravantes (RBA / GAFI / ISO 31000).
    Incluye verificación FEIS→FEIC cuando el asociado tiene perfil
    transaccional bajo (total mensual <= umbral configurable).
    """
    acciones = []
    score         = row.get("Score_Max", 0)
    nivel         = row.get("Nivel_Riesgo", "Bajo")
    es_pep        = row.get("EsPEP", False)
    es_cpe        = row.get("EsCPE", False)
    smurfing      = row.get("Smurfing_Count", 0) > 0
    pico          = row.get("Pico_Count", 0) > 0
    geo           = row.get("Ubicacion_Riesgo", False)
    total_mensual = row.get("Total_Mensual", 0)

    # ── NIVEL CRÍTICO (score ≥ 8) ──────────────────────────────────────────
    if nivel == "Crítico":
        acciones += ["P-01", "P-02"]          # Bloqueo + Rechazo
        acciones += ["C-01", "C-02"]          # DDA + Documentación
        acciones += ["R-01", "R-02"]          # RTS/RTI + Escalamiento
        if es_pep or es_cpe:
            acciones += ["E-01", "E-02"]      # Ajuste perfil + Reclasificación

    # ── NIVEL ALTO (5–7.9) ─────────────────────────────────────────────────
    elif nivel == "Alto":
        acciones += ["P-03"]                  # Limitación montos
        acciones += ["C-01", "C-02", "C-03"]  # DDA + Docs + Revisión manual
        if smurfing or pico:
            acciones += ["R-01"]              # RTS si hay smurfing o pico
        if es_pep or geo:
            acciones += ["R-02"]              # Escalamiento si PEP o geo riesgo

    # ── NIVEL MEDIO (3–4.9) ────────────────────────────────────────────────
    elif nivel == "Medio":
        acciones += ["P-03"]                  # Limitación montos
        acciones += ["C-03"]                  # Revisión manual
        acciones += ["E-01"]                  # Ajuste perfil
        if es_pep or es_cpe:
            acciones += ["C-01"]              # DDA adicional por PEP/CPE

    # ── NIVEL BAJO ─────────────────────────────────────────────────────────
    else:
        acciones += ["E-01"]                  # Ajuste de perfil preventivo

    # ── ALERTA FEIS → FEIC (perfil transaccional bajo) ─────────────────────
    # Solo se activa si: la regla está habilitada Y el total mensual
    # supera el umbral FEIC configurado (indica que ya no es perfil bajo).
    if cfg is not None:
        regla_feic   = cfg.get("regla_feic", True)
        umbral_feic  = cfg.get("umbral_feic", 45000)
        if regla_feic and total_mensual > umbral_feic:
            acciones += ["F-01"]

    return list(dict.fromkeys(acciones))       # eliminar duplicados manteniendo orden


def _buscar_accion(codigo):
    """Retorna el dict de acción dado su código."""
    for cat, items in _CATALOGO.items():
        for item in items:
            if item["codigo"] == codigo:
                return {**item, "categoria": cat}
    return {"accion": codigo, "codigo": codigo, "norma": "—", "categoria": "—"}


def mostrar(df, casos):
    st.markdown("""
    <div class="info-box">
        <strong>ACCIONES DE MITIGACIÓN</strong> — Motor RBA (GAFI) + ISO 31000 + COSO ERM.
        Define automáticamente acciones estandarizadas según nivel de riesgo, score IMPERATOR y factores agravantes.
        Incluye acciones Preventivas, Correctivas, Regulatorias y Estratégicas por cliente.
    </div>
    """, unsafe_allow_html=True)

    # ── MARCO NORMATIVO ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Marco Normativo Aplicado</div>', unsafe_allow_html=True)
    col_n1, col_n2, col_n3 = st.columns(3)
    marcos = [
        ("RBA — GAFI", "Núcleo operativo", "Evalúa el riesgo de cada cliente con enfoque basado en riesgo. Activa acciones proporcionales al nivel detectado.", "#ef4444"),
        ("COSO ERM", "Integración estratégica", "Gobierna el riesgo alineando las acciones a los objetivos institucionales del programa de cumplimiento.", "#3b82f6"),
        ("ISO 31000", "Metodología estructural", "Implementa la gestión del riesgo de forma sistemática: identificar, evaluar, tratar y monitorear.", "#22c55e"),
    ]
    for col, (titulo, subtitulo, desc, color) in zip([col_n1, col_n2, col_n3], marcos):
        with col:
            st.markdown(f"""
            <div style="background:#1b2027; border-left:4px solid {color}; padding:16px; margin-bottom:8px; min-height:120px;">
                <div style="color:{color}; font-size:13px; font-weight:700; font-family:'IBM Plex Mono',monospace;">{titulo}</div>
                <div style="color:#f0f6fc; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:1px; margin:6px 0 4px;">{subtitulo}</div>
                <div style="color:#a08e7a; font-size:12px; line-height:1.6;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── ALERTA FEIS → FEIC ────────────────────────────────────────────────
    cfg_mit = st.session_state.get("aml_config", {})
    regla_feic  = cfg_mit.get("regla_feic", True)
    umbral_feic = cfg_mit.get("umbral_feic", 45000)
    if regla_feic:
        st.markdown(f"""
        <div style="background:#1b1027; border-left:4px solid #a855f7; padding:14px; margin-bottom:16px; font-size:12px; color:#d8c3ad;">
            <span style="color:#a855f7; font-weight:700; font-family:'IBM Plex Mono',monospace;">VERIFICACIÓN FEIS → FEIC ACTIVA</span>
            &nbsp;|&nbsp; Umbral configurado: <strong>Q{umbral_feic:,}</strong><br>
            Los asociados que superen este monto mensual recibirán la acción <strong>F-01</strong>:
            actualización de FEIS a FEIC (Formulario Electrónico de Información del Cliente).
        </div>""", unsafe_allow_html=True)

    # ── CATÁLOGO DE ACCIONES DE MITIGACIÓN ────────────────────────────────
    st.markdown('<div class="section-title">Catálogo de Acciones Estandarizadas</div>', unsafe_allow_html=True)
    col_cats = st.columns(5)
    for col, (cat_nombre, items) in zip(col_cats, _CATALOGO.items()):
        color = _COLOR_CAT[cat_nombre]
        with col:
            filas_html = "".join([
                f"""<div style="display:flex; gap:8px; margin-bottom:8px; align-items:flex-start;">
                    <span style="color:{color}; font-family:'IBM Plex Mono',monospace; font-size:10px; font-weight:700; min-width:36px; padding-top:1px;">{i['codigo']}</span>
                    <div>
                        <div style="color:#dee2ed; font-size:12px; line-height:1.4;">{i['accion']}</div>
                        <div style="color:#6e7681; font-size:10px; font-family:'IBM Plex Mono',monospace;">{i['norma']}</div>
                    </div>
                </div>"""
                for i in items
            ])
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid {color}; border-top:3px solid {color}; padding:16px;">
                <div style="color:{color}; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; margin-bottom:12px; font-family:'IBM Plex Mono',monospace;">{cat_nombre}</div>
                {filas_html}
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── ACCIONES ASIGNADAS POR CLIENTE ────────────────────────────────────
    st.markdown('<div class="section-title">Acciones Asignadas por Cliente</div>', unsafe_allow_html=True)

    # Selector de nivel
    niveles_disp = ["Todos"] + sorted(casos["Nivel_Riesgo"].unique().tolist(), reverse=True)
    nivel_filtro = st.selectbox("Filtrar por nivel de riesgo", niveles_disp)

    df_filtrado = casos if nivel_filtro == "Todos" else casos[casos["Nivel_Riesgo"] == nivel_filtro]

    if df_filtrado.empty:
        st.info("No hay clientes con el nivel seleccionado.")
        return

    # Construir tabla de acciones
    cfg = st.session_state.get("aml_config", {})
    registros = []
    for _, row in df_filtrado.iterrows():
        codigos = _determinar_acciones(row, cfg)
        for cod in codigos:
            det = _buscar_accion(cod)
            registros.append({
                "Cliente":    row["Cliente"],
                "Nivel":      row["Nivel_Riesgo"],
                "Score":      f"{row['Score_Max']:.2f}",
                "Categoría":  det["categoria"],
                "Código":     det["codigo"],
                "Acción":     det["accion"],
                "Norma":      det["norma"],
            })

    df_acciones = pd.DataFrame(registros)

    # KPIs de acciones
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    kpi_data = [
        (len(df_filtrado),                                                 "Clientes Evaluados",  "blue"),
        (len(df_acciones),                                                 "Acciones Generadas",  "amber"),
        (len(df_acciones[df_acciones["Categoría"] == "Regulatorias"]),    "Regulatorias (RTS)",  "red"),
        (len(df_acciones[df_acciones["Categoría"] == "Preventivas"]),     "Preventivas",         "green"),
    ]
    for col, (val, lbl, color) in zip([col_k1, col_k2, col_k3, col_k4], kpi_data):
        with col:
            st.markdown(f"""
            <div class="metric-card {color}">
                <div class="metric-number">{val}</div>
                <div class="metric-label">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Mostrar tabla agrupada por cliente
    for cliente in df_filtrado["Cliente"].tolist():
        acciones_cliente = df_acciones[df_acciones["Cliente"] == cliente]
        if acciones_cliente.empty:
            continue

        row_datos = df_filtrado[df_filtrado["Cliente"] == cliente].iloc[0]
        nivel_c  = row_datos["Nivel_Riesgo"]
        score_c  = row_datos["Score_Max"]
        color_nivel = {"Crítico": "#ef4444", "Alto": "#f97316", "Medio": "#eab308", "Bajo": "#22c55e"}.get(nivel_c, "#8b949e")
        etiquetas = [f"Score: {score_c:.2f} / 10"]
        if row_datos.get("EsPEP"):
            etiquetas.append("PEP")
        if row_datos.get("EsCPE"):
            etiquetas.append("CPE")
        if row_datos.get("Ubicacion_Riesgo"):
            etiquetas.append("Geo-Riesgo")

        cliente_html = _texto_seguro(cliente)
        meta_html = " &nbsp;•&nbsp; ".join(_texto_seguro(item) for item in etiquetas)
        nivel_html = _texto_seguro(nivel_c.upper())

        # Encabezado cliente
        st.markdown(f"""
        <div style="background:#171c23; border:1px solid {color_nivel}; border-left:6px solid {color_nivel};
                    padding:14px 18px; margin-bottom:4px; display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
            <div style="display:flex; flex-direction:column; gap:6px; min-width:0;">
                <div style="color:#f0f6fc; font-weight:700; font-size:15px; font-family:'Manrope',sans-serif;">{cliente_html}</div>
                <div style="color:#a08e7a; font-size:11px; font-family:'IBM Plex Mono',monospace; line-height:1.5; word-break:break-word;">
                    {meta_html}
                </div>
            </div>
            <div style="color:{color_nivel}; font-weight:700; font-size:12px; font-family:'IBM Plex Mono',monospace;
                        border:1px solid {color_nivel}; padding:3px 10px; white-space:nowrap;">{nivel_html}</div>
        </div>
        """, unsafe_allow_html=True)

        # Acciones del cliente
        filas_acc = ""
        for _, acc in acciones_cliente.iterrows():
            cat = acc["Categoría"]
            color_cat = _COLOR_CAT.get(cat, "#8b949e")
            filas_acc += f"""
            <tr>
                <td style="padding:9px 14px; color:{color_cat}; font-family:'IBM Plex Mono',monospace; font-size:11px; font-weight:700;">{_texto_seguro(acc['Código'])}</td>
                <td style="padding:9px 14px; color:{color_cat}; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">{_texto_seguro(acc['Categoría'])}</td>
                <td style="padding:9px 14px; color:#dee2ed; font-size:13px;">{_texto_seguro(acc['Acción'])}</td>
                <td style="padding:9px 14px; color:#6e7681; font-family:'IBM Plex Mono',monospace; font-size:11px;">{_texto_seguro(acc['Norma'])}</td>
            </tr>"""

        st.markdown(f"""
        <table class="aml-table" style="margin-bottom:20px;">
            <thead>
                <tr>
                    <th style="width:60px;">Código</th>
                    <th style="width:130px;">Categoría</th>
                    <th>Acción de Mitigación</th>
                    <th style="width:160px;">Referencia Normativa</th>
                </tr>
            </thead>
            <tbody>{filas_acc}</tbody>
        </table>
        """, unsafe_allow_html=True)

    # ── GRÁFICO: Distribución de acciones por categoría ───────────────────
    st.markdown("---")
    st.markdown('<div class="section-title">Distribución de Acciones por Categoría</div>', unsafe_allow_html=True)

    conteo_cat = df_acciones["Categoría"].value_counts().reset_index()
    conteo_cat.columns = ["Categoría", "Cantidad"]
    colores_bar = [_COLOR_CAT.get(c, "#8b949e") for c in conteo_cat["Categoría"]]

    fig = go.Figure(go.Bar(
        x=conteo_cat["Cantidad"],
        y=conteo_cat["Categoría"],
        orientation="h",
        marker=dict(color=colores_bar, line=dict(color="#0d1117", width=0.5)),
        text=conteo_cat["Cantidad"],
        textposition="outside",
        textfont=dict(color="#c9d1d9", size=12),
        hovertemplate="<b>%{y}</b><br>Acciones: <b>%{x}</b><extra></extra>",
    ))
    fig.update_layout(plotly_dark_layout(
        xaxis_title="Cantidad de acciones generadas",
        height=280,
        yaxis=dict(autorange="reversed", gridcolor="#30353d", tickfont=dict(color="#d8c3ad")),
    ))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("""<div class="info-box" style="margin-top:5px;">
        <b>Interpretación:</b> Distribución del catálogo de acciones ejecutadas en el período.
        El volumen de acciones regulatorias indica la presión de reporte hacia la SIB.
        Las estratégicas reflejan ajustes preventivos al perfil de riesgo del cliente.
    </div>""", unsafe_allow_html=True)
