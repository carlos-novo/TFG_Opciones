import streamlit as st
import hashlib
from datetime import date, datetime
import threading
import time
import random
import json
import pandas as pd
import socket
import os
import plotly.graph_objects as go

from conexion_ibkr import GestorIBKR
from motor_logica import MotorEstrategias, MotorSalida
from base_datos import GestorBaseDatos
from motor_bs import MotorBlackScholes
from notificaciones import enviar_alerta_webhook
from watchdogs import iniciar_watchdog_entradas, iniciar_watchdog_salidas, detener_watchdogs

# Inicialización de la base de datos
db = GestorBaseDatos()

# --- INICIALIZACIÓN GLOBAL DE WATCHDOGS (HITO 4) ---
@st.cache_resource
def iniciar_watchdogs_globales():
    """Inicializa una única vez los watchdogs en segundo plano de entrada y salida."""
    try:
        # Iniciamos el watchdog de entradas (cada 30s) y de salidas (cada 15s)
        hilo_ent = iniciar_watchdog_entradas(db_name="tfg_trading.db", interval=30)
        hilo_sal = iniciar_watchdog_salidas(db_name="tfg_trading.db", interval=15)
        db.registrar_evento("WATCHDOGS_INICIADOS_UI", "Watchdogs globales arrancados desde el frontend.")
        return hilo_ent, hilo_sal
    except Exception as e:
        print(f"Error al iniciar watchdogs: {e}")
        return None, None

# Arrancamos los watchdogs
hilo_ent_glob, hilo_sal_glob = iniciar_watchdogs_globales()

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Plataforma de Trading Multileg", layout="wide")

# --- ESTILOS PREMIUM GLASSMORPHISM (DARK MODE) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    /* Hide the sidebar and collapsed arrow toggle completely */
    section[data-testid="stSidebar"] {
        display: none !important;
    }
    button[data-testid="collapsedControl"] {
        display: none !important;
    }
    
    /* Global Styles */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: #0d0e15;
        color: #e2e8f0;
    }
    
    /* Header styling */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        color: #ffffff;
        letter-spacing: -0.02em;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #06070b;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Card Glassmorphism */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    div[data-testid="stMetric"]:hover {
        border-color: rgba(99, 102, 241, 0.4);
        box-shadow: 0 8px 32px 0 rgba(99, 102, 241, 0.15);
        transform: translateY(-3px);
    }
    
    /* Metric values in theme blue */
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] * {
        color: #6366f1 !important;
    }
    
    /* Tabs customization */
    button[data-baseweb="tab"] {
        font-size: 1.1rem;
        font-weight: 600;
        color: #94a3b8;
        padding: 12px 20px;
        border-radius: 8px;
        transition: all 0.2s ease;
    }
    button[data-baseweb="tab"]:hover {
        color: #ffffff;
        background-color: rgba(255, 255, 255, 0.03);
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #6366f1 !important;
        border-bottom-color: #6366f1 !important;
        background-color: rgba(99, 102, 241, 0.05);
    }
    
    /* Barra inferior de pestaña seleccionada a azul */
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #6366f1 !important;
    }
    div[data-baseweb="tab-highlight-bar"] {
        background-color: #6366f1 !important;
    }
    
    /* Toggles y checkboxes activos a color azul (usando :has ya que la pista del switch está antes del input en el DOM) */
    div[data-testid="stCheckbox"] label:has(input:checked) > *:first-child,
    label[data-baseweb="checkbox"]:has(input:checked) > *:first-child {
        background-color: #6366f1 !important;
        border-color: #6366f1 !important;
    }
    
    /* Prevenir que el texto de las etiquetas se coloree de azul */
    div[data-testid="stWidgetLabel"],
    div[data-testid="stMarkdownContainer"],
    div[data-testid="stWidgetLabel"] *,
    div[data-testid="stMarkdownContainer"] * {
        background-color: transparent !important;
        background: transparent !important;
    }
    
    /* Styled Containers (Expander, Form, etc.) */
    div[data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.01) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2) !important;
    }
    
    .stForm {
        background: rgba(255, 255, 255, 0.01) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 16px !important;
        padding: 24px !important;
    }
    
    /* Accent Buttons */
    div.stButton > button,
    div.stFormSubmitButton > button,
    div.stDownloadButton > button {
        background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 10px 24px;
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);
        transition: all 0.2s ease;
    }
    div.stButton > button:hover,
    div.stFormSubmitButton > button:hover,
    div.stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(79, 70, 229, 0.6);
        background: linear-gradient(135deg, #5a52e6 0%, #4c8ff7 100%);
        color: white;
    }
    div.stButton > button:active,
    div.stFormSubmitButton > button:active,
    div.stDownloadButton > button:active {
        transform: translateY(1px);
    }
    
    /* Top Toolbar Smaller Buttons */
    div[class*="st-key-btn_top_"] button {
        padding: 6px 14px !important;
        font-size: 0.85rem !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.3) !important;
        height: 34px !important;
        min-height: 34px !important;
        line-height: 1.2 !important;
    }
    div[class*="st-key-btn_top_"] button:hover {
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.5) !important;
    }
    
    /* Alert cards custom styles */
    .stAlert {
        border-radius: 12px !important;
        background-color: rgba(30, 41, 59, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    
    /* Option Omega style Segmented Control (Pills) */
    div[data-testid="stSegmentedControl"] {
        background-color: #1a1c29 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 8px !important;
        padding: 2px !important;
        width: 100% !important;
    }
    div[data-testid="stSegmentedControl"] > div {
        display: flex !important;
        gap: 2px !important;
        width: 100% !important;
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1 !important;
        border-radius: 6px !important;
        border: none !important;
        background-color: transparent !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
        padding: 6px 10px !important;
        font-size: 0.85rem !important;
        text-align: center !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stSegmentedControl"] button:hover {
        color: #ffffff !important;
        background-color: rgba(255, 255, 255, 0.05) !important;
    }
    
    /* Custom classes added by JS observer (fallback) */
    button.btn-sell[aria-checked="true"],
    button.btn-sell[aria-selected="true"],
    button.btn-sell[aria-pressed="true"],
    button.btn-sell[data-testid="stBaseButton-segmented_controlActive"],
    button.btn-sell.e1mwqyj913 {
        background-color: #e13c56 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(225, 60, 86, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }
    button.btn-buy[aria-checked="true"],
    button.btn-buy[aria-selected="true"],
    button.btn-buy[aria-pressed="true"],
    button.btn-buy[data-testid="stBaseButton-segmented_controlActive"],
    button.btn-buy.e1mwqyj913 {
        background-color: #6366f1 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }
    .row-action-sell button.btn-call[aria-checked="true"],
    .row-action-sell button.btn-call[aria-selected="true"],
    .row-action-sell button.btn-call[aria-pressed="true"],
    .row-action-sell button.btn-call[data-testid="stBaseButton-segmented_controlActive"],
    .row-action-sell button.btn-call.e1mwqyj913,
    .row-action-sell button.btn-put[aria-checked="true"],
    .row-action-sell button.btn-put[aria-selected="true"],
    .row-action-sell button.btn-put[aria-pressed="true"],
    .row-action-sell button.btn-put[data-testid="stBaseButton-segmented_controlActive"],
    .row-action-sell button.btn-put.e1mwqyj913 {
        background-color: #e13c56 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(225, 60, 86, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }
    .row-action-buy button.btn-call[aria-checked="true"],
    .row-action-buy button.btn-call[aria-selected="true"],
    .row-action-buy button.btn-call[aria-pressed="true"],
    .row-action-buy button.btn-call[data-testid="stBaseButton-segmented_controlActive"],
    .row-action-buy button.btn-call.e1mwqyj913,
    .row-action-buy button.btn-put[aria-checked="true"],
    .row-action-buy button.btn-put[aria-selected="true"],
    .row-action-buy button.btn-put[aria-pressed="true"],
    .row-action-buy button.btn-put[data-testid="stBaseButton-segmented_controlActive"],
    .row-action-buy button.btn-put.e1mwqyj913 {
        background-color: #6366f1 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }

    /* PURE CSS SELECTORS (No JS required) based on Column Wrapper child index */
    
    /* SELL Active in Column 1 (1st child of stHorizontalBlock) */
    div[data-testid="stHorizontalBlock"] > div:nth-child(1) button[data-testid="stBaseButton-segmented_controlActive"]:nth-child(1) {
        background-color: #e13c56 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(225, 60, 86, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }
    
    /* BUY Active in Column 1 (1st child of stHorizontalBlock) */
    div[data-testid="stHorizontalBlock"] > div:nth-child(1) button[data-testid="stBaseButton-segmented_controlActive"]:nth-child(2) {
        background-color: #6366f1 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }
    
    /* Active CALL/PUT inside a SELL row (Column 2 active button when Column 1 has 1st button active) */
    div[data-testid="stHorizontalBlock"]:has(> div:nth-child(1) button[data-testid="stBaseButton-segmented_controlActive"]:nth-child(1))
    > div:nth-child(2) button[data-testid="stBaseButton-segmented_controlActive"] {
        background-color: #e13c56 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(225, 60, 86, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }
    
    /* Active CALL/PUT inside a BUY row (Column 2 active button when Column 1 has 2nd button active) */
    div[data-testid="stHorizontalBlock"]:has(> div:nth-child(1) button[data-testid="stBaseButton-segmented_controlActive"]:nth-child(2))
    > div:nth-child(2) button[data-testid="stBaseButton-segmented_controlActive"] {
        background-color: #6366f1 !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4) !important;
        border: none !important;
        border-color: transparent !important;
        outline: none !important;
    }

    /* Blue 'X' delete button inside column 7 */
    div[data-testid="stHorizontalBlock"] > div:nth-child(7) button {
        background: transparent !important;
        border: 1px solid rgba(99, 102, 241, 0.4) !important;
        color: #6366f1 !important;
        box-shadow: none !important;
        border-radius: 8px !important;
        width: 100% !important;
        height: 40px !important;
        min-height: 40px !important;
        min-width: 40px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        line-height: 1 !important;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(7) button * {
        color: #6366f1 !important;
        font-size: 1.25rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(7) button:hover {
        background: rgba(99, 102, 241, 0.15) !important;
        border-color: #6366f1 !important;
    }
    div[data-testid="stHorizontalBlock"] > div:nth-child(7) button:hover * {
        color: #ffffff !important;
    }

    /* Custom Strategy Card Container */
    div[class*="st-key-strategy_card_"] {
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        border-radius: 12px !important;
        padding: 20px !important;
        margin-bottom: 15px !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
    }

    /* Login Form Card Styling */
    .stForm {
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.1) !important;
        background: rgba(13, 14, 21, 0.8) !important;
    }
    div.stFormSubmitButton > button {
        width: 100% !important;
    }

    /* Align manual close buttons to the right */
    div[class*="st-key-cierre_man_"],
    div[class*="st-key-cierre_man_"] div.stButton {
        width: 100% !important;
        display: flex !important;
        justify-content: flex-end !important;
    }
    div[class*="st-key-cierre_man_"] button {
        width: auto !important;
    }

    /* Logo Title Gradient Override */
    div[data-testid="stMarkdownContainer"] h1.logo-title {
        background: linear-gradient(135deg, #6366f1 0%, #3b82f6 100%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        color: transparent !important;
    }
</style>
""", unsafe_allow_html=True)

# --- LÓGICA DE SEGURIDAD Y ENCRIPTACIÓN ---
ADMIN_USER = "admin"
ADMIN_PASSWORD_HASH = "6051fc84a7a0d74c225fb18a496b09952da5642e60723ecae543298edd7d82d6" # admin2026

def verificar_credenciales(usuario, password):
    hash_input = hashlib.sha256(password.encode()).hexdigest()
    return usuario == ADMIN_USER and hash_input == ADMIN_PASSWORD_HASH

if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

# --- BARRERA DE ENTRADA (LOGIN) ---
login_placeholder = st.empty()
if not st.session_state['autenticado']:
    with login_placeholder.container(key="login_container"):
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align: center; color: #6366f1; font-weight: 700; margin-bottom: 10px;'>Plataforma Algorítmica Multileg</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #94a3b8;'>Introduce tus credenciales para acceder a la plataforma multileg.</p>", unsafe_allow_html=True)
            
            with st.form("login_form"):
                user_input = st.text_input("Usuario")
                pass_input = st.text_input("Contraseña", type="password")
                submit_login = st.form_submit_button("Iniciar Sesión")
                
                if submit_login:
                    if verificar_credenciales(user_input, pass_input):
                        st.session_state['autenticado'] = True
                        db.registrar_evento("LOGIN_EXITOSO", f"Usuario '{user_input}' ha accedido al sistema.")
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas. Acceso denegado.")
    st.stop()

# --- APLICACIÓN PRINCIPAL (AUTENTICADO) ---
if 'broker' not in st.session_state:
    st.session_state.broker = GestorIBKR(port=4002)

if 'posiciones_cartera' not in st.session_state:
    st.session_state['posiciones_cartera'] = None

# --- DIÁLOGO DE CONSULTA DE COTIZACIONES (POPUP MODAL) ---
@st.dialog("🔍 Consultar Cotización")
def mostrar_dialogo_cotizacion():
    st.markdown("<p style='color:#94a3b8; font-size:0.95rem; margin-top:-10px;'>Consulta la cotización en tiempo real o retardada de cualquier ticker en Interactive Brokers.</p>", unsafe_allow_html=True)
    ticker_test = st.text_input(
        "Ticker (ej. AAPL, SPY, SPX)", 
        value="SPY", 
        max_chars=5, 
        key="dialog_ticker",
        help="**¿Cómo funciona la consulta?**\n\nPara garantizar la obtención del precio bajo cualquier circunstancia (incluso con el mercado cerrado o para activos con baja negociación fuera de horas como NVR, BBVA o IBKR), la plataforma realiza una consulta directa de **barras históricas diarias (de resolución 1 día) de los últimos 5 días**.\n\nEsto permite extraer de forma inmediata el **último precio de cierre oficial registrado** (si el mercado está cerrado) o la **cotización en tiempo real actualizada** (si el mercado está abierto), evitando el uso de flujos asíncronos y sin consumir los límites de suscripción en tiempo real de la API de Interactive Brokers."
    ).upper()
    
    if st.button("Consultar", use_container_width=True, type="primary"):
        conectado = st.session_state.broker.esta_conectado()
        if conectado:
            with st.spinner("Consultando en IBKR..."):
                precio = st.session_state.broker.obtener_precio_prueba(ticker_test)
                if precio:
                    st.success(f"📈 Última cotización de **{ticker_test}**: **${precio:.2f}**")
                else:
                    st.error("❌ Fallo en la consulta. Verifica que el ticker sea válido y el mercado esté abierto.")
        else:
            # Fallback en modo offline para demostración/defensa
            if ticker_test == "SPX":
                mock_p = 7267.65
            elif ticker_test == "SPY":
                mock_p = 520.45
            else:
                mock_p = 150.00
            st.info(f"💡 [Modo Offline] Precio simulado de **{ticker_test}**: **${mock_p:.2f}**")

# --- BARRA DE HERRAMIENTAS SUPERIOR (TOP TOOLBAR) ---
conectado = st.session_state.broker.esta_conectado()
color_est = "🟢" if conectado else "🔴"
texto_est = "Conectado" if conectado else "Desconectado"

with st.container(key="top_toolbar_container"):
    col_logo, col_cot, col_conn, col_logout = st.columns([7.2, 1.2, 1.5, 1.1], vertical_alignment="center")

    with col_logo:
        st.markdown("""
        <h1 style='margin:0; font-size:2.5rem; font-weight:800; font-family:"Outfit", sans-serif;
                   background: linear-gradient(135deg, #6366f1 0%, #3b82f6 100%);
                   -webkit-background-clip: text; -webkit-text-fill-color: #6366f1;
                   letter-spacing:-0.03em; line-height:1.1;'>
            Plataforma Algorítmica Multileg
        </h1>
        <p style='color: #94a3b8; font-size: 0.95rem; margin-top: 4px; margin-bottom: 0;'>
            Watchdogs en segundo plano, sensibilidades Black-Scholes y gestión de riesgo
        </p>
        """, unsafe_allow_html=True)

    with col_cot:
        if st.button("Consultar Precio", use_container_width=True, key="btn_top_cot"):
            mostrar_dialogo_cotizacion()

    with col_conn:
        if st.button(f"{color_est} {texto_est}", use_container_width=True, key="btn_top_conn"):
            if conectado:
                st.session_state.broker.desconectar()
            else:
                st.session_state.broker.conectar()
            st.rerun()

    with col_logout:
        if st.button("Cerrar Sesión", use_container_width=True, key="btn_top_logout"):
            st.session_state['autenticado'] = False
            if st.session_state.broker.esta_conectado():
                st.session_state.broker.desconectar()
            st.rerun()

st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

tabs = st.tabs(["Dashboard", "Acciones", "Opciones", "Control Room"])

# ==========================================
# TAB 1: DASHBOARD
# ==========================================
with tabs[0]:
    st.header("Consola Principal del Bróker")
    
    # 1. Indicadores Financieros
    if conectado:
        now = time.time()
        last_summary_fetch = st.session_state.get('last_summary_fetch_time', 0)
        if st.session_state.get('datos_cuenta') is None or (now - last_summary_fetch) >= 14:
            with st.spinner("Sincronizando cuenta con IBKR..."):
                st.session_state['datos_cuenta'] = st.session_state.broker.obtener_resumen_cuenta()
                st.session_state['last_summary_fetch_time'] = now
        datos_cuenta = st.session_state.get('datos_cuenta')
        if datos_cuenta:
            net_liq = float(datos_cuenta['NetLiquidation'])
            buying_power = float(datos_cuenta['BuyingPower'])
            daily_pnl = float(datos_cuenta['DailyPnL'])
        else:
            net_liq, buying_power, daily_pnl = 100000.0, 50000.0, 0.0
    else:
        # Mocks para defensa TFG si no hay gateway conectado
        net_liq, buying_power, daily_pnl = 152430.80, 78920.40, 3250.00
        st.info("💡 Bróker desconectado. Visualizando datos simulados (Modo Demostración TFG).")
        
    c1, c2, c3 = st.columns(3)
    c1.metric("Net Liquidation", f"${net_liq:,.2f}", delta=f"{'+' if daily_pnl >= 0 else ''}${daily_pnl:,.2f} Hoy")
    c2.metric("Buying Power", f"${buying_power:,.2f}")
    c3.metric("Daily P&L (No Realizado)", f"${daily_pnl:,.2f}", delta=f"{'+' if daily_pnl >= 0 else ''}{daily_pnl/net_liq*100:.2f}%", delta_color="normal")
    
    st.divider()
    
    # 2. Posiciones Abiertas
    st.subheader("Posiciones Abiertas en Cartera")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Monitoreo directo del portafolio actual del bróker.</p>", unsafe_allow_html=True)
    
    @st.fragment(run_every=15)
    def render_posiciones_cartera():
        col_ref, _ = st.columns([1, 4])
        actualizar = col_ref.button("🔄 Actualizar Cartera", key="btn_act_pos")
        
        now = time.time()
        last_fetch = st.session_state.get('last_portfolio_fetch_time', 0)
        
        if conectado:
            if actualizar or st.session_state.get('posiciones_cartera') is None or (now - last_fetch) >= 14:
                st.session_state['posiciones_cartera'] = st.session_state.broker.obtener_posiciones_cartera()
                st.session_state['last_portfolio_fetch_time'] = now
        else:
            if actualizar or st.session_state.get('posiciones_cartera') is None:
                st.session_state['posiciones_cartera'] = [
                    {"Símbolo": "AAPL", "Tipo": "Acción", "Vencimiento": "—", "Strike": "—", "Right (C/P)": "—", "Posición": 100, "Precio Medio": 175.50, "Valor Mercado": 18120.00, "P&L No Real.": 570.00},
                    {"Símbolo": "SPY", "Tipo": "Opción", "Vencimiento": "2026-06-19", "Strike": 510.0, "Right (C/P)": "C", "Posición": -2, "Precio Medio": 4.20, "Valor Mercado": -940.00, "P&L No Real.": -100.00},
                    {"Símbolo": "MSFT", "Tipo": "Acción", "Vencimiento": "—", "Strike": "—", "Right (C/P)": "—", "Posición": 50, "Precio Medio": 405.00, "Valor Mercado": 20450.00, "P&L No Real.": 200.00}
                ]
                
        posiciones = st.session_state.get('posiciones_cartera', [])
        
        if not posiciones:
            st.success("✅ Sin posiciones abiertas en la cuenta. La cartera está 100% en efectivo.")
        else:
            df_pos = pd.DataFrame(posiciones)
            # Evitamos que PyArrow falle por tipos mixtos (ej. Strike con '—' y float)
            for col in ["Strike", "Vencimiento", "Right (C/P)"]:
                if col in df_pos.columns:
                    df_pos[col] = df_pos[col].map(lambda x: "—" if (x is None or pd.isna(x) or str(x).strip() == "" or x == "—") else str(x))
            st.dataframe(df_pos, width="stretch", hide_index=True)
            
    render_posiciones_cartera()


with tabs[1]:
    st.header("Nueva Orden Direccional de Acciones")

    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Encolador de estrategias con reglas de entrada técnicas y límites de salida absolutos.</p>", unsafe_allow_html=True)
    
    c_a1, c_a2, c_a3 = st.columns(3)
    ticker_acc = c_a1.text_input("Ticker", value="AAPL", max_chars=5, key="acc_ticker").upper()
    cant_acc = c_a2.number_input("Cantidad de Acciones", min_value=1, value=50, step=1, key="acc_cantidad")
    
    with c_a3:
        tipo_ord_acc = st.selectbox("Tipo de Orden", ["Mercado", "Límite"], key="acc_tipo_orden")
        if tipo_ord_acc == "Límite":
            precio_limite_acc = st.number_input("Precio Límite ($)", min_value=0.01, value=150.0, step=0.1, key="acc_precio_limite")
        else:
            precio_limite_acc = None
            
    accion_acc = "BUY"
    
    st.divider()
    
    # Condiciones de Entrada
    st.subheader("Condiciones de Entrada Avanzadas")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa las condiciones que deben cumplirse antes de que el Watchdog envíe la orden al mercado.</p>", unsafe_allow_html=True)

    _W  = [1.5, 0.7, 1.1, 0.9]  # Anchos idénticos en todas las filas → columnas alineadas
    _SP = "<div style='height:16px'></div>"  # Separación fija preestablecida

    # Fila: Ventana Horaria
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_horario = st.toggle("Ventana Horaria", value=False, key="acc_act_horario")
    if act_horario:
        tipo_horario = _c1.selectbox("", ["Rango", "Hora Fija"], key="acc_tipo_horario", label_visibility="collapsed")
        h_ini_acc    = _c2.text_input("", value="15:30", key="acc_h_ini", label_visibility="collapsed")
        if tipo_horario == "Rango":
            h_fin_acc = _c3.text_input("", value="22:00", key="acc_h_fin", label_visibility="collapsed")
        else:
            try:
                from datetime import datetime, timedelta
                h_fin_acc = (datetime.strptime(h_ini_acc, "%H:%M") + timedelta(minutes=10)).strftime("%H:%M")
            except Exception:
                h_fin_acc = "23:59"
    else:
        h_ini_acc, h_fin_acc = "15:30", "22:00"
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Filtro VIX
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_vix = st.toggle("Filtro VIX", value=False, key="acc_act_vix")
    if act_vix:
        vix_op_acc  = _c1.selectbox("", ["<", "<=", ">", ">="], key="acc_vix_op", label_visibility="collapsed")
        vix_val_acc = _c2.number_input("", min_value=1.0, value=20.0, step=0.5, key="acc_vix_val", label_visibility="collapsed")
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Filtro SMA
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_sma = st.toggle("Filtro SMA", value=False, key="acc_act_sma")
    if act_sma:
        sma_per_acc = _c1.number_input("", min_value=5, value=200, step=5, key="acc_sma_per", label_visibility="collapsed")
        sma_reg_acc = _c2.selectbox("", ["Precio > SMA", "Precio < SMA"], key="acc_sma_reg", label_visibility="collapsed")
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Precio Disparador
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_precio = st.toggle("Precio Disparador", value=False, key="acc_act_precio")
    if act_precio:
        op_precio_acc  = _c1.selectbox("", ["<=", ">="], key="acc_precio_op", label_visibility="collapsed")
        val_precio_acc = _c2.number_input("", min_value=0.0, value=150.0, step=0.5, key="acc_precio_val", label_visibility="collapsed")
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Frecuencia (siempre visible)
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        st.markdown("<p style='margin-top:8px; color:#94a3b8; font-size:0.88rem;'>Frecuencia</p>", unsafe_allow_html=True)
    frec_acc = _c1.selectbox("", ["Única", "Diaria", "Semanal"], key="acc_frecuencia", label_visibility="collapsed")
            
    st.divider()
    
    # Condiciones de Salida
    st.subheader("Condiciones de Salida Avanzadas")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa y configura las reglas de gestión de riesgo que vigilará el Watchdog de Salidas.</p>", unsafe_allow_html=True)

    _W  = [1.5, 0.7, 1.1, 0.9]
    _SP = "<div style='height:16px'></div>"

    # Fila: Stop Loss / Take Profit
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_sl_tp = st.toggle("Stop Loss / Take Profit", value=False, key="acc_act_sl_tp")
    if act_sl_tp:
        stop_loss_acc   = _c1.number_input("", value=-200.0, step=10.0, key="acc_sl_val", label_visibility="collapsed")
        take_profit_acc = _c2.number_input("", value=400.0, step=10.0, key="acc_tp_val", label_visibility="collapsed")
        dest_gestion    = _c3.selectbox("", ["App (Watchdog)", "IBKR (Broker)"], key="acc_gestion_sl_tp", label_visibility="collapsed")
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Cerrar por VIX
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_vix_salida = st.toggle("Cerrar por VIX", value=False, key="acc_act_vix_salida")
    if act_vix_salida:
        vix_max_acc = _c1.number_input("", min_value=1.0, value=30.0, step=0.5, key="acc_vix_max", label_visibility="collapsed")
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Cerrar por SMA
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_sma_salida = st.toggle("Cerrar por SMA", value=False, key="acc_act_sma_salida")
    if act_sma_salida:
        sma_per_sal = _c1.number_input("", min_value=5, value=200, step=5, key="acc_sma_per_sal", label_visibility="collapsed")
        sma_reg_sal = _c2.selectbox("", ["Precio < SMA", "Precio > SMA"], key="acc_sma_reg_sal", label_visibility="collapsed")
    st.markdown(_SP, unsafe_allow_html=True)

    # Fila: Hora Forzada
    _c0, _c1, _c2, _c3 = st.columns(_W)
    with _c0:
        act_hora_salida = st.toggle("Hora Forzada", value=False, key="acc_act_hora_salida")
    if act_hora_salida:
        hora_sal_acc = _c1.text_input("", value="21:45", key="acc_hora_sal", label_visibility="collapsed")
            
    st.markdown("<br>", unsafe_allow_html=True)
    submit_acc = st.button("Encolar Estrategia Acciones", width="stretch", key="btn_encolar_acciones")
    
    if submit_acc:
        if not ticker_acc:
            st.error("Por favor, introduce un ticker válido.")
        else:
            # Serializamos las condiciones
            cond_entrada = {}
            if act_horario:
                cond_entrada["horario"] = {"activo": True, "hora_inicio": h_ini_acc, "hora_fin": h_fin_acc}
            if act_vix:
                cond_entrada["vix"] = {"activo": True, "valor": float(vix_val_acc), "operador": vix_op_acc}
            if act_sma:
                cond_entrada["sma"] = {"activo": True, "periodo": int(sma_per_acc), "regla": sma_reg_acc}
            if act_precio:
                cond_entrada["precio_disparador"] = {"activo": True, "valor": float(val_precio_acc), "operador": op_precio_acc}
            # Frecuencia de ejecución
            cond_entrada["frecuencia"] = {"activo": (frec_acc != "Única"), "tipo": frec_acc}
                
            cond_salida = {}
            if act_sl_tp:
                cond_salida["stop_loss"] = float(stop_loss_acc)
                cond_salida["take_profit"] = float(take_profit_acc)
                cond_salida["gestion"] = dest_gestion
            if act_vix_salida:
                cond_salida["vix_maximo"] = float(vix_max_acc)
            if act_sma_salida:
                cond_salida["sma"] = {"activo": True, "periodo": int(sma_per_sal), "regla": sma_reg_sal}
            if act_hora_salida:
                cond_salida["cierre_horario"] = hora_sal_acc
                
            # Definimos la pata única
            patas = [{"tipo_activo": "STOCK", "accion": accion_acc, "cantidad": int(cant_acc)}]
            
            try:
                est_id = db.crear_estrategia(
                    ticker=ticker_acc,
                    tipo_activo="STOCK",
                    estado="PENDIENTE_ENTRADA",
                    patas=patas,
                    condiciones_entrada=cond_entrada if cond_entrada else None,
                    condiciones_salida=cond_salida if cond_salida else None,
                    precio_entrada=precio_limite_acc
                )
                
                st.success(f"🚀 Estrategia de acciones #{est_id} encolada con éxito en estado PENDIENTE_ENTRADA.")
                db.registrar_evento("CREACION_ESTRATEGIA_UI", f"Estrategia #{est_id} ({ticker_acc}) encolada desde UI.")
                
                # Discord alert
                target_p = f"${precio_limite_acc:.2f} (Límite)" if precio_limite_acc is not None else "Mercado"
                enviar_alerta_webhook(
                    titulo="📥 Nueva Estrategia Encolada (Acciones)",
                    mensaje=f"**ID:** {est_id}\n**Ticker:** {ticker_acc}\n**Acción:** {accion_acc}\n**Cantidad:** {cant_acc}\n**Precio Target:** {target_p}\n**Frecuencia:** {frec_acc}",
                    color="info"
                )
            except Exception as e:
                st.error(f"Error al encolar estrategia: {e}")



# ==========================================
# TAB 3: OPCIONES (CONSTRUCTOR MULTILEG)
# ==========================================
with tabs[2]:
    st.header("Constructor de Opciones Multileg")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Crea combinaciones complejas de opciones (Spreads, Iron Condors, Straddles) y simula su payoff en caliente.</p>", unsafe_allow_html=True)
    
    # Manejo de estado de las patas
    if "patas_opciones" not in st.session_state:
        # Pre-cargar un Iron Condor de muestra para impresionar
        st.session_state["patas_opciones"] = [
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 90.0, "right": "P", "vencimiento": date.today(), "precio_entrada": 1.50},
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 95.0, "right": "P", "vencimiento": date.today(), "precio_entrada": 3.20},
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 105.0, "right": "C", "vencimiento": date.today(), "precio_entrada": 2.80},
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 110.0, "right": "C", "vencimiento": date.today(), "precio_entrada": 1.10}
        ]
        
    opt_ticker = st.text_input("Ticker Subyacente Opciones", value="SPY").upper()
    
    # Caché de precio para Opciones (evita consultas lentas en reruns de sliders)
    if "opt_ticker_previo" not in st.session_state:
        st.session_state["opt_ticker_previo"] = ""
    if "precio_subyacente_opt" not in st.session_state:
        st.session_state["precio_subyacente_opt"] = None

    if opt_ticker != st.session_state["opt_ticker_previo"]:
        st.session_state["opt_ticker_previo"] = opt_ticker
        if st.session_state.broker.esta_conectado():
            try:
                with st.spinner(f"Consultando cotización actual de {opt_ticker}..."):
                    precio = st.session_state.broker.obtener_precio_prueba(opt_ticker)
                    if precio:
                        st.session_state["precio_subyacente_opt"] = precio
                    else:
                        st.session_state["precio_subyacente_opt"] = None
            except:
                st.session_state["precio_subyacente_opt"] = None
        else:
            st.session_state["precio_subyacente_opt"] = None
    
    st.subheader("Configuración de las Patas (Legs)")
    
    # Renderizamos una única cabecera para toda la tabla
    col_h1, col_h2, col_h3, col_h4, col_h5, col_h6, col_h7 = st.columns([1.8, 1.8, 1.5, 1.2, 1.5, 2.0, 1.0])
    col_h1.markdown("<small style='font-weight: 600; color: #94a3b8;'>ACCIÓN</small>", unsafe_allow_html=True)
    col_h2.markdown("<small style='font-weight: 600; color: #94a3b8;'>TIPO</small>", unsafe_allow_html=True)
    col_h3.markdown("<small style='font-weight: 600; color: #94a3b8;'>STRIKE ($)</small>", unsafe_allow_html=True)
    col_h4.markdown("<small style='font-weight: 600; color: #94a3b8;'>RATIO (QTY)</small>", unsafe_allow_html=True)
    col_h5.markdown("<small style='font-weight: 600; color: #94a3b8;'>PRIMA ($)</small>", unsafe_allow_html=True)
    col_h6.markdown("<small style='font-weight: 600; color: #94a3b8;'>VENCIMIENTO</small>", unsafe_allow_html=True)
    col_h7.markdown("<small style='font-weight: 600; color: #94a3b8;'>ELIM.</small>", unsafe_allow_html=True)
    
    patas_eliminar = []
    
    # Formulario dinámico por pata (sin etiquetas repetitivas para máxima limpieza)
    for idx, pata in enumerate(st.session_state["patas_opciones"]):
        col_act, col_right, col_strike, col_qty, col_prem, col_venc, col_del = st.columns([1.8, 1.8, 1.5, 1.2, 1.5, 2.0, 1.0])
        
        # 1. Segmented Control Acción (SELL/BUY)
        accion_opt = col_act.segmented_control(
            f"Acción #{idx+1}",
            options=["SELL", "BUY"],
            default=pata["accion"],
            key=f"leg_act_{idx}",
            label_visibility="collapsed"
        )
        if accion_opt:
            pata["accion"] = accion_opt
            
        # 2. Segmented Control Tipo (CALL/PUT)
        current_right = "CALL" if pata["right"] == "C" else "PUT"
        right_opt = col_right.segmented_control(
            f"C/P #{idx+1}",
            options=["CALL", "PUT"],
            default=current_right,
            key=f"leg_r_{idx}",
            label_visibility="collapsed"
        )
        if right_opt:
            pata["right"] = "C" if right_opt == "CALL" else "P"
            
        # 3. Strike Input (Label collapsed)
        pata["strike"] = col_strike.number_input(
            f"Strike #{idx+1}", 
            min_value=0.1, 
            value=float(pata["strike"]), 
            step=1.0, 
            key=f"leg_k_{idx}",
            label_visibility="collapsed"
        )
        
        # 4. Ratio/Quantity Input (Label collapsed)
        pata["cantidad"] = col_qty.number_input(
            f"Ratio #{idx+1}", 
            min_value=1, 
            value=int(pata["cantidad"]), 
            step=1, 
            key=f"leg_q_{idx}",
            label_visibility="collapsed"
        )
        
        # 5. Prima Input (Label collapsed)
        pata["precio_entrada"] = col_prem.number_input(
            f"Prima #{idx+1}", 
            min_value=0.01, 
            value=float(pata["precio_entrada"]), 
            step=0.05, 
            key=f"leg_p_{idx}",
            label_visibility="collapsed"
        )
        
        # 6. Vencimiento (Label collapsed)
        venc_val = pata["vencimiento"]
        if isinstance(venc_val, str):
            try:
                venc_val = datetime.strptime(venc_val, "%Y-%m-%d").date()
            except:
                venc_val = date.today()
        pata["vencimiento"] = col_venc.date_input(
            f"Venc. #{idx+1}", 
            value=venc_val, 
            key=f"leg_v_{idx}",
            label_visibility="collapsed"
        )
        
        # 7. Botón Borrar Pata (Estilizado como cruz roja en columna 7)
        if col_del.button("X", key=f"leg_del_{idx}"):
            patas_eliminar.append(idx)
            
    # Eliminar patas marcadas
    if patas_eliminar:
        for index in sorted(patas_eliminar, reverse=True):
            st.session_state["patas_opciones"].pop(index)
        st.rerun()
        
    # Añadir nueva pata
    col_add, _ = st.columns([1.5, 8.5])
    if col_add.button("➕ Añadir Pata", width="stretch"):
        if st.session_state["patas_opciones"]:
            nueva_pata = st.session_state["patas_opciones"][-1].copy()
        else:
            nueva_pata = {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 100.0, "right": "C", "vencimiento": date.today(), "precio_entrada": 1.0}
        st.session_state["patas_opciones"].append(nueva_pata)
        st.rerun()
        
    # Inject invisible JS iframe to dynamically classify option leg buttons in the parent DOM
    st.components.v1.html("""
    <script>
    (function() {
        const parentDoc = window.parent.document;
        function applyLegButtonStyles() {
            const rows = parentDoc.querySelectorAll('div[data-testid="stHorizontalBlock"]');
            rows.forEach(row => {
                const col1 = row.querySelector('> div:nth-child(1)');
                const col2 = row.querySelector('> div:nth-child(2)');
                if (!col1 || !col2) return;
                
                const actionButtons = col1.querySelectorAll('button[data-testid^="stBaseButton-segmented_control"]');
                const rightButtons = col2.querySelectorAll('button[data-testid^="stBaseButton-segmented_control"]');
                
                let hasSellActive = false;
                let hasBuyActive = false;
                
                actionButtons.forEach(button => {
                    const text = button.textContent.trim().toUpperCase();
                    const isActive = button.getAttribute('data-testid') === 'stBaseButton-segmented_controlActive' ||
                                     button.getAttribute('aria-checked') === 'true' || 
                                     button.getAttribute('aria-selected') === 'true' || 
                                     button.getAttribute('aria-pressed') === 'true' ||
                                     button.classList.contains('e1mwqyj913');
                    
                    if (text === 'SELL') {
                        button.classList.add('btn-sell');
                        if (isActive) hasSellActive = true;
                    } else if (text === 'BUY') {
                        button.classList.add('btn-buy');
                        if (isActive) hasBuyActive = true;
                    }
                });
                
                rightButtons.forEach(button => {
                    const text = button.textContent.trim().toUpperCase();
                    if (text === 'CALL') {
                        button.classList.add('btn-call');
                    } else if (text === 'PUT') {
                        button.classList.add('btn-put');
                    }
                });
                
                if (hasSellActive) {
                    row.classList.add('row-action-sell');
                    row.classList.remove('row-action-buy');
                } else if (hasBuyActive) {
                    row.classList.add('row-action-buy');
                    row.classList.remove('row-action-sell');
                } else {
                    row.classList.remove('row-action-sell', 'row-action-buy');
                }
            });
        }

        applyLegButtonStyles();
        
        if (!window.parent.legObserverAttached) {
            const observer = new MutationObserver(() => {
                applyLegButtonStyles();
            });
            observer.observe(parentDoc.body, { childList: true, subtree: true });
            window.parent.legObserverAttached = true;
        }
    })();
    </script>
    """, height=0, width=0)
        
    # --- GRÁFICO INTERACTIVO DE PLOTLY (SENSIVILIDAD Y VALOR TEMPORAL) ---
    if st.session_state["patas_opciones"]:
        st.divider()
        st.subheader("Análisis de Sensibilidad Teórico (Black-Scholes)")
        st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Mueve los deslizadores para ver el efecto del paso del tiempo y la volatilidad implícita en la curva teórica.</p>", unsafe_allow_html=True)
        
        c_sl1, c_sl2, c_sl3 = st.columns(3)
        vol_sim = c_sl1.slider("Volatilidad Implícita (σ)", min_value=5, max_value=150, value=25, step=5, format="%d%%", key="opt_vol_sim") / 100.0
        dias_sim = c_sl2.slider("Días al Vencimiento (T)", min_value=0, max_value=365, value=45, step=1, key="opt_dias_sim")
        tasa_sim = c_sl3.slider("Tasa Libre de Riesgo (r)", min_value=0.0, max_value=15.0, value=5.0, step=0.5, format="%.1f%%", key="opt_tasa_sim") / 100.0
        
        # Calcular límites del subyacente para el gráfico
        k_list = [float(p["strike"]) for p in st.session_state["patas_opciones"]]
        min_k, max_k = min(k_list), max(k_list)
        precio_medio_k = (min_k + max_k) / 2.0
        range_min = float(min_k * 0.75)
        range_max = float(max_k * 1.25)
        
        T_years = max(dias_sim / 365.0, 1e-5)
        
        # Calculamos curvas
        payoff_data = MotorBlackScholes.calcular_payoff_estrategia(
            patas=st.session_state["patas_opciones"],
            T=T_years,
            r=tasa_sim,
            sigma=vol_sim,
            precio_min=range_min,
            precio_max=range_max
        )
        
        # Calcular breakevens exactos por interpolación lineal (T=0)
        s_base = list(payoff_data["S"])
        pnl_base = list(payoff_data["pnl_vencimiento"])
        
        beps = []
        for i in range(len(pnl_base) - 1):
            s1, s2 = s_base[i], s_base[i+1]
            p1, p2 = pnl_base[i], pnl_base[i+1]
            if p1 * p2 <= 0:
                if p1 == 0:
                    beps.append(s1)
                elif p2 == 0:
                    continue
                else:
                    s_cross = s1 - p1 * (s2 - s1) / (p2 - p1)
                    beps.append(s_cross)
        
        # Eliminar duplicados muy cercanos para evitar solapamiento de etiquetas
        beps_filtrados = []
        for b in sorted(beps):
            if not beps_filtrados or b - beps_filtrados[-1] > 0.05:
                beps_filtrados.append(b)
                
        # Combinar e insertar los beps de forma ordenada en los arrays para unir los trazos en 0
        puntos_combinados = []
        for s_val, p_val in zip(s_base, pnl_base):
            puntos_combinados.append((s_val, p_val))
            
        for bep in beps_filtrados:
            inserted = False
            for idx, (s_val, p_val) in enumerate(puntos_combinados):
                if bep < s_val:
                    puntos_combinados.insert(idx, (bep, 0.0))
                    inserted = True
                    break
            if not inserted:
                puntos_combinados.append((bep, 0.0))
                
        S_sorted = [p[0] for p in puntos_combinados]
        pnl_sorted = [p[1] for p in puntos_combinados]
        
        # Separar en P&L ganadores (verde) y perdedores (rojo) para la curva T=0
        y_pos = [p_val if p_val >= 0 else None for p_val in pnl_sorted]
        y_neg = [p_val if p_val <= 0 else None for p_val in pnl_sorted]
        
        # Calcular límites del eje Y con un 15% de holgura considerando ambas curvas
        all_pnl_values = pnl_base + list(payoff_data["pnl_temporal"])
        min_pnl = min(all_pnl_values)
        max_pnl = max(all_pnl_values)
        pnl_range = max(1.0, max_pnl - min_pnl)
        y_min_limit = min_pnl - 0.15 * pnl_range
        y_max_limit = max_pnl + 0.15 * pnl_range
        
        fig = go.Figure()
        
        # Curva a vencimiento (T = 0) - Tramo Ganador (Verde con relleno verde)
        fig.add_trace(go.Scatter(
            x=S_sorted,
            y=y_pos,
            mode='lines',
            name='A Vencimiento (T=0)',
            line=dict(color='#10b981', width=3.5),
            fill='tozeroy',
            fillcolor='rgba(16, 185, 129, 0.2)',
            connectgaps=False
        ))
        
        # Curva a vencimiento (T = 0) - Tramo Perdedor (Rojo con relleno rojo)
        fig.add_trace(go.Scatter(
            x=S_sorted,
            y=y_neg,
            mode='lines',
            name='A Vencimiento (T=0)',
            line=dict(color='#f43f5e', width=3.5),
            fill='tozeroy',
            fillcolor='rgba(244, 63, 94, 0.2)',
            showlegend=False,
            connectgaps=False
        ))
        
        # Curva temporal actual (T > 0) - Azul
        fig.add_trace(go.Scatter(
            x=payoff_data["S"],
            y=payoff_data["pnl_temporal"],
            mode='lines',
            name=f'Valor Temporal (T={dias_sim} días)',
            line=dict(color='#6366f1', width=3)
        ))
        
        # Layout premium
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(
                title="Precio del Subyacente ($)",
                gridcolor='rgba(255,255,255,0.05)',
                zerolinecolor='rgba(255,255,255,0.1)',
                tickfont=dict(color="#94a3b8")
            ),
            yaxis=dict(
                title="P&L de la Estrategia ($)",
                gridcolor='rgba(255,255,255,0.05)',
                zerolinecolor='rgba(255,255,255,0.2)',
                tickfont=dict(color="#94a3b8"),
                range=[y_min_limit, y_max_limit]
            ),
            legend=dict(
                font=dict(color="#ffffff"),
                bgcolor='rgba(0,0,0,0)',
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='x unified',
            margin=dict(l=0, r=0, t=10, b=0)
        )
        
        # Línea horizontal en 0$ marcada en blanco
        fig.add_hline(y=0.0, line_dash="solid", line_color="#ffffff", line_width=1.5)
        
        # Líneas verticales para los Breakevens con etiquetas
        for bep in beps_filtrados:
            fig.add_vline(
                x=bep,
                line_color="#38bdf8",
                line_width=1.5,
                line_dash="solid",
                annotation_text=f"{bep:.2f}",
                annotation_position="top",
                annotation_font=dict(color="#38bdf8", size=11, family="Outfit")
            )
            
        # Línea vertical para el valor actual del subyacente (blanca punteada)
        precio_ref = st.session_state.get("precio_subyacente_opt")
        if precio_ref is None:
            precio_ref = precio_medio_k
            
        fig.add_vline(
            x=precio_ref,
            line_color="#ffffff",
            line_width=1.5,
            line_dash="dot",
            annotation_text=f"Actual: {precio_ref:.2f}" if st.session_state.get("precio_subyacente_opt") else f"Medio: {precio_ref:.2f}",
            annotation_position="bottom",
            annotation_font=dict(color="#ffffff", size=10, family="Outfit")
        )
        
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        
        # Cálculo de Greeks agregados teóricos (en el strike medio)
        precio_medio_k = (min_k + max_k) / 2.0
        delta_net = 0.0
        theta_net = 0.0
        vega_net = 0.0
        
        for p in st.session_state["patas_opciones"]:
            sign = 1 if p["accion"] == "BUY" else -1
            qty = int(p["cantidad"])
            g = MotorBlackScholes.calcular_greeks(
                S=precio_medio_k,
                K=float(p["strike"]),
                T=T_years,
                r=tasa_sim,
                sigma=vol_sim,
                tipo=p["right"]
            )
            # Las opciones de acciones controlan 100 acciones
            delta_net += sign * g["delta"] * qty * 100
            theta_net += sign * g["theta"] * qty * 100
            vega_net += sign * g["vega"] * qty * 100
            
        st.markdown(f"##### Greeks Teóricos Estimados (Evaluados a ${precio_medio_k:.2f})")
        col_g1, col_g2, col_g3 = st.columns(3)
        col_g1.metric("Delta Neto de Cartera (Δ)", f"{delta_net:.2f}", help="Sensibilidad respecto al precio del subyacente")
        col_g2.metric("Theta Neto Diario (Θ)", f"${theta_net:.2f}", help="Decaimiento temporal diario de la posición")
        col_g3.metric("Vega Neto (V)", f"${vega_net:.2f}", help="Sensibilidad respecto a cambios del 1% en Volatilidad")
        
        # --- PARÁMETROS ALGORÍTMICOS Y ENVÍO ---
        st.divider()
        st.subheader("Parámetros Algorítmicos y Envío")
        st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Configura el tipo de orden y las condiciones de entrada/salida que vigilará el Watchdog.</p>", unsafe_allow_html=True)

        # Tipo de orden + prima objetivo
        col_o1, col_o2, col_o3 = st.columns(3)
        with col_o1:
            opt_tipo_lmt = st.selectbox("Tipo de Orden", ["Crédito/Débito Neto", "Mercado"], key="opt_tipo_lmt")
        opt_precio_entrada = None
        if opt_tipo_lmt == "Crédito/Débito Neto":
            with col_o2:
                opt_precio_entrada = st.number_input(
                    "Prima de Entrada Objetivo ($ neto, crédito = + / débito = -)",
                    value=0.0, step=0.1, key="opt_prima_obj"
                )

        st.divider()

        # ── CONDICIONES DE ENTRADA ──────────────────────────────────────────
        st.subheader("Condiciones de Entrada Avanzadas")
        st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa las condiciones que deben cumplirse antes de que el Watchdog envíe la orden al mercado.</p>", unsafe_allow_html=True)

        _W  = [1.5, 0.7, 1.1, 0.9]
        _SP = "<div style='height:16px'></div>"

        # Fila: Ventana Horaria
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_horario = st.toggle("Ventana Horaria", value=False, key="opt_act_horario")
        if opt_act_horario:
            opt_tipo_horario = _c1.selectbox("", ["Rango", "Hora Fija"], key="opt_tipo_horario", label_visibility="collapsed")
            o_h_ini          = _c2.text_input("", value="15:45", key="opt_h_ini", label_visibility="collapsed")
            if opt_tipo_horario == "Rango":
                o_h_fin = _c3.text_input("", value="21:30", key="opt_h_fin", label_visibility="collapsed")
            else:
                try:
                    from datetime import timedelta
                    o_h_fin = (datetime.strptime(o_h_ini, "%H:%M") + timedelta(minutes=10)).strftime("%H:%M")
                except Exception:
                    o_h_fin = "23:59"
        else:
            o_h_ini, o_h_fin = "15:45", "21:30"
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Filtro VIX
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_vix = st.toggle("Filtro VIX", value=False, key="opt_act_vix")
        if opt_act_vix:
            opt_vix_op  = _c1.selectbox("", ["<", "<=", ">", ">="], key="opt_vix_op", label_visibility="collapsed")
            opt_vix_val = _c2.number_input("", min_value=1.0, value=20.0, step=0.5, key="opt_vix_val", label_visibility="collapsed")
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Filtro SMA
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_sma = st.toggle("Filtro SMA", value=False, key="opt_act_sma")
        if opt_act_sma:
            opt_sma_per = _c1.number_input("", min_value=5, value=200, step=5, key="opt_sma_per", label_visibility="collapsed")
            opt_sma_reg = _c2.selectbox("", ["Precio > SMA", "Precio < SMA"], key="opt_sma_reg", label_visibility="collapsed")
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Precio Disparador
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_precio = st.toggle("Precio Disparador", value=False, key="opt_act_precio")
        if opt_act_precio:
            opt_precio_op  = _c1.selectbox("", ["<=", ">="], key="opt_precio_op", label_visibility="collapsed")
            opt_precio_val = _c2.number_input("", min_value=0.0, value=100.0, step=0.5, key="opt_precio_val", label_visibility="collapsed")
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Frecuencia (siempre visible)
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            st.markdown("<p style='margin-top:8px; color:#94a3b8; font-size:0.88rem;'>Frecuencia</p>", unsafe_allow_html=True)
        opt_frecuencia = _c1.selectbox("", ["Única", "Diaria", "Semanal"], key="opt_frecuencia", label_visibility="collapsed")

        st.divider()

        # ── CONDICIONES DE SALIDA ───────────────────────────────────────────
        st.subheader("Condiciones de Salida Avanzadas")
        st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa y configura las reglas de gestión de riesgo que vigilará el Watchdog de Salidas.</p>", unsafe_allow_html=True)

        _W  = [1.5, 0.7, 1.1, 0.9]
        _SP = "<div style='height:16px'></div>"

        # Fila: Stop Loss / Take Profit
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_sl_tp = st.toggle("Stop Loss / Take Profit", value=False, key="opt_act_sl_tp")
        if opt_act_sl_tp:
            opt_stop_loss   = _c1.number_input("", value=-300.0, step=10.0, key="opt_sl_val", label_visibility="collapsed")
            opt_take_profit = _c2.number_input("", value=600.0, step=10.0, key="opt_tp_val", label_visibility="collapsed")
            opt_dest_gestion = _c3.selectbox("", ["App (Watchdog)", "IBKR (Broker)"], key="opt_dest_gestion", label_visibility="collapsed")
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Cerrar por VIX
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_vix_sal = st.toggle("Cerrar por VIX", value=False, key="opt_act_vix_sal")
        if opt_act_vix_sal:
            opt_vix_max = _c1.number_input("", min_value=1.0, value=28.0, step=0.5, key="opt_vix_max", label_visibility="collapsed")
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Cerrar por SMA
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_sma_sal = st.toggle("Cerrar por SMA", value=False, key="opt_act_sma_sal")
        if opt_act_sma_sal:
            opt_sma_per_sal = _c1.number_input("", min_value=5, value=200, step=5, key="opt_sma_per_sal", label_visibility="collapsed")
            opt_sma_reg_sal = _c2.selectbox("", ["Precio < SMA", "Precio > SMA"], key="opt_sma_reg_sal", label_visibility="collapsed")
        st.markdown(_SP, unsafe_allow_html=True)

        # Fila: Hora Forzada
        _c0, _c1, _c2, _c3 = st.columns(_W)
        with _c0:
            opt_act_hora_sal = st.toggle("Hora Forzada", value=False, key="opt_act_hora_sal")
        if opt_act_hora_sal:
            opt_hora_sal = _c1.text_input("", value="21:45", key="opt_hora_sal", label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)
        submit_opt = st.button("Encolar Estrategia Opciones", width="stretch", key="btn_encolar_opciones")

        if submit_opt:
            # Serializamos las patas
            patas_serializadas = []
            for p in st.session_state["patas_opciones"]:
                p_copy = p.copy()
                if isinstance(p_copy["vencimiento"], date):
                    p_copy["vencimiento"] = p_copy["vencimiento"].strftime('%Y-%m-%d')
                patas_serializadas.append(p_copy)

            # Construimos condiciones de entrada
            opt_cond_ent = {}
            if opt_act_horario:
                opt_cond_ent["horario"] = {"activo": True, "hora_inicio": o_h_ini, "hora_fin": o_h_fin}
            if opt_act_vix:
                opt_cond_ent["vix"] = {"activo": True, "valor": float(opt_vix_val), "operador": opt_vix_op}
            if opt_act_sma:
                opt_cond_ent["sma"] = {"activo": True, "periodo": int(opt_sma_per), "regla": opt_sma_reg}
            if opt_act_precio:
                opt_cond_ent["precio_disparador"] = {"activo": True, "valor": float(opt_precio_val), "operador": opt_precio_op}
            opt_cond_ent["frecuencia"] = {"activo": (opt_frecuencia != "Única"), "tipo": opt_frecuencia}

            # Construimos condiciones de salida
            opt_cond_sal = {}
            if opt_act_sl_tp:
                opt_cond_sal["stop_loss"] = float(opt_stop_loss)
                opt_cond_sal["take_profit"] = float(opt_take_profit)
                opt_cond_sal["gestion"] = opt_dest_gestion
            if opt_act_vix_sal:
                opt_cond_sal["vix_maximo"] = float(opt_vix_max)
            if opt_act_sma_sal:
                opt_cond_sal["sma"] = {"activo": True, "periodo": int(opt_sma_per_sal), "regla": opt_sma_reg_sal}
            if opt_act_hora_sal:
                opt_cond_sal["cierre_horario"] = opt_hora_sal

            tipo_act_est = "BAG" if len(patas_serializadas) > 1 else "OPTION"

            try:
                est_id = db.crear_estrategia(
                    ticker=opt_ticker,
                    tipo_activo=tipo_act_est,
                    estado="PENDIENTE_ENTRADA",
                    patas=patas_serializadas,
                    condiciones_entrada=opt_cond_ent if opt_cond_ent else None,
                    condiciones_salida=opt_cond_sal if opt_cond_sal else None,
                    precio_entrada=opt_precio_entrada
                )

                st.success(f"🚀 Estrategia de opciones #{est_id} encolada correctamente en estado PENDIENTE_ENTRADA.")
                db.registrar_evento("CREACION_ESTRATEGIA_UI", f"Estrategia #{est_id} de opciones ({opt_ticker}) encolada.")

                enviar_alerta_webhook(
                    titulo="📥 Nueva Estrategia Encolada (Opciones)",
                    mensaje=f"**ID:** {est_id}\n**Ticker:** {opt_ticker}\n**Tipo:** {tipo_act_est}\n**Patas:** {len(patas_serializadas)} patas\n**Precio Objetivo:** {opt_precio_entrada if opt_precio_entrada else 'Mercado'}\n**Frecuencia:** {opt_frecuencia}",
                    color="info"
                )
            except Exception as e:
                st.error(f"Error al guardar estrategia: {e}")


# ==========================================
# TAB 4: MONITORIZACIÓN & CONTROL ROOM
# ==========================================
with tabs[3]:
    st.header("Consola de Control Algorítmico (Control Room)")
    
    # 1. Muestra Estrategias Activas
    st.subheader("Estrategias Activas")
    
    @st.fragment(run_every=15)
    def render_estrategias_activas():
        estrategias_activas = db.obtener_estrategias(estado="ACTIVA")
        
        if not estrategias_activas:
            st.info("No hay estrategias ACTIVAS ejecutándose actualmente en el mercado.")
        else:
            now = time.time()
            last_pnl_fetch = st.session_state.get('last_pnl_fetch_time', 0)
            
            if 'cache_pnl_estrategias' not in st.session_state:
                st.session_state['cache_pnl_estrategias'] = {}
                
            necesita_fetch = (now - last_pnl_fetch) >= 14 or any(est['id'] not in st.session_state['cache_pnl_estrategias'] for est in estrategias_activas)
            
            if conectado and necesita_fetch:
                for est in estrategias_activas:
                    try:
                        pnl_val = st.session_state.broker.calcular_pnl_estrategia(
                            ticker=est["ticker"],
                            tipo_activo=est["tipo_activo"],
                            patas=est["patas"]
                        )
                        st.session_state['cache_pnl_estrategias'][est['id']] = pnl_val
                    except Exception as e_pnl:
                        print(f"Error al calcular P&L para estrategia #{est['id']}: {e_pnl}")
                        st.session_state['cache_pnl_estrategias'][est['id']] = None
                st.session_state['last_pnl_fetch_time'] = now
                
            # Mostramos tarjetas premium para cada estrategia activa
            for est in estrategias_activas:
                ticker = est["ticker"]
                tipo_activo = est["tipo_activo"]
                condiciones_salida = est.get("condiciones_salida") or {}
                
                pnl = None
                pnl_str = "Offline (N/A)"
                pnl_color = "#94a3b8"  # Slate / gris
                
                # Intentamos obtener P&L de la cache si el broker está conectado
                if conectado:
                    pnl = st.session_state['cache_pnl_estrategias'].get(est['id'])
                    if pnl is not None:
                        pnl_color = "#10b981" if pnl >= 0 else "#ef4444"  # Verde o Rojo
                        pnl_str = f"${pnl:+.2f}"
                    else:
                        pnl_str = "Sin datos de posición"
                
                # Info de SL y TP
                sl_val = condiciones_salida.get("stop_loss")
                tp_val = condiciones_salida.get("take_profit")
                
                sl_tp_info = ""
                if sl_val is not None or tp_val is not None:
                    sl_tp_info = "<div style='margin-top: 10px; font-size: 0.9rem; color: #94a3b8; display: flex; flex-wrap: wrap; gap: 20px;'>"
                    if sl_val is not None:
                        dist_sl = ""
                        if pnl is not None:
                            dist = pnl - float(sl_val)
                            dist_sl = f" (Margen: ${dist:.2f})"
                        sl_tp_info += f"<span>🔴 <b>Stop Loss:</b> ${sl_val}{dist_sl}</span>"
                    if tp_val is not None:
                        dist_tp = ""
                        if pnl is not None:
                            dist = float(tp_val) - pnl
                            dist_tp = f" (Falta: ${dist:.2f})"
                        sl_tp_info += f"<span>🟢 <b>Take Profit:</b> ${tp_val}{dist_tp}</span>"
                    sl_tp_info += "</div>"

                with st.container(key=f"strategy_card_{est['id']}"):
                    col_info, col_status = st.columns([3.5, 1.5])
                    
                    with col_info:
                        st.markdown(f"""
                        <h4 style='margin: 0; color: #6366f1;'>#{est['id']} - {est['ticker']} ({est['tipo_activo']})</h4>
                        <div style='margin-top: 10px; display: flex; gap: 40px; font-size: 0.95rem; color: #cbd5e1;'>
                            <p style='margin: 0;'><b>Creada:</b> {est['fecha_creacion'][:19].replace('T', ' ')}</p>
                            <p style='margin: 0;'><b>Precio Entrada:</b> ${est['precio_entrada'] if est['precio_entrada'] is not None else '—'}</p>
                        </div>
                        {sl_tp_info}
                        """, unsafe_allow_html=True)
                    
                    with col_status:
                        st.markdown(f"""
                        <div style='display: flex; flex-direction: column; gap: 8px; align-items: flex-end;'>
                            <span style='background-color: {pnl_color}22; color: {pnl_color}; border: 1px solid {pnl_color}44; padding: 4px 10px; border-radius: 8px; font-weight: bold; font-size: 0.9rem; display: inline-block; text-align: center; width: fit-content;'>P&L: {pnl_str}</span>
                            <span style='background-color: #10b981; color: white; padding: 4px 10px; border-radius: 8px; font-weight: bold; font-size: 0.8rem; display: inline-block; text-align: center; width: fit-content;'>ACTIVA</span>
                        </div>
                        <div style='height: 12px;'></div>
                        """, unsafe_allow_html=True)
                        
                        if st.button(f"🛑 Cierre Forzado Manual", key=f"cierre_man_{est['id']}"):
                            with st.spinner("Enviando orden de cierre forzado manual..."):
                                try:
                                    if conectado:
                                        broker_res = st.session_state.broker.enviar_orden_cierre_generica(
                                            ticker=est["ticker"],
                                            tipo_activo=est["tipo_activo"],
                                            patas=est["patas"]
                                        )
                                        order_id_cierre = broker_res["order_id"]
                                    else:
                                        order_id_cierre = random.randint(100000, 999999)
                                        
                                    db.actualizar_estado_estrategia(
                                        estrategia_id=est["id"],
                                        nuevo_estado="CERRADA_MANUAL",
                                        order_id_salida=order_id_cierre,
                                        precio_salida=0.0,
                                        pnl_realizado=pnl if pnl is not None else 0.0,
                                        fecha_cierre=datetime.now().isoformat()
                                    )
                                    db.registrar_evento("CIERRE_MANUAL_UI", f"Estrategia #{est['id']} ({est['ticker']}) cerrada por el operador desde UI.")
                                    enviar_alerta_webhook(
                                        titulo="🛑 Estrategia Cerrada Manualmente (UI)",
                                        mensaje=f"**ID:** {est['id']}\n**Ticker:** {est['ticker']}\n**Motivo:** Acción del operador",
                                        color="warning"
                                    )
                                    st.success("Posición cerrada con éxito.")
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Fallo al cerrar posición: {ex}")
                                    
                    with st.expander(f"Ver detalle de patas y reglas de la estrategia #{est['id']}"):
                        st.json({"patas": est["patas"], "condiciones_entrada": est["condiciones_entrada"], "condiciones_salida": est["condiciones_salida"]})
                    
                                
    render_estrategias_activas()
    
    st.divider()
    
    # 2. Formulario de Mutación en Caliente (Hot-Reloading SL/TP)
    st.subheader("Modificación de Límites en Caliente")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Modifica instantáneamente los umbrales de Stop Loss y Take Profit de las estrategias activas. El Watchdog cargará los nuevos valores en su próximo ciclo de evaluación.</p>", unsafe_allow_html=True)
    
    todas_estrategias = db.obtener_estrategias()
    est_activas_list = [e for e in todas_estrategias if e["estado"] == "ACTIVA"]
    
    if not est_activas_list:
        st.info("No hay estrategias activas disponibles para modificar límites.")
    else:
        opciones_dropdown = {f"Estrategia #{e['id']} - {e['ticker']} ({e['tipo_activo']})": e["id"] for e in est_activas_list}
        seleccionada_label = st.selectbox("Selecciona la Estrategia Activa", list(opciones_dropdown.keys()))
        est_id_select = opciones_dropdown[seleccionada_label]
        
        # Recuperamos la estrategia seleccionada
        estrategia_sel = next(e for e in est_activas_list if e["id"] == est_id_select)
        condiciones_salida_sel = estrategia_sel.get("condiciones_salida") or {}
        
        current_sl = condiciones_salida_sel.get("stop_loss", -100.0)
        current_tp = condiciones_salida_sel.get("take_profit", 200.0)
        
        col_m1, col_m2 = st.columns(2)
        new_sl = col_m1.number_input("Nuevo Stop Loss ($ absoluto, ej. -150.0)", value=float(current_sl), step=10.0)
        new_tp = col_m2.number_input("Nuevo Take Profit ($ absoluto, ej. 350.0)", value=float(current_tp), step=10.0)
        
        if st.button("💾 Actualizar Límites", type="primary"):
            try:
                res_mut = db.actualizar_limites_sl_tp(estrategia_id=est_id_select, stop_loss=new_sl, take_profit=new_tp)
                if res_mut:
                    st.success("¡Límites actualizados en la base de datos! El Watchdog cargará los nuevos límites en su siguiente ciclo.")
                    db.registrar_evento("MUTACION_LIMITES_UI", f"Modificados límites en caliente para #{est_id_select}. SL: {new_sl}$, TP: {new_tp}$.")
                    enviar_alerta_webhook(
                        titulo="🔄 Límites de Riesgo Modificados",
                        mensaje=f"**ID Estrategia:** {est_id_select}\n**Nuevo Stop Loss:** {new_sl}$\n**Nuevo Take Profit:** {new_tp}$",
                        color="warning"
                    )
                    st.rerun()
                else:
                    st.error("No se pudo actualizar los límites de la estrategia.")
            except Exception as e:
                st.error(f"Error al mutar límites: {e}")
                
    st.divider()
    
    # 3. MOCKS DE SIMULACIÓN SANDBOX (HITO 4)
    with st.expander("Ecosistema de Pruebas Offline (TFG Sandbox Simulator)"):
        st.markdown("<p style='color:#94a3b8;'>Simula los eventos de mercado y los flujos de los Watchdogs de manera interactiva sin conexión al broker real.</p>", unsafe_allow_html=True)
        
        estrategias_todas_list = db.obtener_estrategias()
        
        if not estrategias_todas_list:
            st.warning("No hay estrategias en base de datos. Crea una estrategia en los Tabs de Opciones/Acciones para simular.")
        else:
            opciones_mock_dict = {f"#{e['id']} - {e['ticker']} ({e['tipo_activo']}) [{e['estado']}]": e["id"] for e in estrategias_todas_list}
            label_mock_select = st.selectbox("Selecciona Estrategia a Simular", list(opciones_mock_dict.keys()))
            est_id_mock = opciones_mock_dict[label_mock_select]
            est_mock_data = next(e for e in estrategias_todas_list if e["id"] == est_id_mock)
            
            c_mock1, c_mock2, c_mock3 = st.columns(3)
            
            # Simular Entrada
            if est_mock_data["estado"] == "PENDIENTE_ENTRADA":
                if c_mock1.button("🟢 Simular Activación (Entrada OK)", width="stretch"):
                    db.actualizar_estado_estrategia(
                        estrategia_id=est_id_mock,
                        nuevo_estado="ACTIVA",
                        order_id_entrada=random.randint(100000, 999999),
                        precio_entrada=est_mock_data["precio_entrada"] or 150.0,
                        fecha_ejecucion=datetime.now().isoformat()
                    )
                    db.registrar_evento("SANDBOX_MOCK_ENTRADA", f"Simulada entrada autorizada para Estrategia #{est_id_mock}.")
                    enviar_alerta_webhook(
                        titulo="🚀 Estrategia Lanzada (Sandbox Mock)",
                        mensaje=f"**ID:** {est_id_mock}\n**Ticker:** {est_mock_data['ticker']}\n**Estado:** ACTIVA (Simulación)",
                        color="success"
                    )
                    st.success("Simulación de entrada realizada. Recargando...")
                    st.rerun()
            else:
                c_mock1.markdown("<small style='color:#64748b;'>Simular Entrada (Deshabilitado: ya activa o cerrada)</small>", unsafe_allow_html=True)
                
            # Simular Cierre TP
            if est_mock_data["estado"] == "ACTIVA":
                if c_mock2.button("🟢 Simular Cierre Take Profit", width="stretch"):
                    tp_val_mock = est_mock_data.get("condiciones_salida", {}).get("take_profit", 100.0)
                    db.actualizar_estado_estrategia(
                        estrategia_id=est_id_mock,
                        nuevo_estado="CERRADA_TAKE_PROFIT",
                        order_id_salida=random.randint(100000, 999999),
                        precio_salida=0.0,
                        pnl_realizado=float(tp_val_mock),
                        fecha_cierre=datetime.now().isoformat()
                    )
                    db.registrar_evento("SANDBOX_MOCK_SALIDA_TP", f"Simulado cierre por Take Profit para Estrategia #{est_id_mock}. PnL: {tp_val_mock}$.")
                    enviar_alerta_webhook(
                        titulo="🛑 Estrategia Cerrada (Sandbox TP)",
                        mensaje=f"**ID:** {est_id_mock}\n**Ticker:** {est_mock_data['ticker']}\n**Motivo:** TAKE_PROFIT (Simulado)\n**P&L Realizado:** {tp_val_mock}$",
                        color="success"
                    )
                    st.success("Simulación de cierre por TP realizada.")
                    st.rerun()
                    
                # Simular Cierre SL
                if c_mock3.button("🔴 Simular Cierre Stop Loss", width="stretch"):
                    sl_val_mock = est_mock_data.get("condiciones_salida", {}).get("stop_loss", -100.0)
                    db.actualizar_estado_estrategia(
                        estrategia_id=est_id_mock,
                        nuevo_estado="CERRADA_STOP_LOSS",
                        order_id_salida=random.randint(100000, 999999),
                        precio_salida=0.0,
                        pnl_realizado=float(sl_val_mock),
                        fecha_cierre=datetime.now().isoformat()
                    )
                    db.registrar_evento("SANDBOX_MOCK_SALIDA_SL", f"Simulado cierre por Stop Loss para Estrategia #{est_id_mock}. PnL: {sl_val_mock}$.")
                    enviar_alerta_webhook(
                        titulo="🛑 Estrategia Cerrada (Sandbox SL)",
                        mensaje=f"**ID:** {est_id_mock}\n**Ticker:** {est_mock_data['ticker']}\n**Motivo:** STOP_LOSS (Simulado)\n**P&L Realizado:** {sl_val_mock}$",
                        color="error"
                    )
                    st.success("Simulación de cierre por SL realizada.")
                    st.rerun()
            else:
                c_mock2.markdown("<small style='color:#64748b;'>Simular TP (Deshabilitado: no activa)</small>", unsafe_allow_html=True)
                c_mock3.markdown("<small style='color:#64748b;'>Simular SL (Deshabilitado: no activa)</small>", unsafe_allow_html=True)

    st.divider()
    
    # 4. Historial Completo y Descarga CSV
    st.subheader("Historial de Estrategias y Registro de Auditoría")
    
    df_est_hist = db.obtener_estrategias_df()
    if not df_est_hist.empty:
        # Convertir columnas complejas a strings JSON para evitar errores de PyArrow
        for col in ["patas", "condiciones_entrada", "condiciones_salida"]:
            if col in df_est_hist.columns:
                df_est_hist[col] = df_est_hist[col].apply(lambda x: json.dumps(x) if isinstance(x, (dict, list)) else str(x))
    df_audit_logs = db.obtener_logs(limit=100)
    
    # Tablas de datos
    tab_est, tab_aud = st.tabs(["Listado de Estrategias", "Registro de Auditoría (Logs)"])
    
    with tab_est:
        if df_est_hist.empty:
            st.info("No hay registros en el historial de estrategias.")
        else:
            st.dataframe(df_est_hist, width="stretch", hide_index=True)
            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
            csv_est = df_est_hist.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Historial de Estrategias (CSV)",
                data=csv_est,
                file_name="historial_estrategias_tfg.csv",
                mime="text/csv",
                use_container_width=False,
                key="btn_dl_est"
            )
            
    with tab_aud:
        if df_audit_logs.empty:
            st.info("No hay eventos registrados en la auditoría.")
        else:
            st.dataframe(df_audit_logs, width="stretch", hide_index=True)
            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
            csv_audit = df_audit_logs.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Logs de Auditoría (CSV)",
                data=csv_audit,
                file_name="logs_auditoria_tfg.csv",
                mime="text/csv",
                use_container_width=False,
                key="btn_dl_aud"
            )
