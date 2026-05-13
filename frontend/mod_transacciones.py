import streamlit as st
from frontend.mod_utils import render_html_table

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
        <div class="glossary-item"><span class="glossary-key">_ST / _SC / _SB / _SN</span><span>Componentes del score: Transaccional (T), Contextual (C), Conductual (B) y de Red (N).</span></div>
        <div class="glossary-item"><span class="glossary-key">Score</span><span>Magnitud de riesgo acumulado (Escala 0-10).</span></div>
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

    pilares_cols = ["_ST", "_SC", "_SB", "_SN"]
    
    columnas_mostrar = ["Cliente", "Fecha", "Monto", "Perfil"]
    if "TipoOperacion" in df_view.columns:
        columnas_mostrar.append("TipoOperacion")
    
    columnas_mostrar += bool_cols + pilares_cols + ["Score"]

    st.markdown(f"""
    <div class="warning-box" style="margin-top:10px;">
        <strong>{len(df_view):,} transacción(es)</strong> visibles en la bitácora actual.
        Las columnas de validación muestran <strong>Si</strong> cuando la condición aplica y <strong>--</strong> cuando no fue activada en el análisis.
    </div>
    """, unsafe_allow_html=True)
    tabla = df_view[columnas_mostrar].sort_values("Score", ascending=False).reset_index(drop=True).copy()
    rename_cols = {
        "Monto": "Monto (Q)",
        "Perfil": "Perfil (Q)",
        "Score": "Score",
        "_ST": "S_T",
        "_SC": "S_C",
        "_SB": "S_B",
        "_SN": "S_N",
    }
    for col in ["Monto", "Perfil"]:
        if col in tabla.columns:
            tabla[col] = tabla[col].map(lambda v: f"Q{v:,.2f}")
    for col in ["Score"]:
        if col in tabla.columns:
            tabla[col] = tabla[col].map(lambda v: f"{v:.2f} pts")
    for col in ["_ST", "_SC", "_SB", "_SN"]:
        if col in tabla.columns:
            tabla[col] = tabla[col].map(lambda v: f"{v:.4f}")
    tabla = tabla.rename(columns=rename_cols)
    st.markdown(render_html_table(tabla, max_height=560), unsafe_allow_html=True)
