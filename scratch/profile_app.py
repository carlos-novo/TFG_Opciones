import time

t0 = time.time()
import streamlit as st
print(f"Importing streamlit: {time.time() - t0:.4f}s")

t0 = time.time()
from conexion_ibkr import GestorIBKR
from motor_logica import MotorEstrategias, MotorSalida
from base_datos import GestorBaseDatos
from motor_bs import MotorBlackScholes
from notificaciones import enviar_alerta_webhook
from watchdogs import iniciar_watchdog_entradas, iniciar_watchdog_salidas, detener_watchdogs
print(f"Importing app modules: {time.time() - t0:.4f}s")

t0 = time.time()
db = GestorBaseDatos()
print(f"DB init: {time.time() - t0:.4f}s")

t0 = time.time()
# Mock streamlit session state to simulate authenticated run
st.session_state['autenticado'] = True
st.session_state.broker = GestorIBKR(port=4002)
st.session_state['posiciones_cartera'] = None
print(f"Session state init: {time.time() - t0:.4f}s")

t0 = time.time()
# Check connection status
conectado = st.session_state.broker.esta_conectado()
print(f"Checking connection status (esta_conectado): {time.time() - t0:.4f}s")

t0 = time.time()
# Simulate fetching strategies
estrategias_activas = db.obtener_estrategias(estado="ACTIVA")
print(f"Fetching active strategies from DB: {time.time() - t0:.4f}s")
