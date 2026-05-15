import streamlit as st
import hashlib
from datetime import date
import threading
import time
from conexion_ibkr import GestorIBKR
from motor_logica import MotorEstrategias
from base_datos import GestorBaseDatos
from motor_bs import MotorBlackScholes
from notificaciones import enviar_alerta_webhook
import socket

db = GestorBaseDatos()

# --- HILO DE POLLING ASÍNCRONO (DÍA 8) ---
@st.cache_resource
def iniciar_hilo_polling():
    """Lanza el hilo de polling en background para órdenes (solo 1 vez por sesión global)."""
    db_poll = GestorBaseDatos()
    broker_poll = GestorIBKR()
    
    def worker():
        while True:
            try:
                df_ops = db_poll.obtener_operaciones()
                if df_ops is not None and not df_ops.empty:
                    # Filtramos las órdenes que aún no son finales
                    pendientes = df_ops[~df_ops['status'].isin(['Filled', 'Cancelled', 'Inactive'])]
                    if not pendientes.empty:
                        estados_actuales = broker_poll.consultar_estado_ordenes()
                        for _, row in pendientes.iterrows():
                            oid = row['order_id']
                            estado_anterior = row['status']
                            
                            if oid in estados_actuales:
                                nuevo_estado = estados_actuales[oid]
                                if nuevo_estado != estado_anterior:
                                    db_poll.actualizar_estado_orden(oid, nuevo_estado)
                                    db_poll.registrar_evento('POLLING_ACTUALIZACION', f"Orden #{oid}: {estado_anterior} -> {nuevo_estado}")
                                    if nuevo_estado in ['Filled', 'Cancelled']:
                                        color = "success" if nuevo_estado == 'Filled' else "warning"
                                        enviar_alerta_webhook(f"Actualización de Orden #{oid}", f"Estado cambiado de {estado_anterior} a **{nuevo_estado}**", color)
                            else:
                                # Si no está en OpenOrders ni en Executions, IBKR la ha destruido (ej. rechazo instantáneo)
                                db_poll.actualizar_estado_orden(oid, 'Cancelled')
                                db_poll.registrar_evento('POLLING_ACTUALIZACION', f"Orden #{oid}: {estado_anterior} -> Cancelled (Purgada por IBKR)")
            except Exception as e:
                print(f"Hilo de polling: Error -> {e}")
            
            # Polling cada 10 segundos (no bloquea UI)
            time.sleep(10)

    hilo = threading.Thread(target=worker, daemon=True)
    hilo.start()
    return hilo

# Instanciamos el hilo al arrancar la app
hilo_polling = iniciar_hilo_polling()

# --- HILO WATCHDOG Y COLA DE REINTENTOS (DÍAS 10-11) ---
@st.cache_resource
def iniciar_hilo_watchdog():
    """Lanza el hilo watchdog para comprobar la salud TCP y despachar reintentos."""
    db_wd = GestorBaseDatos()
    broker_wd = GestorIBKR()
    
    def worker():
        estado_previo = True
        while True:
            try:
                # 1. Comprobación de salud TCP (Capa 4)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    resultado = s.connect_ex(('127.0.0.1', 4002))
                    estado_actual = (resultado == 0)
                
                if estado_previo and not estado_actual:
                    db_wd.registrar_evento("WATCHDOG_ALERTA", "Pérdida de conexión TCP con IBKR Gateway (Puerto 4002)")
                elif not estado_previo and estado_actual:
                    db_wd.registrar_evento("WATCHDOG_INFO", "Conexión TCP recuperada con IBKR Gateway")
                
                # 2. Procesar cola de reintentos SIEMPRE que haya conexión (Capa 7)
                if estado_actual:
                    df_cola = db_wd.obtener_reintentos_pendientes()
                    if df_cola is not None and not df_cola.empty:
                        db_wd.registrar_evento("WATCHDOG_INFO", f"Procesando {len(df_cola)} órdenes en cola...")
                        from datetime import datetime
                        for _, row in df_cola.iterrows():
                            try:
                                v_date = datetime.strptime(row['vencimiento'], '%Y%m%d').date()
                                strikes = [row['put_long'], row['put_short'], row['call_short'], row['call_long']]
                                res = broker_wd.enviar_orden_iron_condor(row['ticker'], v_date, strikes, row['credito'])
                                
                                # Recuperación exitosa
                                metricas_dummy = {'max_beneficio': 0, 'max_riesgo': 0, 'ratio_rb': 0}
                                db_wd.registrar_operacion(res['order_id'], row['ticker'], v_date, strikes, row['credito'], metricas_dummy, res['status'])
                                db_wd.marcar_reintento_procesado(row['id'], 'SENT')
                                db_wd.registrar_evento("ORDEN_RECUPERADA", f"Orden encolada enviada al Gateway. OrderId: {res['order_id']}")
                                enviar_alerta_webhook(
                                    "🔄 Orden Recuperada por el Watchdog", 
                                    f"El sistema ha recuperado la conexión y ha enviado con éxito la orden encolada de **{row['ticker']}**.\n**OrderId:** {res['order_id']}", 
                                    "success"
                                )
                            except Exception as e:
                                intentos_act = db_wd.incrementar_intentos(row['id'])
                                if intentos_act >= 3:
                                    db_wd.marcar_reintento_procesado(row['id'], 'FAILED')
                                    db_wd.registrar_evento("WATCHDOG_ERROR", f"Orden {row['ticker']} descartada (Poison Pill). Excedió 3 intentos.")
                                    enviar_alerta_webhook("🚨 Alerta de Poison Pill", f"La orden encolada de **{row['ticker']}** ha sido descartada permanentemente tras 3 intentos fallidos de conexión con el bróker. Verifica los contratos.", "error")
                                else:
                                    pass # Se reintenta en el siguiente ciclo
                
                estado_previo = estado_actual
            except Exception as e:
                print(f"Error en Watchdog: {e}")
                
            time.sleep(5)
            
    hilo = threading.Thread(target=worker, daemon=True)
    hilo.start()
    return hilo

hilo_watchdog = iniciar_hilo_watchdog()

# --- 0. CONFIGURACIÓN DE PÁGINA (Debe ser el primer comando de Streamlit) ---
st.set_page_config(page_title="Plataforma de Trading", layout="wide")

# --- 1. LÓGICA DE SEGURIDAD Y ENCRIPTACIÓN ---
# Usuario: admin | Contraseña para generar el hash: admin2026
ADMIN_USER = "admin"
ADMIN_PASSWORD_HASH = "6051fc84a7a0d74c225fb18a496b09952da5642e60723ecae543298edd7d82d6"

def verificar_credenciales(usuario, password):
    """Encripta la contraseña introducida y la compara con el hash seguro."""
    hash_input = hashlib.sha256(password.encode()).hexdigest()
    return usuario == ADMIN_USER and hash_input == ADMIN_PASSWORD_HASH

# Inicializamos la variable de sesión para el control de acceso
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False


# --- 2. BARRERA DE ENTRADA (PANTALLA DE LOGIN) ---
if not st.session_state['autenticado']:
    
    # Usamos columnas para centrar el formulario de login en la pantalla
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col2:
        st.title("🔐 Acceso Restringido")
        st.info("Introduce tus credenciales para acceder al sistema algorítmico.")
        
        with st.form("login_form"):
            user_input = st.text_input("Usuario")
            pass_input = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Entrar al Sistema")
            
            if submit_login:
                if verificar_credenciales(user_input, pass_input):
                    st.session_state['autenticado'] = True
                    # --- REGISTRO EN BD ---
                    db.registrar_evento("LOGIN_EXITOSO", f"Usuario '{user_input}' ha accedido al sistema.")
                    st.rerun() # Fuerza la recarga para pasar la barrera
                else:
                    st.error("Credenciales incorrectas. Acceso denegado.")
    
    # st.stop() detiene la ejecución del script aquí. 
    # El código del bróker que hay debajo NO se ejecutará si no hay login.
    st.stop() 


# =====================================================================
# --- 3. APLICACIÓN PRINCIPAL (SOLO ACCESIBLE SI AUTENTICADO == TRUE) ---
# =====================================================================

# Inicializamos la clase gestora en el estado de la sesión para no perderla en las recargas
if 'broker' not in st.session_state:
    st.session_state.broker = GestorIBKR(port=4002) # Cambiar a 4002 si usas Gateway puro
if 'precio_test' not in st.session_state:
    st.session_state.precio_test = None

# --- BARRA LATERAL (SIDEBAR) ---
st.sidebar.title("Configuración de Red")

# Botón de Cerrar Sesión añadido en la parte superior del sidebar
if st.sidebar.button("🚪 Cerrar Sesión", width='stretch'):
    st.session_state['autenticado'] = False
    if st.session_state.broker.esta_conectado():
        st.session_state.broker.desconectar()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Prueba de Conectividad")

# Lógica del botón de conexión
if st.sidebar.button("Alternar Conexión al Bróker"):
    if st.session_state.broker.esta_conectado():
        st.session_state.broker.desconectar()
    else:
        st.session_state.broker.conectar()
    st.rerun() # Fuerza la recarga para actualizar los indicadores visuales

# Indicador visual de estado
conectado = st.session_state.broker.esta_conectado()
color = "🟢" if conectado else "🔴"
texto_estado = "Conectado" if conectado else "Desconectado"
st.sidebar.metric(label="Estado IBKR", value=f"{color} {texto_estado}")

# Campo para elegir qué ticker probar
ticker_test = st.sidebar.text_input("Ticker a probar", value="SPY", max_chars=5).upper()

if st.sidebar.button("Probar Datos de Mercado"):
    if conectado:
        with st.sidebar.status("Consultando bróker...", expanded=False) as status:
            precio = st.session_state.broker.obtener_precio_prueba(ticker_test)
            
            if precio:
                status.update(label=f"¡Éxito! {ticker_test}: ${precio}", state="complete")
                st.sidebar.success(f"Último precio de {ticker_test}: **${precio}**")
            else:
                status.update(label="Fallo en la consulta", state="error")
                st.sidebar.error("No se recibió precio. Verifica que el ticker es válido.")
    else:
        st.sidebar.warning("⚠️ Debes estar conectado para probar datos.")


# --- ÁREA PRINCIPAL ---
st.title("Panel de Control - Algorítmico de Opciones")

tabs = st.tabs(["📊 Dashboard", "⚙️ Nueva Estrategia", "📈 Monitorización", "🧪 Backtest Visual"])

with tabs[1]:
    st.header("Definición de Estrategia: Iron Condor")
    
    with st.form("form_iron_condor"):
        # 1. PARÁMETROS DEL ACTIVO
        col1, col2 = st.columns(2)
        ticker = col1.text_input("Ticker del Subyacente", value="SPX")
        vencimiento = col2.date_input("Fecha de Vencimiento")
        
        st.divider()
        st.subheader("Configuración de las Patas (Strikes)")
        c1, c2, c3, c4 = st.columns(4)
        put_long = c1.number_input("Put Long", step=5.0, value=4800.0)
        put_short = c2.number_input("Put Short", step=5.0, value=4900.0)
        call_short = c3.number_input("Call Short", step=5.0, value=5100.0)
        call_long = c4.number_input("Call Long", step=5.0, value=5200.0)
        
        st.divider()
        # 2. PARÁMETROS BLACK-SCHOLES Y ALGORÍTMICOS
        with st.expander("🧮 Parámetros Black-Scholes (Para Griegas y Heatmap)"):
            c_bs1, c_bs2 = st.columns(2)
            volatilidad = c_bs1.slider("Volatilidad Implícita (σ)", min_value=0.05, max_value=0.50, value=0.15, step=0.01)
            tasa_riesgo = c_bs2.slider("Tasa Libre de Riesgo (r)", min_value=0.0, max_value=0.10, value=0.05, step=0.01)

        with st.expander("🛠️ Condiciones Algorítmicas (Análisis Técnico)"):
            st.write("Configura el cruce de Medias Móviles (SMA) para condicionar la entrada.")
            col_at1, col_at2 = st.columns(2)
            activar_sma = col_at1.checkbox("Activar Condición SMA")
            periodo_n = col_at2.number_input("Periodo N días", min_value=1, value=200, step=10)
            tipo_cruce = st.selectbox("Regla de Ejecución", [
                "Entrar si Precio > SMA", 
                "Entrar si Precio < SMA"
            ])

        # 3. ENVÍO DEL FORMULARIO Y LÓGICA DEL MOTOR
        submit = st.form_submit_button("Lanzar Estrategia")
        
    # Lógica de procesamiento tras el envío del formulario
    if submit:
        if not conectado:
            st.error("⚠️ Error: El sistema debe estar conectado al Gateway para lanzar estrategias.")
        else:
            # Iniciamos el contenedor de estado para la telemetría del bot
            with st.status("🚀 Ejecutando Validación Algorítmica...", expanded=True) as status:
                
                # PASO 1: Obtener precio actual del subyacente
                status.write("🔍 Consultando precio actual del subyacente...")
                precio_actual = st.session_state.broker.obtener_precio_prueba(ticker)
                
                if not precio_actual:
                    status.update(label="❌ Error: No se pudo obtener el precio", state="error")
                    st.error("No se ha podido recuperar el precio actual. Verifica el Ticker.")
                    st.stop() # Detiene la ejecución de este bloque

                # PASO 2: Validación de Análisis Técnico (SMA)
                if activar_sma:
                    status.write(f"📈 Calculando Media Móvil (SMA {periodo_n})...")
                    try:
                        validacion = MotorEstrategias.evaluar_condicion_sma(
                            st.session_state.broker, ticker, periodo_n, tipo_cruce, precio_actual
                        )
                        
                        status.write(f"⚖️ Validando Regla: {tipo_cruce} (SMA: {validacion['valor_sma']})")
                        
                        if not validacion["autorizado"]:
                            status.update(label="⛔ Entrada Bloqueada por Regla AT", state="error")
                            # REGISTRO EN BD (Intento fallido)
                            db.registrar_evento("ESTRATEGIA_BLOQUEADA", f"Ticker: {ticker} | Regla: {tipo_cruce}")
                            enviar_alerta_webhook(
                                "⛔ Orden Bloqueada (Regla SMA)", 
                                f"El motor algorítmico ha bloqueado una orden de **{ticker}**.\nEl precio actual (${precio_actual}) no cumple '{tipo_cruce}' respecto a la SMA de {periodo_n} días (${validacion['valor_sma']}).", 
                                "error"
                            )
                            st.warning(
                                f"Entrada BLOQUEADA. El precio (${precio_actual}) no cumple "
                                f"'{tipo_cruce}' respecto a la SMA (${validacion['valor_sma']})."
                            )
                            st.stop()
                        
                        # Filtro AT superado — notificación y registro en BD
                        st.toast(f"Filtro AT superado: SMA {validacion['valor_sma']}", icon="✅")
                        db.registrar_evento("ESTRATEGIA_AUTORIZADA", f"Ticker: {ticker} | SMA: {validacion['valor_sma']}")
                    
                    except Exception as e:
                        status.update(label="❌ Error en cálculo de SMA", state="error")
                        st.error(f"Fallo al evaluar la condición técnica: {e}")
                        st.stop()

                # PASO 3: Consultar Opciones y calcular crédito real
                status.write("⛓️ Consultando primas de las 4 patas del Iron Condor...")
                try:
                    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
                        st.session_state.broker, ticker, vencimiento, put_long, put_short, call_short, call_long
                    )
                    
                    credito_real = resultado["credito_neto"]
                    metricas = MotorEstrategias.calcular_metricas_iron_condor(
                        put_long, put_short, call_short, call_long, credito_real
                    )
                    
                    status.update(label="✅ Validación Completa y Autorizada", state="complete")
                    
                except Exception as e:
                    status.update(label="❌ Error al consultar opciones", state="error")
                    st.error(f"Error en el Motor de Agregación: {e}")
                    st.stop()

            # --- PRESENTACIÓN FINAL DE RESULTADOS (Fuera del status) ---
            st.success(f"Estrategia '{ticker}' validada y lista para ejecución.")
            
            with st.expander("🔍 Ver desglose de Primas de Mercado (Bid/Ask)"):
                d = resultado["detalle"]
                col_a, col_b = st.columns(2)
                col_a.write(f"* **Short Put (Bid):** ${d['p_short_bid']}")
                col_a.write(f"* **Short Call (Bid):** ${d['c_short_bid']}")
                col_b.write(f"* **Long Put (Ask):** ${d['p_long_ask']}")
                col_b.write(f"* **Long Call (Ask):** ${d['c_long_ask']}")
                
            with st.expander("📐 Greeks (Black-Scholes)"):
                dias_vencimiento = (vencimiento - date.today()).days
                T = max(dias_vencimiento / 365.0, 1e-5)
                g_pl = MotorBlackScholes.calcular_greeks(precio_actual, put_long, T, tasa_riesgo, volatilidad, 'P')
                g_ps = MotorBlackScholes.calcular_greeks(precio_actual, put_short, T, tasa_riesgo, volatilidad, 'P')
                g_cs = MotorBlackScholes.calcular_greeks(precio_actual, call_short, T, tasa_riesgo, volatilidad, 'C')
                g_cl = MotorBlackScholes.calcular_greeks(precio_actual, call_long, T, tasa_riesgo, volatilidad, 'C')
                
                st.write("**Sensibilidades calculadas teóricamente:**")
                g1, g2 = st.columns(2)
                g1.write(f"**Long Put:** Δ {g_pl['delta']} | Θ {g_pl['theta']} | V {g_pl['vega']}")
                g1.write(f"**Short Put:** Δ {g_ps['delta']} | Θ {g_ps['theta']} | V {g_ps['vega']}")
                g2.write(f"**Short Call:** Δ {g_cs['delta']} | Θ {g_cs['theta']} | V {g_cs['vega']}")
                g2.write(f"**Long Call:** Δ {g_cl['delta']} | Θ {g_cl['theta']} | V {g_cl['vega']}")

            m1, m2, m3 = st.columns(3)
            m1.metric("Crédito Real Neto", f"${credito_real}")
            m2.metric("Máximo Beneficio", f"${metricas['max_beneficio']}")
            m3.metric("Máximo Riesgo", f"${metricas['max_riesgo']}", delta_color="inverse")

            # Persistimos para el botón de ejecución (sobrevive al rerun de Streamlit)
            st.session_state['estrategia_validada'] = {
                'ticker':       ticker,
                'vencimiento':  vencimiento,
                'strikes':      [put_long, put_short, call_short, call_long],
                'credito_real': credito_real,
                'metricas':     metricas,
                'tasa_riesgo':  tasa_riesgo,
                'volatilidad':  volatilidad,
                'precio_actual': precio_actual
            }

    # --- BLOQUE DE CONFIRMACIÓN Y EJECUCIÓN (persiste entre reruns) ---
    if st.session_state.get('estrategia_validada'):
        ev = st.session_state['estrategia_validada']
        st.divider()
        st.warning(
            "⚠️ ZONA DE EJECUCIÓN — Esta acción envía una orden REAL a IBKR (Paper Trading). "
            "Revisa los parámetros antes de confirmar."
        )
        col_info, col_btn = st.columns([3, 1])
        col_info.markdown(
            f"**Iron Condor `{ev['ticker']}`** · Venc: `{ev['vencimiento']}` "
            f"· Strikes: `{ev['strikes']}` "
            f"· Crédito: `${ev['credito_real']}` "
            f"· Riesgo Máx: `${ev['metricas']['max_riesgo']}`"
        )
        if col_btn.button("🚀 CONFIRMAR Y EJECUTAR", type="primary", key="btn_ejecutar"):
            with st.status("📡 Transmitiendo orden BAG al Gateway IBKR...", expanded=True) as status_ord:
                try:
                    res = st.session_state.broker.enviar_orden_iron_condor(
                        ev['ticker'], ev['vencimiento'], ev['strikes'], ev['credito_real']
                    )
                    status_ord.update(
                        label=f"✅ Orden enviada — OrderId: {res['order_id']}",
                        state="complete"
                    )
                    st.success(
                        f"✅ Orden BAG enviada. OrderId: `{res['order_id']}` "
                        f"| Estado inicial: `{res['status']}`"
                    )
                    db.registrar_evento(
                        "ORDEN_ENVIADA",
                        f"OrderId:{res['order_id']} | Ticker:{ev['ticker']} "
                        f"| Venc:{ev['vencimiento']} | Crédito:{ev['credito_real']}"
                    )
                    db.registrar_operacion(
                        order_id   = res['order_id'],
                        ticker     = ev['ticker'],
                        vencimiento= ev['vencimiento'],
                        strikes    = ev['strikes'],
                        credito    = ev['credito_real'],
                        metricas   = ev['metricas'],
                        status     = res['status']
                    )
                    del st.session_state['estrategia_validada']
                    
                    # --- WEBHOOK DÍA 13 ---
                    enviar_alerta_webhook(
                        "✅ Nueva Orden Iron Condor Enviada", 
                        f"**Ticker:** {ev['ticker']}\n**Crédito:** ${ev['credito_real']}\n**Riesgo Máx:** ${ev['metricas']['max_riesgo']}\n**OrderId:** {res['order_id']}", 
                        "success"
                    )
                    
                    st.rerun()
                except Exception as e:
                    # Encolar en caso de fallo
                    db.encolar_reintento(ev['ticker'], ev['vencimiento'], ev['strikes'], ev['credito_real'])
                    db.registrar_evento("ORDEN_ENCOLADA", f"Fallo al enviar {ev['ticker']}. Añadida a cola de reintentos por caída del Gateway.")
                    status_ord.update(label="⚠️ Servidor caído. Orden encolada", state="error")
                    st.error("El servidor de IBKR parece estar caído. La orden ha sido guardada en la cola de reintentos y se enviará automáticamente (Watchdog) cuando vuelva la conexión.")
                    enviar_alerta_webhook("⚠️ Caída del servidor (Watchdog Activo)", f"La orden de **{ev['ticker']}** no se pudo enviar porque el Gateway IBKR no responde. Se ha metido en la cola de reintentos.", "warning")
                    
        # --- BLOQUE DE ANÁLISIS DE SENSIBILIDAD B-S ---
        st.divider()
        st.subheader("🔥 Análisis Cuantitativo B-S (Heatmap)")
        st.write("Genera un mapa de calor para evaluar cómo varía el ratio B/R si desplazamos los strikes.")
        if st.button("Generar Heatmap de Sensibilidad (B/R)"):
            with st.spinner("Calculando malla Black-Scholes..."):
                dias_venc = (ev['vencimiento'] - date.today()).days
                fig = MotorBlackScholes.generar_heatmap_ic(
                    ev['precio_actual'], ev['tasa_riesgo'], ev['volatilidad'], dias_venc, ev['strikes']
                )
                st.pyplot(fig)

with tabs[0]:
    st.header("Resumen de la Cuenta (Paper Trading)")
    
    if conectado:
        # Obtenemos los datos desde la clase gestora
        with st.spinner("Sincronizando cuenta con IBKR..."):
            datos = st.session_state.broker.obtener_resumen_cuenta()
            
        if datos:
            col1, col2, col3 = st.columns(3)
            # st.metric aplica formato automáticamente, ideal para dashboards financieros
            col1.metric("Net Liquidation", f"${float(datos['NetLiquidation']):,.2f}")
            col2.metric("Buying Power", f"${float(datos['BuyingPower']):,.2f}")
            col3.metric("P&L Diario (Irrealizado)", f"${float(datos['DailyPnL']):,.2f}")
        else:
            st.warning("Conectado, pero esperando datos de la cuenta...")
    else:
        st.info("💡 Conéctate al bróker en la barra lateral para ver los datos de tu cuenta en tiempo real.")
        col1, col2, col3 = st.columns(3)
        col1.metric("Net Liquidation", "---")
        col2.metric("Buying Power", "---")
        col3.metric("P&L Diario", "---")

    # --- PANEL DE POSICIONES ABIERTAS ---
    st.divider()
    st.subheader("📂 Posiciones Abiertas en Cartera")
    st.write("Muestra los contratos actualmente en la cuenta Paper Trading (opciones, acciones, etc.).")

    # Inicializamos el cache de posiciones en session_state para no consultar en cada rerun
    if 'posiciones_cartera' not in st.session_state:
        st.session_state['posiciones_cartera'] = None

    if st.button("🔄 Actualizar Posiciones", key="btn_actualizar_cartera"):
        if not conectado:
            st.warning("⚠️ Debes estar conectado al bróker para consultar la cartera.")
        else:
            with st.spinner("Consultando posiciones en IBKR..."):
                st.session_state['posiciones_cartera'] = st.session_state.broker.obtener_posiciones_cartera()

    posiciones = st.session_state.get('posiciones_cartera')

    if posiciones is None:
        st.info("Pulsa 'Actualizar Posiciones' para cargar los datos del bróker.")
    elif len(posiciones) == 0:
        st.success("✅ Sin posiciones abiertas en la cuenta. La cartera está en efectivo.")
    else:
        import pandas as pd
        df_posiciones = pd.DataFrame(posiciones)
        st.dataframe(
            df_posiciones,
            use_container_width=True,
            hide_index=True
        )

with tabs[2]:
    st.header("📊 Consola de Monitorización y Auditoría")
    st.write("Historial de actividad y decisiones del motor algorítmico.")

    # 1. OBTENCIÓN DE DATOS
    # Llamamos al método de la base de datos
    df_logs = db.obtener_logs()

    if df_logs is not None and not df_logs.empty:
        # 2. CÁLCULO DE MÉTRICAS ESTADÍSTICAS (Resumen rápido)
        total_eventos = len(df_logs)
        accesos = len(df_logs[df_logs['evento'] == 'LOGIN_EXITOSO'])
        autorizadas = len(df_logs[df_logs['evento'] == 'ESTRATEGIA_AUTORIZADA'])
        bloqueadas = len(df_logs[df_logs['evento'] == 'ESTRATEGIA_BLOQUEADA'])

        # Mostrar métricas en columnas profesionales
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total Eventos", total_eventos)
        col_m2.metric("Accesos", accesos)
        col_m3.metric("Autorizadas ✅", autorizadas)
        col_m4.metric("Bloqueadas ⛔", bloqueadas, delta_color="inverse")

        st.divider()

        # 3. BOTÓN DE ACTUALIZACIÓN Y EXPORTACIÓN
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("🔄 Refrescar Logs de Auditoría"):
                st.rerun()
        with col_btn2:
            csv_logs = df_logs.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Logs a CSV",
                data=csv_logs,
                file_name="auditoria_logs_tfg.csv",
                mime="text/csv",
            )

        # 4. VISUALIZACIÓN DE LA TABLA DE LOGS
        st.subheader("Registro Detallado de Actividad")
        st.dataframe(
            df_logs,
            use_container_width=True,
            column_config={
                "fecha": st.column_config.DatetimeColumn(
                    "Marca de Tiempo",
                    format="D MMM YYYY, HH:mm:ss",
                ),
                "evento": "Tipo de Evento",
                "detalles": "Información del Motor"
            },
            hide_index=True # Ocultamos el índice para que parezca una tabla limpia
        )
        
    else:
        st.info("📭 Aún no se han registrado eventos en la base de datos. Los registros aparecerán aquí conforme el sistema opere.")
        if st.button("Actualizar"):
            st.rerun()

    # --- HISTORIAL DE OPERACIONES EJECUTADAS ---
    st.divider()
    st.subheader("📂 Historial de Órdenes Ejecutadas (BAG)")
    st.write("Registro financiero permanente de todas las órdenes Iron Condor transmitidas al bróker.")

    df_ops = db.obtener_operaciones()

    if df_ops is not None and not df_ops.empty:
        total_ops    = len(df_ops)
        credito_total = df_ops['credito'].sum()
        beneficio_max = df_ops['max_beneficio'].sum()
        riesgo_max    = df_ops['max_riesgo'].sum()

        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Órdenes Enviadas",   total_ops)
        o2.metric("Crédito Total",       f"${credito_total:.2f}")
        o3.metric("Benef. Máx. Acum.",  f"${beneficio_max:.2f}")
        o4.metric("Riesgo Máx. Acum.",  f"${riesgo_max:.2f}",   delta_color="inverse")

        # Exportación CSV del historial de operaciones
        csv_ops = df_ops.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Historial a CSV",
            data=csv_ops,
            file_name="historial_operaciones_tfg.csv",
            mime="text/csv",
        )

        st.dataframe(
            df_ops,
            use_container_width=True,
            column_config={
                "fecha":         st.column_config.DatetimeColumn("Fecha",       format="D MMM YYYY, HH:mm:ss"),
                "order_id":      st.column_config.NumberColumn("OrderId",       format="%d"),
                "ticker":        "Ticker",
                "vencimiento":   "Vencimiento",
                "put_long":      st.column_config.NumberColumn("Put Long",      format="%.0f"),
                "put_short":     st.column_config.NumberColumn("Put Short",     format="%.0f"),
                "call_short":    st.column_config.NumberColumn("Call Short",    format="%.0f"),
                "call_long":     st.column_config.NumberColumn("Call Long",     format="%.0f"),
                "credito":       st.column_config.NumberColumn("Crédito/acc",  format="$%.2f"),
                "max_beneficio": st.column_config.NumberColumn("Benef. Máx.",  format="$%.2f"),
                "max_riesgo":    st.column_config.NumberColumn("Riesgo Máx.",  format="$%.2f"),
                "status":        "Estado",
            },
            hide_index=True
        )

        # --- BLOQUE DE CANCELACIÓN DE ORDEN ---
        st.divider()
        st.subheader("❌ Cancelar Orden Abierta")
        st.write(
            "Introduce el **OrderId** de una orden en estado `Submitted` para solicitar su cancelación al bróker. "
            "Solo tienen efecto las órdenes que aún no han sido ejecutadas."
        )

        # Inicializamos el estado del flujo de confirmación de cancelación
        if 'cancelacion_pendiente' not in st.session_state:
            st.session_state['cancelacion_pendiente'] = None

        col_cancel_input, col_cancel_btn = st.columns([2, 1])
        order_id_a_cancelar = col_cancel_input.number_input(
            "OrderId a cancelar", min_value=1, step=1, value=1, key="input_cancel_id"
        )
        if col_cancel_btn.button("🗑️ Solicitar Cancelación", key="btn_solicitar_cancelacion"):
            if not conectado:
                st.warning("⚠️ Debes estar conectado al bróker para cancelar órdenes.")
            else:
                # Guardamos en session_state para sobrevivir al rerun (patrón idéntico al de ejecución)
                st.session_state['cancelacion_pendiente'] = int(order_id_a_cancelar)
                st.rerun()

        # Bloque de confirmación — solo aparece cuando hay una cancelación pendiente de validar
        if st.session_state.get('cancelacion_pendiente') is not None:
            oid = st.session_state['cancelacion_pendiente']
            st.warning(
                f"⚠️ ZONA DE CANCELACIÓN — Vas a solicitar la cancelación de la orden "
                f"**#{oid}** en el bróker. Esta acción es irreversible si la orden está activa."
            )
            col_conf, col_abort = st.columns(2)
            if col_conf.button("✅ CONFIRMAR CANCELACIÓN", type="primary", key="btn_confirmar_cancel"):
                with st.status("📡 Enviando cancelación al Gateway IBKR...", expanded=True) as status_cancel:
                    resultado_cancel = st.session_state.broker.cancelar_orden(oid)
                    if resultado_cancel['exito']:
                        status_cancel.update(label=f"✅ Cancelación enviada — Orden #{oid}", state="complete")
                        st.success(resultado_cancel['mensaje'])
                        db.registrar_evento("ORDEN_CANCELADA", f"OrderId:{oid} | Solicitud de cancelación emitida.")
                        enviar_alerta_webhook(
                            "🗑️ Solicitud de Cancelación", 
                            f"El usuario ha solicitado manualmente la cancelación de la orden **#{oid}** a través del Dashboard.", 
                            "warning"
                        )
                    else:
                        status_cancel.update(label="⚠️ No se pudo cancelar", state="error")
                        st.error(resultado_cancel['mensaje'])
                st.session_state['cancelacion_pendiente'] = None
                st.rerun()
            if col_abort.button("✖️ Abortar", key="btn_abort_cancel"):
                st.session_state['cancelacion_pendiente'] = None
                st.rerun()

    else:
        st.info("📦 Aún no se han ejecutado órdenes en esta sesión. Las órdenes BAG enviadas al bróker aparecerán aquí.")

with tabs[3]:
    st.header("🧪 Backtesting Visual (Data Science)")
    st.write("Simulación retrospectiva del algoritmo SMA sobre el histórico anual del subyacente. Permite validar visualmente las reglas de entrada antes de operar en tiempo real.")
    
    col_bt1, col_bt2, col_bt3 = st.columns(3)
    ticker_bt = col_bt1.text_input("Ticker para simulación", value="SPY", key="ticker_bt").upper()
    periodo_bt = col_bt2.number_input("Periodo SMA", min_value=10, max_value=300, value=200, step=10, key="periodo_bt")
    regla_bt = col_bt3.selectbox("Regla de Trading", ["Precio > SMA", "Precio < SMA"], key="regla_bt")
    
    if st.button("Ejecutar Backtest Anual", key="btn_run_backtest"):
        with st.spinner(f"Descargando datos anuales de {ticker_bt} y simulando el motor..."):
            import yfinance as yf
            import plotly.graph_objects as go
            import pandas as pd
            
            try:
                # 1. Descarga de datos masiva
                ticker_obj = yf.Ticker(ticker_bt)
                df_bt = ticker_obj.history(period="1y")
                
                if df_bt.empty:
                    st.error(f"No se encontraron datos históricos para {ticker_bt}. Yahoo Finance podría estar limitando las peticiones.")
                else:
                    # Garantizar compatibilidad con yfinance multi-index (versiones recientes)
                    if isinstance(df_bt.columns, pd.MultiIndex):
                        close_col = df_bt['Close'].iloc[:, 0]
                    else:
                        close_col = df_bt['Close']
                        
                    # 2. Vectorización matemática (Análisis Cuantitativo)
                    df_res = pd.DataFrame(index=df_bt.index)
                    df_res['Close'] = close_col
                    df_res['SMA'] = df_res['Close'].rolling(window=periodo_bt).mean()
                    
                    # 3. Vectorización de la regla lógica (Filtro Algorítmico)
                    if regla_bt == "Precio > SMA":
                        df_res['Autorizado'] = df_res['Close'] > df_res['SMA']
                    else:
                        df_res['Autorizado'] = df_res['Close'] < df_res['SMA']
                        
                    # 4. Cálculo de transiciones de estado (Derivada discreta)
                    df_res['Cruce'] = df_res['Autorizado'].astype(int).diff()
                    
                    puntos_verdes = df_res[df_res['Cruce'] == 1]
                    puntos_rojos = df_res[df_res['Cruce'] == -1]
                    
                    # 5. Generación del gráfico interactivo (Data Visualization)
                    fig = go.Figure()
                    
                    # Línea de Precio
                    fig.add_trace(go.Scatter(
                        x=df_res.index, y=df_res['Close'],
                        mode='lines', name='Precio (Close)',
                        line=dict(color='#2E86C1', width=2)
                    ))
                    
                    # Línea SMA
                    fig.add_trace(go.Scatter(
                        x=df_res.index, y=df_res['SMA'],
                        mode='lines', name=f'SMA {periodo_bt}',
                        line=dict(color='#F39C12', width=2, dash='dash')
                    ))
                    
                    # Marcadores de Acción
                    fig.add_trace(go.Scatter(
                        x=puntos_verdes.index, y=puntos_verdes['Close'],
                        mode='markers', name='Filtro OK (Entrar)',
                        marker=dict(color='green', size=12, symbol='triangle-up', line=dict(width=1, color='DarkSlateGrey'))
                    ))
                    
                    fig.add_trace(go.Scatter(
                        x=puntos_rojos.index, y=puntos_rojos['Close'],
                        mode='markers', name='Filtro Bloqueado (No Entrar)',
                        marker=dict(color='red', size=12, symbol='triangle-down', line=dict(width=1, color='DarkSlateGrey'))
                    ))
                    
                    fig.update_layout(
                        title=f'Backtest Visual - Dinámica de Autorización para {ticker_bt} (Último Año)',
                        xaxis_title='Fecha',
                        yaxis_title='Precio USD',
                        hovermode='x unified',
                        template='plotly_white',
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        margin=dict(l=0, r=0, t=50, b=0)
                    )
                    
                    st.plotly_chart(fig, width='stretch', config={'scrollZoom': True})
                    
                    # 6. Dashboard Analítico
                    st.subheader("📊 Métricas de la Simulación")
                    c1, c2, c3 = st.columns(3)
                    
                    # Eliminamos los NaNs iniciales producidos por el rolling() de la SMA
                    df_clean = df_res.dropna()
                    dias_totales = len(df_clean)
                    dias_autorizados = df_clean['Autorizado'].sum()
                    porcentaje_autorizado = (dias_autorizados / dias_totales) * 100 if dias_totales > 0 else 0
                    
                    c1.metric("Días Evaluados (post-SMA)", dias_totales)
                    c2.metric("Días con Filtro Autorizado", dias_autorizados)
                    c3.metric("Exposición Teórica al Mercado", f"{porcentaje_autorizado:.1f}%")
                    
            except Exception as e:
                st.error(f"Error interno durante la simulación: {e}")
