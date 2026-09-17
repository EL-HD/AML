import streamlit as st
from frontend.ui_safe import h
st.set_page_config(
    page_title="SOVEREIGN AML | Intelligence Platform",
    layout="wide",
    page_icon="🔍",
    initial_sidebar_state="collapsed"
)
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import plotly.graph_objects as go
import streamlit.components.v1 as components
import requests
import base64
import re
import io
import uuid
import os
from datetime import date, datetime, timedelta


# --- Importaciones Modulares ---
from backend.procesador import validar_columnas, procesar_transacciones
from backend import auditoria, config_aml, crud, schemas, session_token
from backend.database import SessionLocal
from sqlalchemy.exc import SQLAlchemyError
import logging
from frontend import (
    mod_resumen, mod_alertas, mod_transacciones,
    mod_cliente, mod_matrices, mod_manual,
    mod_configuracion, mod_reportes, mod_ubicaciones,
    mod_mitigacion, mod_red_transaccional,
    mod_imperator_diagnostics, mod_sesion, mod_riesgo_ldft
)
from frontend.mod_sesion import _registrar_acceso_auditoria
from frontend import cache_analisis, exportacion, theme, ui_components

def _auditar(modulo: str, accion: str = "VISUALIZACION") -> None:
    """Registra acceso de sesión activa: Art. 19 Ley 6593."""
    ud = st.session_state.get("user_data") or {}
    usuario    = ud.get("user", "desconocido")
    licenciaid = ud.get("licence_id")
    _registrar_acceso_auditoria(usuario, licenciaid, modulo, accion)

# ============================================================
# SISTEMA DE AUTENTICACIÓN Y LICENCIAS
# ============================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "last_activity_at" not in st.session_state:
    st.session_state.last_activity_at = datetime.now()

SESSION_TIMEOUT_MINUTES = 30
SESSION_TIMEOUT_SECONDS = SESSION_TIMEOUT_MINUTES * 60
SESSION_TIMEOUT_QUERY_PARAM = "session_expired"
SESSION_RESTORE_QUERY_PARAM = "restore_session"
SESSION_RESTORE_PAYLOAD_PARAM = "restore_payload"
SESSION_STORAGE_KEY = "sovereign_aml_session"
ANALYSIS_CACHE_QUERY_PARAM = "analysis_cache"


def _licence_id_actual():
    user_data = st.session_state.get("user_data") or {}
    return user_data.get("licence_id") if isinstance(user_data, dict) else None


if "analysis_cache_id" not in st.session_state:
    st.session_state.analysis_cache_id = cache_analisis.uuid_seguro(
        st.query_params.get(ANALYSIS_CACHE_QUERY_PARAM)
    ) or str(uuid.uuid4())
elif st.query_params.get(ANALYSIS_CACHE_QUERY_PARAM):
    st.session_state.analysis_cache_id = cache_analisis.uuid_seguro(
        st.query_params.get(ANALYSIS_CACHE_QUERY_PARAM)
    ) or st.session_state.analysis_cache_id


def save_analysis_cache():
    if "data_raw" not in st.session_state or "aml_config" not in st.session_state:
        return
    bytes_saml = mod_sesion.exportar_sesion(
        st.session_state["data_raw"],
        st.session_state["aml_config"],
        st.session_state.get("archivo_nombre", "analisis")
    )
    cache_analisis.guardar(_licence_id_actual(), st.session_state.get("analysis_cache_id"), bytes_saml)


def restore_analysis_cache():
    if "data" in st.session_state:
        return False
    contenido = cache_analisis.cargar(_licence_id_actual(), st.session_state.get("analysis_cache_id"))
    if contenido is None:
        return False
    try:
        df_raw, cfg_restaurado, session_meta = mod_sesion.importar_sesion(io.BytesIO(contenido))
    except ValueError as exc:
        clear_analysis_cache()
        st.warning(f"No se pudo restaurar el análisis temporal: {exc}")
        return False

    st.session_state["aml_config"] = cfg_restaurado
    es_valido, faltantes = validar_columnas(df_raw)
    if not es_valido:
        clear_analysis_cache()
        st.warning(f"No se pudo restaurar el análisis temporal. Faltan columnas: {', '.join(faltantes)}")
        return False

    df, casos, matriz_alertas, pep_cpe_info = procesar_transacciones(df_raw, cfg_restaurado)
    st.session_state["data"] = (df, casos, matriz_alertas)
    st.session_state["data_raw"] = df_raw
    st.session_state["pep_cpe_info"] = pep_cpe_info
    st.session_state["archivo_nombre"] = session_meta.get("nombre_archivo", "analisis.xlsx")
    st.session_state["session_meta"] = session_meta
    st.session_state["from_cache"] = True
    return True


def clear_analysis_cache():
    cache_analisis.eliminar(_licence_id_actual(), st.session_state.get("analysis_cache_id"))


def _usuario_a_dict(usuario) -> dict:
    """Serializa una Licencia ORM con la misma forma que devuelve la API de autenticación."""
    return schemas.Licencia.model_validate(usuario).model_dump(mode="json")


def _restaurar_desde_token(token: str):
    """
    Restaura la sesión únicamente si el token está firmado, vigente y su session_id
    sigue siendo la sesión más reciente de la licencia (control de sesión única).
    Devuelve (user_data, session_id) o (None, None).
    """
    datos = session_token.verificar_restauracion(token)
    if not datos:
        return None, None
    db = SessionLocal()
    try:
        usuario = crud.sesion_vigente(db, datos["sid"])
        if usuario is None or str(usuario.licence_id) != datos["lid"]:
            return None, None
        if usuario.fecha_expiracion < date.today():
            return None, None
        return _usuario_a_dict(usuario), datos["sid"]
    except SQLAlchemyError:
        logging.getLogger(__name__).exception("No se pudo validar la sesión restaurada en la base de datos.")
        return None, None
    finally:
        db.close()


def _logout_session(timed_out=False):
    clear_analysis_cache()
    st.session_state.authenticated = False
    st.session_state.user_data = None
    st.session_state.access_token = None
    st.session_state.session_id = None
    st.session_state.last_activity_at = datetime.now()
    for key in ["data", "data_raw", "aml_config", "archivo_nombre",
                "pep_cpe_info", "session_meta", "from_cache",
                "analysis_cache_id"]:
        st.session_state.pop(key, None)
    if timed_out:
        st.session_state.session_timeout_alert = True


cache_analisis.limpiar_expirados()


if st.query_params.get(SESSION_TIMEOUT_QUERY_PARAM) == "1":
    _logout_session(timed_out=True)
    del st.query_params[SESSION_TIMEOUT_QUERY_PARAM]


if st.query_params.get(SESSION_RESTORE_QUERY_PARAM) == "1":
    restored_user, restored_sid = _restaurar_desde_token(
        str(st.query_params.get(SESSION_RESTORE_PAYLOAD_PARAM, ""))
    )
    if restored_user:
        st.session_state.authenticated = True
        st.session_state.user_data = restored_user
        st.session_state.access_token = None
        st.session_state.session_id = restored_sid
        st.session_state.last_activity_at = datetime.now()
    else:
        st.session_state.clear_browser_session = True
    for param in (SESSION_RESTORE_QUERY_PARAM, SESSION_RESTORE_PAYLOAD_PARAM):
        if param in st.query_params:
            del st.query_params[param]
    st.rerun()


if st.session_state.authenticated:
    now = datetime.now()
    inactive_for = now - st.session_state.get("last_activity_at", now)
    if inactive_for > timedelta(seconds=SESSION_TIMEOUT_SECONDS):
        _auditar("Sesión", "LOGOUT_INACTIVIDAD")
        _logout_session(timed_out=True)
        st.rerun()
    st.session_state.last_activity_at = now


def session_timeout_guard():
    user_data = st.session_state.get("user_data") or {}
    session_payload = session_token.firmar_restauracion(
        user_data.get("licence_id"), st.session_state.get("session_id")
    ) or ""
    analysis_cache_id = st.session_state.get("analysis_cache_id", "")
    components.html(f"""
    <script>
    (() => {{
        const TIMEOUT_MS = {SESSION_TIMEOUT_SECONDS * 1000};
        const PARAM = "{SESSION_TIMEOUT_QUERY_PARAM}";
        const STORAGE_KEY = "{SESSION_STORAGE_KEY}";
        const SESSION_PAYLOAD = "{session_payload}";
        const ANALYSIS_PARAM = "{ANALYSIS_CACHE_QUERY_PARAM}";
        const ANALYSIS_CACHE_ID = "{analysis_cache_id}";
        let timer = null;

        function expireSession() {{
            window.parent.localStorage.removeItem(STORAGE_KEY);
            const url = new URL(window.parent.location.href);
            url.searchParams.set(PARAM, "1");
            window.parent.location.replace(url.toString());
        }}

        function persistSession() {{
            if (!SESSION_PAYLOAD) {{
                window.parent.localStorage.removeItem(STORAGE_KEY);
                return;
            }}
            window.parent.localStorage.setItem(STORAGE_KEY, JSON.stringify({{
                payload: SESSION_PAYLOAD,
                analysisCacheId: ANALYSIS_CACHE_ID,
                expiresAt: Date.now() + TIMEOUT_MS
            }}));
        }}

        function resetTimer() {{
            if (timer) window.clearTimeout(timer);
            persistSession();
            timer = window.setTimeout(expireSession, TIMEOUT_MS);
        }}

        const events = ["click", "mousemove", "mousedown", "keydown", "scroll", "touchstart"];
        events.forEach((eventName) => {{
            window.parent.document.addEventListener(eventName, resetTimer, true);
        }});
        const url = new URL(window.parent.location.href);
        if (ANALYSIS_CACHE_ID && url.searchParams.get(ANALYSIS_PARAM) !== ANALYSIS_CACHE_ID) {{
            url.searchParams.set(ANALYSIS_PARAM, ANALYSIS_CACHE_ID);
            window.parent.history.replaceState(null, "", url.toString());
        }}
        resetTimer();
    }})();
    </script>
    """, height=0, width=0)


def session_restore_probe():
    components.html(f"""
    <script>
    (() => {{
        const STORAGE_KEY = "{SESSION_STORAGE_KEY}";
        const RESTORE_PARAM = "{SESSION_RESTORE_QUERY_PARAM}";
        const PAYLOAD_PARAM = "{SESSION_RESTORE_PAYLOAD_PARAM}";
        const EXPIRED_PARAM = "{SESSION_TIMEOUT_QUERY_PARAM}";
        const ANALYSIS_PARAM = "{ANALYSIS_CACHE_QUERY_PARAM}";

        try {{
            const raw = window.parent.localStorage.getItem(STORAGE_KEY);
            if (!raw) return;

            const saved = JSON.parse(raw);
            const expired = !saved || !saved.payload || !saved.expiresAt || Number(saved.expiresAt) <= Date.now();
            if (expired) {{
                window.parent.localStorage.removeItem(STORAGE_KEY);
                return;
            }}

            const url = new URL(window.parent.location.href);
            if (url.searchParams.get(RESTORE_PARAM) === "1") return;
            url.searchParams.delete(EXPIRED_PARAM);
            url.searchParams.set(RESTORE_PARAM, "1");
            url.searchParams.set(PAYLOAD_PARAM, saved.payload);
            if (saved.analysisCacheId) {{
                url.searchParams.set(ANALYSIS_PARAM, saved.analysisCacheId);
            }}
            window.parent.location.replace(url.toString());
        }} catch (err) {{
            window.parent.localStorage.removeItem(STORAGE_KEY);
        }}
    }})();
    </script>
    """, height=0, width=0)


def clear_browser_session():
    components.html(f"""
    <script>
    window.parent.localStorage.removeItem("{SESSION_STORAGE_KEY}");
    </script>
    """, height=0, width=0)

def _cabeceras_origen() -> dict:
    """Propaga la IP real del navegador a la API (X-Forwarded-For) para el límite de intentos."""
    try:
        cabeceras = st.context.headers
    except (AttributeError, RuntimeError):
        return {}
    origen = cabeceras.get("X-Forwarded-For") or cabeceras.get("x-forwarded-for")
    return {"X-Forwarded-For": origen} if origen else {}


def _procesar_login(user: str, pwd: str) -> None:
    """Llama a la API de autenticación y muestra mensajes accionables por tipo de fallo."""
    if not user or not pwd:
        st.error("Ingrese usuario y contraseña.")
        return
    api_url = os.getenv("AUTH_API_URL", "http://localhost:8000")
    try:
        response = requests.post(
            f"{api_url}/auth/validate",
            json={"username": user, "password": pwd},
            headers=_cabeceras_origen(),
            timeout=10,
        )
    except requests.Timeout:
        st.error("El servidor de autenticación tardó demasiado en responder. Intente nuevamente en unos segundos.")
        return
    except requests.RequestException:
        st.error("No se pudo conectar con el servidor de autenticación. Verifique el servicio o contacte al administrador.")
        return

    if response.status_code == 429:
        detalle = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else None
        st.error(detalle or "Demasiados intentos. Espere unos minutos antes de volver a intentar.")
        return
    if response.status_code != 200:
        st.error(f"El servidor de autenticación devolvió un error (HTTP {response.status_code}). Contacte al administrador.")
        return
    try:
        data = response.json()
    except ValueError:
        st.error("Respuesta inválida del servidor de autenticación.")
        return
    if not (data.get("exists") and data.get("is_active") and data.get("licencia")):
        st.error(data.get("message", "Acceso denegado."))
        return
    st.session_state.authenticated = True
    st.session_state.user_data = data.get("licencia")
    st.session_state.access_token = data.get("access_token")
    st.session_state.session_id = data.get("session_id")
    st.session_state.last_activity_at = datetime.now()
    st.rerun()


def login_flow():
    theme.cargar_estilos("styles.css", "login.css")

    # --- Interfaz de Login ---
    _, col, _ = st.columns([1.5, 1.2, 1.5])
    
    with col:
        should_clear_browser_session = st.session_state.pop("clear_browser_session", False)
        timeout_alert = st.session_state.pop("session_timeout_alert", False)
        if should_clear_browser_session or timeout_alert:
            clear_browser_session()

        if timeout_alert:
            st.toast("Sesión cerrada por inactividad.")
            st.warning("Sesión cerrada por inactividad. Inicie sesión nuevamente.")

        st.markdown("""
            <div class="brand-title">SOVEREIGN <span>AML</span></div>
            <div class="brand-subtitle">
                ANALYTICAL INTELLIGENCE PLATFORM
            </div>
        """, unsafe_allow_html=True)
        
        import base64
        import os
        logo_b64 = ""
        logo_path = os.path.join(os.path.dirname(__file__), "Logo AML.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
                
        with st.form("login_form", clear_on_submit=False):
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 2rem;">
                    <img src="data:image/png;base64,{h(logo_b64)}" 
                         style="height: 6rem; margin-bottom: 1.5rem; filter: drop-shadow(0 0 15px rgba(245, 158, 11, 0.3));">
                    <div style="color: white; font-size: 1.5rem; font-weight: 600;">Acceso al Sistema</div>
                    <div style="color: #8b949e; font-size: 0.7rem; letter-spacing: 0.15em; text-transform: uppercase;">SISTEMA IMPERATOR ENGINE</div>
                </div>
            """, unsafe_allow_html=True)


            st.markdown('<div class="login-label">Nombre de Usuario</div>', unsafe_allow_html=True)
            user = st.text_input("USUARIO", placeholder="UserName", key="login_user")
            
            st.markdown('<div class="login-label">Contraseña</div>', unsafe_allow_html=True)
            pwd = st.text_input("CONTRASEÑA", type="password", placeholder="••••••••", key="login_pwd")
            
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("INICIAR SESIÓN →", use_container_width=True)
            
            if submit:
                _procesar_login(user, pwd)
            
            st.markdown("""
                <div class="login-help">
                    Si olvidó su contraseña o su licencia expiró, contacte al administrador del sistema.
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("""
            <div class="footer-notice">
                <div class="security-badge">
                    ACCESO RESTRINGIDO - NIVEL 4 CID
                </div>
                <div>EL ACCESO NO AUTORIZADO A ESTE SISTEMA DE INTELIGENCIA ESTÁ ESTRICTAMENTE PROHIBIDO POR LA NORMATIVA SOVEREIGN-V3.</div>
            </div>
        """, unsafe_allow_html=True)

    st.stop()

if not st.session_state.authenticated:
    can_restore_session = not (
        st.session_state.get("clear_browser_session") or
        st.session_state.get("session_timeout_alert")
    )
    if can_restore_session:
        session_restore_probe()
    login_flow()

session_timeout_guard()

# ============================================================
# TEMA Y CONFIGURACIÓN VISUAL
# ============================================================

# --- Sidebar: Info de Licencia y Logout ---
with st.sidebar:
    st.markdown("---")
    if st.session_state.authenticated and st.session_state.user_data:
        lic = st.session_state.user_data
        st.markdown(f"""
        <div class='sidebar-card sidebar-license'>
            <div class='sidebar-label'>Licencia Activa</div>
            <div class='sidebar-primary'>{h(lic['name'])}</div>
            <div class='sidebar-accent'>{h(lic['mail'])}</div>
            <div class='sidebar-label sidebar-spaced'>Empresa</div>
            <div class='sidebar-value'>{h(lic['empresa'])}</div>
            <div class='sidebar-label sidebar-spaced'>Expira</div>
            <div class='sidebar-value'>{h(lic['fecha_expiracion'])}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("CERRAR SESIÓN", use_container_width=True):
            _auditar("Sesión", auditoria.LOGOUT)
            _logout_session()
            st.session_state.clear_browser_session = True
            st.rerun()
    st.markdown("---")

# Sistema de diseño (frontend/theme): tokens + styles.css, cargado una sola vez
theme.cargar_estilos()

# ============================================================
# HEADER SOVEREIGN
# ============================================================
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 2px solid #30353d; padding-bottom: 15px;">
    <div>
        <h1 style="margin: 0; font-size: 32px; letter-spacing: -1px; font-weight: 300;">SOVEREIGN <span style="font-weight: 800; color: #f59e0b;">AML</span></h1>
        <p style="margin: 0; color: #d8c3ad; font-family: 'IBM Plex Mono', monospace; font-size: 12px; letter-spacing: 2px; text-transform: uppercase;">
            <span class="pulse-dot"></span> ANALYTICAL INTELLIGENCE PLATFORM
        </p>
    </div>
    <div style="text-align: right;">
        <div style="color: #f59e0b; font-family: 'IBM Plex Mono', monospace; font-size: 10px; font-weight: 700; letter-spacing: 1px; display:flex; align-items:center; justify-content:flex-end; gap:8px;">
            <span style="width:10px; height:10px; border-radius:50%; background:radial-gradient(circle at 35% 35%, #86efac 0%, #22c55e 45%, #15803d 100%); box-shadow:0 0 0 3px rgba(34,197,94,0.15), 0 0 14px rgba(34,197,94,0.55); display:inline-block;"></span>
            <span>IMPERATOR ENGINE ACTIVE</span>
        </div>
        <div style="color: #d8c3ad; font-family: 'IBM Plex Mono', monospace; font-size: 10px;">CORE VERSION v3.0.0</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("<div class='sidebar-brand'>SOVEREIGN AML</div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-brand-subtitle'>Powered by IMPERATOR Intelligence</div>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("<div class='sidebar-section-label'>AML Intelligence</div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-section-title'>Motor de Cumplimiento</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='sidebar-card'>
        <div class='sidebar-card-title'>Monitoreo AML centralizado</div>
        <div class='sidebar-body'>
            Plataforma para analizar transacciones, priorizar alertas, perfilar clientes y documentar hallazgos de riesgo en un solo flujo operativo.
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("<div class='sidebar-section-label'>Parámetros Activos</div>", unsafe_allow_html=True)
    
    cfg = st.session_state.get("aml_config", None)
    if cfg:
        reglas_activas = sum([
            int(cfg.get("regla_absoluto", False)),
            int(cfg.get("regla_acumulado", False)),
            int(cfg.get("regla_perfil", False)),
            int(cfg.get("regla_frecuencia", False)),
            int(cfg.get("regla_smurfing", False)),
            int(cfg.get("regla_pico", False)),
            int(cfg.get("regla_ubicacion", False)),
        ])
        st.markdown(f"""
        <div class='sidebar-card'>
            <div class='sidebar-params'>
                Reglas activas: {h(reglas_activas)}/7<br>
                Crítico ≥ score {h(cfg['score_critico'])}<br>
                Alto ≥ score {h(cfg['score_alto'])}<br>
                Medio ≥ score {h(cfg['score_medio'])}<br>
                Umbral base: Q{h(format(cfg['umbral_absoluto'], ','))}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class='sidebar-card'>
            <div class='sidebar-params' style='color:#f59e0b;'>
                Usando valores por defecto.<br>Ir a Configuración para personalizar.
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<div class='sidebar-section-label'>Navegación</div>", unsafe_allow_html=True)
    
    if "nav_view" not in st.session_state:
        st.session_state.nav_view = "Resumen Ejecutivo"

    def set_nav():
        if st.session_state.radio_main is not None:
            st.session_state.nav_view = st.session_state.radio_main

    main_ops = [
        "Resumen Ejecutivo",
        "Casos de Alerta",
        "Transacciones",
        "Análisis por Cliente",
        "Matrices de Riesgo",
        "Red Transaccional",
        "Acciones de Mitigación",
        "Imperator Diagnostics",
        "Gestión de Ubicaciones",
        "Riesgo Institucional LD/FT",
        "Informes y Reportes",
        "Configuración",
        "Manual de Usuario"
    ]

    if st.session_state.nav_view == "IMPERATOR Diagnostics":
        st.session_state.nav_view = "Imperator Diagnostics"

    m_idx = main_ops.index(st.session_state.nav_view) if st.session_state.nav_view in main_ops else 0
    st.radio("Vistas Analíticas", main_ops, key="radio_main", index=m_idx, on_change=set_nav, label_visibility="collapsed")
    
    st.markdown("---")

    # ── Exportar sesión ────────────────────────────────────────────
    if "data_raw" in st.session_state and "data" in st.session_state:
        nombre_saml = mod_sesion.nombre_archivo_saml(
            st.session_state.get("archivo_nombre", "analisis")
        )
        bytes_saml = mod_sesion.exportar_sesion(
            st.session_state["data_raw"],
            st.session_state["aml_config"],
            st.session_state.get("archivo_nombre", "analisis")
        )
        exportacion.boton_descarga(
            label="Exportar sesión (.saml)",
            data=bytes_saml,
            file_name=nombre_saml,
            mime="application/octet-stream",
            use_container_width=True,
            help="Descarga el análisis completo con datos y configuración para retomarlo después.",
            modulo="Sesión",
        )
        st.markdown("""
        <div style='font-size:12.5px; color:#8b949e; font-family:IBM Plex Mono,monospace;
                    margin-top:8px; line-height:1.5; text-align:center;'>
            Incluye transacciones + configuración usada.
        </div>""", unsafe_allow_html=True)
        st.markdown("---")

    st.markdown("""
    <div class='sidebar-footer'>
        v3.0 · Sovereign AML Intelligence
    </div>
    <div style="margin-top:8px; line-height:1.5;">
        <span style="font-size:12.5px; font-weight:700; color:#d8c3ad; letter-spacing:0.2px;">
            Ing. Hobéd Díaz
        </span><br>
        <span style="font-size:12.5px; font-weight:600; color:#a08e7a; text-transform:uppercase; letter-spacing:1.1px;">
            Magíster Artium
        </span><br>
        <span style="font-size:12.5px; font-weight:700; color:#f59e0b;">M.A.F.I.</span>
        <span style="font-size:12.5px; font-weight:400; color:#8b949e;"> · Análisis Forense Informático</span>
    </div>
    """, unsafe_allow_html=True)

vista = st.session_state.nav_view

# ============================================================
# CONFIGURACIÓN (Defaults)
# ============================================================
_DEFAULTS = config_aml.config_por_defecto()
if "aml_config" not in st.session_state:
    st.session_state["aml_config"] = _DEFAULTS.copy()
else:
    for k, v in _DEFAULTS.items():
        st.session_state["aml_config"].setdefault(k, v)

if st.session_state.authenticated:
    restore_analysis_cache()
    if "data_raw" in st.session_state and "data" in st.session_state:
        save_analysis_cache()

# ============================================================
# CARGA DE ARCHIVO
# ============================================================
if vista not in ["Configuración", "Manual de Usuario", "Gestión de Ubicaciones", "Red Transaccional", "Acciones de Mitigación", "Imperator Diagnostics", "Riesgo Institucional LD/FT"]:
    data_ready = "data" in st.session_state

    if not data_ready or "archivo_nombre" not in st.session_state:
        # ── Banner de bienvenida ─────────────────────────────────────
        user_data = st.session_state.get("user_data", {})
        user_name = user_data.get("name", "Usuario") if isinstance(user_data, dict) else "Usuario"

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="welcome-panel">
            <div class="welcome-kicker">Centro de análisis</div>
            <div class="welcome-rule"></div>
            <div class="welcome-title">Bienvenido, <span style='color:#ffffff;'>{h(user_name)}</span>.</div>
            <div class="welcome-copy">
                Es un gusto tenerle de vuelta. Inicie un nuevo análisis o restaure una sesión guardada
                para continuar monitoreando transacciones, alertas y perfiles de riesgo desde un solo espacio.
            </div>
        </div>
        """, unsafe_allow_html=True)

        tab_nuevo, tab_sesion = st.tabs(["Nuevo análisis", "Cargar sesión guardada"])

        # ── Tab 1: Nuevo análisis (Excel) ────────────────────────────
        with tab_nuevo:
            st.markdown("""
            <div class="upload-requirements">
                <span style='color:#f0f6fc; font-weight:600;'>Formato:</span> Excel (.xlsx) &nbsp;·&nbsp;
                <span style='color:#f0f6fc; font-weight:600;'>Columnas requeridas:</span>
                <span style='color:#7cc7ff;'>Fecha · Cliente · EsPEP · EsCPE · Monto · Perfil · Ubicacion · UbicacionRiesgo · TipoOperacion · Cliente_Destino</span>
            </div>
            """, unsafe_allow_html=True)

            archivo = st.file_uploader("Subir archivo Excel", type=["xlsx"], label_visibility="collapsed")

            if archivo:
                with st.spinner("Procesando inteligencia AML..."):
                    try:
                        df_raw = pd.read_excel(archivo, nrows=mod_sesion.MAX_FILAS + 1)
                    except ValueError as exc:
                        st.error(f"No se pudo leer el archivo Excel: {exc}")
                        st.stop()
                    if len(df_raw) > mod_sesion.MAX_FILAS:
                        st.error(f"El archivo supera el máximo de {mod_sesion.MAX_FILAS:,} filas permitidas por análisis.")
                        st.stop()
                    es_valido, faltantes = validar_columnas(df_raw)
                    if not es_valido:
                        st.error(f"Faltan columnas: {', '.join(faltantes)}")
                        st.stop()
                    df, casos, matriz_alertas, pep_cpe_info = procesar_transacciones(df_raw, st.session_state["aml_config"])
                    st.session_state["data"]         = (df, casos, matriz_alertas)
                    st.session_state["data_raw"]     = df_raw
                    st.session_state["pep_cpe_info"] = pep_cpe_info
                    st.session_state["archivo_nombre"] = archivo.name
                    _auditar("Carga de datos", f"{auditoria.IMPORTACION}:XLSX")
                    save_analysis_cache()
                    st.rerun()
            else:
                st.markdown("""
                <p class="upload-help">
                    Suba su archivo Excel (.xlsx) con los datos de transacciones.<br>
                    El motor AML procesará automáticamente las reglas de detección.
                </p>""", unsafe_allow_html=True)

        # ── Tab 2: Cargar sesión .saml ───────────────────────────────
        with tab_sesion:
            st.markdown("""
            <div style="background:#171c23; border-left:3px solid #f59e0b; padding:16px;
                        font-size:14px; color:#a08e7a; margin-bottom:18px; font-family:'IBM Plex Mono',monospace;">
                <strong style='color:#f0f6fc;'>Formato .saml</strong>: Sovereign AML Session File.<br>
                Contiene las transacciones originales y la configuración usada en el análisis previo.
                Al cargarlo, el motor reprocesa todo automáticamente restaurando el estado completo.
            </div>
            """, unsafe_allow_html=True)

            archivo_saml = st.file_uploader("Subir archivo .saml", type=["saml"], label_visibility="collapsed")

            if archivo_saml:
                try:
                    with st.spinner("Restaurando sesión de análisis..."):
                        df_raw, cfg_restaurado, session_meta = mod_sesion.importar_sesion(archivo_saml)

                        # Configuración ya validada contra AmlConfig (lista blanca y rangos)
                        st.session_state["aml_config"] = cfg_restaurado

                        es_valido, faltantes = validar_columnas(df_raw)
                        if not es_valido:
                            st.error(f"El archivo .saml contiene datos incompletos. Faltan: {', '.join(faltantes)}")
                            st.stop()

                        df, casos, matriz_alertas, pep_cpe_info = procesar_transacciones(df_raw, cfg_restaurado)
                        st.session_state["data"]            = (df, casos, matriz_alertas)
                        st.session_state["data_raw"]        = df_raw
                        st.session_state["pep_cpe_info"]    = pep_cpe_info
                        st.session_state["archivo_nombre"]  = session_meta.get("nombre_archivo", archivo_saml.name)
                        st.session_state["session_meta"]    = session_meta
                        st.session_state["from_saml"]       = True
                        _auditar("Carga de datos", f"{auditoria.IMPORTACION}:SAML")
                        save_analysis_cache()

                    st.rerun()

                except ValueError as e:
                    st.error(f"Error al cargar la sesión: {e}")
            else:
                st.markdown("""
                <p style='color:#8b949e; font-size:14px; text-align:center;
                          font-family:"IBM Plex Mono",monospace; margin-top:24px;'>
                    Suba un archivo <strong style='color:#f59e0b;'>.saml</strong> generado
                    previamente desde Sovereign AML para retomar el análisis.
                </p>""", unsafe_allow_html=True)

        st.stop()

    else:
        col_inf, col_btn = st.columns([4, 1])
        with col_inf:
            if st.session_state.get("from_cache"):
                st.success(f"Análisis temporal restaurado: '{st.session_state['archivo_nombre']}'.")
            elif st.session_state.get("from_saml"):
                meta = st.session_state.get("session_meta", {})
                exportado = meta.get("exportado_en", "")[:10]
                nombre    = meta.get("nombre_archivo", st.session_state["archivo_nombre"])
                filas     = meta.get("filas", "")
                st.markdown(f"""
                <div style="background:#171c23; border-left:3px solid #f59e0b; padding:12px 16px;
                            font-family:'IBM Plex Mono',monospace; font-size:12px; color:#a08e7a;">
                    <span style="color:#f59e0b; font-weight:700;">SESIÓN RESTAURADA</span>
                    &nbsp;·&nbsp; {h(nombre)}
                    &nbsp;·&nbsp; {h(filas)} registros
                    &nbsp;·&nbsp; Exportada: {h(exportado)}
                </div>""", unsafe_allow_html=True)
            else:
                st.success(f"Archivo '{st.session_state['archivo_nombre']}' cargado y analizado de forma correcta.")
        with col_btn:
            if st.button("Nuevo análisis", use_container_width=True):
                clear_analysis_cache()
                for k in ["data", "data_raw", "archivo_nombre", "pep_cpe_info", "session_meta", "from_saml", "from_cache"]:
                    st.session_state.pop(k, None)
                st.session_state.analysis_cache_id = str(uuid.uuid4())
                st.rerun()
# ============================================================
# ENRUTAMIENTO VISTAS
# ============================================================
data_ready = "data" in st.session_state

if vista == "Resumen Ejecutivo":
    if data_ready:
        pep_cpe_info_s = st.session_state.get("pep_cpe_info", {})
        mod_resumen.mostrar(*st.session_state["data"], pep_cpe_info_s)
    else: st.info("Sube un archivo.")

elif vista == "Casos de Alerta":
    _auditar("Casos de Alerta")
    if data_ready: mod_alertas.mostrar(st.session_state["data"][1])
    else: st.info("Sube un archivo.")

elif vista == "Transacciones":
    if data_ready: mod_transacciones.mostrar(st.session_state["data"][0])
    else: st.info("Sube un archivo.")

elif vista == "Análisis por Cliente":
    _auditar("Análisis por Cliente")
    if data_ready: mod_cliente.mostrar(st.session_state["data"][0], st.session_state["data"][1], st.session_state["aml_config"])
    else: st.info("Sube un archivo.")

elif vista == "Matrices de Riesgo":
    if data_ready: mod_matrices.mostrar(st.session_state["data"][1], st.session_state["data"][2])
    else: st.info("Sube un archivo.")

elif vista == "Red Transaccional":
    if data_ready: mod_red_transaccional.mostrar(st.session_state["data"][0], st.session_state["data"][1])
    else: st.info("Sube un archivo.")

elif vista == "Acciones de Mitigación":
    _auditar("Acciones de Mitigación")
    if data_ready: mod_mitigacion.mostrar(st.session_state["data"][0], st.session_state["data"][1])
    else: st.info("Sube un archivo.")

elif vista == "Imperator Diagnostics":
    if data_ready:
        mod_imperator_diagnostics.mostrar(
            st.session_state["data"][0],
            st.session_state["data"][1],
            st.session_state["aml_config"]
        )
    else: st.info("Sube un archivo para activar el módulo Imperator Diagnostics.")

elif vista == "Gestión de Ubicaciones":
    mod_ubicaciones.mostrar()

elif vista == "Riesgo Institucional LD/FT":
    _auditar("Riesgo Institucional LD/FT")
    mod_riesgo_ldft.mostrar()

elif vista == "Informes y Reportes":
    _auditar("Informes y Reportes")
    if data_ready: mod_reportes.mostrar(*st.session_state["data"], st.session_state["aml_config"])
    else: st.info("Sube un archivo.")

elif vista == "Configuración":
    _auditar("Configuración")
    mod_configuracion.mostrar(_DEFAULTS)

elif vista == "Manual de Usuario":
    mod_manual.mostrar()

# ============================================================
# FOOTER
# ============================================================
st.markdown("""
<div class="footer">
    SOVEREIGN AML Intelligence Platform v3.0 &nbsp;·&nbsp; Sovereign Intelligence Framework
    <div style="margin-top:10px; line-height:1.6;">
        <span style="font-size:12px; font-weight:700; color:#f0f6fc; letter-spacing:0.2px;">
            Diseñado por el Ing. Hobéd Díaz
        </span><br>
        <span style="font-size:12px; font-weight:600; color:#8b949e; text-transform:uppercase; letter-spacing:1.2px;">
            Magíster Artium
        </span>
        &nbsp;·&nbsp;
        <span style="font-size:12px; font-weight:700; color:#f59e0b;">M.A.F.I.</span>
        <span style="font-size:12px; font-weight:400; color:#8b949e;"> Análisis Forense Informático</span>
    </div>
</div>
""", unsafe_allow_html=True)
