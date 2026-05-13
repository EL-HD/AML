import streamlit as st
import plotly.graph_objects as go
from frontend.mod_utils import plotly_dark_layout, render_html_table

def mostrar(df, casos, matriz_alertas, pep_cpe_info=None):
    st.markdown("""<div class="info-box"><strong>RESUMEN EJECUTIVO</strong> — Análisis de alto nivel IMPERATOR Intelligence. Muestra indicadores críticos y distribución de riesgo detectada. Optimizado para supervisión operativa mediante capas tonales.</div>""", unsafe_allow_html=True)

    # KPIs
    total_clientes = len(casos)
    clientes_alerta = len(df[df["Score"] > 0]["Cliente"].unique())
    criticos = len(casos[casos["Nivel_Riesgo"] == "Crítico"])
    altos = len(casos[casos["Nivel_Riesgo"] == "Alto"])
    total_alertas = int(df["Score"].gt(0).sum())
    monto_total = df["Monto"].sum()
    pct_salud = (len(casos[casos["Nivel_Riesgo"] == "Bajo"]) / total_clientes * 100) if total_clientes else 100

    st.markdown("<br>", unsafe_allow_html=True)
    
    col_kpi1, col_kpi2 = st.columns([1.5, 2.5])
    
    with col_kpi1:
        # GAUGE: Salud de Cartera
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = pct_salud,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Salud de Cartera (% Bajo Riesgo)", 'font': {'size': 14}},
            gauge = {
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#8b949e"},
                'bar': {'color': "#22c55e"},
                'bgcolor': "#161b22",
                'borderwidth': 2,
                'bordercolor': "#30363d",
                'steps': [
                    {'range': [0, 50], 'color': 'rgba(239, 68, 68, 0.1)'},
                    {'range': [50, 80], 'color': 'rgba(249, 115, 22, 0.1)'},
                    {'range': [80, 100], 'color': 'rgba(34, 197, 94, 0.1)'}],
                'threshold': {
                    'line': {'color': "white", 'width': 4},
                    'thickness': 0.75,
                    'value': 90}}))
        
        fig_gauge.update_layout(plotly_dark_layout(height=260, margin=dict(t=50, b=10, l=30, r=30)))
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown("""<div class="info-box" style="margin-top: 5px;"><b>Interpretación:</b> Porcentaje de clientes en 'Bajo Riesgo'. Refleja la salud operativa de la cartera según los parámetros del Sovereign Intelligence Framework.</div>""", unsafe_allow_html=True)

    with col_kpi2:
        # Mini-metricas horizontales
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div class="metric-card blue">
                <div class="metric-number">{total_clientes}</div>
                <div class="metric-label">Clientes Analizados</div>
                <div class="metric-sub">{clientes_alerta} con alguna alerta</div>
            </div>""", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="metric-card amber">
                <div class="metric-number">{total_alertas:,}</div>
                <div class="metric-label">Total de Alertas</div>
                <div class="metric-sub">{altos} clientes en nivel Alto</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="metric-card red">
                <div class="metric-number">{criticos}</div>
                <div class="metric-label">Clientes Críticos</div>
                <div class="metric-sub">Requieren revisión inmediata</div>
            </div>""", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="metric-card green">
                <div class="metric-number">Q{monto_total:,.0f}</div>
                <div class="metric-label">Volumen Total</div>
                <div class="metric-sub">Monto acumulado analizado</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="section-title">Distribución de Riesgo por Cliente</div>', unsafe_allow_html=True)
        riesgo_counts = casos["Nivel_Riesgo"].value_counts()

        def color_por_nivel(nivel):
            if "Crítico" in nivel:  return "#ef4444"
            if "Alto"    in nivel:  return "#f97316"
            if "Medio"   in nivel:  return "#eab308"
            if "Bajo"    in nivel:  return "#22c55e"
            return "#8b949e"
        colors_list = [color_por_nivel(k) for k in riesgo_counts.index]

        import re as _re
        labels_limpias = [_re.sub(r'[^\u0000-\u024F\s]', '', k).strip()
                          for k in riesgo_counts.index]

        fig_pie = go.Figure(go.Pie(
            labels=labels_limpias,
            values=riesgo_counts.values,
            marker=dict(colors=colors_list, line=dict(color='#0d1117', width=2)),
            textfont=dict(color='#0d1117', size=13),
            hovertemplate="<b>%{label}</b><br>Clientes: %{value}<br>Porcentaje: %{percent}<extra></extra>",
            hole=0,
        ))
        fig_pie.update_layout(plotly_dark_layout(showlegend=True, height=360))
        st.plotly_chart(fig_pie, use_container_width=True)
        st.markdown("""<div class="info-box" style="margin-top: 10px;"><b>Interpretación:</b> Segmentación porcentual por nivel de riesgo. Los valores se derivan de la matriz de ponderación activa en el motor de cumplimiento.</div>""", unsafe_allow_html=True)

    with col_b:
        st.markdown('<div class="section-title">Alertas por Tipo</div>', unsafe_allow_html=True)

        tipos_bar = matriz_alertas["Tipo de Alerta"].str.replace(r'\s*\(.*\)', '', regex=True).tolist()
        cantidades_bar = matriz_alertas["Cantidad"].tolist()
        impactos = matriz_alertas["Nivel de Impacto"].tolist()
        bar_colors = ["#ef4444" if "Crítico" in imp else "#f97316" if "Alto" in imp else "#eab308" for imp in impactos]

        fig_bar = go.Figure(go.Bar(
            x=cantidades_bar,
            y=tipos_bar,
            orientation='h',
            marker=dict(color=bar_colors, line=dict(color='#0d1117', width=0.5)),
            text=cantidades_bar,
            textposition='outside',
            textfont=dict(color='#c9d1d9', size=11),
            hovertemplate="<b>%{y}</b><br>Alertas: <b>%{x}</b><extra></extra>",
        ))
        fig_bar.update_layout(plotly_dark_layout(
            xaxis_title="Cantidad de alertas",
            height=360,
            yaxis=dict(autorange='reversed', gridcolor='#30353d', linecolor='#30353d', tickfont=dict(color='#d8c3ad')),
        ))
        st.plotly_chart(fig_bar, use_container_width=True)
        st.markdown("""<div class="info-box" style="margin-top: 10px;"><b>Interpretación:</b> Detección analítica por tipología. Identifica vulnerabilidades y patrones recurrentes en el ecosistema transaccional.</div>""", unsafe_allow_html=True)

    # Línea de tiempo
    st.markdown("---")
    st.markdown('<div class="section-title">Volumen de Transacciones en el Tiempo</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        Evolución diaria del volumen transaccional. Los picos pueden indicar ventanas de actividad sospechosa
        o eventos de smurfing coordinado. Se recomienda correlacionar con fechas festivas o eventos externos.
    </div>
    """, unsafe_allow_html=True)

    timeline = df.groupby("Fecha_dia")["Monto"].sum().reset_index()
    fechas_str = [str(d) for d in timeline["Fecha_dia"]]
    media_vol = timeline["Monto"].mean()
    std_vol = timeline["Monto"].std() if not timeline.empty else 0

    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(
        x=fechas_str, y=timeline["Monto"],
        mode='lines+markers',
        line=dict(color='#3b82f6', width=2),
        marker=dict(size=6, color='#3b82f6', line=dict(color='#93c5fd', width=1)),
        fill='tozeroy', fillcolor='rgba(59,130,246,0.15)',
        name='Volumen',
        hovertemplate="<b>%{x}</b><br>Monto: <b>Q%{y:,.0f}</b><extra></extra>",
    ))
    
    # Puntos de interrupción / Anomalías
    umbral_anomalo = media_vol + (std_vol * 1.5)
    anomalias = timeline[timeline["Monto"] > umbral_anomalo]
    if not anomalias.empty:
        fig_line.add_trace(go.Scatter(
            x=[str(d) for d in anomalias["Fecha_dia"]],
            y=anomalias["Monto"],
            mode='markers',
            marker=dict(color='#ef4444', size=10, symbol='diamond', line=dict(color='#fca5a5', width=1)),
            name='Pico Anómalo',
            hovertemplate="<b>Anomalía: %{x}</b><br>Monto: <b>Q%{y:,.0f}</b><extra></extra>"
        ))

    fig_line.update_layout(plotly_dark_layout(
        yaxis_title="Monto total (Q)",
        height=320,
        xaxis=dict(tickangle=-45, gridcolor='#30353d', linecolor='#30353d', tickfont=dict(color='#d8c3ad', size=9)),
    ))
    st.plotly_chart(fig_line, use_container_width=True)
    st.markdown("""<div class="info-box" style="margin-top: 10px;"><b>Interpretación:</b> Serie temporal del volumen económico. Los diamantes rojos indican puntos de ruptura estadística o actividad atípica coordinada.</div>""", unsafe_allow_html=True)

    # Gráfica para Tipo de Operación
    if "TipoOperacion" in df.columns:
        st.markdown("---")
        st.markdown('<div class="section-title">Flujo por Tipo de Operación</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
            Distribución del volumen según el canal o rubro reportado. Esto ayuda a segmentar el monitoreo
            o auditorías por naturaleza del flujo (ej. efectivo, transferencias bancarias).
        </div>
        """, unsafe_allow_html=True)
        
        flujo_tipo = df.groupby("TipoOperacion")["Monto"].sum().reset_index()
        fig_tipo = go.Figure(go.Bar(
            x=flujo_tipo["TipoOperacion"], y=flujo_tipo["Monto"],
            marker=dict(color="#f97316", line=dict(color='#0d1117', width=0.5)),
            text=[f"Q{v/1000:,.0f}k" if v >= 1000 else f"Q{v:,.0f}" for v in flujo_tipo["Monto"]],
            textposition='auto',
            textfont=dict(color='#f8fafc', size=11),
            hovertemplate="<b>%{x}</b><br>Total: <b>Q%{y:,.0f}</b><extra></extra>"
        ))
        fig_tipo.update_layout(plotly_dark_layout(
            yaxis_title="Monto Acumulado (Q)",
            height=320,
        ))
        st.plotly_chart(fig_tipo, use_container_width=True)
        st.markdown("""<div class="info-box" style="margin-top: 10px;"><b>Interpretación:</b> Este gráfico compara el volumen agregado por tipo de operación y permite identificar qué canales concentran mayor exposición económica dentro del período analizado.</div>""", unsafe_allow_html=True)
        # --- BUBBLE CHART: MATRIZ DE OPORTUNIDAD DE CANAL ---
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Matriz de Oportunidad de Canal (Mercadeo vs Riesgo)</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
            Esta matriz cruza el <b>Volumen Económico</b> (Y) contra el <b>Alcance de Clientes</b> (X). 
            El <b>tamaño</b> de la burbuja es la cantidad de transacciones y el <b>color</b> representa el 
            promedio de riesgo. El cuadrante superior derecho indica los canales más rentables para nuevos productos.
        </div>
        """, unsafe_allow_html=True)

        # Preparar data para el Bubble Chart
        stats_bubble = df.groupby("TipoOperacion").agg({
            "Cliente": "nunique",
            "Monto": "sum",
            "Score": "mean",
            "Fecha": "count"
        }).reset_index()
        stats_bubble.columns = ["Canal", "Clientes", "Volumen", "Riesgo_Promedio", "Transacciones"]

        fig_bubble = go.Figure()
        fig_bubble.add_trace(go.Scatter(
            x=stats_bubble["Clientes"],
            y=stats_bubble["Volumen"],
            mode='markers+text',
            marker=dict(
                size=stats_bubble["Transacciones"],
                sizemode='area',
                sizeref=2.*max(stats_bubble["Transacciones"])/(40.**2),
                sizemin=4,
                color=stats_bubble["Riesgo_Promedio"],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Score Riesgo", tickfont=dict(color='#8b949e')),
                line=dict(width=2, color='#0d1117')
            ),
            text=stats_bubble["Canal"],
            textposition="top center",
            hovertemplate="<b>%{text}</b><br>Clientes Únicos: %{x}<br>Volumen Total: Q%{y:,.0f}<br>Riesgo Promedio: %{marker.color:.2f}<extra></extra>"
        ))

        fig_bubble.update_layout(plotly_dark_layout(
            xaxis_title="Alcance (Clientes Únicos)",
            yaxis_title="Volumen Económico (Q)",
            height=450,
        ))
        st.plotly_chart(fig_bubble, use_container_width=True)
        # --- ESTRATEGIA Y BUSINESS INTELLIGENCE (BI) ---
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Insight Estratégico y Oportunidades</div>', unsafe_allow_html=True)
        
        # 1. Cálculos de Inteligencia
        conteo_tipo = df["TipoOperacion"].value_counts()
        canal_frecuente = conteo_tipo.index[0] if not conteo_tipo.empty else "N/A"
        
        monto_tipo = df.groupby("TipoOperacion")["Monto"].sum()
        canal_volumen = monto_tipo.idxmax() if not monto_tipo.empty else "N/A"
        
        # Análisis de riesgo por canal
        criticos_canal = df[df["Score"] >= 3].groupby("TipoOperacion").size()
        canal_riesgoso = criticos_canal.idxmax() if not criticos_canal.empty else "Ninguno"

        # 2. Generación de Estrategia Dinámica
        es_digital = any(x in str(canal_frecuente).lower() for x in ["app", "web", "transferencia", "digital"])
        es_cash = any(x in str(canal_frecuente).lower() for x in ["efectivo", "cash", "ventanilla", "caja"])

        titulo_estrategia = "Estrategia Comercial Recomendada"
        if es_digital:
            desc_estrategia = f"El canal <b>{canal_frecuente}</b> es el preferido por tus clientes. Se recomienda lanzar campañas de fidelización digital (Cashback, Puntos) y notificaciones Push para productos de crédito rápido."
        elif es_cash:
            desc_estrategia = f"El uso de <b>{canal_frecuente}</b> es predominante. Existe una oportunidad para migrar estos clientes a canales digitales mediante incentivos de 'Primera Transferencia' o quioscos de auto-servicio."
        else:
            desc_estrategia = f"El canal <b>{canal_frecuente}</b> lidera la transaccionalidad. Fortalecer la atención en este punto mejorará la retención del cliente."

        st.markdown(f"""
        <div style="background-color: #1b2027; border: 1px solid #f59e0b; border-radius: 0px; padding: 24px; border-left: 8px solid #f59e0b;">
            <div style="color: #f59e0b; font-weight: 700; font-size: 18px; margin-bottom: 15px; display: flex; align-items: center; font-family: 'IBM Plex Sans', sans-serif;">
                <span class="pulse-dot"></span> {titulo_estrategia}
            </div>
            <div style="color: #dee2ed; font-size: 14px; line-height: 1.8;">
                {desc_estrategia}<br><br>
                <b style="color: #f59e0b;">SEGMENTACIÓN DE VALOR:</b> El canal <b>{canal_volumen}</b> concentra el mayor flujo de capital (Q{monto_tipo.max():,.0f}). Optimización recomendada para productos de alta rentabilidad.<br><br>
                <b style="color: #ef4444;">PROTOCOLO DE RIESGO:</b> Detección de anomalías críticas en el canal <b>{canal_riesgoso}</b>. Se requiere monitoreo de transacciones en tiempo real y revisión de EDD.
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── SECCIÓN PEP / CPE ─────────────────────────────────────────────────
    clientes_pep = casos[casos["EsPEP"] == True] if "EsPEP" in casos.columns else None
    clientes_cpe = casos[casos["EsCPE"] == True] if "EsCPE" in casos.columns else None

    tiene_pep = clientes_pep is not None and not clientes_pep.empty
    tiene_cpe = clientes_cpe is not None and not clientes_cpe.empty

    if tiene_pep or tiene_cpe:
        st.markdown("---")
        st.markdown('<div class="section-title">Asociados PEP / CPE Detectados</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box" style="border-left-color: #ef4444;">
            <strong>GAFI — Personas Expuestas Políticamente (PEP) y Contratista o Proveedor del Estado (CPE).</strong>
            Estos clientes requieren Debida Diligencia Ampliada (EDD) según las recomendaciones 12 y 22 del GAFI.
            Su presencia eleva automáticamente el score contextual (S_C) del modelo IMPERATOR.
        </div>
        """, unsafe_allow_html=True)

        col_pep, col_cpe = st.columns(2)

        with col_pep:
            st.markdown("""
            <div style="background:#171c23; border:1px solid #ef4444; border-top:3px solid #ef4444; padding:16px; margin-bottom:8px;">
                <div style="color:#ef4444; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:8px;">
                    ⚠ Personas Expuestas Políticamente (PEP)
                </div>
            </div>
            """, unsafe_allow_html=True)

            if tiene_pep:
                cols_mostrar = ["Cliente", "Score_Max", "Nivel_Riesgo", "Total_Mensual"]
                cols_existentes = [c for c in cols_mostrar if c in clientes_pep.columns]
                df_pep_show = clientes_pep[cols_existentes].copy()
                if "Total_Mensual" in df_pep_show.columns:
                    df_pep_show["Total_Mensual"] = df_pep_show["Total_Mensual"].apply(lambda x: f"Q{x:,.2f}")
                if "Score_Max" in df_pep_show.columns:
                    df_pep_show["Score_Max"] = df_pep_show["Score_Max"].apply(lambda x: f"{x:.2f}")
                df_pep_show.columns = [c.replace("_", " ") for c in df_pep_show.columns]
                st.markdown(render_html_table(df_pep_show, max_height=220), unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#6e7681; font-size:13px; padding:8px 0;">No se detectaron clientes PEP en el período analizado.</div>', unsafe_allow_html=True)

        with col_cpe:
            st.markdown("""
            <div style="background:#171c23; border:1px solid #f97316; border-top:3px solid #f97316; padding:16px; margin-bottom:8px;">
                <div style="color:#f97316; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:8px;">
                    ⚠ Contratista o Proveedor del Estado (CPE)
                </div>
            </div>
            """, unsafe_allow_html=True)

            if tiene_cpe:
                cols_mostrar = ["Cliente", "Score_Max", "Nivel_Riesgo", "Total_Mensual"]
                cols_existentes = [c for c in cols_mostrar if c in clientes_cpe.columns]
                df_cpe_show = clientes_cpe[cols_existentes].copy()
                if "Total_Mensual" in df_cpe_show.columns:
                    df_cpe_show["Total_Mensual"] = df_cpe_show["Total_Mensual"].apply(lambda x: f"Q{x:,.2f}")
                if "Score_Max" in df_cpe_show.columns:
                    df_cpe_show["Score_Max"] = df_cpe_show["Score_Max"].apply(lambda x: f"{x:.2f}")
                df_cpe_show.columns = [c.replace("_", " ") for c in df_cpe_show.columns]
                st.markdown(render_html_table(df_cpe_show, max_height=220), unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#6e7681; font-size:13px; padding:8px 0;">No se detectaron clientes CPE en el período analizado.</div>', unsafe_allow_html=True)
