import logging

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from backend import casos_alerta
from backend.database import SessionLocal
from frontend.mod_utils import render_html_table
from frontend.ui_safe import h
from frontend import casos_persistencia, ui_components, permisos

logger = logging.getLogger(__name__)

# Estados del ciclo de vida (fuente única: backend.casos_alerta)
ESTADOS_ALERTA = list(casos_alerta.ESTADOS)

def mostrar(casos):
    st.markdown("""
    <div class="info-box">
        <strong>CASOS DE ALERTA</strong>: Consolida los clientes que activaron señales de riesgo durante el período analizado.
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

    # Columnas del ciclo de vida (Arts. 28-30 Ley 6593); los estados persistidos
    # se rehidratan en app.py (casos_persistencia.rehidratar_estados) para toda vista.
    casos_alerta.asegurar_columnas_estado(casos)

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

    estado_filtro = st.selectbox(
        "Filtrar por estado",
        ["Todos"] + ESTADOS_ALERTA,
        key="filtro_estado_alerta"
    )

    casos_filtrados = casos[
        (casos["Nivel_Riesgo"].isin(filtro_riesgo)) &
        (casos["Score_Max"] >= min_score)
    ]
    if estado_filtro != "Todos":
        casos_filtrados = casos_filtrados[casos_filtrados["Estado_Alerta"] == estado_filtro]
    casos_filtrados = casos_filtrados.sort_values("Score_Max", ascending=False).reset_index(drop=True)

    bool_cols = ["EsPEP", "EsCPE", "Ubicacion_Riesgo"]
    casos_view = casos_filtrados.copy()
    for col in bool_cols:
        if col in casos_view.columns:
            casos_view[col] = casos_view[col].apply(lambda x: "Si" if x else "--")

    st.markdown(f"""
    <div class="warning-box mt-10">
        <strong>{h(len(casos_view))} caso(s) identificados</strong> con los criterios actuales.
        El listado se presenta de mayor a menor score para facilitar priorización operativa.
    </div>
    """, unsafe_allow_html=True)
    tabla_casos = casos_view.copy()
    if "Total_Mensual" in tabla_casos.columns:
        tabla_casos["Total_Mensual"] = tabla_casos["Total_Mensual"].map(lambda v: ui_components.fmt_moneda(v, 2))
    if "Score_Max" in tabla_casos.columns:
        tabla_casos["Score_Max"] = tabla_casos["Score_Max"].map(lambda v: f"{v:.2f} pts")
    for col in ["ST_Max", "SC_Max", "SB_Max", "SN_Max"]:
        if col in tabla_casos.columns:
            tabla_casos[col] = tabla_casos[col].map(lambda v: f"{v:.4f}")
    if "Anomalia_Percentil" in tabla_casos.columns:
        tabla_casos["Anomalia_Percentil"] = tabla_casos["Anomalia_Percentil"].map(
            lambda v: "--" if v is None or v != v else f"{float(v):.1f}")
    tabla_casos = tabla_casos.rename(columns={
        "Total_Mensual": ui_components.etiqueta_monto("Total Mensual"),
        "Score_Max": "Score de Riesgo",
        "ST_Max": "S_T (Transaccional)",
        "SC_Max": "S_C (Contextual)",
        "SB_Max": "S_B (Conductual)",
        "SN_Max": "S_N (Red)",
        "Transacciones": "N. Transacciones",
        "Nivel_Riesgo": "Nivel de Riesgo",
        "Anomalia_Percentil": "Señal de anomalía (percentil)",
        "Anomalia_Nivel": "Nivel de anomalía",
    })
    st.markdown(render_html_table(tabla_casos, max_height=560), unsafe_allow_html=True)

    # ── PANEL DE GESTIÓN DE CASOS (Arts. 29-30 y 34 Ley 6593) ────────────────
    st.markdown("---")
    ui_components.section_title("Gestión de Casos: Ciclo Inusual -> Sospechosa")
    if casos_filtrados.empty:
        return
    caso_idx = st.selectbox(
        "Seleccionar caso para gestionar",
        casos_filtrados.index.tolist(),
        format_func=lambda i: f"{casos_filtrados.at[i, 'Cliente']}: Score: {casos_filtrados.at[i, 'Score_Max']:.2f}: Estado: {casos_filtrados.at[i, 'Estado_Alerta']}",
        key="sel_caso"
    )
    if caso_idx is None:
        return
    with st.expander("Gestión del caso", expanded=False):
        _panel_gestion_caso(casos, casos_filtrados.loc[caso_idx])


def _panel_gestion_caso(casos, fila) -> None:
    """Carga (o crea) el caso persistido y ofrece solo las transiciones autorizadas."""
    if not permisos.exigir_o_avisar("gestionar_alertas"):
        return
    licenciaid, usuario, rol = casos_persistencia.identidad_sesion()
    hash_lote = casos_persistencia.hash_lote_sesion()
    if not licenciaid or not hash_lote:
        st.error("No se pudo determinar la licencia o el lote activo. Vuelva a iniciar sesión.")
        return

    db = SessionLocal()
    try:
        try:
            caso = casos_alerta.obtener_o_crear_caso(
                db, licenciaid, hash_lote, fila["Cliente"], usuario, rol,
                score_max=fila.get("Score_Max"), nivel_riesgo=fila.get("Nivel_Riesgo"),
                nombre_archivo=st.session_state.get("archivo_nombre"),
            )
        except casos_alerta.ErrorCasoAlerta as exc:
            st.error(str(exc))
            return
        _resumen_caso(caso)
        destinos = casos_alerta.transiciones_permitidas(caso, usuario, rol)
        if caso.estado == casos_alerta.ESTADO_PROPUESTA:
            if casos_alerta.ESTADO_CONFIRMADA in destinos:
                st.warning("Propuesta pendiente de aprobación: al confirmar, proceda a generar el RTS ante la IVE (Art. 30 Ley 6593).")
            else:
                st.info("Propuesta pendiente de aprobación por un Oficial de Cumplimiento o Administrador distinto del proponente (cuatro ojos).")
        if caso.estado == casos_alerta.ESTADO_CONFIRMADA:
            st.warning("Caso confirmado como SOSPECHOSO: estado final. Genere el RTS en el módulo de Reportes (Art. 30 Ley 6593).")
        if not destinos:
            st.info("No hay transiciones disponibles para su rol en el estado actual.")
        else:
            nuevo_estado = st.selectbox("Clasificar como", destinos, key="nuevo_estado")
            fundamento = st.text_area(
                "Fundamento del examen (Art. 29 Ley 6593)",
                value=str(caso.fundamento or ""),
                key="fundamento_examen",
                max_chars=casos_alerta.MAX_CARACTERES_FUNDAMENTO,
                help="Describe la base legal y económica que justifica, escala o descarta la operación.",
            )
            if st.button("Guardar clasificación", key="btn_clasificar"):
                _aplicar_transicion(db, casos, caso, nuevo_estado, fundamento, licenciaid, usuario, rol)
        _tabla_historial(db, licenciaid, caso)
    except SQLAlchemyError:
        logger.exception("Error de base de datos en la gestión del caso de alerta.")
        st.error("No fue posible acceder a la base de datos de casos. Intente de nuevo más tarde.")
    finally:
        db.close()


def _aplicar_transicion(db, casos, caso, nuevo_estado, fundamento, licenciaid, usuario, rol) -> None:
    try:
        caso = casos_alerta.cambiar_estado(db, licenciaid, caso.id, nuevo_estado, fundamento, usuario, rol)
    except casos_alerta.ErrorCasoAlerta as exc:
        st.error(str(exc))
        return
    casos_alerta.rehidratar_dataframe(casos, [caso])
    if nuevo_estado == casos_alerta.ESTADO_CONFIRMADA:
        st.warning("Caso clasificado como SOSPECHOSO. Proceder a generar RTS ante la IVE (Art. 30 Ley 6593).")
    st.success("Clasificación guardada de forma permanente.")
    st.rerun()


def _resumen_caso(caso) -> None:
    detalle = [
        ("Clave del caso", caso.clave_caso[:16]),
        ("Estado", caso.estado),
        ("Propuesto por", caso.propuesto_por or "--"),
        ("Aprobado por", caso.aprobado_por or "--"),
    ]
    celdas_html = "".join(
        f'<div class="glossary-item"><span class="glossary-key">{h(k)}</span><span>{h(v)}</span></div>'
        for k, v in detalle
    )
    st.markdown(f'<div class="glossary">{celdas_html}</div>', unsafe_allow_html=True)


def _tabla_historial(db, licenciaid, caso) -> None:
    historial = casos_alerta.historial_caso(db, licenciaid, caso.id)
    if not historial:
        return
    filas = pd.DataFrame([{
        "Fecha (UTC)": r.registrado_en.strftime("%Y-%m-%d %H:%M") if r.registrado_en else "",
        "Acción": r.accion,
        "De": r.estado_anterior or "--",
        "A": r.estado_nuevo,
        "Usuario": r.usuario,
        "Rol": r.rol,
        "Fundamento": r.fundamento,
    } for r in historial])
    st.markdown("**Historial del caso (registro inmutable, Art. 34 Ley 6593)**")
    st.markdown(render_html_table(filas, max_height=260), unsafe_allow_html=True)
