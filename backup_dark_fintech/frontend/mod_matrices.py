import streamlit as st
import plotly.graph_objects as go
from frontend.mod_utils import plotly_dark_layout

def mostrar(casos, matriz_alertas):
    st.markdown("""<div class="info-box"><strong>MATRICES DE RIESGO</strong> — Arquitectura de decisión IMPERATOR. Clasificación técnica por perfiles de riesgo y tipologías de alerta analitica. Optimizado para calibración de umbrales y priorización táctica.</div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-title">👥 Matriz de Riesgo por Cliente</div>', unsafe_allow_html=True)
    st.markdown("""<div class="glossary"><div class="glossary-title">DICCIONARIO DE DATOS</div><div class="glossary-item"><span class="glossary-key">Cliente</span><span>Identificador soberano.</span></div><div class="glossary-item"><span class="glossary-key">Total_Mensual</span><span>Volumen económico en el ciclo.</span></div><div class="glossary-item"><span class="glossary-key">Score_Max</span><span>Magnitud de riesgo (IMPERATOR 0–12).</span></div><div class="glossary-item"><span class="glossary-key">Transacciones</span><span>Densidad operativa.</span></div><div class="glossary-item"><span class="glossary-key">Nivel_Riesgo</span><span>Clasificación táctica.</span></div></div>""", unsafe_allow_html=True)

    casos_view = casos.copy()
    for col in ["EsPEP", "EsCPE", "Ubicacion_Riesgo"]:
        if col in casos_view.columns:
            casos_view[col] = casos_view[col].apply(lambda x: "Si" if x else "--")

    st.dataframe(
        casos_view.sort_values("Score_Max", ascending=False).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total_Mensual": st.column_config.NumberColumn("Total Mensual (Q)", format="Q%.2f"),
            "Score_Max": st.column_config.NumberColumn("Score Máx.", format="%d pts"),
            "EsPEP": st.column_config.TextColumn("EsPEP"),
            "EsCPE": st.column_config.TextColumn("EsCPE"),
            "Ubicacion_Riesgo": st.column_config.TextColumn("Ubicacion_Riesgo"),
        }
    )

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">🛡️ Matriz de Tipos de Alerta</div>', unsafe_allow_html=True)
    st.markdown("""<div class="glossary"><div class="glossary-title">DICCIONARIO DE REGLAS</div><div class="glossary-item"><span class="glossary-key">Tipo de Alerta</span><span>Regla IMPERATOR aplicada.</span></div><div class="glossary-item"><span class="glossary-key">Cantidad</span><span>Detecciones activas.</span></div><div class="glossary-item"><span class="glossary-key">Nivel de Impacto</span><span>Magnitud de severidad.</span></div><div class="glossary-item"><span class="glossary-key">Peso en Score</span><span>Ponderación analítica.</span></div><div class="glossary-item"><span class="glossary-key">Descripción</span><span>Lógica de detección técnica.</span></div></div>""", unsafe_allow_html=True)

    # ── Tabla limpia HTML — texto blanco garantizado ──
    filas_html = ""
    for _, row in matriz_alertas.iterrows():
        imp = row["Nivel de Impacto"]
        if "Alto" in imp and "Medio" not in imp:
            imp_color = "#ef4444"
        elif "Medio-Alto" in imp:
            imp_color = "#f97316"
        elif "Medio" in imp:
            imp_color = "#eab308"
        else:
            imp_color = "#22c55e"
        filas_html += f"""
        <tr>
            <td style="font-weight: 600;">{row['Tipo de Alerta']}</td>
            <td style='text-align:center; font-family:IBM Plex Mono,monospace; font-weight:600; color:{imp_color};'>{int(row['Cantidad'])}</td>
            <td><span style='color:{imp_color}; font-weight:600; font-family:IBM Plex Mono,monospace;'>{imp}</span></td>
            <td style='text-align:center; font-family:IBM Plex Mono,monospace;'>{int(row['Peso en Score'])}</td>
            <td style='color:#d8c3ad; font-size:12px;'>{row['Descripción']}</td>
        </tr>"""

    st.markdown(f"""
    <div style="overflow-x:auto; border:1px solid #30353d; border-radius:0px; overflow:hidden;">
    <table class="aml-table">
        <thead><tr>
            <th>Tipo de Alerta</th>
            <th style='text-align:center;'>Detecciones</th>
            <th>Nivel de Impacto</th>
            <th style='text-align:center;'>Ponderación</th>
            <th>Descripción Técnica</th>
        </tr></thead>
        <tbody>{filas_html}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

    # Gráfica de pesos
    st.markdown("---")
    st.markdown('<div class="section-title">Contribución al Score por Tipo de Alerta</div>', unsafe_allow_html=True)

    contrib = (matriz_alertas["Cantidad"] * matriz_alertas["Peso en Score"]).tolist()
    tipos_contrib = matriz_alertas["Tipo de Alerta"].str.replace(r'\s*\(.*\)', '', regex=True).tolist()
    bar_c2 = ["#ef4444" if p >= 3 else ("#f97316" if p == 2 else "#eab308") for p in matriz_alertas["Peso en Score"]]

    fig_contrib = go.Figure(go.Bar(
        x=tipos_contrib, y=contrib,
        marker=dict(color=bar_c2, line=dict(color='#0d1117', width=0.5)),
        text=[str(int(v)) for v in contrib],
        textposition='outside',
        textfont=dict(color='#c9d1d9', size=11),
        hovertemplate="<b>%{x}</b><br>Score acumulado: <b>%{y}</b><extra></extra>",
    ))
    fig_contrib.update_layout(plotly_dark_layout(
        yaxis_title="Score total acumulado", height=340,
        xaxis=dict(tickangle=-30, gridcolor='#30353d', linecolor='#30353d', tickfont=dict(color='#d8c3ad', size=9)),
    ))
    st.plotly_chart(fig_contrib, use_container_width=True)
    st.markdown("""<div class="info-box" style="margin-top: 5px;"><b>📌 Interpretación:</b> Análisis de contribución ponderada. Destaca las reglas que inyectan mayor riesgo distribuido en la cartera analizada.</div>""", unsafe_allow_html=True)
