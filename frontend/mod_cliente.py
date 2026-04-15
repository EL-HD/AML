import streamlit as st
import plotly.graph_objects as go
from frontend.mod_utils import plotly_dark_layout

def mostrar(df, casos, cfg):
    st.markdown("""<div class="info-box"><strong>ANÁLISIS POR CLIENTE</strong> — Perfil detallado de comportamiento transaccional IMPERATOR. Identifica vectores de riesgo individuales, picos de actividad estadística y patrones de fragmentación técnica (smurfing).</div>""", unsafe_allow_html=True)

    cliente = st.selectbox("Selecciona un cliente para analizar", df["Cliente"].unique())
    datos = df[df["Cliente"] == cliente].sort_values("Fecha")
    datos["Fecha_str"] = datos["Fecha"].dt.strftime("%Y-%m-%d")

    # KPIs del cliente
    info_cliente = casos[casos["Cliente"] == cliente].iloc[0]
    col1, col2, col3, col4 = st.columns(4)

    nivel = info_cliente["Nivel_Riesgo"]
    color_card = "red" if "Crítico" in nivel else ("amber" if "Alto" in nivel else ("blue" if "Medio" in nivel else "green"))

    with col1:
        st.markdown(f"""
        <div class="metric-card {color_card}">
            <div class="metric-number">{nivel}</div>
            <div class="metric-label">Nivel de Riesgo</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card amber">
            <div class="metric-number">{int(info_cliente['Score_Max'])}</div>
            <div class="metric-label">Score Máximo</div>
            <div class="metric-sub">sobre 12 posibles</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card blue">
            <div class="metric-number">{int(info_cliente['Transacciones'])}</div>
            <div class="metric-label">Transacciones</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card green">
            <div class="metric-number">Q{info_cliente['Total_Mensual']:,.0f}</div>
            <div class="metric-label">Total Mensual</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── RESUMEN ANALÍTICO DEL CLIENTE (IA) ──────────────────────────────
    st.markdown('<div class="section-title">Resumen Analítico del Cliente <span class="section-badge">IA</span></div>', unsafe_allow_html=True)

    datos_cliente = df[df["Cliente"] == cliente]

    # Calcular métricas para el prompt
    picos_count      = int(datos_cliente["Pico"].sum())
    smurfing_count   = int(datos_cliente["Smurfing"].sum())
    alerta_abs_count = int(datos_cliente["Alerta_Absoluto"].sum())
    alerta_15_count  = int(datos_cliente["Alerta_15"].sum())
    alerta_frec      = bool(datos_cliente["Alerta_Frecuencia"].iloc[0])
    alerta_acum      = bool(datos_cliente["Alerta_Acumulado"].iloc[0])
    score_max_c      = int(info_cliente["Score_Max"])
    total_c          = float(info_cliente["Total_Mensual"])
    transac_c        = int(info_cliente["Transacciones"])
    perfil_c         = float(datos_cliente["Perfil"].iloc[0])
    nivel_c          = info_cliente["Nivel_Riesgo"]

    # ── RESUMEN DEL CLIENTE (MANUAL) ──────────────────────────────
    st.markdown('<div class="section-title">Resumen del Cliente</div>', unsafe_allow_html=True)

    # Construcción de resumen manual basado en reglas
    resumen_manual = f"El cliente presenta un nivel de riesgo {nivel_c} con un score acumulado de {score_max_c}/12. "
    resumen_manual += f"En el período analizado, realizó {transac_c} transacciones por un volumen total de Q{total_c:,.2f}, frente a un perfil esperado de Q{perfil_c:,.2f}. "

    alertas_list = []
    if picos_count > 0: alertas_list.append(f"{picos_count} pico(s) estadísticos(s)")
    if alerta_abs_count > 0: alertas_list.append(f"{alerta_abs_count} transacción(es) mayor(es) al umbral absoluto")
    if alerta_15_count > 0: alertas_list.append(f"{alerta_15_count} exceso(s) sobre tolerancia de perfil")
    if smurfing_count > 0: alertas_list.append(f"{smurfing_count} caso(s) de smurfing detectados")
    
    if alertas_list:
        resumen_manual += "Se identificaron los siguientes hallazgos inusuales: " + ", ".join(alertas_list) + ". "
    else:
        resumen_manual += "No se registraron parámetros inusuales específicos de picos estadísticos ni smurfing. "
    
    if alerta_frec:
        resumen_manual += "Adicionalmente, exhibe una frecuencia operativa recurrentemente alta. "
    if alerta_acum:
        resumen_manual += "Por otro lado, el monto acumulado en el tiempo evaluado sobrepasa de manera considerable los parámetros base de su perfil transaccional mensual. "

    resumen_manual += "<br><br>"
    if "Crítico" in nivel_c:
        resumen_manual += "<strong>Recomendación Crítica:</strong> Congelar transacciones inmediatamente y reportar este caso a la SIB (mediante la IVE) generando un RTS (Reporte de Transacción Sospechosa)."
    elif "Alto" in nivel_c:
        resumen_manual += "<strong>Recomendación Alta:</strong> Solicitar Debida Diligencia Ampliada (EDD) e indagar activamente por los documentos de justificación del origen de los fondos."
    elif "Medio" in nivel_c:
        resumen_manual += "<strong>Recomendación Media:</strong> Proceder a clasificación bajo monitoreo reforzado y programar una actualización inminente de su perfil legal y financiero."
    else:
        resumen_manual += "<strong>Recomendación Baja:</strong> La actividad se considera dentro de los límites y perfil del usuario, continuar bajo las medidas de Debida Diligencia Estándar vigente."

    nivel_color = (
        "#ef4444" if "Crítico" in nivel_c else
        "#f97316" if "Alto"    in nivel_c else
        "#eab308" if "Medio"   in nivel_c else
        "#22c55e"
    )

    st.markdown(f"""
    <div style="background-color: #1b2027; border: 1px solid {nivel_color}; border-radius: 0px; padding: 24px; border-left: 8px solid {nivel_color};">
        <div style="font-size: 11px; color: #f59e0b; text-transform: uppercase; letter-spacing: 2px; font-family: 'IBM Plex Mono', monospace; margin-bottom: 15px;">
            <span class="pulse-dot"></span> RESUMEN TÉCNICO IMPERATOR INTELLIGENCE
        </div>
        <div style="color: #dee2ed; font-size: 14px; line-height: 1.8;">
            {resumen_manual}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Tendencia
    st.markdown('<div class="section-title">Tendencia de Montos</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        Evolución de los montos transaccionados por el cliente. La línea punteada indica su <strong>perfil de riesgo</strong>
        (nivel esperado de actividad). Montos consistentemente por encima del perfil son una señal de alerta.
    </div>
    """, unsafe_allow_html=True)

    perfil_val = datos["Perfil"].iloc[0]
    fig_tend = go.Figure()
    fig_tend.add_trace(go.Scatter(
        x=datos["Fecha_str"], y=datos["Monto"],
        mode='lines+markers', name='Monto',
        line=dict(color='#3b82f6', width=2),
        marker=dict(size=6, color='#3b82f6'),
        hovertemplate="<b>%{x}</b><br>Monto: <b>Q%{y:,.2f}</b><extra></extra>",
    ))
    fig_tend.add_trace(go.Scatter(
        x=datos["Fecha_str"], y=[perfil_val]*len(datos),
        mode='lines', name=f'Perfil: Q{perfil_val:,.0f}',
        line=dict(color='#f59e0b', width=1.5, dash='dash'),
        hovertemplate="Perfil: <b>Q%{y:,.0f}</b><extra></extra>",
    ))
    # Área de exceso sobre perfil
    exceso_y = [m if m > perfil_val else perfil_val for m in datos["Monto"].values]
    fig_tend.add_trace(go.Scatter(
        x=datos["Fecha_str"], y=exceso_y,
        fill='tonexty', fillcolor='rgba(239,68,68,0.1)',
        line=dict(width=0), showlegend=False, hoverinfo='skip',
        name='Exceso'
    ))
    fig_tend.update_layout(plotly_dark_layout(
        yaxis_title="Monto (Q)", height=320,
        xaxis=dict(tickangle=-45, gridcolor='#30353d', linecolor='#30353d', tickfont=dict(color='#d8c3ad', size=9)),
    ))
    st.plotly_chart(fig_tend, use_container_width=True)
    st.markdown("""<div class="info-box" style="margin-top: 5px;"><b>📌 Interpretación:</b> Análisis de desviación sobre perfil de riesgo. El área roja destaca transacciones que superan los umbrales de tolerancia institucional.</div>""", unsafe_allow_html=True)


    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown('<div class="section-title">Detección de Picos Anómalos</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
            Transacciones que superan la media histórica + 2 desviaciones estándar del cliente.
            Los puntos rojos son anomalías estadísticas que merecen investigación.
        </div>
        """, unsafe_allow_html=True)

        media = datos["Media"].iloc[0]
        std   = datos["Std"].iloc[0] if datos["Std"].iloc[0] > 0 else 0
        picos = datos[datos["Pico"] == True]

        fig_picos = go.Figure()
        fig_picos.add_trace(go.Scatter(
            x=datos["Fecha_str"], y=datos["Monto"],
            mode='lines+markers', name='Monto',
            line=dict(color='#58a6ff', width=1.5),
            marker=dict(size=5, color='#58a6ff'),
            hovertemplate="<b>%{x}</b><br>Monto: Q%{y:,.2f}<extra></extra>",
        ))
        if len(picos) > 0:
            fig_picos.add_trace(go.Scatter(
                x=picos["Fecha_str"], y=picos["Monto"],
                mode='markers', name=f'{len(picos)} pico(s) anómalo(s)',
                marker=dict(size=12, color='#ef4444', line=dict(color='#fca5a5', width=1.5)),
                hovertemplate="<b>⚠ Pico anómalo</b><br>%{x}<br>Monto: Q%{y:,.2f}<extra></extra>",
            ))
        fig_picos.add_hline(y=media, line=dict(color='#8b949e', dash='dot', width=1),
                            annotation_text="Media", annotation_font_color='#8b949e')
        fig_picos.add_hline(y=media + 2*std, line=dict(color='#ef4444', dash='dash', width=1),
                            annotation_text="+2 Std", annotation_font_color='#ef4444')
        fig_picos.update_layout(plotly_dark_layout(
            height=320,
            xaxis=dict(tickangle=-45, gridcolor='#30353d', linecolor='#30353d', tickfont=dict(color='#d8c3ad', size=8)),
        ))
        st.plotly_chart(fig_picos, use_container_width=True)
        st.markdown("""<div class="info-box" style="margin-top: 5px;"><b>📌 Interpretación:</b> Identificación de anomalías estadísticas (+2 Std). Los diamantes rojos representan actividad que rompe la distribución normal del cliente.</div>""", unsafe_allow_html=True)


    with col_g2:
        st.markdown('<div class="section-title">Frecuencia Diaria de Operaciones</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
            Número de transacciones por día. Días con ≥5 operaciones activan la alerta de <strong>smurfing</strong>
            (posible fragmentación de montos para evadir controles).
        </div>
        """, unsafe_allow_html=True)

        freq_d = datos.groupby("Fecha_str").size().reset_index(name="N")
        freq_colors = ["#ef4444" if v >= cfg["umbral_smurfing"] else "#3b82f6" for v in freq_d["N"]]

        fig_freq = go.Figure(go.Bar(
            x=freq_d["Fecha_str"], y=freq_d["N"],
            marker=dict(color=freq_colors, line=dict(color='#0d1117', width=0.5)),
            name='Operaciones',
            hovertemplate="<b>%{x}</b><br>Transacciones: <b>%{y}</b><extra></extra>",
        ))
        fig_freq.add_hline(
            y=cfg["umbral_smurfing"],
            line=dict(color='#f59e0b', dash='dash', width=1.2),
            annotation_text=f'Umbral smurfing ({cfg["umbral_smurfing"]})',
            annotation_font_color='#f59e0b',
        )
        fig_freq.update_layout(plotly_dark_layout(
            yaxis_title="N° de transacciones", height=320,
            xaxis=dict(tickangle=-45, gridcolor='#30353d', linecolor='#30353d', tickfont=dict(color='#d8c3ad', size=8)),
        ))
        st.plotly_chart(fig_freq, use_container_width=True)
        st.markdown("""<div class="info-box" style="margin-top: 5px;"><b>📌 Interpretación:</b> Vigilancia de fragmentación estructural. Barras rojas indican una densidad operativa superior al umbral crítico de smurfing.</div>""", unsafe_allow_html=True)
