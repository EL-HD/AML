import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
from datetime import date as _date
from backend import models
from backend.database import SessionLocal
from frontend import exportacion, permisos
from frontend.mod_utils import apply_dark_style, render_html_table
from frontend.ui_safe import h
from frontend import ui_components

# Catálogos globales del RTS disponibles para verificación (normativa IVE vigente).
# Un solo diccionario de configuración evita repetir la misma consulta 10 veces.
_CATALOGOS_RTS = {
    "Departamentos":              (models.CatDepartamento,           ["codigo", "nombre", "activo"]),
    "Municipios":                 (models.CatMunicipio,               ["codigo", "nombre", "departamento_codigo", "activo"]),
    "Países":                     (models.CatPais,                    ["codigo", "nombre", "activo"]),
    "Monedas":                    (models.CatMoneda,                  ["codigo", "nombre", "activo"]),
    "Tipo de Canal":               (models.CatTipoCanal,               ["codigo", "nombre", "activo"]),
    "Tipo de Instrumento":         (models.CatTipoInstrumento,         ["codigo", "nombre", "activo"]),
    "Tipo de Producto (oficial)":  (models.CatTipoProductoOficial,     ["codigo", "nombre", "activo"]),
    "Tipo de Identificación":      (models.CatTipoIdentificacion,      ["codigo", "nombre", "activo"]),
    "Motivo de Involucramiento":   (models.CatMotivoInvolucramiento,   ["codigo", "nombre", "activo"]),
    "Tipo de Reporte":             (models.CatTipoReporte,             ["codigo", "nombre", "es_regulatorio", "articulo_legal", "activo"]),
}


def _consultar_catalogo_df(db, modelo, columnas: list) -> pd.DataFrame:
    """
    Consulta todas las filas de un catálogo global y las devuelve como DataFrame.
    Reutilizable para cualquier catálogo de `_CATALOGOS_RTS`: evita repetir la
    misma lógica de consulta/serialización por cada tabla.
    """
    filas = db.query(modelo).order_by(modelo.codigo).all()
    return pd.DataFrame([{col: getattr(fila, col) for col in columnas} for fila in filas], columns=columnas)


def _actualizar_estado_catalogo(db, modelo, codigo: str, activo: bool) -> bool:
    """
    Activa o inactiva una entrada de catálogo por su `codigo` (clave primaria).
    Validación explícita: si el registro no existe, no hace nada y retorna False
   : evita depender de que la fila exista de forma implícita.
    Reutilizable para cualquier catálogo de `_CATALOGOS_RTS`.
    """
    registro = db.get(modelo, codigo)
    if registro is None:
        return False
    registro.activo = activo
    db.commit()
    return True

_RETENCION_MINIMA_ANOS = 5  # Art. 34 Ley 6593

def _validar_retencion(fecha_registro, anos_retencion: int = _RETENCION_MINIMA_ANOS) -> bool:
    """
    Retorna True si el registro puede eliminarse (superó el período de retención).
    Retorna False si está dentro del período de retención (Art. 34 Ley 6593).
    """
    if fecha_registro is None:
        return False
    fecha_limite = _date.today().replace(year=_date.today().year - anos_retencion)
    puede_eliminar = fecha_registro < fecha_limite
    if not puede_eliminar:
        st.error(
            f"🚫 No se puede eliminar este registro. "
            f"La Ley 6593 (Art. 34) exige conservarlo hasta "
            f"{fecha_registro.replace(year=fecha_registro.year + anos_retencion)}."
        )
    return puede_eliminar

def _auditar_cambio_config() -> None:
    """Registra CAMBIO_CONFIG en la bitácora (Art. 19 Ley 6593)."""
    from frontend.mod_sesion import _registrar_acceso_auditoria
    from backend import auditoria

    datos = st.session_state.get("user_data") or {}
    _registrar_acceso_auditoria(datos.get("user", "desconocido"), datos.get("licence_id"),
                                "Configuración", auditoria.CAMBIO_CONFIG)


def mostrar(_DEFAULTS):
    st.markdown("""
    <div class="info-box">
        <strong>CONFIGURACIÓN DE REGLAS AML</strong>: Parámetros de detección y ponderación del motor de riesgo.
        Administre umbrales, reglas de detección y clasificación de riesgo.
        Los ajustes se integran en tiempo real al análisis.
    </div>
    """, unsafe_allow_html=True)

    c = st.session_state["aml_config"].copy()
    puede_editar = permisos.puede("configurar_parametros")
    if not puede_editar:
        permisos.aviso_solo_lectura("configurar_parametros")

    # ── TABS de secciones ────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Reglas de Detección",
        "Pesos del Score",
        "Clasificación de Riesgo",
        "Resumen y Aplicar",
        "Catálogos IVE (RTS)",
    ])

    # ── Botón Restablecer prominente arriba de los tabs ─────────────────
    if puede_editar:
        col_rst1, col_rst2, col_rst3 = st.columns([3, 2, 3])
        with col_rst2:
            if st.button("Restablecer configuración base", use_container_width=True):
                st.session_state["aml_config"] = _DEFAULTS.copy()
                st.success("Todos los parámetros han sido restaurados a los valores por defecto.")
                st.rerun()
    st.markdown("<br>", unsafe_allow_html=True)


    # ── TAB 1: Reglas de Detección ──────────────────────────────────────
    with tab1:
        st.markdown("""
        <div class="info-box" style="background-color: #1b2027; border-left-color: #f59e0b;">
            <strong>CALIBRACIÓN TÉCNICA:</strong> La alteración de umbrales impacta directamente en la sensibilidad del motor.
            Un umbral bajo incrementa la densidad de alertas. Ajuste según el apetito de riesgo institucional.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 1: Monto Alto Absoluto ──────────────────────────────
        col_on, col_title = st.columns([1, 9])
        with col_on:
            c["regla_absoluto"] = st.toggle("", value=c["regla_absoluto"], key="tog_abs")
        with col_title:
            estado_abs = "ACTIVA" if c["regla_absoluto"] else "DESACTIVADA"
            ui_components.regla_titulo("Regla 1: Monto Alto Absoluto", c["regla_absoluto"])

        col_desc1, col_ctrl1 = st.columns([3, 2])
        with col_desc1:
            ui_components.spec_card(
                """Validación contra <strong>umbral absoluto configurado</strong>.
Regla de detección directa: activación inmediata si el monto individual excede el límite institucional.""",
                "Vector_Absoluto",
                f"Monto > Q{c['umbral_absoluto']:,}",
            )
        with col_ctrl1:
            c["umbral_absoluto"] = st.number_input(
                "Umbral absoluto (Q)",
                min_value=1000, max_value=10_000_000, value=int(c["umbral_absoluto"]), step=1000,
                help="Cualquier transacción individual mayor a este monto activa la alerta.",
                disabled=not c["regla_absoluto"]
            )
            ui_components.regla_kpi(f"Q{c['umbral_absoluto']:,}", "Umbral actual", c['peso_absoluto'], c['regla_absoluto'])

        st.markdown("---")

        # ── Regla 2: Acumulado Mensual ────────────────────────────────
        col_on2, col_title2 = st.columns([1, 9])
        with col_on2:
            c["regla_acumulado"] = st.toggle("", value=c["regla_acumulado"], key="tog_acum")
        with col_title2:
            estado_acum = "ACTIVA" if c["regla_acumulado"] else "DESACTIVADA"
            ui_components.regla_titulo("Regla 2: Acumulado Mensual", c["regla_acumulado"])

        col_desc2, col_ctrl2 = st.columns([3, 2])
        with col_desc2:
            ui_components.spec_card(
                """Evaluación de <strong>volumen acumulado por ciclo</strong>.
Identifica acumulación de capital por encima del multiplicador de perfil configurado.""",
                "Vector_Acumulado",
                f"Total > Perfil × {c['mult_acumulado']}x",
                impacto_html=(
                    "<strong>Bajar el multiplicador -></strong> Se detectan más clientes con acumulación sospechosa.<br>"
                    "<strong>Subir el multiplicador -></strong> Solo se alertan clientes con acumulaciones extremas.<br>"
                    "<strong>Desactivar -></strong> El sistema ignora el volumen total; útil si los perfiles no están bien calibrados."
                ),
            )
        with col_ctrl2:
            c["mult_acumulado"] = st.slider(
                "Multiplicador sobre perfil (Nx)",
                1.0, 10.0, float(c["mult_acumulado"]), 0.1,
                help="Si total_mensual > perfil × N, se activa la alerta.",
                disabled=not c["regla_acumulado"]
            )
            ui_components.regla_kpi(f"{c['mult_acumulado']}x", "Multiplicador actual", c['peso_acumulado'], c['regla_acumulado'])

        st.markdown("---")

        # ── Regla 3: Tolerancia sobre Perfil ──────────────────────────
        col_on3, col_title3 = st.columns([1, 9])
        with col_on3:
            c["regla_perfil"] = st.toggle("", value=c["regla_perfil"], key="tog_perf")
        with col_title3:
            estado_perf = "ACTIVA" if c["regla_perfil"] else "DESACTIVADA"
            ui_components.regla_titulo("Regla 3: Exceso sobre Perfil", c["regla_perfil"])

        col_desc3, col_ctrl3 = st.columns([3, 2])
        with col_desc3:
            ui_components.spec_card(
                """Detección de <strong>ruptura de perfil individual</strong>.
Valida desviaciones porcentuales sobre el comportamiento histórico del cliente.""",
                "Vector_Riesgo_P",
                f"> Perfil + {c['tolerancia_perfil']}%",
            )
        with col_ctrl3:
            c["tolerancia_perfil"] = st.slider(
                "Tolerancia sobre perfil (%)",
                0, 100, int(c["tolerancia_perfil"]), 1,
                help="Porcentaje máximo que puede superar el monto al perfil esperado.",
                disabled=not c["regla_perfil"]
            )
            ui_components.regla_kpi(f"{c['tolerancia_perfil']}%", "Tolerancia actual", c['peso_perfil'], c['regla_perfil'])

        st.markdown("---")

        # ── Regla 4: Frecuencia Alta ───────────────────────────────────
        col_on4, col_title4 = st.columns([1, 9])
        with col_on4:
            c["regla_frecuencia"] = st.toggle("", value=c["regla_frecuencia"], key="tog_frec")
        with col_title4:
            estado_frec = "ACTIVA" if c["regla_frecuencia"] else "DESACTIVADA"
            ui_components.regla_titulo("Regla 4: Frecuencia Alta", c["regla_frecuencia"])

        col_desc4, col_ctrl4 = st.columns([3, 2])
        with col_desc4:
            ui_components.spec_card(
                """Análisis de <strong>densidad operativa</strong>.
Identifica saturación de transacciones en el ciclo, vector clave para detección de uso de cuenta puente.""",
                "Vector_Frecuencia",
                f"N > {c['umbral_frecuencia']} ops",
            )
        with col_ctrl4:
            c["umbral_frecuencia"] = st.number_input(
                "Máximo de transacciones en el período",
                min_value=1, max_value=500, value=int(c["umbral_frecuencia"]), step=1,
                help="Si el cliente supera este número de transacciones, se activa la alerta.",
                disabled=not c["regla_frecuencia"]
            )
            ui_components.regla_kpi(f"&gt;{c['umbral_frecuencia']}", "Umbral de transacciones", c['peso_frecuencia'], c['regla_frecuencia'])

        st.markdown("---")

        # ── Regla 5: Smurfing ──────────────────────────────────────────
        col_on5, col_title5 = st.columns([1, 9])
        with col_on5:
            c["regla_smurfing"] = st.toggle("", value=c["regla_smurfing"], key="tog_smurf")
        with col_title5:
            estado_smurf = "ACTIVA" if c["regla_smurfing"] else "DESACTIVADA"
            ui_components.regla_titulo("Regla 5: Smurfing (Fragmentación)", c["regla_smurfing"])

        col_desc5, col_ctrl5 = st.columns([3, 2])
        with col_desc5:
            ui_components.spec_card(
                """Detección de <strong>pitufeo (smurfing)</strong>.
Identifica fragmentación técnica de capital en ventanas de 24 horas para evadir controles de umbral fijo.""",
                "Vector_Smurfing",
                f"Ops/Día ≥ {c['umbral_smurfing']}",
            )
        with col_ctrl5:
            c["umbral_smurfing"] = st.number_input(
                "Transacciones en mismo día para activar",
                min_value=2, max_value=50, value=int(c["umbral_smurfing"]), step=1,
                help="Número de transacciones en un mismo día que activa la alerta de smurfing.",
                disabled=not c["regla_smurfing"]
            )
            ui_components.regla_kpi(f"≥{c['umbral_smurfing']}/día", "Umbral smurfing + gráfica", c['peso_smurfing'], True, tone="red")

        st.markdown("---")

        # ── Regla 6: Pico Anómalo ──────────────────────────────────────

        col_on6, col_title6 = st.columns([1, 9])
        with col_on6:
            c["regla_pico"] = st.toggle("", value=c["regla_pico"], key="tog_pico")
        with col_title6:
            estado_pico = "ACTIVA" if c["regla_pico"] else "DESACTIVADA"
            ui_components.regla_titulo("Regla 6: Pico Anómalo Estadístico", c["regla_pico"])

        col_desc6, col_ctrl6 = st.columns([3, 2])
        with col_desc6:
            ui_components.spec_card(
                """Detección de <strong>outliers estadísticos</strong>.
Valida anomalías de comportamiento mediante desviación estándar (Sigma) sobre la media histórica del cliente.""",
                "Vector_Sigma_P",
                f"> Media + {c['mult_std_pico']}σ",
            )
        with col_ctrl6:
            c["mult_std_pico"] = st.slider(
                "Multiplicador de desviación estándar (N)",
                0.5, 5.0, float(c["mult_std_pico"]), 0.5,
                help="Activa si monto > (media + N × std). Menor valor = más sensible.",
                disabled=not c["regla_pico"]
            )
            ui_components.regla_kpi(f"μ + {c['mult_std_pico']}σ", "Umbral estadístico", c['peso_pico'], c['regla_pico'])

        st.markdown("---")

        # ── Regla 7: Verificación FEIS → FEIC ─────────────────────────
        col_on7, col_title7 = st.columns([1, 9])
        with col_on7:
            c["regla_feic"] = st.toggle("", value=c.get("regla_feic", True), key="tog_feic")
        with col_title7:
            ui_components.regla_titulo("Regla 7: Verificación FEIS → FEIC", c.get("regla_feic", True))

        col_desc7, col_ctrl7 = st.columns([3, 2])
        with col_desc7:
            umbral_actual = c.get("umbral_feic", 45000)
            ui_components.spec_card(
                """Verifica que los <strong>asociados con perfil transaccional bajo</strong>
registrados con FEIS actualicen a FEIC cuando sus transacciones superan el umbral definido.
Si el total mensual no supera el umbral, <strong>NO</strong> se genera la acción de mitigación.""",
                "FEIS: Simplificado",
                "FEIC: Completo",
                acento="#b47cf7",
                etiqueta_variable="Formulario origen",
                etiqueta_logica="Formulario objetivo",
                impacto_titulo="LÓGICA DE ACTIVACIÓN",
                impacto_html=(
                    f"<strong>Total Mensual &gt; Q{h(format(umbral_actual, ','))} →</strong> Se agrega acción F-01 en Mitigación.<br>"
                    f"<strong>Total Mensual ≤ Q{h(format(umbral_actual, ','))} →</strong> No se muestra la acción (perfil bajo OK)."
                ),
            )
        with col_ctrl7:
            c["umbral_feic"] = st.number_input(
                "Umbral máximo perfil bajo (Q)",
                min_value=1000, max_value=500_000,
                value=int(c.get("umbral_feic", 45000)),
                step=1000,
                help="Si el total mensual del asociado supera este monto, se activa la acción F-01 (actualizar a FEIC).",
                disabled=not c.get("regla_feic", True)
            )
            ui_components.regla_kpi(
                f"Q{c.get('umbral_feic', 45000):,}", "Umbral FEIC actual", "F-01 | GAFI Rec. 10",
                c.get("regla_feic", True), tone="violet",
            )

    # ── TAB 2: Pesos del Score ──────────────────────────────────────────
    with tab2:
        st.markdown("""
        <div class="info-box">
            <strong>PONDERACIÓN DE SCORE</strong>: Distribución de criticidad analítica.
            El Score de Riesgo resulta de la agregación ponderada de vectores activos.
            Configure los pesos para priorizar las tipologías más relevantes según la política institucional.
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:16px;">
            <div style="color:#f59e0b; font-size:12px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                <span class="pulse-dot"></span> MATRIZ DE PONDERACIÓN
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px; font-size:12px; color:#b8a58e; line-height:1.8;">
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>CORRECCIÓN MONTO</span>: Penalización escalar por volumen transaccional directo.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>VOLUMEN CICLO</span>: Priorización de acumulación económica persistente.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>DESVIACIÓN PERFIL</span>: Sensibilidad ante cambios de nivel declarado.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>FRECUENCIA</span>: Control de densidad operativa en el período.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>FRAGMENTACIÓN</span>: Defensa contra técnicas de ocultamiento (Smurfing).</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>SIGMA ANOMALÍA</span>: Ponderación de rareza estadística histórica.</div>
            </div>
        </div>""", unsafe_allow_html=True)

        col_p1, col_p2 = st.columns(2)

        with col_p1:
            st.markdown("### Pilares Estratégicos (S_T, S_C, S_B, S_N)")
            st.markdown("""
            <div style="font-size:12px; color:#b8a58e; margin-bottom:12px;">
                Defina la importancia relativa de cada pilar en el Score Total. La suma de estos pesos determinará el núcleo del motor.
            </div>""", unsafe_allow_html=True)
            
            c["w_st"] = st.slider("w1: Transaccional (S_T)", 0.0, 1.0, float(c["w_st"]), 0.05, help="Importancia de las reglas de detección de montos y frecuencias.")
            c["w_sc"] = st.slider("w2: Contextual (S_C)", 0.0, 1.0, float(c["w_sc"]), 0.05, help="Importancia de la naturaleza del cliente (PEP, CPE, Ubicación).")
            c["w_sb"] = st.slider("w3: Conductual (S_B)", 0.0, 1.0, float(c["w_sb"]), 0.05, help="Importancia de las desviaciones del perfil histórico.")
            c["w_sn"] = st.slider("w4: Red (S_N)", 0.0, 1.0, float(c["w_sn"]), 0.05, help="Importancia de la interconexión y flujos en la red.")
            
            suma_w = c["w_st"] + c["w_sc"] + c["w_sb"] + c["w_sn"]
            if abs(suma_w - 1.0) > 0.001:
                st.warning(f"⚠️ La suma de pesos es {suma_w:.2f}. Se recomienda que sea 1.00 para una escala de 0-10 estándar.")
            else:
                st.success("✅ Ponderación equilibrada (Suma = 1.00)")

            st.markdown("---")
            st.markdown("### Componentes Técnicos (S_T)")
            st.markdown("""
            <div style="font-size:12px; color:#b8a58e; margin-bottom:12px;">
                Ajusta el peso individual de cada regla que alimenta al pilar Transaccional. (0 = off, 10 = max).
            </div>""", unsafe_allow_html=True)
            
            c["peso_absoluto"]   = st.number_input("Peso: Monto Alto Absoluto",   0, 10, int(c["peso_absoluto"]),   key="p1")
            c["peso_acumulado"]  = st.number_input("Peso: Acumulado Mensual",      0, 10, int(c["peso_acumulado"]),  key="p2")
            c["peso_perfil"]     = st.number_input("Peso: Exceso sobre Perfil",    0, 10, int(c["peso_perfil"]),     key="p3")
            c["peso_frecuencia"] = st.number_input("Peso: Frecuencia Alta",        0, 10, int(c["peso_frecuencia"]), key="p4")
            c["peso_smurfing"]   = st.number_input("Peso: Smurfing",               0, 10, int(c["peso_smurfing"]),   key="p5")
            c["peso_pico"]       = st.number_input("Peso: Pico Anómalo",           0, 10, int(c["peso_pico"]),       key="p6")

        with col_p2:
            score_max_teorico = (
                c["peso_absoluto"] + c["peso_acumulado"] + c["peso_perfil"] +
                c["peso_frecuencia"] + c["peso_smurfing"] + c["peso_pico"]
            )
            st.markdown("**Distribución visual de pesos**")
            st.markdown(f"""
            <div class="metric-card red">
                <div class="metric-number">{h(score_max_teorico)}</div>
                <div class="metric-label">Score máximo teórico</div>
                <div class="metric-sub">Con todas las reglas activas simultáneamente</div>
            </div><br>
            """, unsafe_allow_html=True)

            reglas_nombres = ["Monto Absoluto","Acumulado","Exceso Perfil","Frecuencia","Smurfing","Pico"]
            pesos_vals     = [c["peso_absoluto"],c["peso_acumulado"],c["peso_perfil"],
                              c["peso_frecuencia"],c["peso_smurfing"],c["peso_pico"]]

            fig_p, ax_p = plt.subplots(figsize=(5, 3))
            fig_p, ax_p = apply_dark_style(fig_p, ax_p)
            colores_p = ["#ef4444","#f97316","#eab308","#eab308","#ef4444","#f97316"]
            bars_p = ax_p.barh(reglas_nombres, pesos_vals, color=colores_p, edgecolor='#0d1117', height=0.5)
            for bar, val in zip(bars_p, pesos_vals):
                ax_p.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
                          str(val), va='center', color='#c9d1d9', fontsize=10, fontweight='bold')
            ax_p.set_xlabel("Puntos al Score", color='#a7b0bb')
            ax_p.invert_yaxis()
            plt.tight_layout()
            st.pyplot(fig_p)
            plt.close()

            st.markdown(f"""
            <div class="warning-box" style="margin-top:12px;">
                <strong>⚠️ Recuerda:</strong> Si cambias los pesos, ajusta también los umbrales de
                clasificación en <em>Clasificación de Riesgo</em> para que Crítico/Alto/Medio
                sigan siendo proporcionales al nuevo score máximo de <strong>{h(score_max_teorico)} pts</strong>.
            </div>""", unsafe_allow_html=True)

    # ── TAB 3: Clasificación de Riesgo ─────────────────────────────────
    with tab3:
        st.markdown("""
        <div class="info-box">
            <strong>CLASIFICACIÓN DE RIESGO</strong>: Calibración de niveles de alerta.
            Determine los umbrales de score y volumen para la segmentación del universo transaccional.
            Los cambios afectan la distribución táctica de recursos de investigación.
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:16px;">
            <div style="color:#f59e0b; font-size:12px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                <span class="pulse-dot"></span> LÓGICA DE SEGMENTACIÓN
            </div>
            <div style="font-size:12px; color:#b8a58e; line-height:2;">
                <span style='color:#ef4444; font-weight:700;'>NIVEL CRÍTICO</span>: Clientes en zona de reporte regulatorio inmediato.<br>
                <span style='color:#f97316; font-weight:700;'>NIVEL ALTO</span>: Objetivos de debida diligencia ampliada (EDD).<br>
                <span style='color:#eab308; font-weight:700;'>NIVEL MEDIO</span>: Monitoreo preventivo y actualización de perfil.<br>
                <span style='color:#10b981; font-weight:700;'>NIVEL BAJO</span>: Actividad dentro de parámetros normales establecidos.
            </div>
        </div>""", unsafe_allow_html=True)

        col_r1, col_r2 = st.columns(2)

        with col_r1:
            st.markdown("**Nivel Crítico**")
            c["score_critico"] = st.number_input(
                "Score mínimo para Crítico",
                min_value=1, max_value=30, value=int(c["score_critico"]),
                help="Clientes con score ≥ este valor son clasificados como Críticos. Requieren revisión urgente."
            )
            c["monto_critico"] = st.number_input(
                "Monto total mínimo para Crítico (Q)",
                min_value=1000, max_value=10_000_000, value=int(c["monto_critico"]), step=1000,
                help="Clientes cuyo total mensual supere este monto son Críticos, independiente del score."
            )

            st.markdown("<br>**Nivel Alto**", unsafe_allow_html=True)
            c["score_alto"] = st.number_input(
                "Score mínimo para Alto",
                min_value=1, max_value=30, value=int(c["score_alto"]),
                help="Clientes con score ≥ este valor (y menor que Crítico) son clasificados como Alto."
            )

            st.markdown("<br>**Nivel Medio**", unsafe_allow_html=True)
            c["score_medio"] = st.number_input(
                "Score mínimo para Medio",
                min_value=1, max_value=30, value=int(c["score_medio"]),
                help="Clientes con score ≥ este valor (y menor que Alto) son clasificados como Medio."
            )

            st.markdown("""
            <div class="info-box" style="margin-top:12px;">
                <strong>Nivel Bajo</strong>: Se asigna automáticamente a todo cliente cuyo score
                sea menor al umbral Medio y cuyo total mensual no supere el monto crítico.
                Son clientes sin señales de alerta significativas en el período.
            </div>""", unsafe_allow_html=True)

        with col_r2:
            st.markdown("**Escala de clasificación actual**")
            escala = [
                ("Crítico", f"Score ≥ {c['score_critico']} o Total > Q{c['monto_critico']:,}", "#ef4444",
                 "Reporte RTS a la IVE (Art. 30 Ley 6593)"),
                ("Alto",    f"Score ≥ {c['score_alto']}",  "#f97316",
                 "Seguimiento prioritario / Actualizar perfil"),
                ("Medio",   f"Score ≥ {c['score_medio']}", "#eab308",
                 "Monitoreo preventivo / Revisión periódica"),
                ("Bajo",    f"Score < {c['score_medio']}",  "#22c55e",
                 "Sin acciones requeridas en este período"),
            ]
            for nivel_e, cond_e, color_e, accion_e in escala:
                st.markdown(f"""
                <div style="background:#1b2027; border-left:8px solid {h(color_e)}; border-radius:0px; padding:16px; margin-bottom:12px; border-bottom: 1px solid rgba(83, 68, 52, 0.1);">
                    <div style="color:{h(color_e)}; font-weight:700; font-size:14px; text-transform:uppercase; letter-spacing:1px;">{h(nivel_e)}</div>
                    <div style="color:#dee2ed; font-size:12px; margin-top:6px; font-family:IBM Plex Mono,monospace;">
                        CRITERIO: {h(cond_e)}
                    </div>
                    <div style="color:#b8a58e; font-size:12px; margin-top:4px;">
                        PROTOCOLO DE ACCIÓN: {h(accion_e)}
                    </div>
                </div>""", unsafe_allow_html=True)

            if c["score_medio"] >= c["score_alto"]:
                st.error("⚠️ El score de Medio debe ser menor que el de Alto.")
            if c["score_alto"] >= c["score_critico"]:
                st.error("⚠️ El score de Alto debe ser menor que el de Crítico.")

    # ── TAB 4: Resumen y Aplicar ────────────────────────────────────────
    with tab4:
        st.markdown("### Resumen de la Configuración Actual")

        col_res1, col_res2 = st.columns(2)

        with col_res1:
            st.markdown("**Reglas de Detección**")
            reglas_resumen = [
                ("Monto Alto Absoluto", c["regla_absoluto"],   f"Umbral: Q{c['umbral_absoluto']:,}"),
                ("Acumulado Mensual",   c["regla_acumulado"],  f"Multiplicador: {c['mult_acumulado']}x"),
                ("Exceso sobre Perfil", c["regla_perfil"],     f"Tolerancia: {c['tolerancia_perfil']}%"),
                ("Frecuencia Alta",     c["regla_frecuencia"], f"Umbral: >{c['umbral_frecuencia']} transacciones"),
                ("Smurfing",            c["regla_smurfing"],   f"Umbral: ≥{c['umbral_smurfing']} en mismo día"),
                ("Pico Anómalo",        c["regla_pico"],       f"Umbral: μ + {c['mult_std_pico']}σ"),
            ]
            for nombre_r, activa_r, detalle_r in reglas_resumen:
                estado_color = "#22c55e" if activa_r else "#ef4444"
                estado_txt   = "ACTIVA" if activa_r else "OFF"
                st.markdown(f"""
                <div style="background:#171c23; border:1px solid #21262d; border-radius:0px;
                            padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="color:#c9d1d9; font-size:13px;">{h(nombre_r)}</div>
                        <div style="color:#a7b0bb; font-size:12px; font-family:IBM Plex Mono,monospace;">{h(detalle_r)}</div>
                    </div>
                    <div style="color:{h(estado_color)}; font-size:12px; font-weight:700;
                                font-family:IBM Plex Mono,monospace; border:1px solid {h(estado_color)};
                                padding:2px 8px; border-radius:0px;">{h(estado_txt)}</div>
                </div>""", unsafe_allow_html=True)

        with col_res2:
            st.markdown("**Pesos y Clasificación**")
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #21262d; border-radius:0px; padding:16px;">
                <div style="font-family:IBM Plex Mono,monospace; font-size:12px; color:#a7b0bb; line-height:2;">
                    <hr style='border-color:#21262d; margin:8px 0;'>
                    <div style='color:#f0f6fc; font-weight:700; margin-bottom:5px;'>Ponderación de Pilares:</div>
                    S_T (Transaccional) → <span style='color:#3b82f6;'>{h(format(c['w_st'], '.2f'))}</span><br>
                    S_C (Contextual) → <span style='color:#3b82f6;'>{h(format(c['w_sc'], '.2f'))}</span><br>
                    S_B (Conductual) → <span style='color:#3b82f6;'>{h(format(c['w_sb'], '.2f'))}</span><br>
                    S_N (Red) → <span style='color:#3b82f6;'>{h(format(c['w_sn'], '.2f'))}</span>
                    <hr style='border-color:#21262d; margin:8px 0;'>
                    Score máx. teórico → <span style='color:#ef4444; font-weight:700;'>
                        {h(c['peso_absoluto']+c['peso_acumulado']+c['peso_perfil']+c['peso_frecuencia']+c['peso_smurfing']+c['peso_pico'])} pts
                    </span><br><br>
                    Crítico: score ≥ <span style='color:#ef4444;'>{h(c['score_critico'])}</span>
                        o total &gt; <span style='color:#ef4444;'>Q{h(format(c['monto_critico'], ','))}</span><br>
                    Alto: score ≥ <span style='color:#f97316;'>{h(c['score_alto'])}</span><br>
                    Medio: score ≥ <span style='color:#eab308;'>{h(c['score_medio'])}</span><br>
                    Bajo: score &lt; <span style='color:#22c55e;'>{h(c['score_medio'])}</span>
                </div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 2])

    with col_btn1:
        c["moneda"] = st.selectbox(
            "Moneda de presentación", options=["GTQ", "USD"],
            index=0 if c.get("moneda", "GTQ") == "GTQ" else 1,
            help="Moneda con la que se muestran montos y umbrales en toda la plataforma. "
                 "El umbral RTE del Art. 31 se mantiene en USD por mandato legal.",
            disabled=not puede_editar,
        )
        if st.button("Aplicar Configuración", type="primary", use_container_width=True, disabled=not puede_editar):
            errores = []
            if c["score_medio"] >= c["score_alto"]:
                errores.append("Score Medio debe ser menor que Score Alto.")
            if c["score_alto"] >= c["score_critico"]:
                errores.append("Score Alto debe ser menor que Score Crítico.")
            if not any([c["regla_absoluto"], c["regla_acumulado"], c["regla_perfil"],
                        c["regla_frecuencia"], c["regla_smurfing"], c["regla_pico"]]):
                errores.append("Debes tener al menos una regla activa.")
            if errores:
                for err in errores:
                    st.error(f"Error: {err}")
            else:
                st.session_state["aml_config"] = c
                _auditar_cambio_config()
                st.success("Configuración aplicada. Vuelve a subir el archivo para reprocesar con los nuevos parámetros.")

    with col_btn2:
        if st.button("Restablecer a valores base", use_container_width=True, disabled=not puede_editar):
            st.session_state["aml_config"] = _DEFAULTS.copy()
            st.success("Valores restaurados a los defaults.")
            st.rerun()

    with col_btn3:
        import json as _json_export
        cfg_export = _json_export.dumps(st.session_state["aml_config"], indent=2, ensure_ascii=False)
        exportacion.boton_descarga(
            "Exportar Configuración (JSON)",
            data=cfg_export,
            file_name="aml_config.json",
            mime="application/json",
            use_container_width=True,
            modulo="Configuración",
        )

    # ── TAB 5: Catálogos IVE (RTS): solo lectura ────────────────────────
    with tab5:
        st.markdown("""
        <div class="info-box">
            <strong>CATÁLOGOS GLOBALES DEL RTS</strong>: Datos de referencia oficiales del
            normativa IVE vigente, compartidos por todas las licencias. El código
            y nombre son de solo lectura; puede activar o inactivar entradas según la necesidad
            de su institución.
        </div>
        """, unsafe_allow_html=True)

        db = SessionLocal()
        try:
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            conteos = {
                nombre: db.query(modelo).count()
                for nombre, (modelo, _cols) in _CATALOGOS_RTS.items()
            }
            for columna, nombre in zip(
                [col_m1, col_m2, col_m3, col_m4],
                ["Departamentos", "Municipios", "Países", "Monedas"],
            ):
                with columna:
                    st.metric(nombre, conteos.get(nombre, 0))

            if conteos.get("Municipios", 0) != 340:
                st.warning(
                    f"Se esperaban 340 municipios (Guatemala) y hay {conteos.get('Municipios', 0)}. "
                    "Contacte a soporte técnico para regularizar el catálogo."
                )

            st.markdown("<br>", unsafe_allow_html=True)
            catalogo_sel = st.selectbox("Ver catálogo completo", options=list(_CATALOGOS_RTS.keys()))
            modelo_sel, columnas_sel = _CATALOGOS_RTS[catalogo_sel]
            df_catalogo = _consultar_catalogo_df(db, modelo_sel, columnas_sel)
            st.caption(f"{len(df_catalogo)} registro(s).")
            if df_catalogo.empty:
                st.info("Este catálogo aún no tiene datos. Contacte a soporte técnico.")
            else:
                render_html_table(df_catalogo, table_id="tabla_catalogos_rts")

                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown("**Activar / Inactivar entrada**")
                opciones_entrada = [
                    f"{fila['codigo']}: {fila['nombre']}" for _, fila in df_catalogo.iterrows()
                ]
                col_sel, col_estado, col_btn = st.columns([3, 1, 1], vertical_alignment="center")
                with col_sel:
                    entrada_sel = st.selectbox(
                        "Entrada", options=opciones_entrada, key="entrada_catalogo_sel",
                        label_visibility="collapsed",
                    )
                codigo_sel = entrada_sel.split(": ", 1)[0]
                activo_actual = bool(
                    df_catalogo.loc[df_catalogo["codigo"] == codigo_sel, "activo"].iloc[0]
                )
                with col_estado:
                    color_estado = "#2ecc71" if activo_actual else "#e74c3c"
                    texto_estado = "Activo" if activo_actual else "Inactivo"
                    st.markdown(
                        f"<div style='text-align:center; font-weight:600; color:{h(color_estado)};'>"
                        f"{h(texto_estado)}</div>",
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    etiqueta_boton = "Inactivar" if activo_actual else "Activar"
                    if st.button(etiqueta_boton, key="btn_toggle_catalogo", use_container_width=True,
                                 disabled=not permisos.puede("gestionar_catalogos")):
                        actualizado = _actualizar_estado_catalogo(
                            db, modelo_sel, codigo_sel, not activo_actual
                        )
                        if actualizado:
                            st.success(f"'{codigo_sel}' ahora está {'activo' if not activo_actual else 'inactivo'}.")
                            st.rerun()
                        else:
                            st.error(f"No se encontró el código '{codigo_sel}' en el catálogo.")
        finally:
            db.close()

    # ── POLÍTICA DE RETENCIÓN DE DATOS (Art. 34 Ley 6593) ─────────────────────
    st.markdown("---")
    st.markdown("### Política de Retención de Datos")
    st.markdown(
        "**Art. 34 Ley 6593:** Los sujetos obligados deben conservar todos los registros y documentos "
        "por un mínimo de **5 años** desde la fecha de la transacción o finalización de la relación comercial."
    )

    RETENCION_MINIMA_ANOS = 5  # Art. 34: no modificable por el usuario

    col_ret1, col_ret2 = st.columns(2)
    with col_ret1:
        st.metric("Retención mínima obligatoria", f"{RETENCION_MINIMA_ANOS} años",
                  help="Art. 34 Ley 6593: no configurable")
    with col_ret2:
        retencion_config = st.number_input(
            "Retención configurada por la institución (años)",
            min_value=RETENCION_MINIMA_ANOS,
            max_value=20,
            value=RETENCION_MINIMA_ANOS,
            step=1,
            help="No puede ser inferior al mínimo legal de 5 años."
        )

    st.info(f"ℹ️ El sistema bloqueará cualquier eliminación de registros con antigüedad inferior a {retencion_config} años.")
