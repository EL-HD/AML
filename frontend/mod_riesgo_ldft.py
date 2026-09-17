"""
mod_riesgo_ldft.py: Administración de Riesgo Institucional de LD/FT

Módulo operativo/administrativo alineado al modelo GAFILAT / IVE (GERILAFT
App) y al Art. 8-11 del Decreto 15-2026 (enfoque basado en riesgo):
Identificación (Segmentación + Eventos) -> Medición (probabilidad/impacto) ->
Control (mitigadores + riesgo residual) -> Monitoreo (Plan de acción,
Resultados, Reportes).

Persistencia: PostgreSQL vía SQLAlchemy (backend.crud_riesgo), siempre
aislada por `licenciaid` (una Persona Obligada por licencia: Art. 19
Ley 6593 / control de acceso). Este módulo abre su propia sesión de base
de datos dentro del proceso de Streamlit, replicando el patrón ya usado
por frontend/mod_sesion.py para la bitácora de auditoría; no se expone
vía auth_api.py.

Seguridad (validaciones explícitas, sin atajos que oculten comportamiento):
  * `licenciaid` se obtiene únicamente de `st.session_state.user_data`,
    poblado por el backend tras autenticación JWT: nunca de un campo de
    texto editable por el usuario.
  * Toda entrada de formulario se valida con los esquemas Pydantic de
    `backend.schemas` (listas cerradas, rangos 1-4, longitudes máximas)
    antes de tocar la base de datos.
"""
from frontend.ui_safe import h

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from backend import crud_riesgo as crud
from backend import riesgo_ldft_logic as logic
from backend import schemas
from backend.database import SessionLocal
from frontend.mod_utils import plotly_dark_layout, render_html_table
from frontend import exportacion, permisos
from frontend import ui_components


def _solo_lectura() -> bool:
    """True cuando el rol de la sesión no puede modificar el modelo de riesgo."""
    return not permisos.puede("editar_riesgo_ldft")


def _sesion_usuario():
    """Obtiene (licenciaid, username) desde la sesión autenticada (server-trusted)."""
    ud = st.session_state.get("user_data") or {}
    licenciaid = ud.get("licence_id")
    username = ud.get("user", "desconocido")
    return licenciaid, username


def _badge_nivel(nivel: int) -> str:
    color = logic.color_nivel(nivel)
    texto = logic.descripcion_nivel(nivel)
    return f'<span class="badge-soft {h(ui_components.tone_class(color))}">{h(texto)}</span>'


def mostrar():
    st.markdown("""
    <div class="info-box">
        <strong>ADMINISTRACIÓN DE RIESGO INSTITUCIONAL DE LD/FT</strong>: Modelo GAFILAT / IVE
        (Art. 8-11 Decreto 15-2026). Identificación, medición, control y monitoreo del riesgo de
        Lavado de Dinero y Financiamiento del Terrorismo a nivel de Persona Obligada.
    </div>
    """, unsafe_allow_html=True)

    licenciaid, username = _sesion_usuario()
    if not licenciaid:
        st.error("No se pudo determinar la licencia activa. Vuelva a iniciar sesión.")
        return
    permisos.exigir_o_avisar("editar_riesgo_ldft")

    db = SessionLocal()
    try:
        tab_seg, tab_ev, tab_ctrl, tab_plan, tab_res, tab_rep = st.tabs(
            ["Segmentación", "Eventos", "Controles", "Plan de Acción", "Resultados", "Reportes"]
        )
        with tab_seg:
            _tab_segmentacion(db, licenciaid, username)
        with tab_ev:
            _tab_eventos(db, licenciaid, username)
        with tab_ctrl:
            _tab_controles(db, licenciaid, username)
        with tab_plan:
            _tab_planes(db, licenciaid, username)
        with tab_res:
            _tab_resultados(db, licenciaid)
        with tab_rep:
            _tab_reportes(db, licenciaid)
    finally:
        db.close()


# ── Segmentación ─────────────────────────────────────────────────────────

def _tab_segmentacion(db, licenciaid, username):
    ui_components.section_title("Nuevo segmento")
    st.caption("Clasifique sus eventos de riesgo por Factor -> Segmento -> Variable (Art. 9 Decreto 15-2026).")
    with st.form("form_nuevo_segmento", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        factor = col1.selectbox("Factor", logic.FACTORES_LDFT)
        segmento = col2.text_input("Segmento", placeholder="Ej. Individual")
        variable = col3.text_input("Variable", placeholder="Ej. PEP")
        enviado = st.form_submit_button("Agregar segmento", type="primary", disabled=_solo_lectura())
        if enviado:
            try:
                data = schemas.RiesgoSegmentoCreate(factor=factor, segmento=segmento, variable=variable)
            except ValidationError as e:
                st.error(f"Datos inválidos: {e.errors()[0]['msg']}")
            else:
                crud.crear_segmento(db, licenciaid, data.factor, data.segmento, data.variable, username)
                st.success("Segmento agregado.")
                st.rerun()

    st.markdown("---")
    ui_components.section_title("Segmentos configurados")
    segmentos = crud.listar_segmentos(db, licenciaid)
    if not segmentos:
        ui_components.empty_state("Sin segmentos configurados", "La segmentación agrupa clientes, productos, canales y zonas geográficas para medir el riesgo por factor.", "Use el formulario superior para agregar el primer segmento.")
        return

    df = pd.DataFrame([{
        "Factor": s.factor, "Segmento": s.segmento, "Variable": s.variable,
        "Creado por": s.creado_por, "Fecha": s.creado_en.strftime("%d/%m/%Y"),
    } for s in segmentos])
    st.markdown(render_html_table(df, max_height=360), unsafe_allow_html=True)

    with st.expander("Eliminar segmento"):
        opciones = {f"{s.factor} · {s.segmento} · {s.variable}": s.id for s in segmentos}
        sel = st.selectbox("Seleccione el segmento a eliminar", list(opciones.keys()), key="del_seg_sel")
        if st.button("Eliminar segmento seleccionado", key="btn_del_seg", disabled=_solo_lectura()):
            if crud.eliminar_segmento(db, licenciaid, opciones[sel]):
                st.success("Segmento eliminado.")
                st.rerun()


# ── Eventos ───────────────────────────────────────────────────────────────

def _tab_eventos(db, licenciaid, username):
    ui_components.section_title("Nuevo evento de riesgo")
    segmentos = crud.listar_segmentos(db, licenciaid)
    opciones_segmento = {"Sin segmentar": None}
    opciones_segmento.update({f"{s.factor} · {s.segmento} · {s.variable}": s.id for s in segmentos})

    with st.form("form_nuevo_evento", clear_on_submit=True):
        nombre = st.text_input("Nombre del evento", placeholder="Ej. Falsedad en el documento de identificación")
        descripcion = st.text_area(
            "Descripción: ¿qué podría ocurrir? ¿por qué podría ocurrir? ¿qué consecuencia generaría?",
            max_chars=1000,
        )
        col1, col2 = st.columns(2)
        factor = col1.selectbox("Factor", logic.FACTORES_LDFT, key="ev_factor")
        segmento_sel = col2.selectbox("Segmento / variable asociado", list(opciones_segmento.keys()), key="ev_segmento")

        st.markdown("**Probabilidad e impacto por riesgos asociados** &nbsp;(1 = poco probable/menor · 4 = altamente probable/crítico)")
        col_p, col_o, col_l, col_r, col_c = st.columns(5)
        probabilidad = col_p.selectbox("Probabilidad", [1, 2, 3, 4], key="ev_prob")
        r_op = col_o.selectbox("Operacional", [1, 2, 3, 4], key="ev_rop")
        r_leg = col_l.selectbox("Legal", [1, 2, 3, 4], key="ev_rleg")
        r_rep = col_r.selectbox("Reputacional", [1, 2, 3, 4], key="ev_rrep")
        r_con = col_c.selectbox("Contagio", [1, 2, 3, 4], key="ev_rcon")

        enviado = st.form_submit_button("Crear evento", type="primary", disabled=_solo_lectura())
        if enviado:
            try:
                data = schemas.RiesgoEventoCreate(
                    nombre=nombre, descripcion=descripcion or None, factor=factor,
                    segmento_id=opciones_segmento[segmento_sel],
                    probabilidad=probabilidad, riesgo_operacional=r_op,
                    riesgo_legal=r_leg, riesgo_reputacional=r_rep, riesgo_contagio=r_con,
                )
            except ValidationError as e:
                st.error(f"Datos inválidos: {e.errors()[0]['msg']}")
            else:
                evento = crud.crear_evento(db, licenciaid, data, username)
                st.success(f"Evento {evento.codigo} creado: Riesgo inherente: {logic.descripcion_nivel(evento.nivel_inherente)}.")
                st.rerun()

    st.markdown("---")
    ui_components.section_title("Eventos registrados")
    eventos = crud.listar_eventos(db, licenciaid)
    if not eventos:
        ui_components.empty_state("Sin eventos de riesgo", "Cada evento describe una amenaza LD/FT con su probabilidad e impacto.", "Registre el primer evento con el formulario superior.")
        return

    controles_todos = crud.listar_controles(db, licenciaid)
    # Se agrega un sufijo del id para evitar colisiones si dos controles comparten nombre.
    opciones_control = {f"{c.nombre} ({str(c.id)[:8]})": c.id for c in controles_todos}

    for e in eventos:
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        # e.nombre / e.factor se escapan antes de interpolarse en HTML (previene XSS almacenado).
        c1.markdown(
            f"**{h(e.codigo)} · {h(e.nombre)}**  \n<span class='tx-muted fs-12'>{h(e.factor)}</span>",
            unsafe_allow_html=True,
        )
        c2.markdown(f"Inherente<br>{_badge_nivel(e.nivel_inherente)}", unsafe_allow_html=True)
        c3.markdown(f"Residual<br>{_badge_nivel(e.nivel_residual)}", unsafe_allow_html=True)
        c4.markdown("Plan requerido<br>" + ("Sí" if e.requiere_plan_accion else "No"), unsafe_allow_html=True)

        with st.expander(f"Detalle y controles: {e.codigo}"):
            if e.descripcion:
                st.caption(e.descripcion)
            st.write(
                f"Probabilidad: {e.probabilidad} · Impacto: {e.impacto} "
                f"(máximo entre riesgos asociados: Operacional {e.riesgo_operacional}, "
                f"Legal {e.riesgo_legal}, Reputacional {e.riesgo_reputacional}, Contagio {e.riesgo_contagio})"
            )

            if opciones_control:
                vinculados = crud.controles_de_evento(db, licenciaid, e.id)
                ids_vinculados = {c.id for c in vinculados}
                default_labels = [f"{c.nombre} ({str(c.id)[:8]})" for c in vinculados]
                sel_control = st.multiselect(
                    "Controles vinculados", list(opciones_control.keys()),
                    default=default_labels, key=f"ctrl_ev_{e.id}",
                )
                if st.button("Guardar vínculos de controles", key=f"btn_vinc_{e.id}", disabled=_solo_lectura()):
                    seleccionados_ids = {opciones_control[n] for n in sel_control}
                    for cid in seleccionados_ids - ids_vinculados:
                        crud.vincular_control(db, licenciaid, e.id, cid)
                    for cid in ids_vinculados - seleccionados_ids:
                        crud.desvincular_control(db, licenciaid, e.id, cid)
                    st.success("Vínculos actualizados: riesgo residual recalculado.")
                    st.rerun()
            else:
                st.info("Registre controles en la pestaña 'Controles' para poder vincularlos a este evento.")

            if st.button("Eliminar evento", key=f"del_ev_{e.id}", disabled=_solo_lectura()):
                crud.eliminar_evento(db, licenciaid, e.id)
                st.success("Evento eliminado.")
                st.rerun()


# ── Controles ─────────────────────────────────────────────────────────────

def _tab_controles(db, licenciaid, username):
    ui_components.section_title("Nuevo control / mitigador")
    with st.form("form_nuevo_control", clear_on_submit=True):
        nombre = st.text_input("Nombre del control", placeholder="Ej. Conocimiento del cliente")
        descripcion = st.text_area("Descripción", placeholder="Ej. Procedimiento para identificación de PEP y aprobación del inicio de la relación comercial.")
        col1, col2, col3 = st.columns(3)
        documentado = col1.radio("¿Documentado y aprobado?", ["Sí", "No"], horizontal=True) == "Sí"
        tipo_control = col2.selectbox("Tipo de control", logic.TIPOS_CONTROL)
        ejecucion = col3.selectbox("Ejecución", logic.EJECUCIONES_CONTROL)
        col4, col5 = st.columns(2)
        nivel_cumplimiento = col4.selectbox("Nivel de cumplimiento", logic.NIVELES_CUALITATIVOS)
        nivel_efectividad = col5.selectbox("Nivel de efectividad", logic.NIVELES_CUALITATIVOS)
        col6, col7, col8 = st.columns(3)
        evaluado = col6.radio("¿Ha sido evaluado?", ["Sí", "No"], horizontal=True) == "Sí"
        responsable_evaluacion = col7.text_input("Responsable de la evaluación", placeholder="Ej. Auditoría Interna")
        fecha_evaluacion = col8.date_input("Fecha de la evaluación", value=None)

        enviado = st.form_submit_button("Crear control", type="primary", disabled=_solo_lectura())
        if enviado:
            try:
                data = schemas.RiesgoControlCreate(
                    nombre=nombre, descripcion=descripcion, documentado=documentado,
                    tipo_control=tipo_control, ejecucion=ejecucion,
                    nivel_cumplimiento=nivel_cumplimiento, nivel_efectividad=nivel_efectividad,
                    evaluado=evaluado, responsable_evaluacion=responsable_evaluacion or None,
                    fecha_evaluacion=fecha_evaluacion if evaluado else None,
                )
            except ValidationError as e:
                st.error(f"Datos inválidos: {e.errors()[0]['msg']}")
            else:
                control = crud.crear_control(db, licenciaid, data, username)
                nivel_txt = logic.NIVELES_CONTROL[control.nivel_ponderacion]
                st.success(f"Control creado: Ponderación: {control.ponderacion}/100 ({nivel_txt}).")
                st.rerun()

    st.markdown("---")
    ui_components.section_title("Controles registrados")
    controles = crud.listar_controles(db, licenciaid)
    if not controles:
        ui_components.empty_state("Sin controles registrados", "Los controles mitigan los eventos de riesgo y reducen el riesgo residual.", "Registre el primer control con el formulario superior.")
        return

    df = pd.DataFrame([{
        "Control": c.nombre, "Tipo": c.tipo_control, "Ejecución": c.ejecucion,
        "Cumplimiento": c.nivel_cumplimiento, "Efectividad": c.nivel_efectividad,
        "Ponderación": f"{c.ponderacion}/100", "Nivel": logic.NIVELES_CONTROL[c.nivel_ponderacion],
    } for c in controles])
    st.markdown(render_html_table(df, max_height=360), unsafe_allow_html=True)

    with st.expander("Eliminar control"):
        opciones = {f"{c.nombre} ({str(c.id)[:8]})": c.id for c in controles}
        sel = st.selectbox("Seleccione el control a eliminar", list(opciones.keys()), key="del_ctrl_sel")
        if st.button("Eliminar control seleccionado", key="btn_del_ctrl", disabled=_solo_lectura()):
            crud.eliminar_control(db, licenciaid, opciones[sel])
            st.success("Control eliminado. Los eventos vinculados fueron recalculados.")
            st.rerun()


# ── Plan de acción ────────────────────────────────────────────────────────

def _tab_planes(db, licenciaid, username):
    from datetime import date as _date

    eventos = crud.listar_eventos(db, licenciaid)
    eventos_requieren = [e for e in eventos if e.requiere_plan_accion]

    ui_components.section_title("Nuevo plan de acción")
    st.caption("Obligatorio para eventos con riesgo residual Medio Alto o Alto (Art. 11 Decreto 15-2026).")
    if not eventos_requieren:
        st.info("No hay eventos con riesgo residual Medio Alto o Alto que requieran plan de acción.")
    else:
        with st.form("form_nuevo_plan", clear_on_submit=True):
            opciones_evento = {
                f"{e.codigo} · {e.nombre} ({logic.descripcion_nivel(e.nivel_residual)})": e.id
                for e in eventos_requieren
            }
            evento_sel = st.selectbox("Evento de riesgo", list(opciones_evento.keys()))
            medida = st.text_area("Medida propuesta")
            col1, col2 = st.columns(2)
            responsable = col1.text_input("Responsable")
            avance = col2.number_input("Porcentaje de avance inicial", min_value=0, max_value=100, value=0)
            col3, col4 = st.columns(2)
            fecha_inicio = col3.date_input("Fecha de inicio", value=_date.today())
            fecha_fin = col4.date_input("Fecha de finalización", value=_date.today())
            enviado = st.form_submit_button("Crear plan de acción", type="primary", disabled=_solo_lectura())
            if enviado:
                try:
                    data = schemas.RiesgoPlanAccionCreate(
                        medida_propuesta=medida, responsable=responsable,
                        fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, porcentaje_avance=avance,
                    )
                except ValidationError as e:
                    st.error(f"Datos inválidos: {e.errors()[0]['msg']}")
                else:
                    plan = crud.crear_plan_accion(db, licenciaid, opciones_evento[evento_sel], data, username)
                    if plan:
                        st.success("Plan de acción creado.")
                        st.rerun()
                    else:
                        st.error("El evento seleccionado no está disponible para esta licencia.")

    st.markdown("---")
    ui_components.section_title("Planes de acción registrados")
    planes = crud.listar_planes(db, licenciaid)
    if not planes:
        ui_components.empty_state("Sin planes de acción", "Los planes de acción atienden los eventos con riesgo residual Medio Alto o Alto.", "Cree un plan desde el formulario superior.")
        return

    mapa_eventos = {e.id: e for e in eventos}
    for p in planes:
        evento = mapa_eventos.get(p.evento_id)
        nombre_evento = f"{evento.codigo} · {evento.nombre}" if evento else "(evento no disponible)"
        estado = logic.estado_plan_accion(p.porcentaje_avance)
        with st.expander(f"{nombre_evento}: {estado} ({p.porcentaje_avance}%)"):
            st.write(p.medida_propuesta)
            st.caption(
                f"Responsable: {p.responsable} · Inicio: {p.fecha_inicio.strftime('%d/%m/%Y')} · "
                f"Fin: {p.fecha_fin.strftime('%d/%m/%Y')}"
            )
            nuevo_avance = st.slider("Porcentaje de avance", 0, 100, value=p.porcentaje_avance, key=f"avance_{p.id}")
            if st.button("Actualizar avance", key=f"btn_avance_{p.id}", disabled=_solo_lectura()):
                crud.actualizar_avance_plan(db, licenciaid, p.id, nuevo_avance)
                st.success("Avance actualizado.")
                st.rerun()


# ── Resultados ────────────────────────────────────────────────────────────

def _render_tabla_conteo(eventos):
    filas = []
    for nivel in [4, 3, 2, 1]:
        inherente = sum(1 for e in eventos if e.nivel_inherente == nivel)
        residual = sum(1 for e in eventos if e.nivel_residual == nivel)
        filas.append({
            "Cantidad de eventos: riesgo inherente": inherente,
            "Cantidad de eventos: riesgo residual": residual,
            "Descripción del riesgo": logic.descripcion_nivel(nivel),
        })
    df = pd.DataFrame(filas)
    st.markdown(render_html_table(df, max_height=260), unsafe_allow_html=True)


def _render_mapa_calor(eventos, key: str):
    conteo = {}
    for e in eventos:
        clave = (e.probabilidad, e.impacto)
        conteo[clave] = conteo.get(clave, 0) + 1

    fig = go.Figure()
    for fila_idx, probabilidad in enumerate(range(1, 5)):
        for col_idx, impacto in enumerate(range(1, 5)):
            cantidad = conteo.get((probabilidad, impacto), 0)
            color = logic.color_nivel(logic.nivel_desde_producto(probabilidad, impacto))
            fig.add_shape(
                type="rect", x0=col_idx, x1=col_idx + 1, y0=fila_idx, y1=fila_idx + 1,
                fillcolor=color, opacity=0.75, line=dict(color="#0d1117", width=1),
            )
            fig.add_annotation(
                x=col_idx + 0.5, y=fila_idx + 0.5, text=str(cantidad),
                showarrow=False, font=dict(color="#0d1117", size=16, family="IBM Plex Mono, monospace"),
            )
    fig.update_xaxes(
        tickmode="array", tickvals=[0.5, 1.5, 2.5, 3.5],
        ticktext=["Menor (1)", "Moderado (2)", "Mayor (3)", "Crítico (4)"],
        range=[0, 4], title="Impacto",
    )
    fig.update_yaxes(
        tickmode="array", tickvals=[0.5, 1.5, 2.5, 3.5],
        ticktext=["Poco probable (1)", "Probable (2)", "Muy probable (3)", "Altamente probable (4)"],
        range=[0, 4], title="Probabilidad",
    )
    fig.update_layout(plotly_dark_layout(height=420, showlegend=False))
    st.plotly_chart(fig, use_container_width=True, key=key)


def _tab_resultados(db, licenciaid):
    ui_components.section_title("Panel de seguimiento")
    sin_control = crud.eventos_sin_control(db, licenciaid)
    sin_plan = crud.eventos_sin_plan(db, licenciaid)
    sin_segmentar = crud.eventos_sin_segmentar(db, licenciaid)
    controles_libres = crud.controles_sin_evento(db, licenciaid)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eventos sin control", len(sin_control))
    c2.metric("Eventos sin plan de acción", len(sin_plan))
    c3.metric("Eventos sin segmentar", len(sin_segmentar))
    c4.metric("Controles sin evento vinculado", len(controles_libres))

    st.markdown("---")
    ui_components.section_title("Mapa de calor: Riesgo inherente de la Persona Obligada")
    eventos = crud.listar_eventos(db, licenciaid)
    if not eventos:
        ui_components.empty_state("Mapa de calor no disponible", "Se necesita al menos un evento de riesgo medido.", "Vaya a la pestaña Eventos para registrarlo.")
        return
    _render_mapa_calor(eventos, key="mapa_calor_resultados")
    st.markdown("<br>", unsafe_allow_html=True)
    _render_tabla_conteo(eventos)


# ── Reportes ──────────────────────────────────────────────────────────────

def _tab_reportes(db, licenciaid):
    ui_components.section_title("Matriz de riesgo consolidada")
    eventos = crud.listar_eventos(db, licenciaid)
    if not eventos:
        ui_components.empty_state("Reportes no disponibles", "Se necesita al menos un evento de riesgo medido.", "Vaya a la pestaña Eventos para registrarlo.")
        return

    _render_tabla_conteo(eventos)
    st.markdown("<br>", unsafe_allow_html=True)
    _render_mapa_calor(eventos, key="mapa_calor_reportes")

    st.markdown("---")
    ui_components.section_title("Riesgo por factor")
    df_factor = pd.DataFrame([{
        "Factor": e.factor, "Evento": f"{e.codigo} · {e.nombre}",
        "Riesgo inherente": logic.descripcion_nivel(e.nivel_inherente),
        "Riesgo residual": logic.descripcion_nivel(e.nivel_residual),
        "¿Requiere plan de acción?": "Sí" if e.requiere_plan_accion else "No",
    } for e in eventos])
    st.markdown(render_html_table(df_factor, max_height=420), unsafe_allow_html=True)

    st.markdown("---")
    nivel_global = max(e.nivel_residual for e in eventos)
    st.markdown(f"""
    <div class="info-box">
        <strong>Resultado global de la gestión de riesgo (residual consolidado):</strong>
        &nbsp;{_badge_nivel(nivel_global)}
    </div>
    """, unsafe_allow_html=True)

    # Saneado anti-inyección de fórmulas centralizado en frontend.exportacion (S-09).
    if permisos.exigir_o_avisar("exportar_datos"):
        exportacion.boton_descarga(
            "Descargar matriz (CSV)", data=exportacion.csv_bytes(df_factor),
            file_name="matriz_riesgo_ldft.csv", mime="text/csv", modulo="Riesgo Institucional LD/FT",
        )
