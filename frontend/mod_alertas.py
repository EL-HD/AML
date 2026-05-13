import streamlit as st
from frontend.mod_utils import render_html_table

def mostrar(casos):
    st.markdown("""
    <div class="info-box">
        <strong>CASOS DE ALERTA</strong> — Consolida los clientes que activaron señales de riesgo durante el período analizado.
        Esta vista prioriza sujetos con exposición relevante, resume factores activados y facilita la selección de expedientes para revisión, escalamiento y debida diligencia ampliada.
    </div>
    """, unsafe_allow_html=True)

    # Glosario de columnas
    st.markdown("""
    <div class="glossary">
        <div class="glossary-title">DICCIONARIO DE DATOS ANALÍTICOS</div>
        <div class="glossary-item"><span class="glossary-key">Cliente</span><span>Identificador soberano de la entidad analizada.</span></div>
        <div class="glossary-item"><span class="glossary-key">Total_Mensual</span><span>Volumen económico acumulado en el ciclo de vigilancia.</span></div>
        <div class="glossary-item"><span class="glossary-key">Score_Max</span><span>Puntaje máximo de riesgo acumulado por el cliente tras aplicar reglas, pesos y factores adicionales.</span></div>
        <div class="glossary-item"><span class="glossary-key">Transacciones</span><span>Número de operaciones consideradas dentro del período cargado.</span></div>
        <div class="glossary-item"><span class="glossary-key">EsPEP / EsCPE / Ubicacion_Riesgo</span><span>Indican si el caso presenta marca positiva en el archivo fuente o en la gestión interna configurada.</span></div>
        <div class="glossary-item"><span class="glossary-key">Nivel_Riesgo</span><span>Clasificación táctica final según los umbrales institucionales configurados en el motor.</span></div>
        <div class="glossary-item"><span class="glossary-key">ST_Max</span><span>Score Transaccional: Riesgo derivado de montos, frecuencias y alertas técnicas.</span></div>
        <div class="glossary-item"><span class="glossary-key">SC_Max</span><span>Score Contextual: Riesgo derivado de la naturaleza del cliente (PEP, CPE, Geo).</span></div>
        <div class="glossary-item"><span class="glossary-key">SB_Max</span><span>Score Conductual: Riesgo por desviación estadística del perfil esperado.</span></div>
        <div class="glossary-item"><span class="glossary-key">SN_Max</span><span>Score de Red: Riesgo por nivel de interconexión y volumen en la red.</span></div>
    </div>
    """, unsafe_allow_html=True)

    # Filtros rápidos
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        filtro_riesgo = st.multiselect(
            "Nivel de riesgo a visualizar",
            options=casos["Nivel_Riesgo"].unique().tolist(),
            default=casos["Nivel_Riesgo"].unique().tolist()
        )
    with col_f2:
        min_score = st.slider("Score mínimo requerido", 0, 12, 0)

    casos_filtrados = casos[
        (casos["Nivel_Riesgo"].isin(filtro_riesgo)) &
        (casos["Score_Max"] >= min_score)
    ].sort_values("Score_Max", ascending=False).reset_index(drop=True)

    bool_cols = ["EsPEP", "EsCPE", "Ubicacion_Riesgo"]
    casos_view = casos_filtrados.copy()
    for col in bool_cols:
        if col in casos_view.columns:
            casos_view[col] = casos_view[col].apply(lambda x: "Si" if x else "--")

    st.markdown(f"""
    <div class="warning-box" style="margin-top:10px;">
        <strong>{len(casos_view)} caso(s) identificados</strong> con los criterios actuales.
        El listado se presenta de mayor a menor score para facilitar priorización operativa.
    </div>
    """, unsafe_allow_html=True)
    tabla_casos = casos_view.copy()
    if "Total_Mensual" in tabla_casos.columns:
        tabla_casos["Total_Mensual"] = tabla_casos["Total_Mensual"].map(lambda v: f"Q{v:,.2f}")
    if "Score_Max" in tabla_casos.columns:
        tabla_casos["Score_Max"] = tabla_casos["Score_Max"].map(lambda v: f"{v:.2f} pts")
    for col in ["ST_Max", "SC_Max", "SB_Max", "SN_Max"]:
        if col in tabla_casos.columns:
            tabla_casos[col] = tabla_casos[col].map(lambda v: f"{v:.4f}")
    tabla_casos = tabla_casos.rename(columns={
        "Total_Mensual": "Total Mensual (Q)",
        "Score_Max": "Score de Riesgo",
        "ST_Max": "S_T (Transaccional)",
        "SC_Max": "S_C (Contextual)",
        "SB_Max": "S_B (Conductual)",
        "SN_Max": "S_N (Red)",
        "Transacciones": "N. Transacciones",
        "Nivel_Riesgo": "Nivel de Riesgo",
    })
    st.markdown(render_html_table(tabla_casos, max_height=560), unsafe_allow_html=True)
