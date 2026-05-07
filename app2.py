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
from datetime import date


# --- Importaciones Modulares ---
from backend.procesador import validar_columnas, procesar_transacciones
from frontend import (
    mod_resumen, mod_alertas, mod_transacciones,
    mod_cliente, mod_matrices, mod_manual,
    mod_configuracion, mod_reportes, mod_ubicaciones,
    mod_mitigacion, mod_red_transaccional
)

# ============================================================
# SISTEMA DE AUTENTICACIÓN Y LICENCIAS
# ============================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "user_data" not in st.session_state:
    st.session_state.user_data = None

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
        st.markdown("""
            <div class="brand-title">SOVEREIGN <span>AML</span></div>
            <div class="brand-subtitle">
                ANALYTICAL INTELLIGENCE PLATFORM
            </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            st.markdown("""
                <div style="text-align: center; margin-bottom: 2rem;">
                    <img src="https://lh3.googleusercontent.com/aida/ADBb0ughVlAFHGAl_O43L89zUQKvmsVoyV3bgFQqWUkxDa5IPTuZe2k3v8PZSHGf-JNco6L8es0jlgaD2liO_FtD-Z-i1yyj84eEvRFbOFyIViYX3Fp7zNWRTB1cRW2gGAYnG3KeN0uiK9scAZhw3tplnZULHNRdhLD0j4pcF3TZnhIgD-10PwlCdAtD4lZFgR48PtxbbZ6X0UDT5ZgSCMa3SYujiPaIuieRjR_2pjj42pTyUq12TBcCrPP_whLO5ilkUnCQ4_3KxaHh9w" 
                         style="height: 6rem; margin-bottom: 1.5rem; filter: brightness(1.1) drop-shadow(0 0 15px rgba(245, 158, 11, 0.3));">
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
                    response = requests.post("http://localhost:8000/auth/validate", json={"username": user, "password": pwd})
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("exists") and data.get("is_active"):
                            st.session_state.authenticated = True
                            st.session_state.user_data = data.get("licencia")
                            st.session_state.access_token = data.get("access_token")
                            st.rerun()
                        else:
                            st.error(data.get("message", "Acceso denegado."))
                    else:
                        st.error("Error de conexión con la API.")
                except Exception as e:
                    st.error(f"Error: {e}")
            
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
    login_flow()

# ============================================================
# TEMA Y CONFIGURACIÓN VISUAL
# ============================================================

# --- Sidebar: Info de Licencia y Logout ---
with st.sidebar:
    st.markdown("---")
    if st.session_state.authenticated and st.session_state.user_data:
        lic = st.session_state.user_data
        st.markdown(f"""
        <div style='background: #171c23; padding: 15px; border-left: 3px solid #f59e0b; margin-bottom: 20px;'>
            <p style='margin:0; font-size:10px; color:#8b949e; text-transform:uppercase;'>Licencia Activa</p>
            <p style='margin:0; font-size:14px; font-weight:700; color:#ffffff;'>{lic['name']}</p>
            <p style='margin:0; font-size:11px; color:#f59e0b;'>{lic['mail']}</p>
            <p style='margin-top:10px; font-size:10px; color:#8b949e; text-transform:uppercase;'>Empresa</p>
            <p style='margin:0; font-size:11px; color:#dee2ed;'>{lic['empresa']}</p>
            <p style='margin-top:10px; font-size:10px; color:#8b949e; text-transform:uppercase;'>Expira</p>
            <p style='margin:0; font-size:11px; color:#dee2ed;'>{lic['fecha_expiracion']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("CERRAR SESIÓN", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user_data = None
            st.session_state.access_token = None
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
        font-size: 14px !important;
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
    st.markdown("<h2 style='color:#f59e0b; font-size: 21px; font-weight: 800; margin-bottom:2px; letter-spacing:0.4px;'>SOVEREIGN AML</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#d8c3ad; font-size: 12px; margin-top:0; margin-bottom:8px; font-weight:500; letter-spacing:0.2px;'>Powered by IMPERATOR Intelligence</p>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("<div style='color:#a08e7a; font-size:11px; letter-spacing:1.6px; text-transform:uppercase; font-family:IBM Plex Mono, monospace; margin-bottom:6px;'>AML Intelligence</div>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:15px; margin-top:0; margin-bottom:8px; font-weight:700; color:#d8c3ad; letter-spacing:0.3px;'>MOTOR DE CUMPLIMIENTO</p>", unsafe_allow_html=True)
    st.markdown("""
    <div style='background:#171c23; border-left:3px solid #f59e0b; padding:12px 14px; margin-bottom:8px;'>
        <div style='color:#dee2ed; font-size:12px; font-weight:600; margin-bottom:4px;'>Monitoreo AML centralizado</div>
        <div style='color:#a08e7a; font-size:11.5px; line-height:1.65;'>
            Plataforma para analizar transacciones, priorizar alertas, perfilar clientes y documentar hallazgos de riesgo en un solo flujo operativo.
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("<div style='color:#a08e7a; font-size:11px; letter-spacing:1.6px; text-transform:uppercase; font-family:IBM Plex Mono, monospace; margin-bottom:8px;'>PARÁMETROS ACTIVOS</div>", unsafe_allow_html=True)
    
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
        <div style='font-size:12px; color:#8b949e; font-family:IBM Plex Mono,monospace;
                    background:#171c23; border-radius:0px; padding:12px; line-height:1.9; border-left:2px solid #f59e0b;'>
        Reglas activas: {reglas_activas}/7<br>
        Crítico ≥ score {cfg['score_critico']}<br>
        Alto ≥ score {cfg['score_alto']}<br>
        Medio ≥ score {cfg['score_medio']}<br>
        Umbral base: Q{cfg['umbral_absoluto']:,}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='font-size:12px; color:#f59e0b; font-family:IBM Plex Mono,monospace;
                    background:#171c23; border-radius:0px; padding:12px; line-height:1.8;'>
        Usando valores por defecto.<br>Ir a Configuración para personalizar.
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<div style='color:#a08e7a; font-size:11px; letter-spacing:1.6px; text-transform:uppercase; font-family:IBM Plex Mono, monospace; margin-bottom:8px;'>NAVEGACIÓN</div>", unsafe_allow_html=True)
    
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
        "Gestión de Ubicaciones",
        "Informes y Reportes",
        "Configuración",
        "Manual de Usuario"
    ]

    m_idx = main_ops.index(st.session_state.nav_view) if st.session_state.nav_view in main_ops else 0
    st.radio("Vistas Analíticas", main_ops, key="radio_main", index=m_idx, on_change=set_nav, label_visibility="collapsed")
    
    st.markdown("---")
    st.markdown("""
    <div style='font-size:12px; color:#d8c3ad; font-family: IBM Plex Mono, monospace; line-height:1.8;'>
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
    "ubicaciones_manuales": ["Huehuetenango", "San Marcos", "Izabal", "Petén", "Escuintla"]
}
if "aml_config" not in st.session_state:
    st.session_state["aml_config"] = _DEFAULTS.copy()
else:
    for k, v in _DEFAULTS.items():
        st.session_state["aml_config"].setdefault(k, v)

# ============================================================
# CARGA DE ARCHIVO
# ============================================================
if vista not in ["Configuración", "Manual de Usuario", "Gestión de Ubicaciones", "Red Transaccional", "Acciones de Mitigación"]:
    data_ready = "data" in st.session_state
    
    if not data_ready or "archivo_nombre" not in st.session_state:
        st.markdown("""
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 700; color: #8b949e; letter-spacing: 1px; text-transform: uppercase;">CARGAR DATOS DE TRANSACCIONES</div>
        <div style="font-family: 'IBM Plex Mono', monospace; font-size: 11.5px; color: #c7d0db; margin-bottom: 20px; line-height: 1.8;">
            <span style="color:#f0f6fc; font-weight:600;">Formato requerido:</span> Excel (.xlsx) ·
            <span style="color:#f0f6fc; font-weight:600;">Columnas:</span>
            <span style="color:#7cc7ff;">Fecha Cliente EsPEP EsCPE Monto Perfil Ubicacion UbicacionRiesgo TipoOperacion Cliente_Destino</span>
        </div>
        """, unsafe_allow_html=True)
        
        archivo = st.file_uploader("Upload XLSX", type=["xlsx"], label_visibility="collapsed")

        if not archivo:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown("<div style='text-align:center; font-family:\"IBM Plex Mono\", monospace; font-weight: 800; font-size: 14px; letter-spacing: 4px; color: #f59e0b;'>AML · INTELLIGENCE PLATFORM</div>", unsafe_allow_html=True)
            st.markdown("<div style='text-align:center; width: 60px; height: 1px; background: linear-gradient(90deg, transparent, #f59e0b, transparent); margin: 10px auto 25px;'></div>", unsafe_allow_html=True)
            st.markdown("<h3 style='margin-bottom:0; text-align:center; font-family: \"IBM Plex Sans\", sans-serif; font-size: 24px;'>Cargue un archivo para iniciar el análisis</h3>", unsafe_allow_html=True)
            st.markdown("<p style='color:#8b949e; font-size:13px; text-align:center; font-family: \"IBM Plex Mono\", monospace;'>Suba su archivo Excel (.xlsx) con los datos de transacciones.<br>El motor AML procesará automáticamente las reglas de detección.</p>", unsafe_allow_html=True)
            st.stop()
        
        with st.spinner("Procesando inteligencia AML..."):
            df_raw = pd.read_excel(archivo)
            es_valido, faltantes = validar_columnas(df_raw)
            if not es_valido:
                st.error(f"Faltan columnas: {', '.join(faltantes)}")
                st.stop()
            df, casos, matriz_alertas, pep_cpe_info = procesar_transacciones(df_raw, st.session_state["aml_config"])
            st.session_state["data"] = (df, casos, matriz_alertas)
            st.session_state["pep_cpe_info"] = pep_cpe_info
            st.session_state["archivo_nombre"] = archivo.name
            st.rerun()
    else:
        st.success(f"Archivo '{st.session_state['archivo_nombre']}' cargado y analizado de forma correcta.")
        if st.button("Cargar nuevo archivo"):
            del st.session_state["data"]
            del st.session_state["archivo_nombre"]
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
    if data_ready: mod_alertas.mostrar(st.session_state["data"][1])
    else: st.info("Sube un archivo.")

elif vista == "Transacciones":
    if data_ready: mod_transacciones.mostrar(st.session_state["data"][0])
    else: st.info("Sube un archivo.")

elif vista == "Análisis por Cliente":
    if data_ready: mod_cliente.mostrar(st.session_state["data"][0], st.session_state["data"][1], st.session_state["aml_config"])
    else: st.info("Sube un archivo.")

elif vista == "Matrices de Riesgo":
    if data_ready: mod_matrices.mostrar(st.session_state["data"][1], st.session_state["data"][2])
    else: st.info("Sube un archivo.")

elif vista == "Red Transaccional":
    if data_ready: mod_red_transaccional.mostrar(st.session_state["data"][0], st.session_state["data"][1])
    else: st.info("Sube un archivo.")

elif vista == "Acciones de Mitigación":
    if data_ready: mod_mitigacion.mostrar(st.session_state["data"][0], st.session_state["data"][1])
    else: st.info("Sube un archivo.")

elif vista == "Gestión de Ubicaciones":
    mod_ubicaciones.mostrar()

elif vista == "Informes y Reportes":
    if data_ready: mod_reportes.mostrar(*st.session_state["data"], st.session_state["aml_config"])
    else: st.info("Sube un archivo.")

elif vista == "Configuración":
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
