import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from frontend.mod_utils import plotly_dark_layout, render_html_table

# ═══════════════════════════════════════════════════════════════════════════════
# IMPERATOR DIAGNOSTICS — Centro de Validación del Motor y Aseguramiento de Riesgo
# Diseñado por Ing. Hobéd Díaz, Msc. M.A.F.I.
# ═══════════════════════════════════════════════════════════════════════════════

_REGLAS = [
    "Monto Absoluto", "Acumulado Mensual", "Exceso Perfil",
    "Frecuencia Alta", "Fragmentación", "Pico Anómalo"
]

_COLS_ALERTA = [
    "Alerta_Absoluto", "Alerta_Acumulado", "Alerta_15",
    "Alerta_Frecuencia", "Smurfing", "Pico"
]

_COLS_SCORE = ["_ST", "_SC", "_SB", "_SN"]
_LABEL_SCORE = ["S_T Transaccional", "S_C Contextual", "S_B Conductual", "S_N Red"]
_COLOR_SCORE = ["#f59e0b", "#3b82f6", "#10b981", "#a855f7"]


def _card(titulo, valor, subtitulo, color="amber"):
    return f"""
    <div class="metric-card {color}">
        <div class="metric-label">{titulo}</div>
        <div class="metric-number" style="font-size:26px;">{valor}</div>
        <div class="metric-sub">{subtitulo}</div>
    </div>"""


def _section(titulo):
    st.markdown(f'<div class="section-title">{titulo}</div>', unsafe_allow_html=True)


def _calcular_dominancia(df):
    """Retorna DataFrame con conteo de alertas por regla."""
    counts = [int(df[c].sum()) if c in df.columns else 0 for c in _COLS_ALERTA]
    return pd.DataFrame({"Regla": _REGLAS, "Alertas": counts}).sort_values("Alertas", ascending=False)


def _calcular_fp_estimado(df, casos):
    """
    Estima falsos positivos: alertas generadas en clientes con nivel Bajo.
    Aproximación: alertas en clientes cuyo Score_Max < 3.
    """
    clientes_bajo = set(casos[casos["Nivel_Riesgo"] == "Bajo"]["Cliente"].tolist())
    df_bajo = df[df["Cliente"].isin(clientes_bajo)]
    total_alertas = sum(int(df[c].sum()) for c in _COLS_ALERTA if c in df.columns)
    fp = sum(int(df_bajo[c].sum()) for c in _COLS_ALERTA if c in df.columns)
    tasa = round((fp / total_alertas * 100), 1) if total_alertas > 0 else 0.0
    return fp, total_alertas, tasa


def _score_composition(casos):
    """Media de cada componente de puntaje por nivel de riesgo."""
    niveles = ["Crítico", "Alto", "Medio", "Bajo"]
    result = []
    for nivel in niveles:
        sub = casos[casos["Nivel_Riesgo"] == nivel]
        if sub.empty:
            continue
        fila = {"Nivel": nivel}
        for col, lbl in zip(["ST_Max", "SC_Max", "SB_Max", "SN_Max"], _LABEL_SCORE):
            fila[lbl] = round(sub[col].mean(), 2) if col in sub.columns else 0.0
        result.append(fila)
    return pd.DataFrame(result)


def _stress_test(df, cfg, parametro, valores):
    """
    Simula cambios en un parámetro y retorna el nº de alertas para cada valor.
    Sólo re-evalúa la regla afectada sin re-procesar todo el motor.
    """
    resultados = []
    for v in valores:
        cfg_sim = {**cfg, parametro: v}
        if parametro == "umbral_absoluto":
            cnt = int((df["Monto"] > v).sum()) if cfg_sim.get("regla_absoluto", True) else 0
        elif parametro == "mult_acumulado":
            cnt = int((df["Total_Mensual"] > df["Perfil"] * v).sum()) if cfg_sim.get("regla_acumulado", True) else 0
        elif parametro == "umbral_smurfing":
            if "Count" in df.columns:
                cnt = int((df["Count"] >= v).sum()) if cfg_sim.get("regla_smurfing", True) else 0
            else:
                cnt = 0
        else:
            cnt = 0
        resultados.append(cnt)
    return resultados


def _risk_density(casos):
    """Distribución del puntaje por deciles."""
    scores = casos["Score_Max"].dropna()
    hist, edges = np.histogram(scores, bins=10, range=(0, 10))
    labels = [f"{edges[i]:.1f}–{edges[i+1]:.1f}" for i in range(len(hist))]
    return pd.DataFrame({"Rango de Puntaje": labels, "Clientes": hist})


def mostrar(df, casos, cfg):
    st.markdown("""
    <div class="info-box">
        <strong>IMPERATOR DIAGNOSTICS</strong> — Centro de validación del motor y aseguramiento de riesgo.<br>
        Módulo de gobernanza analítica: valida efectividad de reglas, explica composición de puntajes,
        estima falsos positivos y simula cambios de configuración.
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Dominancia de Reglas",
        "Explicabilidad",
        "Falsos Positivos",
        "Pruebas de Estrés",
        "Densidad de Riesgo"
    ])

    # ── TAB 1: Análisis de Dominancia de Reglas ─────────────────────────────
    with tab1:
        _section("Análisis de Dominancia de Reglas")
        st.markdown("""
        <div style="background:#171c23; border-left:3px solid #f59e0b; padding:14px; margin-bottom:16px; font-size:12px; color:#a08e7a;">
            Identifica qué reglas generan mayor volumen de alertas. Una regla dominante con bajo impacto
            en puntaje puede ser fuente de ruido analítico. Evalúe si su peso refleja su contribución real.
        </div>""", unsafe_allow_html=True)

        dominancia = _calcular_dominancia(df)
        total_alertas_dom = int(dominancia["Alertas"].sum())

        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            st.markdown(_card("Total de Alertas Generadas", total_alertas_dom, "Suma de todas las reglas activas"), unsafe_allow_html=True)
        with col_k2:
            regla_top = dominancia.iloc[0]["Regla"] if not dominancia.empty else "—"
            cnt_top = int(dominancia.iloc[0]["Alertas"]) if not dominancia.empty else 0
            st.markdown(_card("Regla Dominante", regla_top, f"{cnt_top} alertas activadas", "red"), unsafe_allow_html=True)
        with col_k3:
            reglas_inactivas = int((dominancia["Alertas"] == 0).sum())
            st.markdown(_card("Reglas sin Activación", reglas_inactivas, "Posible sobreconfiguración", "blue"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        colores_dom = ["#ef4444" if i == 0 else "#f59e0b" if i == 1 else "#3b82f6"
                       for i in range(len(dominancia))]
        fig_dom = go.Figure(go.Bar(
            y=dominancia["Regla"], x=dominancia["Alertas"],
            orientation="h",
            marker=dict(color=colores_dom),
            text=dominancia["Alertas"], textposition="outside",
            textfont=dict(color="#c9d1d9", size=12),
            hovertemplate="<b>%{y}</b><br>Alertas: <b>%{x}</b><extra></extra>",
        ))
        fig_dom.update_layout(plotly_dark_layout(
            xaxis_title="Cantidad de alertas generadas",
            height=300,
            yaxis=dict(autorange="reversed"),
        ))
        st.plotly_chart(fig_dom, use_container_width=True)

        # Participación porcentual
        dominancia["% Participación"] = (
            dominancia["Alertas"] / total_alertas_dom * 100
        ).round(1).astype(str) + "%" if total_alertas_dom > 0 else "0%"
        st.markdown(render_html_table(dominancia, max_height=300), unsafe_allow_html=True)

    # ── TAB 2: Motor de Explicabilidad ──────────────────────────────────────
    with tab2:
        _section("Motor de Explicabilidad — Composición del Puntaje")
        st.markdown("""
        <div style="background:#171c23; border-left:3px solid #3b82f6; padding:14px; margin-bottom:16px; font-size:12px; color:#a08e7a;">
            Muestra cómo se construyó el puntaje por nivel de riesgo. Analiza qué pilares
            (S_T, S_C, S_B, S_N) contribuyen más a cada segmento y detecta desbalances de ponderación.
        </div>""", unsafe_allow_html=True)

        comp = _score_composition(casos)
        if comp.empty:
            st.info("No hay datos suficientes para la composición.")
        else:
            fig_comp = go.Figure()
            colores_comp = ["#ef4444", "#f97316", "#eab308", "#22c55e"]
            for i, nivel in enumerate(comp["Nivel"]):
                row = comp[comp["Nivel"] == nivel].iloc[0]
                vals = [row.get(lbl, 0) for lbl in _LABEL_SCORE]
                fig_comp.add_trace(go.Bar(
                    name=nivel, x=_LABEL_SCORE, y=vals,
                    marker_color=colores_comp[i % len(colores_comp)],
                    hovertemplate=f"<b>{nivel}</b><br>%{{x}}: <b>%{{y:.2f}}</b><extra></extra>",
                ))
            fig_comp.update_layout(plotly_dark_layout(
                barmode="group",
                yaxis_title="Puntaje promedio (0–10)",
                height=350,
                legend=dict(font=dict(color="#c9d1d9"), bgcolor="rgba(0,0,0,0)"),
            ))
            st.plotly_chart(fig_comp, use_container_width=True)

            st.markdown("**Detalle por nivel de riesgo**")
            comp_view = comp.copy()
            for lbl in _LABEL_SCORE:
                if lbl in comp_view.columns:
                    comp_view[lbl] = comp_view[lbl].map(lambda v: f"{v:.2f}")
            st.markdown(render_html_table(comp_view, max_height=300), unsafe_allow_html=True)

            # Radar del cliente más crítico
            top_cliente = casos.sort_values("Score_Max", ascending=False).iloc[0] if not casos.empty else None
            if top_cliente is not None:
                st.markdown(f"**Radar de componentes — Cliente de mayor riesgo: `{top_cliente['Cliente']}`**")
                vals_radar = [
                    top_cliente.get("ST_Max", 0), top_cliente.get("SC_Max", 0),
                    top_cliente.get("SB_Max", 0), top_cliente.get("SN_Max", 0),
                ]
                fig_r = go.Figure(go.Scatterpolar(
                    r=vals_radar + [vals_radar[0]],
                    theta=_LABEL_SCORE + [_LABEL_SCORE[0]],
                    fill="toself", fillcolor="rgba(245,158,11,0.12)",
                    line=dict(color="#f59e0b", width=2),
                    name=str(top_cliente["Cliente"]),
                ))
                fig_r.update_layout(
                    paper_bgcolor="#0f141b", plot_bgcolor="#0f141b",
                    polar=dict(
                        bgcolor="#171c23",
                        radialaxis=dict(visible=True, range=[0, 10], color="#6e7681"),
                        angularaxis=dict(color="#8b949e"),
                    ),
                    showlegend=False, height=320, margin=dict(l=40, r=40, t=30, b=30),
                )
                st.plotly_chart(fig_r, use_container_width=True)

    # ── TAB 3: Estimación de Falsos Positivos ───────────────────────────────
    with tab3:
        _section("Estimación de Falsos Positivos")
        st.markdown("""
        <div style="background:#171c23; border-left:3px solid #10b981; padding:14px; margin-bottom:16px; font-size:12px; color:#a08e7a;">
            Estima el ruido analítico: alertas generadas sobre clientes clasificados como Bajo riesgo.
            Una tasa &gt;30% sugiere que los umbrales necesitan recalibración.
        </div>""", unsafe_allow_html=True)

        fp, total_a, tasa_fp = _calcular_fp_estimado(df, casos)

        col_fp1, col_fp2, col_fp3 = st.columns(3)
        color_tasa = "red" if tasa_fp > 30 else "amber" if tasa_fp > 15 else "green"
        with col_fp1:
            st.markdown(_card("Total de Alertas", total_a, "Generadas por el motor"), unsafe_allow_html=True)
        with col_fp2:
            st.markdown(_card("Alertas en Clientes de Riesgo Bajo", fp, "Potenciales falsos positivos", color_tasa), unsafe_allow_html=True)
        with col_fp3:
            st.markdown(_card("Tasa de Falsos Positivos Estimada", f"{tasa_fp}%", "Umbral recomendado: <15%", color_tasa), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # FP por regla
        clientes_bajo = set(casos[casos["Nivel_Riesgo"] == "Bajo"]["Cliente"].tolist())
        df_bajo = df[df["Cliente"].isin(clientes_bajo)]
        fp_regla = []
        for col_a, regla in zip(_COLS_ALERTA, _REGLAS):
            if col_a in df.columns:
                total_r = int(df[col_a].sum())
                fp_r = int(df_bajo[col_a].sum()) if col_a in df_bajo.columns else 0
                tasa_r = round(fp_r / total_r * 100, 1) if total_r > 0 else 0.0
                fp_regla.append({"Regla": regla, "Total de Alertas": total_r,
                                  "Falsos Positivos Estimados": fp_r, "Tasa de Falsos Positivos %": tasa_r})

        df_fp = pd.DataFrame(fp_regla).sort_values("Tasa de Falsos Positivos %", ascending=False)
        if not df_fp.empty:
            df_fp["Tasa de Falsos Positivos %"] = df_fp["Tasa de Falsos Positivos %"].map(lambda v: f"{v:.1f}%")
        st.markdown(render_html_table(df_fp, max_height=320), unsafe_allow_html=True)

        if tasa_fp > 30:
            st.markdown("""
            <div class="warning-box">
                <strong>Tasa de falso positivo elevada.</strong> Considere aumentar los umbrales de detección
                o ajustar los multiplicadores de perfil para reducir el ruido analítico.
            </div>""", unsafe_allow_html=True)

    # ── TAB 4: Motor de Pruebas de Estrés ───────────────────────────────────
    with tab4:
        _section("Motor de Pruebas de Estrés — Simulación de Configuración")
        st.markdown("""
        <div style="background:#171c23; border-left:3px solid #a855f7; padding:14px; margin-bottom:16px; font-size:12px; color:#a08e7a;">
            Simula el impacto de modificar un parámetro clave sin reprocesar todo el motor.
            Útil para calibrar umbrales antes de aplicar cambios definitivos.
        </div>""", unsafe_allow_html=True)

        param_opts = {
            "Umbral Monto Absoluto (Q)": "umbral_absoluto",
            "Multiplicador Acumulado (Nx)": "mult_acumulado",
            "Umbral de Fragmentación (operaciones/día)": "umbral_smurfing",
        }
        param_label = st.selectbox("Parámetro a simular", list(param_opts.keys()))
        param_key = param_opts[param_label]

        val_actual = cfg.get(param_key, 1)

        if param_key == "umbral_absoluto":
            rango = st.slider("Rango de simulación (Q)", 5000, 100000,
                              (max(5000, int(val_actual) - 10000), min(100000, int(val_actual) + 20000)), 1000)
            valores_sim = list(range(rango[0], rango[1] + 1, max(1000, (rango[1] - rango[0]) // 10)))
        elif param_key == "mult_acumulado":
            rango = st.slider("Rango multiplicador", 0.5, 10.0, (max(0.5, float(val_actual) - 1.0), min(10.0, float(val_actual) + 2.0)), 0.5)
            valores_sim = [round(rango[0] + i * 0.5, 1) for i in range(int((rango[1] - rango[0]) / 0.5) + 1)]
        else:
            rango = st.slider("Rango del umbral de fragmentación", 2, 20, (max(2, int(val_actual) - 2), min(20, int(val_actual) + 4)), 1)
            valores_sim = list(range(rango[0], rango[1] + 1))

        alertas_sim = _stress_test(df, cfg, param_key, valores_sim)

        fig_stress = go.Figure()
        fig_stress.add_trace(go.Scatter(
            x=valores_sim, y=alertas_sim, mode="lines+markers",
            line=dict(color="#a855f7", width=2),
            marker=dict(color="#a855f7", size=6),
            hovertemplate="Valor: <b>%{x}</b><br>Alertas: <b>%{y}</b><extra></extra>",
        ))
        fig_stress.add_vline(x=val_actual, line=dict(color="#f59e0b", dash="dash", width=1.5),
                              annotation_text=f"Actual: {val_actual}", annotation_font_color="#f59e0b")
        fig_stress.update_layout(plotly_dark_layout(
            xaxis_title=param_label,
            yaxis_title="Alertas generadas",
            height=320,
        ))
        st.plotly_chart(fig_stress, use_container_width=True)

        st.markdown(f"""
        <div class="info-box">
            Valor actual: <strong>{val_actual}</strong> genera
            <strong>{_stress_test(df, cfg, param_key, [val_actual])[0]}</strong> alertas para esta regla.
            Ajuste el rango para ver cómo cambia la sensibilidad del motor.
        </div>""", unsafe_allow_html=True)

    # ── TAB 5: Análisis de Densidad de Riesgo ───────────────────────────────
    with tab5:
        _section("Análisis de Densidad de Riesgo")
        st.markdown("""
        <div style="background:#171c23; border-left:3px solid #ef4444; padding:14px; margin-bottom:16px; font-size:12px; color:#a08e7a;">
            Analiza la concentración del riesgo en la cartera. Identifica si el riesgo está
            concentrado en pocos clientes o distribuido. Una concentración extrema puede indicar
            un sesgo de reglas o un grupo de actividad inusual.
        </div>""", unsafe_allow_html=True)

        density = _risk_density(casos)

        col_d1, col_d2, col_d3 = st.columns(3)
        score_p90 = round(float(np.percentile(casos["Score_Max"], 90)), 2) if not casos.empty else 0
        score_medio_c = round(float(casos["Score_Max"].mean()), 2) if not casos.empty else 0
        clientes_criticos = int((casos["Nivel_Riesgo"] == "Crítico").sum())

        with col_d1:
            st.markdown(_card("Puntaje Promedio", score_medio_c, "Media de la cartera"), unsafe_allow_html=True)
        with col_d2:
            st.markdown(_card("Percentil 90 (Puntaje)", score_p90, "Umbral del 10% más riesgoso", "red"), unsafe_allow_html=True)
        with col_d3:
            st.markdown(_card("Clientes Críticos", clientes_criticos, "Requieren acción inmediata", "red"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        colores_dens = ["#22c55e" if i < 3 else "#eab308" if i < 6 else "#f97316" if i < 8 else "#ef4444"
                        for i in range(len(density))]
        fig_dens = go.Figure(go.Bar(
            x=density["Rango de Puntaje"], y=density["Clientes"],
            marker=dict(color=colores_dens),
            text=density["Clientes"], textposition="outside",
            textfont=dict(color="#c9d1d9", size=11),
            hovertemplate="Puntaje <b>%{x}</b><br>Clientes: <b>%{y}</b><extra></extra>",
        ))
        fig_dens.update_layout(plotly_dark_layout(
            xaxis_title="Rango de Puntaje", yaxis_title="N. de Clientes",
            height=320,
        ))
        st.plotly_chart(fig_dens, use_container_width=True)

        # Matriz de Distribución de Alertas
        st.markdown("---")
        _section("Matriz de Distribución de Alertas")
        nivel_counts = casos["Nivel_Riesgo"].value_counts().reset_index()
        nivel_counts.columns = ["Nivel", "Clientes"]
        color_map = {"Crítico": "#ef4444", "Alto": "#f97316", "Medio": "#eab308", "Bajo": "#22c55e"}
        fig_dist = go.Figure(go.Pie(
            labels=nivel_counts["Nivel"], values=nivel_counts["Clientes"],
            marker=dict(colors=[color_map.get(n, "#8b949e") for n in nivel_counts["Nivel"]]),
            hole=0.55,
            textinfo="label+percent",
            textfont=dict(color="#dee2ed", size=12),
            hovertemplate="<b>%{label}</b><br>Clientes: <b>%{value}</b><br>%{percent}<extra></extra>",
        ))
        fig_dist.update_layout(
            paper_bgcolor="#0f141b", plot_bgcolor="#0f141b",
            showlegend=True,
            legend=dict(font=dict(color="#c9d1d9"), bgcolor="rgba(0,0,0,0)"),
            height=300, margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_dist, use_container_width=True)
