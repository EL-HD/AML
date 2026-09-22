"""
mod_anomalias.py: señal de anomalía (T8) en la interfaz.

* Caché por hash del lote y de los parámetros en st.session_state (se recalcula
  solo si cambia el archivo cargado o la configuración de anomalías).
* Marca las columnas Anomalia_Percentil / Anomalia_Nivel en `casos` (señal
  complementaria: no altera Score_Max, Nivel_Riesgo ni Estado_Alerta).
* Pestaña "Señal de Anomalía" en Imperator Diagnostics y ficha en Análisis por Cliente.
"""
import logging
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend import anomalias
from backend.anomalias import NIVEL_ALTO, NIVEL_BAJO, NIVEL_MEDIO
from frontend import casos_persistencia, ui_components
from frontend.mod_utils import plotly_dark_layout, render_html_table
from frontend.theme.tokens import COLORES
from frontend.ui_safe import h, html_block

logger = logging.getLogger(__name__)

_CLAVE_CACHE = "anomalia_resultado"
_CLAVE_CACHE_ID = "anomalia_resultado_clave"
_TONO_NIVEL = {NIVEL_ALTO: "red", NIVEL_MEDIO: "amber", NIVEL_BAJO: "green"}
_COLOR_NIVEL = {NIVEL_ALTO: COLORES["peligro"], NIVEL_MEDIO: COLORES["amarillo"], NIVEL_BAJO: COLORES["exito_texto"]}
_MAX_FILAS_TABLA = 300

LIMITACIONES = [
    "Es una señal no supervisada: no hay etiquetas de casos confirmados, por lo que 'anómalo' significa "
    "'distinto de la mayoría del lote', no 'sospechoso'. Requiere examen humano (Art. 29 Ley 6593).",
    "Los percentiles son relativos al lote cargado: con pocos clientes (menos de 12 se usa el puntaje robusto MAD) "
    "o con lotes muy homogéneos la señal pierde poder discriminante.",
    "Deriva: la distribución de la cartera cambia entre períodos; un cliente puede ser anómalo en un mes y no en otro "
    "sin que su conducta cambie. Compare siempre con el histórico del expediente.",
    "Un cliente con pocos movimientos de bajo monto también puede resultar 'atípico' (dirección por debajo de la cartera); "
    "la explicación indica la dirección para descartarlo rápidamente.",
]

GOBIERNO = [
    "Validación inicial: contrastar el top de anomalías con casos ya examinados y con las alertas de reglas; documentar "
    "precisión observada en el top 25 antes de usarla como criterio de priorización.",
    "Recalibración: revisar percentiles (Alto/Medio), umbral de punto ciego y variables al menos trimestralmente o cuando "
    "cambie la composición de la cartera o los umbrales regulatorios (RTE, FEIC).",
    "Trazabilidad: cada corrida registra versión del modelo, método, parámetros (hash) y hash del lote; incluya esta línea "
    "en el fundamento del caso y en los reportes.",
    "Independencia: la señal no modifica el Score IMPERATOR ni los estados; cualquier uso para escalar un caso debe "
    "quedar fundamentado por el analista y aprobado bajo el flujo de cuatro ojos.",
]


def _hash_lote_o_local(df: pd.DataFrame) -> str:
    hash_lote = None
    try:
        hash_lote = casos_persistencia.hash_lote_sesion()
    except Exception:  # noqa: BLE001 - la caché no debe romper la vista
        logger.exception("No se pudo obtener el hash del lote para la señal de anomalía.")
    return hash_lote or f"local-{id(df)}-{len(df)}"


def obtener_resultado(df: pd.DataFrame, cfg: dict) -> Optional[anomalias.ResultadoAnomalias]:
    """Devuelve el resultado (cacheado por hash de lote + parámetros) o None si falla."""
    params = anomalias.ParametrosAnomalia.desde_config(cfg)
    hash_lote = _hash_lote_o_local(df)
    clave = f"{hash_lote}|{params.hash()}"
    if st.session_state.get(_CLAVE_CACHE_ID) == clave and st.session_state.get(_CLAVE_CACHE) is not None:
        return st.session_state[_CLAVE_CACHE]
    try:
        resultado = anomalias.calcular_anomalias(df, cfg, hash_lote=hash_lote if not hash_lote.startswith("local-") else None,
                                                 params=params)
    except anomalias.ErrorAnomalias as exc:
        logger.warning("Señal de anomalía no disponible: %s", exc)
        return None
    st.session_state[_CLAVE_CACHE] = resultado
    st.session_state[_CLAVE_CACHE_ID] = clave
    return resultado


def olvidar_cache() -> None:
    for clave in (_CLAVE_CACHE, _CLAVE_CACHE_ID):
        st.session_state.pop(clave, None)


def marcar_casos(df: pd.DataFrame, casos: pd.DataFrame, cfg: dict) -> int:
    """Añade la señal a `casos` (columnas Anomalia_*). Devuelve clientes marcados."""
    resultado = obtener_resultado(df, cfg)
    return anomalias.marcar_casos(casos, resultado)


def _badge_nivel(nivel) -> str:
    nivel = str(nivel)
    tono = ui_components.tone_class(_COLOR_NIVEL.get(nivel, COLORES["texto_secundario"]))
    return html_block('<span class="badge badge-tone {tono}">{nivel}</span>', tono=tono, nivel=nivel)


def _lista_html(items) -> str:
    return '<ul class="list-tight">' + "".join(f"<li>{h(t)}</li>" for t in items) + "</ul>"


def _panel_variables(fila: pd.Series, moneda_txt: str = "") -> None:
    variables = fila.get("Anomalia_Variables") or []
    if not variables:
        ui_components.info_panel("Sin variables discriminantes para este cliente.", titulo="Explicación")
        return
    filas = []
    for v in variables:
        _etq, formato = anomalias.DESCRIPCION_VARIABLES.get(v["variable"], (v["variable"], "decimal"))
        filas.append({
            "Variable": v["etiqueta"],
            "Valor del cliente": anomalias.formatear_valor(v["valor"], formato, moneda_txt or ui_components.simbolo_moneda()),
            "Referencia (mediana de la cartera)": anomalias.formatear_valor(v["referencia"], formato, moneda_txt or ui_components.simbolo_moneda()),
            "Dirección": v["direccion"],
            "Desviaciones robustas": f"{abs(v['z']):.1f}",
        })
    st.markdown(render_html_table(pd.DataFrame(filas), max_height=220), unsafe_allow_html=True)
    ui_components.info_panel(str(fila.get("Anomalia_Explicacion", "")), titulo="Lectura para el Oficial de Cumplimiento")


def senal_cliente(cliente, casos: pd.DataFrame, df: pd.DataFrame, cfg: dict) -> None:
    """Ficha de la señal de anomalía en Análisis por Cliente (KPI + 3 variables)."""
    resultado = obtener_resultado(df, cfg)
    if resultado is None or resultado.vacio:
        motivo = (resultado.metadata.get("motivo") if resultado else None) or "Señal de anomalía no disponible."
        st.markdown(ui_components.status_badge("info", f"Señal de anomalía: {motivo}"), unsafe_allow_html=True)
        return
    fila = resultado.clientes[resultado.clientes["Cliente"] == str(cliente)]
    if fila.empty:
        st.markdown(ui_components.status_badge("info", "Señal de anomalía: cliente sin datos en el lote."), unsafe_allow_html=True)
        return
    fila = fila.iloc[0]
    nivel = str(fila["Anomalia_Nivel"])
    ui_components.section_title("Señal de Anomalía (complementaria)")
    col1, col2, col3 = st.columns(3)
    with col1:
        ui_components.kpi("Percentil de anomalía", f"{float(fila['Anomalia_Percentil']):.1f}", "0-100 dentro del lote",
                          tone=_TONO_NIVEL.get(nivel, "blue"))
    with col2:
        ui_components.kpi("Nivel de anomalía", nivel, "No altera el Score IMPERATOR", tone=_TONO_NIVEL.get(nivel, "blue"))
    with col3:
        score = casos.loc[casos["Cliente"] == cliente, "Score_Max"]
        score_val = float(score.iloc[0]) if not score.empty else 0.0
        es_ciego = nivel == NIVEL_ALTO and score_val < anomalias.ParametrosAnomalia.desde_config(cfg).score_punto_ciego
        ui_components.kpi("Posible punto ciego de reglas", "Sí" if es_ciego else "No",
                          "Anomalía alta con score bajo" if es_ciego else "Coherente con las reglas",
                          tone="red" if es_ciego else "green")
    _panel_variables(fila, ui_components.simbolo_moneda())
    st.caption(anomalias.resumen_trazabilidad(resultado.metadata))


def _grafico_dispersion(tabla: pd.DataFrame, params: anomalias.ParametrosAnomalia) -> go.Figure:
    fig = go.Figure()
    for nivel in (NIVEL_BAJO, NIVEL_MEDIO, NIVEL_ALTO):
        sub = tabla[tabla["Anomalia_Nivel"] == nivel]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["Score_Max"], y=sub["Anomalia_Percentil"], mode="markers", name=f"Anomalía {nivel}",
            marker=dict(color=_COLOR_NIVEL[nivel], size=8, opacity=0.85),
            text=[h(c) for c in sub["Cliente"]],
            hovertemplate="<b>%{text}</b><br>Score IMPERATOR: %{x:.2f}<br>Percentil anomalía: %{y:.1f}<extra></extra>",
        ))
    ciegos = tabla[tabla["Punto_Ciego"]]
    if not ciegos.empty:
        fig.add_trace(go.Scatter(
            x=ciegos["Score_Max"], y=ciegos["Anomalia_Percentil"], mode="markers", name="Posible punto ciego",
            marker=dict(color="rgba(0,0,0,0)", size=16, line=dict(color=COLORES["acento"], width=2)),
            text=[h(c) for c in ciegos["Cliente"]],
            hovertemplate="<b>%{text}</b><br>Anomalía alta con score bajo<extra></extra>",
        ))
    fig.add_vline(x=params.score_punto_ciego, line=dict(color=COLORES["acento"], dash="dash", width=1),
                  annotation_text="Score bajo", annotation_font_color=COLORES["acento"])
    fig.add_hline(y=params.percentil_alto, line=dict(color=COLORES["peligro"], dash="dot", width=1),
                  annotation_text="Anomalía alta", annotation_font_color=COLORES["peligro"])
    fig.update_layout(plotly_dark_layout(
        xaxis_title="Score IMPERATOR (0-10)", yaxis_title="Percentil de anomalía (0-100)", height=400,
        xaxis=dict(range=[-0.2, 10.2], gridcolor="rgba(83, 68, 52, 0.2)", linecolor="#534434", tickfont=dict(color="#d8c3ad")),
        yaxis=dict(range=[-2, 103], gridcolor="rgba(83, 68, 52, 0.2)", linecolor="#534434", tickfont=dict(color="#d8c3ad")),
    ))
    return fig


def _tabla_union(casos: pd.DataFrame, resultado: anomalias.ResultadoAnomalias, params) -> pd.DataFrame:
    base = casos[["Cliente", "Score_Max", "Nivel_Riesgo"]].copy() if "Score_Max" in casos.columns else casos[["Cliente"]].copy()
    base["Cliente"] = base["Cliente"].astype(str)
    tabla = resultado.clientes.merge(base, on="Cliente", how="left")
    tabla["Score_Max"] = pd.to_numeric(tabla.get("Score_Max"), errors="coerce").fillna(0.0)
    tabla["Nivel_Riesgo"] = tabla.get("Nivel_Riesgo", pd.Series(index=tabla.index, dtype=object)).fillna("N/D")
    tabla["Punto_Ciego"] = (tabla["Anomalia_Nivel"] == NIVEL_ALTO) & (tabla["Score_Max"] < params.score_punto_ciego)
    return tabla


def mostrar_tab(df: pd.DataFrame, casos: pd.DataFrame, cfg: dict) -> None:
    """Contenido de la pestaña "Señal de Anomalía" en Imperator Diagnostics."""
    ui_components.info_panel(
        "Detección no supervisada (ensamble de Isolation Forest, implementación propia con numpy, y puntaje robusto MAD) sobre variables de monto, "
        "desviación del perfil, frecuencia, montos redondos, proximidad a umbrales (RTE, absoluto, FEIC), calendario, "
        "contrapartes y ubicación. Es una señal complementaria: no altera el Score IMPERATOR ni el "
        "estado de los casos. Sirve para encontrar conductas atípicas que las reglas no cubren.",
        titulo="SEÑAL DE ANOMALÍA",
    )
    params = anomalias.ParametrosAnomalia.desde_config(cfg)
    resultado = obtener_resultado(df, cfg)
    if resultado is None or resultado.vacio:
        motivo = (resultado.metadata.get("motivo") if resultado else None) or "No fue posible calcular la señal."
        ui_components.empty_state("Señal de anomalía no disponible", motivo,
                                  "Revise Configuración > Reglas de Detección > Señal de anomalía.")
        return

    tabla = _tabla_union(casos, resultado, params)
    n_alto = int((tabla["Anomalia_Nivel"] == NIVEL_ALTO).sum())
    n_ciegos = int(tabla["Punto_Ciego"].sum())
    metodo = ("Isolation Forest + MAD" if resultado.metadata.get("metodo_clientes") == anomalias.METODO_ENSAMBLE
              else "Puntaje robusto MAD")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        ui_components.kpi("Clientes con anomalía alta", n_alto, f"Percentil >= {params.percentil_alto}", tone="red")
    with k2:
        ui_components.kpi("Posibles puntos ciegos", n_ciegos, f"Anomalía alta y score < {params.score_punto_ciego:g}", tone="amber")
    with k3:
        ui_components.kpi("Método", metodo, f"{resultado.metadata.get('n_clientes', 0)} clientes analizados", tone="blue")
    with k4:
        ui_components.kpi("Tiempo de cálculo", f"{resultado.metadata.get('duracion_s', 0):.2f} s",
                          f"{len(resultado.metadata.get('variables_cliente', []))} variables", tone="green")

    st.markdown("<br>", unsafe_allow_html=True)
    st.plotly_chart(_grafico_dispersion(tabla, params), use_container_width=True)
    ui_components.info_panel(
        "Los puntos con borde ámbar (arriba a la izquierda) son clientes con anomalía alta y score IMPERATOR bajo: "
        "posibles puntos ciegos de las reglas. Revíselos primero; si el examen confirma conducta inusual, "
        "considere ajustar umbrales o añadir una regla.", titulo="Cómo leer el gráfico")

    if n_ciegos:
        ui_components.section_title("Posibles puntos ciegos de las reglas")
        ciegos = tabla[tabla["Punto_Ciego"]].head(_MAX_FILAS_TABLA)
        vista = pd.DataFrame({
            "Cliente": ciegos["Cliente"],
            "Score IMPERATOR": ciegos["Score_Max"].map(lambda v: f"{v:.2f}"),
            "Nivel de Riesgo": ciegos["Nivel_Riesgo"],
            "Percentil anomalía": ciegos["Anomalia_Percentil"].map(lambda v: f"{v:.1f}"),
            "Explicación": ciegos["Anomalia_Explicacion"],
        })
        st.markdown(render_html_table(vista, max_height=320), unsafe_allow_html=True)

    ui_components.section_title("Ranking de anomalía por cliente")
    nivel_filtro = st.multiselect("Nivel de anomalía", [NIVEL_ALTO, NIVEL_MEDIO, NIVEL_BAJO],
                                  default=[NIVEL_ALTO, NIVEL_MEDIO], key="anomalia_filtro_nivel")
    filtrada = tabla[tabla["Anomalia_Nivel"].isin(nivel_filtro)] if nivel_filtro else tabla
    filtrada = filtrada.sort_values(["Anomalia_Percentil", "Cliente"], ascending=[False, True]).head(_MAX_FILAS_TABLA)
    vista = pd.DataFrame({
        "Cliente": filtrada["Cliente"],
        "Percentil anomalía": filtrada["Anomalia_Percentil"].map(lambda v: f"{v:.1f}"),
        "Nivel anomalía": filtrada["Anomalia_Nivel"],
        "Score IMPERATOR": filtrada["Score_Max"].map(lambda v: f"{v:.2f}"),
        "Nivel de Riesgo": filtrada["Nivel_Riesgo"],
        "Punto ciego": filtrada["Punto_Ciego"].map(lambda v: "Sí" if v else "--"),
        "Variable principal": filtrada["Anomalia_Variables"].map(lambda v: v[0]["etiqueta"] if v else "--"),
    })
    st.markdown(render_html_table(vista, max_height=420), unsafe_allow_html=True)

    ui_components.section_title("Detalle explicativo por cliente")
    opciones = filtrada["Cliente"].tolist() or tabla["Cliente"].tolist()
    cliente_sel = st.selectbox("Cliente", opciones, key="anomalia_cliente_detalle")
    fila = tabla[tabla["Cliente"] == cliente_sel]
    if not fila.empty:
        fila = fila.iloc[0]
        st.markdown(
            f"<div class='mb-8'>{_badge_nivel(fila['Anomalia_Nivel'])} "
            f"<span class='tx-muted fs-12'>Percentil {h(format(float(fila['Anomalia_Percentil']), '.1f'))} · "
            f"Score IMPERATOR {h(format(float(fila['Score_Max']), '.2f'))} · Nivel de riesgo {h(fila['Nivel_Riesgo'])}</span></div>",
            unsafe_allow_html=True,
        )
        _panel_variables(fila, ui_components.simbolo_moneda())
        if "Anomalia_Tx_Percentil" in resultado.transacciones.columns and "Cliente" in df.columns:
            idx = df.index[df["Cliente"].astype(str) == cliente_sel]
            tx = resultado.transacciones.loc[resultado.transacciones.index.intersection(idx)]
            if not tx.empty:
                top_tx = tx.sort_values("Anomalia_Tx_Percentil", ascending=False).head(5)
                columnas = [c for c in ("Fecha", "Monto", "TipoOperacion", "Cliente_Destino", "Ubicacion") if c in df.columns]
                detalle = df.loc[top_tx.index, columnas].copy()
                if "Fecha" in detalle.columns:
                    detalle["Fecha"] = pd.to_datetime(detalle["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
                if "Monto" in detalle.columns:
                    detalle["Monto"] = detalle["Monto"].map(lambda v: ui_components.fmt_moneda(v, 2))
                detalle["Percentil anomalía (transacción)"] = top_tx["Anomalia_Tx_Percentil"].map(lambda v: f"{v:.1f}")
                st.markdown("**Operaciones más atípicas del cliente**")
                st.markdown(render_html_table(detalle, max_height=220), unsafe_allow_html=True)

    with st.expander("Limitaciones y gobierno del modelo", expanded=False):
        st.markdown(html_block("<div class='info-box'><strong>Limitaciones</strong>{lista_html}</div>",
                               lista_html=_lista_html(LIMITACIONES)), unsafe_allow_html=True)
        st.markdown(html_block("<div class='info-box'><strong>Buenas prácticas de gobierno</strong>{lista_html}</div>",
                               lista_html=_lista_html(GOBIERNO)), unsafe_allow_html=True)
        variables = ", ".join(anomalias.DESCRIPCION_VARIABLES.get(v, (v, ""))[0]
                              for v in resultado.metadata.get("variables_cliente", []))
        st.caption(f"Variables usadas: {variables}")
        st.caption(anomalias.resumen_trazabilidad(resultado.metadata))


def parrafo_reporte(casos: pd.DataFrame, cfg: dict) -> str:
    """Texto plano para los informes: resumen de la señal y línea de trazabilidad (versión, parámetros, lote)."""
    resultado = st.session_state.get(_CLAVE_CACHE)
    if resultado is None or resultado.vacio or "Anomalia_Nivel" not in casos.columns:
        return ""
    params = anomalias.ParametrosAnomalia.desde_config(cfg)
    n_alto = int((casos["Anomalia_Nivel"] == NIVEL_ALTO).sum())
    n_ciegos = int(len(anomalias.puntos_ciegos(casos, params)))
    return (f"Señal de anomalía (complementaria, no altera el Score IMPERATOR): {n_alto} cliente(s) con anomalía alta "
            f"(percentil >= {params.percentil_alto}) y {n_ciegos} posible(s) punto(s) ciego(s) de las reglas "
            f"(anomalía alta con score < {params.score_punto_ciego:g}). Trazabilidad: "
            f"{anomalias.resumen_trazabilidad(resultado.metadata)}.")
