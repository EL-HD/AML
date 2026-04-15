import streamlit as st

def mostrar(casos):
    st.markdown("""
    <div class="info-box">
        <strong>CASOS DE ALERTA</strong> — Consolidado analítico de identidades con vectores de riesgo activos.
        Los perfiles críticos son priorizados por el <strong>Motor Sentinel</strong> para procesos de Debida Diligencia Ampliada (EDD).
    </div>
    """, unsafe_allow_html=True)

    # Glosario de columnas
    st.markdown("""
    <div class="glossary">
        <div class="glossary-title">📖 DICCIONARIO DE DATOS ANALÍTICOS</div>
        <div class="glossary-item"><span class="glossary-key">Cliente</span><span>Identificador soberano de la entidad analizada.</span></div>
        <div class="glossary-item"><span class="glossary-key">Total_Mensual</span><span>Volumen económico acumulado en el ciclo de vigilancia.</span></div>
        <div class="glossary-item"><span class="glossary-key">Score_Max</span><span>Magnitud máxima de riesgo detectada (Escala Sentinel 0–12).</span></div>
        <div class="glossary-item"><span class="glossary-key">Transacciones</span><span>Densidad de actividad en el período.</span></div>
        <div class="glossary-item"><span class="glossary-key">Nivel_Riesgo</span><span>Clasificación táctica según umbrales de seguridad institucional.</span></div>
    </div>
    """, unsafe_allow_html=True)

    # Filtros rápidos
    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        filtro_riesgo = st.multiselect(
            "Filtrar por nivel de riesgo",
            options=casos["Nivel_Riesgo"].unique().tolist(),
            default=casos["Nivel_Riesgo"].unique().tolist()
        )
    with col_f2:
        min_score = st.slider("Score mínimo", 0, 12, 0)

    casos_filtrados = casos[
        (casos["Nivel_Riesgo"].isin(filtro_riesgo)) &
        (casos["Score_Max"] >= min_score)
    ].sort_values("Score_Max", ascending=False).reset_index(drop=True)

    st.markdown(f"**{len(casos_filtrados)} casos** encontrados con los filtros aplicados.")
    st.dataframe(
        casos_filtrados,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Cliente": st.column_config.TextColumn("Cliente"),
            "Total_Mensual": st.column_config.NumberColumn("Total Mensual (Q)", format="Q%.2f"),
            "Score_Max": st.column_config.NumberColumn("Score de Riesgo", format="%d pts"),
            "Transacciones": st.column_config.NumberColumn("N° Transacciones"),
            "Nivel_Riesgo": st.column_config.TextColumn("Nivel de Riesgo"),
        }
    )
