import streamlit as st
import matplotlib.pyplot as plt
from datetime import date as _date
from frontend.mod_utils import apply_dark_style

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

def mostrar(_DEFAULTS):
    st.markdown("""
    <div class="info-box">
        <strong>CONFIGURACIÓN DE REGLAS AML</strong> — Parámetros de detección y ponderación del motor de riesgo.
        Administre umbrales, reglas de detección y clasificación de riesgo.
        Los ajustes se integran en tiempo real al análisis.
    </div>
    """, unsafe_allow_html=True)

    c = st.session_state["aml_config"].copy()

    # ── TABS de secciones ────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "Reglas de Detección",
        "Pesos del Score",
        "Clasificación de Riesgo",
        "Resumen y Aplicar"
    ])

    # ── Botón Restablecer prominente arriba de los tabs ─────────────────
    col_rst1, col_rst2, col_rst3 = st.columns([3, 2, 3])
    with col_rst2:
        if st.button("Restablecer configuración base", use_container_width=True):
            st.session_state["aml_config"] = _DEFAULTS.copy()
            st.success("✅ Todos los parámetros han sido restaurados a los valores por defecto.")
            st.rerun()
    st.markdown("<br>", unsafe_allow_html=True)


    # ── TAB 1: Reglas de Detección ──────────────────────────────────────
    with tab1:
        st.markdown("""
        <div class="info-box" style="background-color: #1b2027; border-left-color: #f59e0b;">
            <strong>⚠️ CALIBRACIÓN TÉCNICA:</strong> La alteración de umbrales impacta directamente en la sensibilidad del motor.
            Un umbral bajo incrementa la densidad de alertas. Ajuste según el apetito de riesgo institucional.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 1 — Monto Alto Absoluto ──────────────────────────────
        col_on, col_title = st.columns([1, 9])
        with col_on:
            c["regla_absoluto"] = st.toggle("", value=c["regla_absoluto"], key="tog_abs")
        with col_title:
            estado_abs = "ACTIVA" if c["regla_absoluto"] else "DESACTIVADA"
            st.markdown(f'<div class="section-title">Regla 1 — Monto Alto Absoluto &nbsp;<span class="section-badge">{estado_abs}</span></div>', unsafe_allow_html=True)

        col_desc1, col_ctrl1 = st.columns([3, 2])
        with col_desc1:
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Validación contra <strong style='color:#f59e0b;'>umbral absoluto configurado</strong>.
                    Regla de detección directa: activación inmediata si el monto individual excede el límite institucional.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Variable IMPERATOR</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Vector_Absoluto</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lógica Algebraica</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Monto &gt; Q{c['umbral_absoluto']:,}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl1:
            c["umbral_absoluto"] = st.number_input(
                "Umbral absoluto (Q)",
                min_value=1000, max_value=10_000_000, value=int(c["umbral_absoluto"]), step=1000,
                help="Cualquier transacción individual mayor a este monto activa la alerta.",
                disabled=not c["regla_absoluto"]
            )
            st.markdown(f"""
            <div class="metric-card {'amber' if c['regla_absoluto'] else 'blue'}" style="margin-top:8px;">
                <div class="metric-number" style="font-size:22px;">Q{c['umbral_absoluto']:,}</div>
                <div class="metric-label">Umbral actual</div>
                <div class="metric-sub">Peso en score: <strong>{c['peso_absoluto']} pts</strong></div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 2 — Acumulado Mensual ────────────────────────────────
        col_on2, col_title2 = st.columns([1, 9])
        with col_on2:
            c["regla_acumulado"] = st.toggle("", value=c["regla_acumulado"], key="tog_acum")
        with col_title2:
            estado_acum = "ACTIVA" if c["regla_acumulado"] else "DESACTIVADA"
            st.markdown(f'<div class="section-title">Regla 2 — Acumulado Mensual &nbsp;<span class="section-badge">{estado_acum}</span></div>', unsafe_allow_html=True)

        col_desc2, col_ctrl2 = st.columns([3, 2])
        with col_desc2:
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Evaluación de <strong style='color:#f59e0b;'>volumen acumulado por ciclo</strong>.
                    Identifica acumulación de capital por encima del multiplicador de perfil configurado.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Variable IMPERATOR</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Vector_Acumulado</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lógica Algebraica</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Total &gt; Perfil × {c['mult_acumulado']}x</div>
                    </div>
                </div>
                <div style="margin-top:12px; padding:10px; background:#1b2027; border-left:2px solid #3b82f6;">
                    <div style="color:#a08e7a; font-size:11px; font-family:IBM Plex Mono,monospace;">IMPACTO AL MODIFICAR</div>
                    <div style="color:#a08e7a; font-size:12px; margin-top:4px; line-height:1.7;">
                        <strong style='color:#c9d1d9;'>Bajar el multiplicador -></strong> Se detectan más clientes con acumulación sospechosa.<br>
                        <strong style='color:#c9d1d9;'>Subir el multiplicador -></strong> Solo se alertan clientes con acumulaciones extremas.<br>
                        <strong style='color:#c9d1d9;'>Desactivar -></strong> El sistema ignora el volumen total; útil si los perfiles no están bien calibrados.
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl2:
            c["mult_acumulado"] = st.slider(
                "Multiplicador sobre perfil (Nx)",
                1.0, 10.0, float(c["mult_acumulado"]), 0.1,
                help="Si total_mensual > perfil × N, se activa la alerta.",
                disabled=not c["regla_acumulado"]
            )
            st.markdown(f"""
            <div class="metric-card {'amber' if c['regla_acumulado'] else 'blue'}" style="margin-top:8px;">
                <div class="metric-number" style="font-size:22px;">{c['mult_acumulado']}x</div>
                <div class="metric-label">Multiplicador actual</div>
                <div class="metric-sub">Peso en score: <strong>{c['peso_acumulado']} pts</strong></div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 3 — Tolerancia sobre Perfil ──────────────────────────
        col_on3, col_title3 = st.columns([1, 9])
        with col_on3:
            c["regla_perfil"] = st.toggle("", value=c["regla_perfil"], key="tog_perf")
        with col_title3:
            estado_perf = "ACTIVA" if c["regla_perfil"] else "DESACTIVADA"
            st.markdown(f'<div class="section-title">Regla 3 — Exceso sobre Perfil &nbsp;<span class="section-badge">{estado_perf}</span></div>', unsafe_allow_html=True)

        col_desc3, col_ctrl3 = st.columns([3, 2])
        with col_desc3:
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Detección de <strong style='color:#f59e0b;'>ruptura de perfil individual</strong>.
                    Valida desviaciones porcentuales sobre el comportamiento histórico del cliente.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Variable IMPERATOR</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Vector_Riesgo_P</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lógica Algebraica</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">&gt; Perfil + {c['tolerancia_perfil']}%</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl3:
            c["tolerancia_perfil"] = st.slider(
                "Tolerancia sobre perfil (%)",
                0, 100, int(c["tolerancia_perfil"]), 1,
                help="Porcentaje máximo que puede superar el monto al perfil esperado.",
                disabled=not c["regla_perfil"]
            )
            st.markdown(f"""
            <div class="metric-card {'amber' if c['regla_perfil'] else 'blue'}" style="margin-top:8px;">
                <div class="metric-number" style="font-size:22px;">{c['tolerancia_perfil']}%</div>
                <div class="metric-label">Tolerancia actual</div>
                <div class="metric-sub">Peso en score: <strong>{c['peso_perfil']} pts</strong></div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 4 — Frecuencia Alta ───────────────────────────────────
        col_on4, col_title4 = st.columns([1, 9])
        with col_on4:
            c["regla_frecuencia"] = st.toggle("", value=c["regla_frecuencia"], key="tog_frec")
        with col_title4:
            estado_frec = "ACTIVA" if c["regla_frecuencia"] else "DESACTIVADA"
            st.markdown(f'<div class="section-title">Regla 4 — Frecuencia Alta &nbsp;<span class="section-badge">{estado_frec}</span></div>', unsafe_allow_html=True)

        col_desc4, col_ctrl4 = st.columns([3, 2])
        with col_desc4:
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Análisis de <strong style='color:#f59e0b;'>densidad operativa</strong>.
                    Identifica saturación de transacciones en el ciclo, vector clave para detección de uso de cuenta puente.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Variable IMPERATOR</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Vector_Frecuencia</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lógica Algebraica</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">N &gt; {c['umbral_frecuencia']} ops</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl4:
            c["umbral_frecuencia"] = st.number_input(
                "Máximo de transacciones en el período",
                min_value=1, max_value=500, value=int(c["umbral_frecuencia"]), step=1,
                help="Si el cliente supera este número de transacciones, se activa la alerta.",
                disabled=not c["regla_frecuencia"]
            )
            st.markdown(f"""
            <div class="metric-card {'amber' if c['regla_frecuencia'] else 'blue'}" style="margin-top:8px;">
                <div class="metric-number" style="font-size:22px;">&gt;{c['umbral_frecuencia']}</div>
                <div class="metric-label">Umbral de transacciones</div>
                <div class="metric-sub">Peso en score: <strong>{c['peso_frecuencia']} pts</strong></div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 5 — Smurfing ──────────────────────────────────────────
        col_on5, col_title5 = st.columns([1, 9])
        with col_on5:
            c["regla_smurfing"] = st.toggle("", value=c["regla_smurfing"], key="tog_smurf")
        with col_title5:
            estado_smurf = "ACTIVA" if c["regla_smurfing"] else "DESACTIVADA"
            st.markdown(f'<div class="section-title">Regla 5 — Smurfing (Fragmentación) &nbsp;<span class="section-badge">{estado_smurf}</span></div>', unsafe_allow_html=True)

        col_desc5, col_ctrl5 = st.columns([3, 2])
        with col_desc5:
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Detección de <strong style='color:#f59e0b;'>pitufeo (smurfing)</strong>.
                    Identifica fragmentación técnica de capital en ventanas de 24 horas para evadir controles de umbral fijo.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Variable IMPERATOR</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Vector_Smurfing</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lógica Algebraica</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Ops/Día ≥ {c['umbral_smurfing']}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl5:
            c["umbral_smurfing"] = st.number_input(
                "Transacciones en mismo día para activar",
                min_value=2, max_value=50, value=int(c["umbral_smurfing"]), step=1,
                help="Número de transacciones en un mismo día que activa la alerta de smurfing.",
                disabled=not c["regla_smurfing"]
            )
            st.markdown(f"""
            <div class="metric-card red" style="margin-top:8px;">
                <div class="metric-number" style="font-size:22px;">≥{c['umbral_smurfing']}/día</div>
                <div class="metric-label">Umbral smurfing + gráfica</div>
                <div class="metric-sub">Peso en score: <strong>{c['peso_smurfing']} pts</strong></div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 6 — Pico Anómalo ──────────────────────────────────────

        col_on6, col_title6 = st.columns([1, 9])
        with col_on6:
            c["regla_pico"] = st.toggle("", value=c["regla_pico"], key="tog_pico")
        with col_title6:
            estado_pico = "ACTIVA" if c["regla_pico"] else "DESACTIVADA"
            st.markdown(f'<div class="section-title">Regla 6 — Pico Anómalo Estadístico &nbsp;<span class="section-badge">{estado_pico}</span></div>', unsafe_allow_html=True)

        col_desc6, col_ctrl6 = st.columns([3, 2])
        with col_desc6:
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Detección de <strong style='color:#f59e0b;'>outliers estadísticos</strong>.
                    Valida anomalías de comportamiento mediante desviación estándar (Sigma) sobre la media histórica del cliente.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Variable IMPERATOR</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">Vector_Sigma_P</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border: 1px solid rgba(83, 68, 52, 0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Lógica Algebraica</div>
                        <div style="color:#f59e0b; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">&gt; Media + {c['mult_std_pico']}σ</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl6:
            c["mult_std_pico"] = st.slider(
                "Multiplicador de desviación estándar (N)",
                0.5, 5.0, float(c["mult_std_pico"]), 0.5,
                help="Activa si monto > (media + N × std). Menor valor = más sensible.",
                disabled=not c["regla_pico"]
            )
            st.markdown(f"""
            <div class="metric-card {'amber' if c['regla_pico'] else 'blue'}" style="margin-top:8px;">
                <div class="metric-number" style="font-size:22px;">μ + {c['mult_std_pico']}σ</div>
                <div class="metric-label">Umbral estadístico</div>
                <div class="metric-sub">Peso en score: <strong>{c['peso_pico']} pts</strong></div>
            </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Regla 7 — Verificación FEIS → FEIC ─────────────────────────
        col_on7, col_title7 = st.columns([1, 9])
        with col_on7:
            c["regla_feic"] = st.toggle("", value=c.get("regla_feic", True), key="tog_feic")
        with col_title7:
            estado_feic = "ACTIVA" if c.get("regla_feic", True) else "DESACTIVADA"
            st.markdown(
                f'<div class="section-title">Regla 7 — Verificación FEIS → FEIC &nbsp;'
                f'<span class="section-badge">{estado_feic}</span></div>',
                unsafe_allow_html=True
            )

        col_desc7, col_ctrl7 = st.columns([3, 2])
        with col_desc7:
            umbral_actual = c.get("umbral_feic", 45000)
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:12px;">
                <div style="color:#a855f7; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                    <span class="pulse-dot" style="background:#a855f7; box-shadow:0 0 10px rgba(168,85,247,0.8);"></span> ESPECIFICACIÓN TÉCNICA
                </div>
                <div style="color:#dee2ed; font-size:13px; line-height:1.8; margin-bottom:15px;">
                    Verifica que los <strong style='color:#a855f7;'>asociados con perfil transaccional bajo</strong>
                    registrados con FEIS actualicen a FEIC cuando sus transacciones superan el umbral definido.
                    Si el total mensual no supera el umbral, <strong>NO</strong> se genera la acción de mitigación.
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border:1px solid rgba(168,85,247,0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Formulario origen</div>
                        <div style="color:#a855f7; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">FEIS — Simplificado</div>
                    </div>
                    <div style="background:#1b2027; border-radius:0px; padding:12px; border:1px solid rgba(168,85,247,0.2);">
                        <div style="color:#a08e7a; font-size:10px; text-transform:uppercase; letter-spacing:1px;">Formulario objetivo</div>
                        <div style="color:#a855f7; font-family:IBM Plex Mono,monospace; font-size:12px; margin-top:4px;">FEIC — Completo</div>
                    </div>
                </div>
                <div style="margin-top:12px; padding:10px; background:#1b2027; border-left:2px solid #a855f7;">
                    <div style="color:#a08e7a; font-size:11px; font-family:IBM Plex Mono,monospace;">LÓGICA DE ACTIVACIÓN</div>
                    <div style="color:#a08e7a; font-size:12px; margin-top:4px; line-height:1.7;">
                        <strong style='color:#c9d1d9;'>Total Mensual &gt; Q{umbral_actual:,} →</strong> Se agrega acción F-01 en Mitigación.<br>
                        <strong style='color:#c9d1d9;'>Total Mensual ≤ Q{umbral_actual:,} →</strong> No se muestra la acción (perfil bajo OK).
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col_ctrl7:
            c["umbral_feic"] = st.number_input(
                "Umbral máximo perfil bajo (Q)",
                min_value=1000, max_value=500_000,
                value=int(c.get("umbral_feic", 45000)),
                step=1000,
                help="Si el total mensual del asociado supera este monto, se activa la acción F-01 (actualizar a FEIC).",
                disabled=not c.get("regla_feic", True)
            )
            color_feic = "amber" if c.get("regla_feic", True) else "blue"
            st.markdown(f"""
            <div class="metric-card {color_feic}" style="margin-top:8px; border-left-color:#a855f7;">
                <div class="metric-number" style="font-size:22px; color:#a855f7;">Q{c.get('umbral_feic', 45000):,}</div>
                <div class="metric-label">Umbral FEIC actual</div>
                <div class="metric-sub">Código de acción: <strong>F-01</strong> | Norma: GAFI Rec. 10</div>
            </div>""", unsafe_allow_html=True)

    # ── TAB 2: Pesos del Score ──────────────────────────────────────────
    with tab2:
        st.markdown("""
        <div class="info-box">
            <strong>PONDERACIÓN DE SCORE</strong> — Distribución de criticidad analítica.
            El Score de Riesgo resulta de la agregación ponderada de vectores activos.
            Configure los pesos para priorizar las tipologías más relevantes según la política institucional.
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:16px;">
            <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                <span class="pulse-dot"></span> MATRIZ DE PONDERACIÓN
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px; font-size:12px; color:#a08e7a; line-height:1.8;">
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>CORRECCIÓN MONTO</span> — Penalización escalar por volumen transaccional directo.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>VOLUMEN CICLO</span> — Priorización de acumulación económica persistente.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>DESVIACIÓN PERFIL</span> — Sensibilidad ante cambios de nivel declarado.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>FRECUENCIA</span> — Control de densidad operativa en el período.</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>FRAGMENTACIÓN</span> — Defensa contra técnicas de ocultamiento (Smurfing).</div>
                <div><span style='color:#f59e0b; font-family:IBM Plex Mono;'>SIGMA ANOMALÍA</span> — Ponderación de rareza estadística histórica.</div>
            </div>
        </div>""", unsafe_allow_html=True)

        col_p1, col_p2 = st.columns(2)

        with col_p1:
            st.markdown("### Pilares Estratégicos (S_T, S_C, S_B, S_N)")
            st.markdown("""
            <div style="font-size:11px; color:#a08e7a; margin-bottom:12px;">
                Defina la importancia relativa de cada pilar en el Score Total. La suma de estos pesos determinará el núcleo del motor.
            </div>""", unsafe_allow_html=True)
            
            c["w_st"] = st.slider("w1 — Transaccional (S_T)", 0.0, 1.0, float(c["w_st"]), 0.05, help="Importancia de las reglas de detección de montos y frecuencias.")
            c["w_sc"] = st.slider("w2 — Contextual (S_C)", 0.0, 1.0, float(c["w_sc"]), 0.05, help="Importancia de la naturaleza del cliente (PEP, CPE, Ubicación).")
            c["w_sb"] = st.slider("w3 — Conductual (S_B)", 0.0, 1.0, float(c["w_sb"]), 0.05, help="Importancia de las desviaciones del perfil histórico.")
            c["w_sn"] = st.slider("w4 — Red (S_N)", 0.0, 1.0, float(c["w_sn"]), 0.05, help="Importancia de la interconexión y flujos en la red.")
            
            suma_w = c["w_st"] + c["w_sc"] + c["w_sb"] + c["w_sn"]
            if abs(suma_w - 1.0) > 0.001:
                st.warning(f"⚠️ La suma de pesos es {suma_w:.2f}. Se recomienda que sea 1.00 para una escala de 0-10 estándar.")
            else:
                st.success("✅ Ponderación equilibrada (Suma = 1.00)")

            st.markdown("---")
            st.markdown("### Componentes Técnicos (S_T)")
            st.markdown("""
            <div style="font-size:11px; color:#a08e7a; margin-bottom:12px;">
                Ajusta el peso individual de cada regla que alimenta al pilar Transaccional. (0 = off, 10 = max).
            </div>""", unsafe_allow_html=True)
            
            c["peso_absoluto"]   = st.number_input("Peso — Monto Alto Absoluto",   0, 10, int(c["peso_absoluto"]),   key="p1")
            c["peso_acumulado"]  = st.number_input("Peso — Acumulado Mensual",      0, 10, int(c["peso_acumulado"]),  key="p2")
            c["peso_perfil"]     = st.number_input("Peso — Exceso sobre Perfil",    0, 10, int(c["peso_perfil"]),     key="p3")
            c["peso_frecuencia"] = st.number_input("Peso — Frecuencia Alta",        0, 10, int(c["peso_frecuencia"]), key="p4")
            c["peso_smurfing"]   = st.number_input("Peso — Smurfing",               0, 10, int(c["peso_smurfing"]),   key="p5")
            c["peso_pico"]       = st.number_input("Peso — Pico Anómalo",           0, 10, int(c["peso_pico"]),       key="p6")

        with col_p2:
            score_max_teorico = (
                c["peso_absoluto"] + c["peso_acumulado"] + c["peso_perfil"] +
                c["peso_frecuencia"] + c["peso_smurfing"] + c["peso_pico"]
            )
            st.markdown("**Distribución visual de pesos**")
            st.markdown(f"""
            <div class="metric-card red">
                <div class="metric-number">{score_max_teorico}</div>
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
            ax_p.set_xlabel("Puntos al Score", color='#8b949e')
            ax_p.invert_yaxis()
            plt.tight_layout()
            st.pyplot(fig_p)
            plt.close()

            st.markdown(f"""
            <div class="warning-box" style="margin-top:12px;">
                <strong>⚠️ Recuerda:</strong> Si cambias los pesos, ajusta también los umbrales de
                clasificación en <em>Clasificación de Riesgo</em> para que Crítico/Alto/Medio
                sigan siendo proporcionales al nuevo score máximo de <strong>{score_max_teorico} pts</strong>.
            </div>""", unsafe_allow_html=True)

    # ── TAB 3: Clasificación de Riesgo ─────────────────────────────────
    with tab3:
        st.markdown("""
        <div class="info-box">
            <strong>CLASIFICACIÓN DE RIESGO</strong> — Calibración de niveles de alerta.
            Determine los umbrales de score y volumen para la segmentación del universo transaccional.
            Los cambios afectan la distribución táctica de recursos de investigación.
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#171c23; border:1px solid #534434; border-radius:0px; padding:20px; margin-bottom:16px;">
            <div style="color:#f59e0b; font-size:11px; text-transform:uppercase; letter-spacing:2px; font-family:IBM Plex Mono,monospace; margin-bottom:12px;">
                <span class="pulse-dot"></span> LÓGICA DE SEGMENTACIÓN
            </div>
            <div style="font-size:12px; color:#a08e7a; line-height:2;">
                <span style='color:#ef4444; font-weight:700;'>NIVEL CRÍTICO</span> — Clientes en zona de reporte regulatorio inmediato.<br>
                <span style='color:#f97316; font-weight:700;'>NIVEL ALTO</span> — Objetivos de debida diligencia ampliada (EDD).<br>
                <span style='color:#eab308; font-weight:700;'>NIVEL MEDIO</span> — Monitoreo preventivo y actualización de perfil.<br>
                <span style='color:#10b981; font-weight:700;'>NIVEL BAJO</span> — Actividad dentro de parámetros normales establecidos.
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
                <strong>Nivel Bajo</strong> — Se asigna automáticamente a todo cliente cuyo score
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
                <div style="background:#1b2027; border-left:8px solid {color_e}; border-radius:0px; padding:16px; margin-bottom:12px; border-bottom: 1px solid rgba(83, 68, 52, 0.1);">
                    <div style="color:{color_e}; font-weight:700; font-size:14px; text-transform:uppercase; letter-spacing:1px;">{nivel_e}</div>
                    <div style="color:#dee2ed; font-size:12px; margin-top:6px; font-family:IBM Plex Mono,monospace;">
                        CRITERIO: {cond_e}
                    </div>
                    <div style="color:#a08e7a; font-size:11px; margin-top:4px;">
                        PROTOCOLO DE ACCIÓN: {accion_e}
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
                        <div style="color:#c9d1d9; font-size:13px;">{nombre_r}</div>
                        <div style="color:#6e7681; font-size:11px; font-family:IBM Plex Mono,monospace;">{detalle_r}</div>
                    </div>
                    <div style="color:{estado_color}; font-size:10px; font-weight:700;
                                font-family:IBM Plex Mono,monospace; border:1px solid {estado_color};
                                padding:2px 8px; border-radius:0px;">{estado_txt}</div>
                </div>""", unsafe_allow_html=True)

        with col_res2:
            st.markdown("**Pesos y Clasificación**")
            st.markdown(f"""
            <div style="background:#171c23; border:1px solid #21262d; border-radius:0px; padding:16px;">
                <div style="font-family:IBM Plex Mono,monospace; font-size:12px; color:#8b949e; line-height:2;">
                    <hr style='border-color:#21262d; margin:8px 0;'>
                    <div style='color:#f0f6fc; font-weight:700; margin-bottom:5px;'>Ponderación de Pilares:</div>
                    S_T (Transaccional) → <span style='color:#3b82f6;'>{c['w_st']:.2f}</span><br>
                    S_C (Contextual) → <span style='color:#3b82f6;'>{c['w_sc']:.2f}</span><br>
                    S_B (Conductual) → <span style='color:#3b82f6;'>{c['w_sb']:.2f}</span><br>
                    S_N (Red) → <span style='color:#3b82f6;'>{c['w_sn']:.2f}</span>
                    <hr style='border-color:#21262d; margin:8px 0;'>
                    Score máx. teórico → <span style='color:#ef4444; font-weight:700;'>
                        {c['peso_absoluto']+c['peso_acumulado']+c['peso_perfil']+c['peso_frecuencia']+c['peso_smurfing']+c['peso_pico']} pts
                    </span><br><br>
                    Crítico: score ≥ <span style='color:#ef4444;'>{c['score_critico']}</span>
                        o total &gt; <span style='color:#ef4444;'>Q{c['monto_critico']:,}</span><br>
                    Alto: score ≥ <span style='color:#f97316;'>{c['score_alto']}</span><br>
                    Medio: score ≥ <span style='color:#eab308;'>{c['score_medio']}</span><br>
                    Bajo: score &lt; <span style='color:#22c55e;'>{c['score_medio']}</span>
                </div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 2])

    with col_btn1:
        if st.button("Aplicar Configuración", type="primary", use_container_width=True):
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
                st.success("Configuración aplicada. Vuelve a subir el archivo para reprocesar con los nuevos parámetros.")
                st.balloons()

    with col_btn2:
        if st.button("Restablecer a valores base", use_container_width=True):
            st.session_state["aml_config"] = _DEFAULTS.copy()
            st.success("Valores restaurados a los defaults.")
            st.rerun()

    with col_btn3:
        import json as _json_export
        cfg_export = _json_export.dumps(st.session_state["aml_config"], indent=2, ensure_ascii=False)
        st.download_button(
            "Exportar Configuración (JSON)",
            data=cfg_export,
            file_name="aml_config.json",
            mime="application/json",
            use_container_width=True
        )

    # ── POLÍTICA DE RETENCIÓN DE DATOS (Art. 34 Ley 6593) ─────────────────────
    st.markdown("---")
    st.markdown("### 🗄️ Política de Retención de Datos")
    st.markdown(
        "**Art. 34 Ley 6593:** Los sujetos obligados deben conservar todos los registros y documentos "
        "por un mínimo de **5 años** desde la fecha de la transacción o finalización de la relación comercial."
    )

    RETENCION_MINIMA_ANOS = 5  # Art. 34 — no modificable por el usuario

    col_ret1, col_ret2 = st.columns(2)
    with col_ret1:
        st.metric("Retención mínima obligatoria", f"{RETENCION_MINIMA_ANOS} años",
                  help="Art. 34 Ley 6593 — no configurable")
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
