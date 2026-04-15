import streamlit as st

def mostrar(df):
    st.markdown("""
    <div class="info-box">
        <strong>BITÁCORA TRANSACCIONAL IMPERATOR</strong> — Registro granular de operaciones analizadas.
        Cada registro incluye vectores de detección técnicos y el score de riesgo acumulado según el motor de cumplimiento.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="glossary">
        <div class="glossary-title">DICCIONARIO DE VECTORES ANALÍTICOS</div>
        <div class="glossary-item"><span class="glossary-key">EsPEP / EsCPE</span><span>Asociado expuesto políticamente o sub-contratista estatal.</span></div>
        <div class="glossary-item"><span class="glossary-key">Alerta_15</span><span>Desviación superior a tolerancia sobre perfil del cliente.</span></div>
        <div class="glossary-item"><span class="glossary-key">Alerta_Absoluto</span><span>Transacción individual superior al umbral crítico institucional.</span></div>
        <div class="glossary-item"><span class="glossary-key">Alerta_Acumulado</span><span>Volumen mensual superior a multiplicador técnico de perfil.</span></div>
        <div class="glossary-item"><span class="glossary-key">Alerta_Frecuencia</span><span>Densidad operativa superior a límite de vigilancia.</span></div>
        <div class="glossary-item"><span class="glossary-key">Smurfing</span><span>Fragmentación coordinada identificada por fecha calendario.</span></div>
        <div class="glossary-item"><span class="glossary-key">Pico</span><span>Ruptura de distribución estadística (Anomalía +2 Std).</span></div>
        <div class="glossary-item"><span class="glossary-key">Score</span><span>Magnitud de riesgo acumulado (Métrica IMPERATOR).</span></div>
    </div>
    """, unsafe_allow_html=True)

    # Filtros
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        cliente_filtro = st.multiselect("Filtrar por cliente", df["Cliente"].unique())
    with col_c2:
        solo_alertas = st.checkbox("Mostrar solo transacciones con alertas", value=False)

    df_view = df.copy()
    if cliente_filtro:
        df_view = df_view[df_view["Cliente"].isin(cliente_filtro)]
    if solo_alertas:
        df_view = df_view[df_view["Score"] > 0]

    bool_cols = ["Alerta_15", "Alerta_Absoluto", "Alerta_Acumulado", 
                 "Alerta_Frecuencia", "Smurfing", "Pico", "EsPEP", "EsCPE", "Ubicacion_Riesgo"]
    
    for c in bool_cols:
        if c in df_view.columns:
            df_view[c] = df_view[c].apply(lambda x: "Si" if x else "--")

    columnas_mostrar = ["Cliente", "Fecha", "Monto", "Perfil"]
    if "TipoOperacion" in df_view.columns:
        columnas_mostrar.append("TipoOperacion")
    
    columnas_mostrar += bool_cols + ["Score"]

    st.markdown(f"""
    <div class="warning-box" style="margin-top:10px;">
        <strong>{len(df_view):,} transacción(es)</strong> visibles en la bitácora actual.
        Las columnas de validación muestran <strong>Si</strong> cuando la condición aplica y <strong>--</strong> cuando no fue activada en el análisis.
    </div>
    """, unsafe_allow_html=True)
    st.dataframe(
        df_view[columnas_mostrar].sort_values("Score", ascending=False).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Monto": st.column_config.NumberColumn("Monto (Q)", format="Q%.2f"),
            "Perfil": st.column_config.NumberColumn("Perfil (Q)", format="Q%.2f"),
            "Score": st.column_config.NumberColumn("Score", format="%d pts"),
            "Fecha": st.column_config.DateColumn("Fecha"),
        }
    )
