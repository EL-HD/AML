import streamlit as st
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
import hashlib
import hmac
import json
import re
import tempfile
import time
import uuid
from pathlib import Path
import os
from datetime import date, datetime, timedelta


# --- Importaciones Modulares ---
from backend.procesador import validar_columnas, procesar_transacciones
from frontend import (
    mod_resumen, mod_alertas, mod_transacciones,
    mod_cliente, mod_matrices, mod_manual,
    mod_configuracion, mod_reportes, mod_ubicaciones,
    mod_mitigacion, mod_red_transaccional,
    mod_imperator_diagnostics, mod_sesion
)
from frontend.mod_sesion import _registrar_acceso_auditoria

def _auditar(modulo: str, accion: str = "VISUALIZACION") -> None:
    """Registra acceso de sesión activa — Art. 19 Ley 6593."""
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
if "last_activity_at" not in st.session_state:
    st.session_state.last_activity_at = datetime.now()

SESSION_TIMEOUT_MINUTES = 30
SESSION_TIMEOUT_SECONDS = SESSION_TIMEOUT_MINUTES * 60
SESSION_TIMEOUT_QUERY_PARAM = "session_expired"
SESSION_RESTORE_QUERY_PARAM = "restore_session"
SESSION_RESTORE_PAYLOAD_PARAM = "restore_payload"
SESSION_STORAGE_KEY = "sovereign_aml_session"
ANALYSIS_CACHE_QUERY_PARAM = "analysis_cache"
ANALYSIS_CACHE_DIR = Path(tempfile.gettempdir()) / "sovereign_aml_cache"
ANALYSIS_CACHE_TTL_SECONDS = SESSION_TIMEOUT_SECONDS


def _safe_cache_id(value):
    value = str(value or "")
    return value if re.fullmatch(r"[a-f0-9-]{36}", value) else None


if "analysis_cache_id" not in st.session_state:
    st.session_state.analysis_cache_id = _safe_cache_id(
        st.query_params.get(ANALYSIS_CACHE_QUERY_PARAM)
    ) or str(uuid.uuid4())
elif st.query_params.get(ANALYSIS_CACHE_QUERY_PARAM):
    st.session_state.analysis_cache_id = _safe_cache_id(
        st.query_params.get(ANALYSIS_CACHE_QUERY_PARAM)
    ) or st.session_state.analysis_cache_id


def _cache_path(cache_id=None):
    cache_id = _safe_cache_id(cache_id or st.session_state.get("analysis_cache_id"))
    if not cache_id:
        return None
    return ANALYSIS_CACHE_DIR / f"{cache_id}.saml"


def _cleanup_analysis_cache():
    ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for path in ANALYSIS_CACHE_DIR.glob("*.saml"):
        try:
            if now - path.stat().st_mtime > ANALYSIS_CACHE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def save_analysis_cache():
    if "data_raw" not in st.session_state or "aml_config" not in st.session_state:
        return
    path = _cache_path()
    if not path:
        return
    ANALYSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    bytes_saml = mod_sesion.exportar_sesion(
        st.session_state["data_raw"],
        st.session_state["aml_config"],
        st.session_state.get("archivo_nombre", "analisis")
    )
    path.write_bytes(bytes_saml)


def restore_analysis_cache():
    if "data" in st.session_state:
        return False
    path = _cache_path()
    if not path or not path.exists():
        return False
    if time.time() - path.stat().st_mtime > ANALYSIS_CACHE_TTL_SECONDS:
        clear_analysis_cache()
        return False

    with path.open("rb") as f:
        df_raw, cfg_restaurado, session_meta = mod_sesion.importar_sesion(f)

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
    path.touch()
    return True


def clear_analysis_cache():
    path = _cache_path()
    if path and path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def _session_sign_key() -> bytes | None:
    """Retorna la clave para firmar payloads de sesión, o None si no está configurada."""
    key = os.getenv("SESSION_SIGN_KEY", "")
    return key.encode() if key else None


def _encode_session_payload(user_data) -> str:
    """Codifica user_data en base64 y le añade firma HMAC-SHA256 (C1 fix)."""
    payload = json.dumps(user_data or {}, ensure_ascii=False).encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii")
    key = _session_sign_key()
    if not key:
        return b64
    sig = hmac.new(key, b64.encode("ascii"), digestmod=hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _decode_session_payload(token: str):
    """Verifica la firma HMAC y decodifica el payload de sesión (C1 fix)."""
    try:
        key = _session_sign_key()
        if key:
            parts = token.rsplit(".", 1)
            if len(parts) != 2:
                return None
            b64, sig = parts
            expected = hmac.new(key, b64.encode("ascii"), digestmod=hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
        else:
            b64 = token
        data = base64.urlsafe_b64decode(b64.encode("ascii"))
        parsed = json.loads(data.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _logout_session(timed_out=False):
    st.session_state.authenticated = False
    st.session_state.user_data = None
    st.session_state.access_token = None
    st.session_state.last_activity_at = datetime.now()
    clear_analysis_cache()
    for key in ["data", "data_raw", "aml_config", "archivo_nombre",
                "pep_cpe_info", "session_meta", "from_cache",
                "analysis_cache_id"]:
        st.session_state.pop(key, None)
    if timed_out:
        st.session_state.session_timeout_alert = True


_cleanup_analysis_cache()


if st.query_params.get(SESSION_TIMEOUT_QUERY_PARAM) == "1":
    _logout_session(timed_out=True)
    del st.query_params[SESSION_TIMEOUT_QUERY_PARAM]


if st.query_params.get(SESSION_RESTORE_QUERY_PARAM) == "1":
    restored_user = _decode_session_payload(st.query_params.get(SESSION_RESTORE_PAYLOAD_PARAM, ""))
    if restored_user:
        st.session_state.authenticated = True
        st.session_state.user_data = restored_user
        st.session_state.access_token = None
        st.session_state.last_activity_at = datetime.now()
    if SESSION_RESTORE_QUERY_PARAM in st.query_params:
        del st.query_params[SESSION_RESTORE_QUERY_PARAM]
    if SESSION_RESTORE_PAYLOAD_PARAM in st.query_params:
        del st.query_params[SESSION_RESTORE_PAYLOAD_PARAM]
    if restored_user:
        st.rerun()


if st.session_state.authenticated:
    now = datetime.now()
    inactive_for = now - st.session_state.get("last_activity_at", now)
    if inactive_for > timedelta(seconds=SESSION_TIMEOUT_SECONDS):
        _logout_session(timed_out=True)
        st.rerun()
    st.session_state.last_activity_at = now


def session_timeout_guard():
    session_payload = _encode_session_payload(st.session_state.get("user_data", {}))
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

def login_flow():
    # --- CSS para Login Premium (Sovereign AML New Design) ---
    st.markdown("""
    <style>
        /* Fondo de la App */
        .stApp { background-color: #0f141b !important; }
        
        /* DESAPARECER SIDEBAR COMPLETAMENTE EN LOGIN */
        [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
            width: 0px !important;
        }
        
        /* Ajustar contenedor principal al centro total */
        [data-testid="stMain"] {
            margin-left: 0px !important;
            width: 100% !important;
        }

        /* Ocultar elementos innecesarios de Streamlit */
        [data-testid="stWidgetLabel"] { display: none; }
        [data-testid="stForm"] {
            background-color: #1a1f26 !important;
            border: none !important;
            border-left: 2px solid #f59e0b !important;
            padding: 3rem !important;
            border-radius: 0px !important;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5) !important;
        }
        
        /* Estilo de los Inputs */
        .stTextInput input {
            background-color: rgba(15, 20, 27, 0.8) !important;
            border: none !important;
            border-bottom: 1px solid #30353d !important;
            color: #ffffff !important;
            border-radius: 0px !important;
            padding: 1rem 1rem !important;
            font-family: 'IBM Plex Mono', monospace !important;
        }
        .stTextInput input:focus {
            border-bottom: 1px solid #f59e0b !important;
            box-shadow: none !important;
        }
        
        /* Botón de Iniciar Sesión */
        div.stButton > button {
            background-color: #f59e0b !important;
            color: #0f141b !important;
            border-radius: 0px !important;
            height: 3.5rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.1em !important;
            text-transform: uppercase !important;
            border: none !important;
            transition: all 0.3s ease !important;
            margin-top: 1rem !important;
        }
        div.stButton > button:hover {
            background-color: #fbbf24 !important;
            color: #0f141b !important;
        }

        .brand-title { 
            color: #ffffff; 
            font-size: 2.5rem; 
            font-weight: 300; 
            letter-spacing: -0.05em; 
            text-align: center;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
        }
        .brand-title span { font-weight: 900; color: #f59e0b; }
        
        .brand-subtitle { 
            color: #8b949e; 
            font-size: 0.6rem; 
            letter-spacing: 0.4em; 
            text-align: center; 
            text-transform: uppercase;
            margin-bottom: 3rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }

        .login-label {
            color: #8b949e;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            margin-bottom: 0.5rem;
            margin-top: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .footer-notice {
            margin-top: 4rem;
            text-align: center;
            color: rgba(139, 148, 158, 0.4);
            font-size: 0.6rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            line-height: 1.5;
        }
        .security-badge {
            background-color: #171c23;
            border: 1px solid rgba(160, 142, 122, 0.1);
            padding: 0.6rem 1.25rem;
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            color: #8b949e;
            font-size: 0.6rem;
            letter-spacing: 0.25em;
            margin-bottom: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

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
                    <img src="data:image/png;base64,{logo_b64}" 
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
                try:
                    api_url = os.getenv("AUTH_API_URL", "http://localhost:8000")
                    endpoint = f"{api_url}/auth/validate"
                    response = requests.post(endpoint, json={"username": user, "password": pwd})
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("exists") and data.get("is_active"):
                            st.session_state.authenticated = True
                            st.session_state.user_data = data.get("licencia")
                            st.session_state.access_token = data.get("access_token")
                            st.session_state.last_activity_at = datetime.now()
                            st.rerun()
                        else:
                            st.error(data.get("message", "Acceso denegado."))
                    else:
                        st.error("Error de conexión con la API.")
                except Exception:
                    st.error("No se pudo conectar con el servidor de autenticación. Intente nuevamente.")
            
            st.markdown("""
                <div style="text-align: center; margin-top: 2rem;">
                    <a href="#" style="color: #8b949e; font-size: 0.7rem; text-decoration: none; text-transform: uppercase; letter-spacing: 0.1em;">
                       ¿Olvidó su contraseña?
                    </a>
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
            <div class='sidebar-primary'>{lic['name']}</div>
            <div class='sidebar-accent'>{lic['mail']}</div>
            <div class='sidebar-label sidebar-spaced'>Empresa</div>
            <div class='sidebar-value'>{lic['empresa']}</div>
            <div class='sidebar-label sidebar-spaced'>Expira</div>
            <div class='sidebar-value'>{lic['fecha_expiracion']}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("CERRAR SESIÓN", use_container_width=True):
            _logout_session()
            st.session_state.clear_browser_session = True
            st.rerun()
    st.markdown("---")

# CSS personalizado - SOVEREIGN INTELLIGENCE FRAMEWORK
st.markdown("""
<style>
    /* ---- FUENTES: Manrope & IBM Plex Mono ---- */
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Manrope:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Manrope', sans-serif;
    }

    /* ---- TEMA OSCURO: Chromatic Tectonics ---- */
    .stApp {
        background-color: #0f141b;
        color: #dee2ed;
    }

    /* ---- SIDEBAR: Tonal Stacking ---- */
    [data-testid="stSidebar"] {
        background-color: #0f141b;
        border-right: 1px solid rgba(83, 68, 52, 0.15);
    }

    [data-testid="stSidebar"] * {
        letter-spacing: 0;
    }

    [data-testid="stSidebar"] hr {
        border-color: rgba(83, 68, 52, 0.18);
        margin: 1.35rem 0;
    }

    [data-testid="stSidebar"] .sidebar-brand {
        color: #f59e0b !important;
        font-size: 22px;
        font-weight: 800;
        line-height: 1.2;
        margin: 0 0 4px;
        letter-spacing: 0.2px;
    }

    .sidebar-brand-subtitle,
    .sidebar-footer {
        color: #d8c3ad;
        font-size: 13px;
        line-height: 1.55;
        margin: 0;
    }

    .sidebar-section-label {
        color: #a08e7a;
        font-size: 12.5px;
        line-height: 1.4;
        letter-spacing: 1.2px !important;
        text-transform: uppercase;
        font-family: 'IBM Plex Mono', monospace;
        margin: 0 0 8px;
    }

    .sidebar-section-title {
        color: #d8c3ad;
        font-size: 15px;
        line-height: 1.35;
        font-weight: 700;
        margin: 0 0 10px;
    }

    .sidebar-card {
        background: #171c23;
        border-left: 3px solid #f59e0b;
        padding: 16px 18px;
        margin-bottom: 10px;
    }

    .sidebar-label {
        margin: 0 0 8px;
        color: #9aa4b2;
        font-size: 13px;
        line-height: 1.35;
        text-transform: uppercase;
        letter-spacing: 0.5px !important;
        font-weight: 600;
    }

    .sidebar-spaced {
        margin-top: 18px;
    }

    .sidebar-primary {
        margin: 0 0 4px;
        color: #ffffff;
        font-size: 15px;
        line-height: 1.35;
        font-weight: 700;
    }

    .sidebar-value,
    .sidebar-accent,
    .sidebar-body,
    .sidebar-params {
        font-size: 14px;
        line-height: 1.6;
    }

    .sidebar-value {
        margin: 0;
        color: #dee2ed;
    }

    .sidebar-accent {
        margin: 0;
        color: #f59e0b;
    }

    .sidebar-body {
        color: #a08e7a;
        margin: 0;
    }

    .sidebar-card-title {
        color: #dee2ed;
        font-size: 14px;
        line-height: 1.4;
        font-weight: 700;
        margin: 0 0 6px;
    }

    .sidebar-params {
        color: #b8c0cc;
        font-family: 'IBM Plex Mono', monospace;
        margin: 0;
    }

    [data-testid="stSidebar"] div.stButton > button,
    [data-testid="stSidebar"] div.stDownloadButton > button {
        min-height: 48px !important;
        font-size: 14px !important;
        line-height: 1.2 !important;
    }

    /* ---- HEADERS & TITLES ---- */
    h1, h2, h3 {
        color: #f0f6fc;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    /* ---- COMPONENTES: Sharp Edges & Tonal Layering ---- */
    div.stButton > button {
        border-radius: 0px !important;
        background-color: #f59e0b !important;
        color: #472a00 !important;
        border: none !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        background-color: #fbbf24 !important;
        box-shadow: 0 0 15px rgba(245, 158, 11, 0.3);
    }

    div.stDownloadButton > button {
        border-radius: 0px !important;
        background: linear-gradient(90deg, #f59e0b 0%, #f97316 100%) !important;
        color: #fff8eb !important;
        border: none !important;
        font-weight: 800 !important;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        transition: all 0.2s ease;
    }

    div.stDownloadButton > button:hover {
        background: linear-gradient(90deg, #fbbf24 0%, #fb923c 100%) !important;
        box-shadow: 0 0 18px rgba(245, 158, 11, 0.28);
    }

    /* ---- TARJETAS Y CONTENEDORES ---- */
    .metric-card {
        background-color: #171c23; /* surface-container-low */
        border: none;
        border-radius: 0px;
        padding: 24px;
        margin-bottom: 20px;
        position: relative;
    }
    
    .metric-card.amber { border-left: 4px solid #f59e0b; background-color: #1b2027; }
    .metric-card.red   { border-left: 4px solid #ef4444; background-color: #1b2027; }
    .metric-card.blue  { border-left: 4px solid #3b82f6; background-color: #1b2027; }
    .metric-card.green { border-left: 4px solid #10b981; background-color: #1b2027; }

    .metric-number {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 32px;
        font-weight: 700;
        color: #dee2ed;
    }

    .metric-label {
        color: #d8c3ad; /* on_surface_variant */
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 4px;
    }

    /* ---- INFO BOXES: Institutional Kit ---- */
    .info-box {
        background-color: #1b2027; /* surface-container */
        border-left: 2px solid #3b82f6;
        padding: 16px;
        font-size: 13px;
        color: #d8c3ad;
        margin-bottom: 16px;
    }
    
    .warning-box {
        background-color: #1b2027;
        border-left: 2px solid #f59e0b;
        padding: 16px;
        font-size: 13px;
        color: #d8c3ad;
        margin-bottom: 16px;
    }

    /* ---- DATA TABLES ---- */
    [data-testid="stDataFrame"] {
        border-radius: 0px !important;
        border: 1px solid #30353d !important;
    }
    
    [data-testid="stDataFrame"] * {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 12px !important;
        color: #dee2ed !important;
    }

    /* ---- FORM CONTROLS: HIGHER CONTRAST ---- */
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] span {
        color: #d8c3ad !important;
        font-weight: 600 !important;
    }

    [data-testid="stCheckbox"] label,
    [data-testid="stCheckbox"] span {
        color: #d8c3ad !important;
        font-weight: 600 !important;
    }

    [data-baseweb="select"] > div {
        background-color: #171c23 !important;
        border-color: #534434 !important;
    }

    [data-baseweb="select"] * {
        color: #dee2ed !important;
    }

    [data-baseweb="tag"] {
        background-color: #1b2027 !important;
        border: 1px solid #534434 !important;
    }

    [data-baseweb="slider"] [role="slider"] {
        background: #ff5a5f !important;
        box-shadow: 0 0 0 3px rgba(255, 90, 95, 0.18) !important;
    }

    [data-baseweb="slider"] [data-testid="stTickBar"] {
        background-color: #30353d !important;
    }

    /* ---- TABS: REPORT MODULE VISIBILITY ---- */
    [data-testid="stTabs"] [role="tablist"] {
        gap: 14px;
        border-bottom: 1px solid rgba(83, 68, 52, 0.18);
        margin-bottom: 8px;
    }

    [data-testid="stTabs"] [role="tab"] {
        color: #a08e7a !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        padding: 10px 4px 12px !important;
    }

    [data-testid="stTabs"] [role="tab"]:hover {
        color: #f0f6fc !important;
    }

    [data-testid="stTabs"] [aria-selected="true"] {
        color: #f59e0b !important;
        border-bottom-color: #f59e0b !important;
    }

    /* ---- PULSE ANIMATION ---- */
    @keyframes pulse {
        0% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.2); opacity: 0.7; }
        100% { transform: scale(1); opacity: 1; }
    }
    .pulse-dot {
        width: 8px;
        height: 8px;
        background-color: #f59e0b;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 10px rgba(245, 158, 11, 0.8);
        animation: pulse 2s infinite;
        margin-right: 8px;
    }

    /* ---- GLOSSARY & LISTS ---- */
    .glossary {
        background-color: #171c23;
        padding: 20px;
        border-left: 2px solid #a08e7a;
        margin-bottom: 24px;
        border-radius: 0px;
    }
    .glossary-title {
        color: #f0f6fc;
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 700;
        margin-bottom: 15px;
        text-transform: uppercase;
        font-size: 12px;
        letter-spacing: 1.5px;
    }
    .glossary-item {
        display: flex;
        gap: 20px;
        margin-bottom: 10px;
        font-size: 12px;
        align-items: flex-start;
    }
    .glossary-key {
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 600;
        color: #f59e0b;
        min-width: 130px;
        flex-shrink: 0;
    }
    .glossary-item span:last-child {
        color: #d8c3ad;
    }

    /* ---- SECTION HEADERS ---- */
    .section-title {
        font-family: 'Manrope', sans-serif;
        font-size: 18px;
        font-weight: 700;
        color: #f0f6fc;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .section-title::before {
        content: '';
        display: inline-block;
        width: 4px;
        height: 18px;
        background-color: #f59e0b;
    }

    /* ---- MAIN WELCOME VIEW ---- */
    .welcome-panel {
        max-width: 900px;
        margin: 20px auto 30px;
        text-align: center;
    }

    .welcome-kicker {
        font-family: 'IBM Plex Mono', monospace;
        font-weight: 800;
        font-size: 16px;
        letter-spacing: 2.5px;
        color: #f59e0b;
        text-transform: uppercase;
    }

    .welcome-rule {
        width: 96px;
        height: 2px;
        background: linear-gradient(90deg, transparent, #f59e0b, transparent);
        margin: 14px auto 18px;
    }

    .welcome-title {
        color: #f0f6fc;
        font-size: 24px;
        line-height: 1.35;
        font-weight: 700;
        margin-bottom: 10px;
    }

    .welcome-copy {
        color: #b8c0cc;
        font-size: 16px;
        line-height: 1.7;
        max-width: 720px;
        margin: 0 auto;
    }

    .upload-requirements {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 14px;
        color: #c7d0db;
        margin-bottom: 18px;
        line-height: 1.9;
    }

    .upload-help {
        color: #9aa4b2;
        font-size: 15px;
        text-align: center;
        font-family: 'Manrope', sans-serif;
        line-height: 1.7;
        margin-top: 26px;
    }

    /* ---- CUSTOM TABLES (HTML) ---- */
    .aml-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'Manrope', sans-serif;
        font-size: 13px;
    }
    .aml-table th {
        background-color: #1b2027; /* surface-container */
        color: #f59e0b;
        text-align: left;
        padding: 12px 16px;
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 1.5px;
        font-family: 'IBM Plex Mono', monospace;
    }
    .aml-table td {
        padding: 12px 16px;
        border-bottom: 1px solid rgba(83, 68, 52, 0.1);
        color: #dee2ed;
    }
    .aml-table tr:hover {
        background-color: rgba(245, 158, 11, 0.05);
    }

    .footer {
        border-top: 1px solid #30353d;
        padding: 24px;
        text-align: center;
        color: #d8c3ad;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 11px;
    }

    /* ---- FIX NAVEGACIÓN RADIO BUTTON TEXT ---- */
    div[data-testid="stRadio"] label, 
    div[data-testid="stRadio"] div[data-testid="stMarkdownContainer"] p {
        color: #d8c3ad !important;
        font-size: 15px !important;
        line-height: 1.4 !important;
        font-weight: 600 !important;
    }

    /* ---- FIX BROWSE FILES BUTTON TEXT ---- */
    div[data-testid="stFileUploader"] section button {
        color: #171c23 !important;
        background-color: #dee2ed !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

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
                Reglas activas: {reglas_activas}/7<br>
                Crítico ≥ score {cfg['score_critico']}<br>
                Alto ≥ score {cfg['score_alto']}<br>
                Medio ≥ score {cfg['score_medio']}<br>
                Umbral base: Q{cfg['umbral_absoluto']:,}
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
        st.download_button(
            label="Exportar sesión (.saml)",
            data=bytes_saml,
            file_name=nombre_saml,
            mime="application/octet-stream",
            use_container_width=True,
            help="Descarga el análisis completo con datos y configuración para retomarlo después."
        )
        st.markdown("""
        <div style='font-size:12.5px; color:#8b949e; font-family:IBM Plex Mono,monospace;
                    margin-top:8px; line-height:1.5; text-align:center;'>
            Incluye transacciones + configuración usada.
        </div>""", unsafe_allow_html=True)
        st.markdown("---")

    st.markdown("""
    <div class='sidebar-footer'>
        v3.0 · Sovereign AML Intelligence<br>
        Ing. Hobéd Díaz Msc. M.A.F.I.
    </div>
    """, unsafe_allow_html=True)

vista = st.session_state.nav_view

# ============================================================
# CONFIGURACIÓN (Defaults)
# ============================================================
_DEFAULTS = {
    "tolerancia_perfil": 15, "umbral_absoluto": 20000, "mult_acumulado": 2.0, "umbral_frecuencia": 5,
    "umbral_smurfing": 5, "mult_std_pico": 2.0, "score_critico": 8, "monto_critico": 30000,
    "score_alto": 5, "score_medio": 3, "peso_absoluto": 3, "peso_acumulado": 2, "peso_perfil": 1,
    "peso_frecuencia": 1, "peso_smurfing": 3, "peso_pico": 2, "regla_absoluto": True, "regla_acumulado": True,
    "regla_perfil": True, "regla_frecuencia": True, "regla_smurfing": True, "regla_pico": True,
    "regla_ubicacion": True, "peso_pep_cpe": 2, "peso_ubicacion": 2,
    "w_st": 0.40, "w_sc": 0.25, "w_sb": 0.20, "w_sn": 0.15,
    "ubicaciones_manuales": ["Huehuetenango", "San Marcos", "Izabal", "Petén", "Escuintla"],
    "regla_feic": True, "umbral_feic": 45000,
}
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
if vista not in ["Configuración", "Manual de Usuario", "Gestión de Ubicaciones", "Red Transaccional", "Acciones de Mitigación", "Imperator Diagnostics"]:
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
            <div class="welcome-title">Bienvenido, <span style='color:#ffffff;'>{user_name}</span>.</div>
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
                    df_raw = pd.read_excel(archivo)
                    es_valido, faltantes = validar_columnas(df_raw)
                    if not es_valido:
                        st.error(f"Faltan columnas: {', '.join(faltantes)}")
                        st.stop()
                    df, casos, matriz_alertas, pep_cpe_info = procesar_transacciones(df_raw, st.session_state["aml_config"])
                    st.session_state["data"]         = (df, casos, matriz_alertas)
                    st.session_state["data_raw"]     = df_raw
                    st.session_state["pep_cpe_info"] = pep_cpe_info
                    st.session_state["archivo_nombre"] = archivo.name
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
                <strong style='color:#f0f6fc;'>Formato .saml</strong> — Sovereign AML Session File.<br>
                Contiene las transacciones originales y la configuración usada en el análisis previo.
                Al cargarlo, el motor reprocesa todo automáticamente restaurando el estado completo.
            </div>
            """, unsafe_allow_html=True)

            archivo_saml = st.file_uploader("Subir archivo .saml", type=["saml"], label_visibility="collapsed")

            if archivo_saml:
                try:
                    with st.spinner("Restaurando sesión de análisis..."):
                        df_raw, cfg_restaurado, session_meta = mod_sesion.importar_sesion(archivo_saml)

                        # Restaurar configuración guardada en la sesión
                        st.session_state["aml_config"] = cfg_restaurado
                        for k, v in cfg_restaurado.items():
                            st.session_state["aml_config"].setdefault(k, v)

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
                    &nbsp;—&nbsp; {nombre}
                    &nbsp;·&nbsp; {filas} registros
                    &nbsp;·&nbsp; Exportada: {exportado}
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
    SOVEREIGN AML Intelligence Platform v3.0 &nbsp;·&nbsp;
    Diseñado por el Ing. Hobéd Díaz Msc. M.A.F.I. &nbsp;·&nbsp;
    Sovereign Intelligence Framework
</div>
""", unsafe_allow_html=True)
