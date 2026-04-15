import streamlit as st
import pandas as pd

def mostrar():
    st.markdown("""
    <div class="info-box">
        <h2 style="margin-top:0; color:#f59e0b; font-size: 20px;">Gestión de Ubicaciones de Riesgo</h2>
        Administre manualmente las zonas geográficas consideradas de alto riesgo (fronteras, zonas rojas, etc.). 
        El sistema marcará automáticamente cualquier transacción originada en estas ubicaciones si la columna 
        <strong>Ubicacion</strong> coincide con alguno de estos nombres.
    </div>
    """, unsafe_allow_html=True)

    if "aml_config" not in st.session_state:
        st.session_state["aml_config"] = {}

    st.session_state["aml_config"].setdefault(
        "ubicaciones_manuales",
        ["Huehuetenango", "San Marcos", "Izabal", "Petén", "Escuintla"]
    )

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown('<div class="section-title">➕ Agregar Nueva Zona</div>', unsafe_allow_html=True)
        nueva_ubic = st.text_input("Nombre de la ubicación (Departamento o Municipio):", placeholder="Ej. El Progreso")
        
        c_add, _ = st.columns([1, 2])
        if c_add.button("Añadir a Vigilancia", type="primary", use_container_width=True):
            if nueva_ubic:
                if nueva_ubic not in st.session_state["aml_config"]["ubicaciones_manuales"]:
                    st.session_state["aml_config"]["ubicaciones_manuales"].append(nueva_ubic)
                    st.success(f"'{nueva_ubic}' ahora es zona de riesgo.")
                    st.rerun()
                else:
                    st.warning("Esa ubicación ya está en la lista.")
            else:
                st.error("Ingrese un nombre válido.")
    
    with col2:
        st.markdown('<div class="section-title">🚩 Zonas Bajo Vigilancia</div>', unsafe_allow_html=True)
        if not st.session_state["aml_config"]["ubicaciones_manuales"]:
            st.info("No hay ubicaciones configuradas.")
        else:
            for i, loc in enumerate(st.session_state["aml_config"]["ubicaciones_manuales"]):
                container = st.container()
                c_text, c_del = container.columns([4, 1])
                c_text.markdown(f"""
                    <div style="background: rgba(255,255,255,0.05); padding: 8px 12px; border-radius: 0px; margin-bottom: 4px; border-left: 3px solid #f59e0b;">
                        {loc}
                    </div>
                """, unsafe_allow_html=True)
                if c_del.button("🗑️", key=f"del_{i}"):
                    st.session_state["aml_config"]["ubicaciones_manuales"].pop(i)
                    st.rerun()

    st.markdown("---")
    st.markdown("""
    <div style="font-size: 13px; color: #8b949e;">
        <strong>Nota:</strong> Estas ubicaciones se aplican globalmente al procesamiento de datos. 
        Si el archivo Excel ya contiene una columna <code>UbicacionRiesgo</code> con valores 'SI', 
        estas también serán tomadas en cuenta.
    </div>
    """, unsafe_allow_html=True)
