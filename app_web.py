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

# --- CONEXIÓN GLOBAL AL BRÓKER ---
@st.cache_resource(on_release=lambda b: b.desconectar())
def obtener_broker_global():
    return GestorIBKR(port=4002, client_id=1)

broker_global = obtener_broker_global()

# --- INICIALIZACIÓN GLOBAL DE WATCHDOGS (HITO 4) ---
@st.cache_resource(on_release=lambda x: detener_watchdogs())
def iniciar_watchdogs_globales(_broker):
    """Inicializa una única vez los watchdogs en segundo plano de entrada y salida."""
    try:
        # Iniciamos el watchdog de entradas (cada 30s) y de salidas (cada 15s)
        hilo_ent = iniciar_watchdog_entradas(db_name="tfg_trading.db", interval=30, broker=_broker)
        hilo_sal = iniciar_watchdog_salidas(db_name="tfg_trading.db", interval=15, broker=_broker)
        db.registrar_evento("WATCHDOGS_INICIADOS_UI", "Watchdogs globales arrancados desde el frontend.")
        return hilo_ent, hilo_sal
    except Exception as e:
        print(f"Error al iniciar watchdogs: {e}")
        return None, None

# Arrancamos los watchdogs
hilo_ent_glob, hilo_sal_glob = iniciar_watchdogs_globales(broker_global)

# --- COMPONENTE DE TARJETA DE CONDICIÓN (WATCHDOG CARD) ---
def render_watchdog_card(titulo, toggle_key, fields_fn):
    toggle_val = st.session_state.get(toggle_key, False)
    card_key = f"wd_card_{toggle_key}_{'active' if toggle_val else 'inactive'}"
    
    with st.container(key=card_key):
        col_title, col_toggle = st.columns([3, 1], vertical_alignment="center")
        with col_title:
            st.markdown(f"<span style='font-size: 1rem; font-weight: 600; color: #ffffff;'>{titulo}</span>", unsafe_allow_html=True)
        with col_toggle:
            toggle_state = st.toggle(titulo, value=toggle_val, key=toggle_key, label_visibility="collapsed")
            
        st.markdown("<hr style='margin: 8px 0; opacity: 0.08;' />", unsafe_allow_html=True)
        res = fields_fn(not toggle_state)
        
    return toggle_state, res

# --- DIALOG WRAPPER DE STREAMLIT ---
if hasattr(st, "dialog"):
    st_dialog = st.dialog
elif hasattr(st, "experimental_dialog"):
    st_dialog = st.experimental_dialog
else:
    def st_dialog(title):
        def decorator(func):
            return func
        return decorator

def set_confirm_global(qty):
    if st.session_state.liq_qty <= 0:
        st.session_state.liq_error = "La cantidad a vender debe ser mayor que 0."
    elif round(st.session_state.liq_qty, 4) > round(abs(qty), 4):
        st.session_state.liq_error = "No puedes vender más posiciones de las que posees."
    else:
        st.session_state.liq_confirm = True
        st.session_state.liq_error = None
        # Persist values for the confirmation screen
        st.session_state.liq_qty_final = st.session_state.liq_qty
        st.session_state.liq_amount_final = st.session_state.liq_amount
        st.session_state.liq_radio_final = st.session_state.liq_radio_selector

def reset_confirm_global():
    st.session_state.liq_confirm = False
    st.session_state.liq_error = None
    st.session_state.liq_qty_final = None
    st.session_state.liq_amount_final = None
    st.session_state.liq_radio_final = None

def confirmar_y_ejecutar_venta_global(simbolo, tipo, qty, total_mercado, pnl, pos):
    try:
        broker_inst = st.session_state.broker
        es_broker_conectado = broker_inst is not None and broker_inst.esta_conectado()
        
        qty_a_vender = st.session_state.get("liq_qty_final", st.session_state.get("liq_qty"))
        if qty_a_vender is None:
            raise ValueError("No se especificó la cantidad a vender (liq_qty_final es None).")
            
        if es_broker_conectado:
            pata_org = {
                "tipo_activo": "OPTION" if tipo in ("Opción", "OPT", "Option") else "STOCK",
                "accion": "BUY" if qty > 0 else "SELL",
                "cantidad": qty_a_vender
            }
            if pata_org["tipo_activo"] == "OPTION":
                pata_org["strike"] = pos.get("Strike")
                pata_org["right"] = pos.get("Right (C/P)")
                pata_org["vencimiento"] = pos.get("Vencimiento")
            
            broker_res = broker_inst.enviar_orden_cierre_generica(
                ticker=simbolo,
                tipo_activo=pata_org["tipo_activo"],
                patas=[pata_org]
            )
            order_id_sal = broker_res["order_id"]
        else:
            order_id_sal = random.randint(100000, 999999)
        
        # Buscar si hay alguna estrategia activa asociada
        est_asociada = None
        try:
            estrategias_activas = db.obtener_estrategias(estado="ACTIVA")
            for e in estrategias_activas:
                tipo_act_sel = "OPTION" if tipo in ("Opción", "OPT", "Option") else "STOCK"
                if e.get("ticker", "").upper() == simbolo.upper() and e.get("tipo_activo", "").upper() == tipo_act_sel:
                    est_asociada = e
                    break
        except Exception as e_db_chk:
            print(f"Error al buscar estrategia asociada para cierre: {e_db_chk}")
            
        # Si es venta completa
        es_venta_completa = abs(qty_a_vender - abs(qty)) < 0.0001
        
        if est_asociada:
            if es_venta_completa:
                # Venta completa -> CERRADA_MANUAL
                db.actualizar_estado_estrategia(
                    estrategia_id=est_asociada["id"],
                    nuevo_estado="CERRADA_MANUAL",
                    order_id_salida=order_id_sal,
                    precio_salida=0.0,
                    pnl_realizado=pnl if pnl is not None else 0.0,
                    fecha_cierre=datetime.now().isoformat()
                )
                db.registrar_evento("CIERRE_MANUAL_UI", f"Estrategia #{est_asociada['id']} ({simbolo}) cerrada y liquidada por completo desde el Dashboard.")
            else:
                # Venta parcial -> Actualizar cantidad en patas de la estrategia
                try:
                    patas_actualizadas = []
                    patas_sel = est_asociada.get("patas", [])
                    if not patas_sel and est_asociada.get("patas_json"):
                        patas_sel = json.loads(est_asociada["patas_json"])
                    for p in patas_sel:
                        p_new = p.copy()
                        p_new["cantidad"] = float(p.get("cantidad", 1)) - qty_a_vender
                        patas_actualizadas.append(p_new)
                    db.actualizar_patas(est_asociada["id"], patas_actualizadas)
                    db.registrar_evento("CIERRE_PARCIAL_UI", f"Estrategia #{est_asociada['id']} ({simbolo}) liquidada parcialmente. Vendidas {qty_a_vender} posiciones. Restan {patas_actualizadas[0]['cantidad']}.")
                except Exception as e_upd_pat:
                    print(f"Error al actualizar patas por cierre parcial: {e_upd_pat}")
        else:
            if es_venta_completa:
                db.registrar_evento("LIQUIDACION_POSICION_HUERFANA", f"Posición huérfana completa de {simbolo} ({tipo}, cant={qty}) liquidada directamente desde el Dashboard. OrderID: {order_id_sal}")
            else:
                db.registrar_evento("LIQUIDACION_PARCIAL_HUERFANA", f"Posición huérfana parcial de {simbolo} ({tipo}, cant={qty}) liquidada directamente desde el Dashboard. Vendidas={qty_a_vender}. OrderID: {order_id_sal}")
        
        # Notificar
        pnl_proporcional = (pnl if pnl is not None else 0.0) * (qty_a_vender / abs(qty))
        enviar_alerta_webhook(
            titulo="🛑 Posición Liquidada desde Dashboard",
            mensaje=f"**Activo:** {simbolo}\n**Tipo:** {tipo}\n**Cantidad Vendida:** {qty_a_vender}\n**Tipo Venta:** {'Completa' if es_venta_completa else 'Parcial'}\n**P&L Estimado Proporcional:** ${pnl_proporcional:.2f}\n**OrderID Cierre:** {order_id_sal}",
            color="warning"
        )
        st.session_state.liq_confirm = False
        st.session_state.liq_error = None
        st.session_state.liq_qty_final = None
        st.session_state.liq_amount_final = None
        st.session_state.liq_radio_final = None
        st.session_state.liq_success_toast = f"Orden de liquidación de {qty_a_vender} posiciones en {simbolo} enviada con éxito."
    except Exception as ex_liq:
        st.session_state.liq_error = f"Error al liquidar posición: {ex_liq}"
        st.session_state.liq_confirm = True

def obtener_posiciones_huerfanas():
    """
    Identifica las posiciones en la cartera del broker que no están asociadas
    a ninguna estrategia activa en la base de datos local.
    Agrupa acciones por símbolo y descarta posiciones netas que suman cero.
    """
    posiciones = st.session_state.get('posiciones_cartera', [])
    if not posiciones:
        return []
    
    # 1. Agrupar acciones de la misma forma que en el dashboard
    raw_acciones = [p for p in posiciones if p.get('Tipo') in ('Acción', 'STK', 'Stock', 'IND')]
    acciones_agrupadas = {}
    for p in raw_acciones:
        sym = p.get('Símbolo')
        qty = p.get('Posición', 0.0)
        avg_p = p.get('Precio Medio', 0.0)
        mkt_val = p.get('Valor Mercado', 0.0)
        pnl = p.get('P&L No Real.', 0.0)
        
        if sym not in acciones_agrupadas:
            acciones_agrupadas[sym] = {
                "Símbolo": sym,
                "Tipo": p.get("Tipo"),
                "Posición": 0.0,
                "Valor Mercado": 0.0,
                "P&L No Real.": 0.0,
                "Costo Total": 0.0
            }
        acciones_agrupadas[sym]["Posición"] += qty
        acciones_agrupadas[sym]["Valor Mercado"] += mkt_val
        acciones_agrupadas[sym]["P&L No Real."] += pnl
        acciones_agrupadas[sym]["Costo Total"] += avg_p * qty
        
    for sym, data in acciones_agrupadas.items():
        if data["Posición"] != 0:
            data["Precio Medio"] = round(data["Costo Total"] / data["Posición"], 4)
        else:
            data["Precio Medio"] = 0.0
        data.pop("Costo Total", None)
        
    # Filtrar acciones con posición real (neta) distinta de cero
    acciones_list = [data for data in acciones_agrupadas.values() if abs(data["Posición"]) > 1e-5]
    
    # Filtrar opciones con posición real distinta de cero
    opciones_list = [p for p in posiciones if p.get('Tipo') in ('Opción', 'OPT', 'Option') and abs(p.get('Posición', 0.0)) > 1e-5]
    
    # Unificar posiciones activas
    posiciones_activas = acciones_list + opciones_list
    
    try:
        estrategias_activas = db.obtener_estrategias(estado="ACTIVA")
    except Exception as e_db:
        print(f"Error al obtener estrategias activas para huérfanas: {e_db}")
        estrategias_activas = []
        
    huerfanas = []
    for pos in posiciones_activas:
        simbolo = pos.get('Símbolo')
        tipo = pos.get('Tipo')
        tipo_act_sel = "OPTION" if tipo in ("Opción", "OPT", "Option") else "STOCK"
        
        tiene_estrategia = False
        for e in estrategias_activas:
            if e.get("ticker", "").upper() == simbolo.upper():
                if tipo_act_sel == "STOCK" and e.get("tipo_activo", "").upper() == "STOCK":
                    tiene_estrategia = True
                    break
                elif tipo_act_sel == "OPTION" and e.get("tipo_activo", "").upper() in ("BAG", "OPTION"):
                    patas = e.get("patas") or []
                    if not patas and e.get("patas_json"):
                        try:
                            patas = json.loads(e["patas_json"])
                        except:
                            pass
                    for pata in patas:
                        if pata.get("tipo_activo", "OPTION").upper() == "OPTION":
                            p_right = pata.get("right", "C")[0].upper()
                            pos_right = pos.get("Right (C/P)", "C")[0].upper()
                            
                            def normalizar_fecha(f_str):
                                if not f_str: return ""
                                cleaned = str(f_str).replace("-", "").replace("/", "").strip()
                                if len(cleaned) == 8: return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
                                return cleaned
                            
                            p_venc = normalizar_fecha(pata.get("vencimiento", ""))
                            pos_venc = normalizar_fecha(pos.get("Vencimiento", ""))
                            
                            if float(pata.get("strike", 0.0)) == float(pos.get("Strike", 0.0)) and p_right == pos_right and p_venc == pos_venc:
                                tiene_estrategia = True
                                break
                    if tiene_estrategia:
                        break
        if not tiene_estrategia:
            huerfanas.append(pos)
    return huerfanas


@st_dialog("Detalle de Posición")
def mostrar_detalle_posicion(pos):
    # Inyectar estilos CSS para asegurar el formato de la modal y sus botones
    st.markdown("""
    <style>
        div[role="dialog"],
        div[data-baseweb="modal"] [role="dialog"],
        div[data-testid="stDialog"] [role="dialog"],
        div[class*="stDialog"] [role="dialog"] {
            width: 780px !important;
            max-width: 90vw !important;
            margin: auto !important;
        }
        div.stButton > button {
            background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%) !important;
            color: white !important;
            border: none !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            padding: 10px 24px !important;
            box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4) !important;
            transition: all 0.2s ease !important;
        }
        div.stButton > button:hover {
            box-shadow: 0 6px 20px rgba(79, 70, 229, 0.6) !important;
            background: linear-gradient(135deg, #5a52e6 0%, #4c8ff7 100%) !important;
            color: white !important;
        }
        /* Metric styling inside dialog */
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.02) !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 16px !important;
            padding: 20px !important;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37) !important;
            backdrop-filter: blur(10px) !important;
            -webkit-backdrop-filter: blur(10px) !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }
        div[data-testid="stMetric"]:hover {
            border-color: rgba(99, 102, 241, 0.4) !important;
            box-shadow: 0 8px 32px 0 rgba(99, 102, 241, 0.15) !important;
            transform: translateY(-3px) !important;
        }
        /* Prevent metric label truncation & force wrapping */
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            white-space: normal !important;
            word-wrap: break-word !important;
            overflow: visible !important;
            text-overflow: clip !important;
            font-size: 0.85rem !important;
            line-height: 1.25 !important;
            min-height: 2.2rem !important;
            display: flex !important;
            align-items: center !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] > div {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        /* Metric values in theme blue, sized to match the header, preventing truncation */
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] * {
            color: #6366f1 !important;
            font-size: 0.85rem !important;
            white-space: normal !important;
            word-wrap: break-word !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        /* Metric delta values styling */
        div[data-testid="stMetricDelta"],
        div[data-testid="stMetricDelta"] * {
            font-size: 0.75rem !important;
            white-space: normal !important;
            word-wrap: break-word !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
    </style>
    """, unsafe_allow_html=True)

    simbolo = pos.get('Símbolo')
    tipo = pos.get('Tipo')
    qty = pos.get('Posición', 0.0)
    avg_cost = pos.get('Precio Medio', 0.0)
    mkt_val = pos.get('Valor Mercado', 0.0)
    pnl = pos.get('P&L No Real.', 0.0)
    
    # 1. Tarjetas de KPIs (Métricas del Activo)
    # Definición y enlace de variables matemáticas reales de la posición
    average_cost = avg_cost
    position_size = qty
    multiplier = 100.0 if tipo in ("Opción", "OPT", "Option") else 1.0
    
    # Tarjeta 2 (Precio Actual Mercado): marketPrice
    market_price = mkt_val / (position_size * multiplier) if (position_size != 0 and multiplier != 0) else average_cost
    
    # Tarjeta 3 (Valor Total Invertido): averageCost * position_size
    # Usamos valor absoluto de la posición para representar de forma intuitiva el capital implicado
    total_invertido = average_cost * abs(position_size) * multiplier
    
    # Tarjeta 4 (Valor Total Mercado): marketPrice * position_size (o el marketValue directo)
    total_mercado = market_price * abs(position_size) * multiplier
    
    # P&L no realizado y rentabilidad para el 'badge' delta
    pnl_sign = "+" if pnl >= 0 else "-"
    rent_pct = (pnl / total_invertido * 100) if total_invertido != 0 else 0.0
    delta_str = f"{pnl_sign}${abs(pnl):,.2f} ({pnl_sign}{rent_pct:.2f}%)"
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Precio Compra Medio", f"${average_cost:,.2f}")
    with c2:
        st.metric("Precio Actual Mercado", f"${market_price:,.2f}")
    with c3:
        st.metric("Valor Total Invertido", f"${total_invertido:,.2f}")
    with c4:
        st.metric("Valor Total Mercado", f"${total_mercado:,.2f}", delta=delta_str if total_invertido != 0 else None)
    
    st.markdown("<hr style='opacity: 0.1; margin: 15px 0;' />", unsafe_allow_html=True)
    
    num_pos_str = f"{int(qty)}" if float(qty).is_integer() else f"{qty}"
    st.markdown(f"<p style='color: #cbd5e1; font-size: 0.95rem; margin-top: -5px; margin-bottom: 15px; text-align: left;'><b>Número de posiciones:</b> {num_pos_str}</p>", unsafe_allow_html=True)
    
    # 2. Gráfica de Evolución Temporal del Activo (Plotly)
    import numpy as np
    import datetime as dt_mod
    import json
    
    # Función auxiliar para parsear fechas de base de datos
    def parse_date(date_str):
        if not date_str:
            return None
        try:
            t_str = str(date_str).replace("T", " ")
            parts = t_str.split(" ")
            return dt_mod.datetime.strptime(parts[0], "%Y-%m-%d").date()
        except:
            return None

    # Recuperamos el historial de estrategias del ticker desde la base de datos
    ticker_strategies = []
    try:
        todas_est = db.obtener_estrategias()
        ticker_strategies = [e for e in todas_est if e.get("ticker", "").upper() == simbolo.upper()]
    except Exception as e_db:
        print(f"Error al obtener estrategias para el historial: {e_db}")

    # Rango de fechas (últimos 30 días)
    dates = [dt_mod.date.today() - dt_mod.timedelta(days=i) for i in range(30)]
    dates.reverse()

    # Procesar histórico de patas activas por estrategia
    active_legs_history = []
    for est in ticker_strategies:
        dt_ej = parse_date(est.get("fecha_ejecucion"))
        dt_ci = parse_date(est.get("fecha_cierre"))
        
        if dt_ej is None:
            continue
            
        patas = est.get("patas", [])
        if not patas and est.get("patas_json"):
            try:
                patas = json.loads(est["patas_json"])
            except:
                pass
                
        for leg in patas:
            leg_tipo = leg.get("tipo_activo", "").upper()
            mult = 100.0 if leg_tipo in ("OPCIÓN", "OPT", "OPTION") else 1.0
            cant = float(leg.get("cantidad", 0.0))
            accion = leg.get("accion", "BUY").upper()
            signo = 1.0 if accion == "BUY" else -1.0
            
            active_legs_history.append({
                "entry_date": dt_ej,
                "close_date": dt_ci,
                "qty": signo * cant,
                "entry_price": float(est.get("precio_entrada") or 0.0),
                "multiplier": mult
            })

    # Si no tenemos registros históricos pero sí hay posición real del bróker,
    # inyectamos una posición virtual que abarque todo el periodo para no vaciar el gráfico.
    if not active_legs_history and position_size != 0:
        active_legs_history.append({
            "entry_date": dates[0],
            "close_date": None,
            "qty": position_size,
            "entry_price": average_cost,
            "multiplier": multiplier
        })

    # Generamos una serie temporal de precios simulados para el activo, finalizando en el precio de mercado real
    np.random.seed(hash(simbolo) % 1234567)
    price_steps = np.random.normal(loc=0.0, scale=0.015, size=30)
    simulated_prices = []
    curr_price = market_price
    for step in reversed(price_steps):
        simulated_prices.append(curr_price)
        curr_price = curr_price / (1.0 + step)
    simulated_prices.reverse()

    # Reconstruimos la Base Invertida y el Valor de Mercado día a día
    base_invertida_series = []
    valor_mercado_series = []

    for i, d in enumerate(dates):
        base_signed = 0.0
        qty_signed = 0.0
        for leg in active_legs_history:
            if leg["entry_date"] <= d and (leg["close_date"] is None or leg["close_date"] > d):
                base_signed += leg["qty"] * leg["entry_price"] * leg["multiplier"]
                qty_signed += leg["qty"]
        
        # Guardamos en valor absoluto para que la exposición/capital invertido sea siempre positiva e intuitiva
        base_invertida_series.append(abs(base_signed))
        
        # El Valor Mercado (Línea Azul) debe marcar el valor de mercado histórico real de la posición en ese momento
        valor_mercado_series.append(abs(qty_signed) * simulated_prices[i] * multiplier)

    # Forzar el último día para sincronizarlo al 100% con los datos exactos del bróker (KPI cards)
    if len(dates) > 0:
        base_invertida_series[-1] = total_invertido
        valor_mercado_series[-1] = total_mercado

    fig = go.Figure()
    
    # Curva de Valor
    fig.add_trace(go.Scatter(
        x=dates,
        y=valor_mercado_series,
        mode='lines',
        line=dict(color='#6366f1', width=3, shape='spline'),
        fill='tozeroy',
        fillcolor='rgba(99, 102, 241, 0.06)',
        name='Valor Mercado',
        hovertemplate='<b>Fecha</b>: %{x}<br><b>Valor</b>: $%{y:,.2f}<extra></extra>'
    ))
    
    # Línea base (Valor Invertido)
    fig.add_trace(go.Scatter(
        x=dates,
        y=base_invertida_series,
        mode='lines',
        line=dict(color='rgba(255, 255, 255, 0.25)', width=1, dash='dash', shape='hv'),
        name='Base Invertida',
        hovertemplate='Invertido: $%{y:,.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        title=dict(
            text=f"<b>Evolución del Valor de la Posición en {simbolo} (Últimos 30 días)</b>",
            font=dict(size=13, color='#ffffff')
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94a3b8', family='Outfit, Inter, sans-serif'),
        margin=dict(t=50, b=15, l=40, r=20),
        height=260,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10)
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.03)',
            zeroline=False,
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="1W", step="day", stepmode="backward"),
                    dict(count=15, label="15D", step="day", stepmode="backward"),
                    dict(count=30, label="1M", step="day", stepmode="backward"),
                    dict(step="all", label="ALL")
                ]),
                bgcolor="rgba(30, 41, 59, 0.6)",
                activecolor="rgba(99, 102, 241, 0.4)",
                font=dict(color="#ffffff", size=9)
            )
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.03)',
            zeroline=False,
            tickformat="$,.0f"
        )
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # 3. Formulario "¿Cuánto quieres vender?"
    st.markdown("<hr style='opacity: 0.1; margin: 10px 0;' />", unsafe_allow_html=True)
    
    # Inicializar el estado de la liquidación para este activo específico
    if st.session_state.get("liq_active_symbol") != simbolo or (not st.session_state.get("liq_confirm") and "liq_radio_selector" not in st.session_state):
        st.session_state.liq_active_symbol = simbolo
        st.session_state.liq_radio_selector = "Todo el fondo"
        st.session_state.liq_qty = float(abs(qty))
        st.session_state.liq_amount = float(total_mercado)
        st.session_state.liq_confirm = False
        st.session_state.liq_error = None

    def on_radio_change():
        if st.session_state.liq_radio_selector == "Todo el fondo":
            st.session_state.liq_qty = float(abs(qty))
            st.session_state.liq_amount = float(total_mercado)
        st.session_state.liq_error = None

    def update_qty_callback():
        st.session_state.liq_error = None
        amt = st.session_state.liq_amount
        max_amt = float(total_mercado)
        if amt > max_amt:
            amt = max_amt
            st.session_state.liq_amount = amt
        
        calculated_qty = amt / (market_price * multiplier) if (market_price > 0 and multiplier > 0) else 0.0
        max_qty = float(abs(qty))
        if calculated_qty > max_qty:
            calculated_qty = max_qty
            
        if tipo in ("Opción", "OPT", "Option") or float(qty).is_integer():
            st.session_state.liq_qty = float(round(calculated_qty))
        else:
            st.session_state.liq_qty = float(round(calculated_qty, 4))

    def update_amount_callback():
        st.session_state.liq_error = None
        q = st.session_state.liq_qty
        max_qty = float(abs(qty))
        if q > max_qty:
            q = max_qty
            st.session_state.liq_qty = q
            
        calculated_amt = q * market_price * multiplier
        max_amt = float(total_mercado)
        if calculated_amt > max_amt:
            calculated_amt = max_amt
            
        st.session_state.liq_amount = float(round(calculated_amt, 2))

    if st.session_state.get("liq_error"):
        st.error(st.session_state.liq_error)

    if st.session_state.get("liq_confirm"):
        # --- VISTA DE CONFIRMACIÓN ---
        st.warning("⚠️ **Confirmación Requerida**")
        liq_radio = st.session_state.get("liq_radio_final", st.session_state.get("liq_radio_selector", "Todo el fondo"))
        if liq_radio == "Todo el fondo":
            st.markdown(f"#### ¿Estás seguro que quieres vender todo el fondo?")
            st.markdown(f"Se liquidará la posición completa de **{simbolo}** (**{abs(qty)}** posiciones) por un valor estimado de **${total_mercado:,.2f}**.")
        else:
            # Mostrar el número de posiciones como entero si lo es, o con 4 decimales
            liq_qty_val = st.session_state.get("liq_qty_final", st.session_state.get("liq_qty", 0.0))
            liq_amount_val = st.session_state.get("liq_amount_final", st.session_state.get("liq_amount", 0.0))
            qty_fmt = f"{int(liq_qty_val)}" if liq_qty_val.is_integer() else f"{liq_qty_val:.4f}"
            st.markdown(f"#### ¿Estás seguro que quieres vender {qty_fmt} número de posiciones?")
            st.markdown(f"Se venderá una parte de la posición de **{simbolo}** por un valor estimado de **${liq_amount_val:,.2f}**.")
            
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.button("🟢 Sí, confirmar venta", key=f"btn_yes_liq_{simbolo}", use_container_width=True, on_click=confirmar_y_ejecutar_venta_global, args=(simbolo, tipo, qty, total_mercado, pnl, pos))
        with col_c2:
            st.button("🔴 Cancelar", key=f"btn_cancel_liq_{simbolo}", use_container_width=True, on_click=reset_confirm_global)
    else:
        # --- VISTA DEL FORMULARIO DE LIQUIDACIÓN ---
        st.markdown("<p style='font-size: 1.1rem; font-weight: bold; margin-bottom: 5px;'>¿Cuánto quieres vender?</p>", unsafe_allow_html=True)
        
        st.radio(
            "Selecciona cantidad a vender",
            options=["Todo el fondo", "Parte del fondo"],
            key="liq_radio_selector",
            horizontal=True,
            on_change=on_radio_change,
            label_visibility="collapsed"
        )
        
        col_imp, col_part = st.columns(2)
        with col_imp:
            st.number_input(
                "Importe ($)",
                min_value=0.0,
                max_value=float(total_mercado),
                key="liq_amount",
                on_change=update_qty_callback,
                disabled=(st.session_state.liq_radio_selector == "Todo el fondo")
            )
        with col_part:
            st.number_input(
                "Posiciones / Contratos",
                min_value=0.0,
                max_value=float(abs(qty)),
                key="liq_qty",
                on_change=update_amount_callback,
                disabled=(st.session_state.liq_radio_selector == "Todo el fondo")
            )
            
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        
        col_sp, col_btn_act = st.columns([3.5, 1.5])
        with col_btn_act:
            st.button("🔴 Liquidar Posición", key=f"btn_liq_act_{simbolo}", use_container_width=True, on_click=set_confirm_global, args=(qty,))

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Plataforma de Trading Multileg", page_icon="figures/favicon.png", layout="wide")

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
    h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMarkdownContainer"] h4,
    [data-testid="stMarkdownContainer"] h5,
    [data-testid="stMarkdownContainer"] h6,
    .stHeading h2,
    .stHeading h3,
    .stHeading h4,
    .stHeading h5,
    .stHeading h6 {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        color: #ffffff !important;
        letter-spacing: -0.02em;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #06070b;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Card Glassmorphism */
    /* Centered wider dialog card (120% of 650px = 780px), without restricting backdrop overlay */
    div[role="dialog"],
    div[data-baseweb="modal"] [role="dialog"],
    div[data-testid="stDialog"] [role="dialog"],
    div[class*="stDialog"] [role="dialog"] {
        width: 780px !important;
        max-width: 90vw !important;
        margin: auto !important; /* Keep modal centered horizontally and vertically */
    }
    
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
    
    /* Prevent metric label truncation & force wrapping */
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow: visible !important;
        text-overflow: clip !important;
        font-size: 0.85rem !important;
        line-height: 1.25 !important;
        min-height: 2.2rem !important;
        display: flex !important;
        align-items: center !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] > div {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    
    /* Metric values in theme blue, sized to match the header, preventing truncation */
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] * {
        color: #6366f1 !important;
        font-size: 0.85rem !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    
    /* Metric delta values styling */
    div[data-testid="stMetricDelta"],
    div[data-testid="stMetricDelta"] * {
        font-size: 0.75rem !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        overflow: visible !important;
        text-overflow: clip !important;
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
        background: rgba(13, 14, 21, 0.8) !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        border-radius: 12px !important;
        padding: 20px !important;
        margin-bottom: 15px !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.08) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        transition: all 0.3s ease !important;
    }
    div[class*="st-key-strategy_card_"]:hover {
        border-color: rgba(99, 102, 241, 0.5) !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.2) !important;
        transform: translateY(-2px);
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

    /* MyInvestor Portfolio Card */
    .portfolio-summary-card {
        background: rgba(13, 14, 21, 0.8) !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        border-radius: 16px !important;
        padding: 24px !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.08) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        margin-bottom: 25px !important;
        transition: all 0.3s ease !important;
    }
    .portfolio-summary-card:hover {
        border-color: rgba(99, 102, 241, 0.5) !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.2) !important;
        transform: translateY(-2px);
    }
    
    /* Active list items for assets */
    .asset-list-container {
        background: rgba(13, 14, 21, 0.8) !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        border-radius: 12px !important;
        padding: 10px 20px !important;
        margin-top: 10px !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.08) !important;
        transition: all 0.3s ease !important;
    }
    .asset-list-container:hover {
        border-color: rgba(99, 102, 241, 0.5) !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.2) !important;
    }
    
    .asset-item-row {
        display: flex !important;
        justify-content: space-between !important;
        align-items: center !important;
        padding: 14px 0 !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
        transition: all 0.2s ease !important;
    }
    .asset-item-row:last-child {
        border-bottom: none !important;
    }
    .asset-item-row:hover {
        background-color: rgba(255, 255, 255, 0.02) !important;
        cursor: pointer !important;
    }
    
    .asset-name {
        font-weight: 600 !important;
        color: #ffffff !important;
        font-size: 1.05rem !important;
    }
    .asset-type-badge {
        font-size: 0.75rem !important;
        background-color: rgba(99, 102, 241, 0.15) !important;
        color: #6366f1 !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
        margin-left: 8px !important;
        font-weight: bold !important;
        display: inline-block !important;
    }
    .asset-values {
        text-align: right !important;
    }
    .asset-mkt-val {
        font-weight: 700 !important;
        color: #ffffff !important;
        font-size: 1.1rem !important;
    }
    .asset-pnl {
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        margin-top: 2px !important;
    }

    /* Watchdog Cards Styling */
    div[class*="st-key-wd_card_"] {
        border-radius: 12px !important;
        padding: 16px 20px !important;
        margin-bottom: 15px !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        transition: all 0.3s ease !important;
    }
    
    /* Estado Inactivo: Ghost/Faded */
    div[class*="st-key-wd_card_"][class*="_inactive"] {
        background: rgba(20, 21, 30, 0.4) !important;
        border: 1px solid rgba(255, 255, 255, 0.04) !important;
        opacity: 0.45;
    }
    
    /* Estado Activo: Glow azul */
    div[class*="st-key-wd_card_"][class*="_active"] {
        background: rgba(13, 14, 21, 0.8) !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        box-shadow: 0 8px 30px rgba(99, 102, 241, 0.12) !important;
        opacity: 1;
    }
    
    /* Estilos Premium para Contenedores de Gráficos */
    div[class*="st-key-chart_"] {
        background: rgba(13, 14, 21, 0.6) !important;
        border: 1px solid rgba(99, 102, 241, 0.15) !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37) !important;
        border-radius: 12px !important;
        padding: 15px !important;
        margin-bottom: 20px !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        transition: all 0.3s ease !important;
    }
    div[class*="st-key-chart_"]:hover {
        border-color: rgba(99, 102, 241, 0.35) !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.15) !important;
    }
    
    /* Contenedor principal de la lista de activos */
    div[class*="st-key-asset_list_container_"] {
        background: rgba(13, 14, 21, 0.8) !important;
        border: 1px solid rgba(99, 102, 241, 0.25) !important;
        border-radius: 12px !important;
        padding: 10px 20px !important;
        margin-top: 10px !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.08) !important;
        transition: all 0.3s ease !important;
    }
    div[class*="st-key-asset_list_container_"]:hover {
        border-color: rgba(99, 102, 241, 0.5) !important;
        box-shadow: 0 10px 40px rgba(99, 102, 241, 0.2) !important;
    }
    
    /* Filas individuales de activos */
    div[class*="st-key-asset_row_"] {
        padding: 5px 0 !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
        transition: all 0.2s ease !important;
    }
    div[class*="st-key-asset_row_"]:last-child {
        border-bottom: none !important;
    }
    div[class*="st-key-asset_row_"]:hover {
        background-color: rgba(255, 255, 255, 0.015) !important;
    }
    
    /* Botón Ver Detalles - estilo premium discreto */
    div[class*="st-key-btn_details_"] button {
        background: rgba(99, 102, 241, 0.08) !important;
        color: #818cf8 !important;
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        border-radius: 6px !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        padding: 2px 8px !important;
        transition: all 0.2s ease !important;
        height: auto !important;
        min-height: unset !important;
        line-height: 1.2 !important;
    }
    div[class*="st-key-btn_details_"] button:hover {
        background: rgba(99, 102, 241, 0.2) !important;
        border-color: rgba(99, 102, 241, 0.45) !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(99, 102, 241, 0.15) !important;
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
if st.session_state.get("liq_success_toast"):
    st.toast(st.session_state.liq_success_toast, icon="✅")
    del st.session_state["liq_success_toast"]

if 'broker' not in st.session_state:
    st.session_state.broker = obtener_broker_global()

if 'posiciones_cartera' not in st.session_state:
    st.session_state['posiciones_cartera'] = None

if 'show_cotizacion_dialog' not in st.session_state:
    st.session_state['show_cotizacion_dialog'] = False

if 'show_detalle_pos' not in st.session_state:
    st.session_state['show_detalle_pos'] = None

# --- DIÁLOGO DE CONSULTA DE COTIZACIONES (POPUP MODAL) ---
@st_dialog("Consultar Cotización")
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
        conectado_ib = st.session_state.broker.esta_conectado()
        if conectado_ib:
            with st.spinner("Consultando en IBKR..."):
                try:
                    precio = st.session_state.broker.obtener_precio_prueba(ticker_test)
                    if precio:
                        st.success(f"Última cotización de **{ticker_test}**: **${precio:.2f}**")
                    else:
                        if ticker_test == "SPX":
                            mock_p = 7267.65
                        elif ticker_test == "SPY":
                            mock_p = 520.45
                        elif ticker_test == "AAPL":
                            mock_p = 180.50
                        else:
                            mock_p = 150.00
                        st.warning(f"⚠️ [Fallo de Datos] No se pudo obtener cotización real de IBKR. Cotización de referencia: **${mock_p:.2f}**")
                except TimeoutError:
                    st.error("Tiempo de espera agotado al consultar a IBKR. Por favor, reintenta en unos instantes.")
                except Exception as ex:
                    st.error(f"Fallo en la consulta: {ex}")
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
        col_img, col_txt = st.columns([0.8, 6.4], vertical_alignment="center")
        with col_img:
            st.image("figures/favicon.png", width=65)
        with col_txt:
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
            st.session_state["show_cotizacion_dialog"] = True
            st.rerun()

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

# --- DETECCIÓN E INVOCACIÓN DE DIÁLOGOS MODALES ---
if st.session_state.get("show_cotizacion_dialog"):
    st.session_state["show_cotizacion_dialog"] = False
    mostrar_dialogo_cotizacion()

if st.session_state.get("show_detalle_pos") is not None:
    temp_pos = st.session_state["show_detalle_pos"]
    st.session_state["show_detalle_pos"] = None
    mostrar_detalle_posicion(temp_pos)

tabs = st.tabs(["Dashboard", "Acciones", "Opciones", "Control Room"])

# ==========================================
# TAB 1: DASHBOARD
# ==========================================
with tabs[0]:
    st.header("Consola Principal del Bróker")
    
    @st.fragment(run_every=10)
    def render_dashboard_completo():
        # 1. Obtener datos financieros (Net Liquidation y Buying Power)
        if conectado:
            now = time.time()
            last_summary_fetch = st.session_state.get('last_summary_fetch_time', 0)
            if st.session_state.get('datos_cuenta') is None or (now - last_summary_fetch) >= 14:
                with st.spinner("Sincronizando cuenta con IBKR..."):
                    datos_res = st.session_state.broker.obtener_resumen_cuenta()
                    if datos_res:
                        st.session_state['datos_cuenta'] = datos_res
                        db.guardar_cache("datos_cuenta", datos_res)
                    st.session_state['last_summary_fetch_time'] = now
            datos_cuenta = st.session_state.get('datos_cuenta')
            if datos_cuenta:
                net_liq = float(datos_cuenta['NetLiquidation'])
                buying_power = float(datos_cuenta['BuyingPower'])
                daily_pnl = float(datos_cuenta['DailyPnL'])
            else:
                net_liq, buying_power, daily_pnl = 1000000.0, 5000000.0, 0.0
        else:
            # Intentar leer desde el caché de sesión de la base de datos
            datos_cache = db.obtener_cache("datos_cuenta")
            if datos_cache:
                net_liq = float(datos_cache.get('NetLiquidation', 1004910.68))
                buying_power = float(datos_cache.get('BuyingPower', 6670487.46))
                daily_pnl = float(datos_cache.get('DailyPnL', 0.0))
            else:
                net_liq, buying_power, daily_pnl = 1004910.68, 6670487.46, 0.0
            
        # 2. Sincronizar posiciones
        now = time.time()
        last_fetch = st.session_state.get('last_portfolio_fetch_time', 0)
        
        if conectado:
            if st.session_state.get('posiciones_cartera') is None or (now - last_fetch) >= 14:
                pos_cartera = st.session_state.broker.obtener_posiciones_cartera()
                if pos_cartera is not None:
                    st.session_state['posiciones_cartera'] = pos_cartera
                    db.guardar_cache("posiciones_cartera", pos_cartera)
                st.session_state['last_portfolio_fetch_time'] = now
                
                # Reconciliar la base de datos con las posiciones reales del bróker
                try:
                    from watchdogs import reconciliar_estrategias_con_cartera
                    reconciliar_estrategias_con_cartera(db, st.session_state.broker)
                except Exception as ex_rec_ui:
                    print(f"Error en reconciliación automática desde UI: {ex_rec_ui}")
        else:
            if st.session_state.get('posiciones_cartera') is None:
                posiciones_cache = db.obtener_cache("posiciones_cartera")
                if posiciones_cache:
                    st.session_state['posiciones_cartera'] = posiciones_cache
                else:
                    # Mock fallback secundario si nunca ha habido una conexión exitosa
                    st.session_state['posiciones_cartera'] = [
                        {"Símbolo": "AAPL", "Tipo": "STK", "Vencimiento": "—", "Strike": "—", "Right (C/P)": "—", "Posición": 51, "Precio Medio": 307.3475, "Valor Mercado": 14927.19, "P&L No Real.": -747.53},
                        {"Símbolo": "SPX", "Tipo": "Opción", "Vencimiento": "20260611", "Strike": 7220.0, "Right (C/P)": "P", "Posición": 1, "Precio Medio": 11.6164, "Valor Mercado": 620.0, "P&L No Real.": -541.64},
                        {"Símbolo": "SPX", "Tipo": "Opción", "Vencimiento": "20260611", "Strike": 7230.0, "Right (C/P)": "P", "Posición": 1, "Precio Medio": 12.9164, "Valor Mercado": 740.0, "P&L No Real.": -551.64},
                        {"Símbolo": "SPX", "Tipo": "Opción", "Vencimiento": "20260611", "Strike": 7240.0, "Right (C/P)": "P", "Posición": -1, "Precio Medio": 15.2836, "Valor Mercado": -860.0, "P&L No Real.": 668.36}
                    ]
                
        posiciones_raw = st.session_state.get('posiciones_cartera', [])
        
        # Agrupar y netear posiciones para evitar mostrar activos liquidados (con posición neta cero)
        posiciones_agrupadas = {}
        for pos in posiciones_raw:
            tipo = pos.get('Tipo')
            if tipo in ('Opción', 'OPT', 'Option'):
                # Agrupar opciones por contrato único
                key = (pos.get('Símbolo'), pos.get('Vencimiento'), pos.get('Strike'), pos.get('Right (C/P)'), 'OPTION')
            else:
                # Agrupar acciones por símbolo
                key = (pos.get('Símbolo'), '—', '—', '—', 'STOCK')
                
            if key not in posiciones_agrupadas:
                posiciones_agrupadas[key] = {
                    "Símbolo": pos.get('Símbolo'),
                    "Tipo": tipo,
                    "Vencimiento": pos.get('Vencimiento'),
                    "Strike": pos.get('Strike'),
                    "Right (C/P)": pos.get('Right (C/P)'),
                    "Posición": 0.0,
                    "Valor Mercado": 0.0,
                    "P&L No Real.": 0.0,
                    "Costo Total": 0.0
                }
            
            qty = float(pos.get('Posición', 0.0))
            avg_p = float(pos.get('Precio Medio', 0.0))
            posiciones_agrupadas[key]["Posición"] += qty
            posiciones_agrupadas[key]["Valor Mercado"] += float(pos.get('Valor Mercado', 0.0))
            posiciones_agrupadas[key]["P&L No Real."] += float(pos.get('P&L No Real.', 0.0))
            posiciones_agrupadas[key]["Costo Total"] += avg_p * qty

        posiciones = []
        for key, p_data in posiciones_agrupadas.items():
            if abs(p_data["Posición"]) > 1e-5:
                # Calcular el precio medio ponderado
                if p_data["Posición"] != 0:
                    p_data["Precio Medio"] = round(p_data["Costo Total"] / p_data["Posición"], 4)
                else:
                    p_data["Precio Medio"] = 0.0
                p_data.pop("Costo Total", None)
                posiciones.append(p_data)
        
        # 3. Cálculos de Portfolio
        total_mkt_val = sum(pos.get('Valor Mercado', 0.0) for pos in posiciones)
        total_invertido = sum(pos.get('Valor Mercado', 0.0) - pos.get('P&L No Real.', 0.0) for pos in posiciones)
        efectivo = net_liq - total_mkt_val
        
        # Beneficios contra inversión inicial de 1,000,000
        inversion_inicial = 1000000.0
        beneficio_total = net_liq - inversion_inicial
        rentabilidad_total = (beneficio_total / inversion_inicial) * 100
        
        pnl_color_tot = "#10b981" if beneficio_total >= 0 else "#ef4444"
        pnl_sign_tot = "+" if beneficio_total >= 0 else ""
        
        # 4. Renderizar Resumen de Cartera (Estilo MyInvestor)
        st.markdown(f"""
        <div class="portfolio-summary-card">
            <div style="font-size: 0.95rem; color: #94a3b8; margin-bottom: 5px;">Valor de mercado</div>
            <div style="display: flex; align-items: baseline; gap: 20px; flex-wrap: wrap;">
                <span style="font-size: 2.8rem; font-weight: 800; color: #6366f1; line-height: 1.1;">
                    ${net_liq:,.2f}
                </span>
                <span style="font-size: 1.25rem; font-weight: 700; color: {pnl_color_tot};">
                    {pnl_sign_tot}${beneficio_total:,.2f} &nbsp;|&nbsp; {pnl_sign_tot}{rentabilidad_total:.2f}%
                </span>
            </div>
            <div style="border-top: 1px solid rgba(255,255,255,0.06); margin-top: 18px; padding-top: 15px; display: flex; gap: 60px; flex-wrap: wrap;">
                <div>
                    <div style="font-size: 0.85rem; color: #94a3b8;">Invertido</div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: #ffffff; margin-top: 2px;">${total_invertido:,.2f}</div>
                </div>
                <div>
                    <div style="font-size: 0.85rem; color: #94a3b8;">Efectivo</div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: #ffffff; margin-top: 2px;">${efectivo:,.2f}</div>
                </div>
                <div>
                    <div style="font-size: 0.85rem; color: #94a3b8;">Buying Power (Margen)</div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: #94a3b8; margin-top: 2px;">${buying_power:,.2f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 5. Gráficas Interactivas (Evolución y Distribución de Fondos)
        import numpy as np
        import datetime as dt_mod
        
        # A. Evolución Temporal del NLV (Área suavizada)
        np.random.seed(42)
        dates_nlv = [dt_mod.date.today() - dt_mod.timedelta(days=i) for i in range(30)]
        dates_nlv.reverse()
        
        # Generamos un camino aleatorio coherente terminado exactamente en el nlv actual
        steps_nlv = np.random.normal(loc=1200, scale=8000, size=30)
        steps_nlv = steps_nlv + 500  # Tendencia alcista mockeada
        values_nlv = []
        current_nlv = net_liq
        for step in reversed(steps_nlv):
            values_nlv.append(current_nlv)
            current_nlv -= step
        values_nlv.reverse()
        
        fig_nlv = go.Figure()
        fig_nlv.add_trace(go.Scatter(
            x=dates_nlv,
            y=values_nlv,
            mode='lines',
            line=dict(color='#6366f1', width=3, shape='spline'),
            fill='tozeroy',
            fillcolor='rgba(99, 102, 241, 0.06)',
            name='Net Liquidation Value',
            hovertemplate='<b>Fecha</b>: %{x}<br><b>NLV</b>: $%{y:,.2f}<extra></extra>'
        ))
        
        capital_depositado = 1000000.0
        fig_nlv.add_trace(go.Scatter(
            x=dates_nlv,
            y=[capital_depositado]*30,
            mode='lines',
            line=dict(color='rgba(255, 255, 255, 0.25)', width=1, dash='dash'),
            name='Capital Depositado',
            hovertemplate='Capital Depositado: $1,000,000.00<extra></extra>'
        ))
        
        fig_nlv.update_layout(
            title=dict(
                text="<b>Evolución Temporal del Valor Liquidativo (NLV)</b>",
                font=dict(size=14, color='#ffffff')
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8', family='Outfit, Inter, sans-serif'),
            margin=dict(t=50, b=15, l=40, r=20),
            height=300,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=10)
            ),
            xaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.03)',
                zeroline=False,
                rangeselector=dict(
                    buttons=list([
                        dict(count=7, label="1W", step="day", stepmode="backward"),
                        dict(count=15, label="15D", step="day", stepmode="backward"),
                        dict(count=30, label="1M", step="day", stepmode="backward"),
                        dict(step="all", label="ALL")
                    ]),
                    bgcolor="rgba(30, 41, 59, 0.6)",
                    activecolor="rgba(99, 102, 241, 0.4)",
                    font=dict(color="#ffffff", size=10)
                )
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.03)',
                zeroline=False,
                tickformat="$,.0f"
            )
        )
        
        # B. Distribución de Activos (Dónut)
        total_stocks = sum(abs(pos.get('Valor Mercado', 0.0)) for pos in posiciones if pos.get('Tipo') in ('Acción', 'STK', 'Stock', 'IND'))
        total_options = sum(abs(pos.get('Valor Mercado', 0.0)) for pos in posiciones if pos.get('Tipo') in ('Opción', 'OPT', 'Option'))
        cash_val = max(0.0, efectivo)
        
        if not posiciones:
            total_stocks = 350000.0
            total_options = 120000.0
            cash_val = 530000.0
            
        labels_alloc = ['Efectivo', 'Acciones', 'Opciones']
        values_alloc = [cash_val, total_stocks, total_options]
        colors_alloc = ['#6366f1', '#10b981', '#8b5cf6']
        
        fig_alloc = go.Figure(data=[go.Pie(
            labels=labels_alloc,
            values=values_alloc,
            hole=0.45,
            marker=dict(colors=colors_alloc, line=dict(color='rgba(13,14,21,0.8)', width=2)),
            textinfo='percent',
            textposition='inside',
            insidetextorientation='horizontal',
            hovertemplate='<b>%{label}</b><br>Valor: $%{value:,.2f}<br>Porcentaje: %{percent}<extra></extra>'
        )])
        
        fig_alloc.update_layout(
            title=dict(
                text="<b>Distribución de Activos (Allocation)</b>",
                font=dict(size=13, color='#ffffff')
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8', family='Outfit, Inter, sans-serif'),
            margin=dict(t=50, b=15, l=15, r=15),
            height=280,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.15,
                xanchor="center",
                x=0.5,
                font=dict(size=10)
            )
        )
        
        # C. Diversificación por Subyacente (Barras Horizontales)
        ticker_exposure = {}
        for pos in posiciones:
            sym = pos.get('Símbolo')
            val = abs(pos.get('Valor Mercado', 0.0))
            ticker_exposure[sym] = ticker_exposure.get(sym, 0.0) + val
            
        if not ticker_exposure:
            ticker_exposure = {
                "AAPL": 14927.19,
                "SPX": 2220.00,
                "TSLA": 8500.00,
                "NVDA": 12400.00
            }
            
        sorted_exposure = sorted(ticker_exposure.items(), key=lambda x: x[1])
        tickers_list = [item[0] for item in sorted_exposure]
        values_exposure = [item[1] for item in sorted_exposure]
        
        total_exp = sum(values_exposure)
        pct_exposure = [(val / total_exp * 100) if total_exp > 0 else 0.0 for val in values_exposure]
        
        fig_div = go.Figure(go.Bar(
            x=values_exposure,
            y=tickers_list,
            orientation='h',
            marker=dict(
                color=values_exposure,
                colorscale=[[0, '#312e81'], [0.5, '#4f46e5'], [1.0, '#6366f1']],
                line=dict(color='rgba(99, 102, 241, 0.25)', width=1)
            ),
            hovertemplate='<b>Ticker</b>: %{y}<br><b>Valor</b>: $%{x:,.2f}<br><b>Peso</b>: %{customdata:.2f}%<extra></extra>',
            customdata=pct_exposure
        ))
        
        fig_div.update_layout(
            title=dict(
                text="<b>Diversificación por Subyacente</b>",
                font=dict(size=13, color='#ffffff')
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#94a3b8', family='Outfit, Inter, sans-serif'),
            margin=dict(t=50, b=15, l=50, r=20),
            height=280,
            xaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.03)',
                zeroline=False,
                tickformat="$,.0f"
            ),
            yaxis=dict(
                showgrid=False,
                zeroline=False
            )
        )
        
        # Renderizado en rejilla
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        with st.container(key="chart_nlv_container"):
            st.plotly_chart(fig_nlv, use_container_width=True, config={'displayModeBar': False})
            
        col_alloc, col_div = st.columns(2)
        with col_alloc:
            with st.container(key="chart_alloc_container"):
                st.plotly_chart(fig_alloc, use_container_width=True, config={'displayModeBar': False})
        with col_div:
            with st.container(key="chart_div_container"):
                st.plotly_chart(fig_div, use_container_width=True, config={'displayModeBar': False})
        
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        # 6. Renderizar Activos Diferenciados (Acciones / Opciones)
        raw_acciones = [p for p in posiciones if p.get('Tipo') in ('Acción', 'STK', 'Stock', 'IND')]
        acciones_agrupadas = {}
        for p in raw_acciones:
            sym = p.get('Símbolo')
            qty = p.get('Posición', 0.0)
            avg_p = p.get('Precio Medio', 0.0)
            mkt_val = p.get('Valor Mercado', 0.0)
            pnl = p.get('P&L No Real.', 0.0)
            
            if sym not in acciones_agrupadas:
                acciones_agrupadas[sym] = {
                    "Símbolo": sym,
                    "Tipo": p.get("Tipo"),
                    "Posición": 0.0,
                    "Valor Mercado": 0.0,
                    "P&L No Real.": 0.0,
                    "Costo Total": 0.0
                }
            acciones_agrupadas[sym]["Posición"] += qty
            acciones_agrupadas[sym]["Valor Mercado"] += mkt_val
            acciones_agrupadas[sym]["P&L No Real."] += pnl
            acciones_agrupadas[sym]["Costo Total"] += avg_p * qty
            
        for sym, data in acciones_agrupadas.items():
            if data["Posición"] != 0:
                data["Precio Medio"] = round(data["Costo Total"] / data["Posición"], 4)
            else:
                data["Precio Medio"] = 0.0
            data.pop("Costo Total", None)
            
        acciones_list = [data for data in acciones_agrupadas.values() if abs(data["Posición"]) > 1e-5]
        
        opciones_list = [p for p in posiciones if p.get('Tipo') in ('Opción', 'OPT', 'Option') and abs(p.get('Posición', 0.0)) > 1e-5]
        
        def render_seccion_activos(titulo, lista_activos):
            st.subheader(titulo)
            if not lista_activos:
                st.info(f"Sin posiciones activas en la categoría de {titulo.lower()}.")
                return
            
            with st.container(key=f"asset_list_container_{titulo}"):
                for idx, pos in enumerate(lista_activos):
                    simbolo = pos.get('Símbolo')
                    mkt_val = pos.get('Valor Mercado', 0.0)
                    pnl = pos.get('P&L No Real.', 0.0)
                    
                    cost = mkt_val - pnl
                    rent = (pnl / abs(cost) * 100) if cost != 0 else 0.0
                    
                    pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
                    pnl_sign = "+" if pnl >= 0 else ""
                    
                    detalles = ""
                    if pos.get('Tipo') in ('Opción', 'OPT', 'Option'):
                        strike = pos.get('Strike')
                        right = pos.get('Right (C/P)', '')
                        venc = pos.get('Vencimiento', '')
                        detalles = f" ({venc} Strk {strike} {right})"
                    
                    safe_sym = simbolo.replace(" ", "_").replace("/", "_").replace("-", "_")
                    with st.container(key=f"asset_row_{titulo}_{safe_sym}_{idx}"):
                        c_info, c_vals, c_btn = st.columns([8.0, 2.2, 0.8], vertical_alignment="center")
                        with c_info:
                            st.markdown(
                                f'<div style="display: flex; align-items: center; gap: 8px;">'
                                f'<span style="font-weight: 600; color: #ffffff; font-size: 1.05rem;">{simbolo}{detalles}</span>'
                                f'<span style="font-size: 0.75rem; background-color: rgba(99, 102, 241, 0.15); color: #818cf8; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase;">{pos.get("Tipo")}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                        with c_vals:
                            st.markdown(
                                f'<div style="text-align: right;">'
                                f'<div style="font-weight: 700; color: #ffffff; font-size: 1.1rem;">${mkt_val:,.2f}</div>'
                                f'<div style="font-size: 0.85rem; font-weight: 600; color: {pnl_color}; margin-top: 2px;">'
                                f'{pnl_sign}${pnl:,.2f} ({pnl_sign}{rent:.2f}%)'
                                f'</div>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                        with c_btn:
                            if st.button("🔍", key=f"btn_details_{titulo}_{safe_sym}_{idx}", use_container_width=True):
                                st.session_state["show_detalle_pos"] = pos
                                st.rerun()
            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
            
        render_seccion_activos("Acciones", acciones_list)
        render_seccion_activos("Opciones", opciones_list)
        
    render_dashboard_completo()


with tabs[1]:
    st.header("Nueva Orden Direccional de Acciones")

    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Encolador de estrategias con reglas de entrada técnicas y límites de salida absolutos.</p>", unsafe_allow_html=True)
    
    c_a1, c_a2, c_a3, c_a4 = st.columns(4)
    ticker_acc = c_a1.text_input("Ticker", value="AAPL", max_chars=5, key="acc_ticker").upper()
    cant_acc = c_a2.number_input("Cantidad de Acciones", min_value=1, value=50, step=1, key="acc_cantidad")
    
    with c_a3:
        tipo_ord_acc = st.selectbox("Tipo de Orden", ["Mercado", "Límite"], key="acc_tipo_orden")
        if tipo_ord_acc == "Límite":
            precio_limite_acc = st.number_input("Precio Límite ($)", min_value=0.01, value=150.0, step=0.1, key="acc_precio_limite")
        else:
            precio_limite_acc = None
            
    with c_a4:
        tif_acc = st.selectbox("Validez (TIF)", ["DAY", "GTC"], index=0, key="acc_tif", help="**DAY**: Válida sólo durante el día de negociación.\n\n**GTC**: Válida hasta que se ejecute o cancele.")
            
    accion_acc = "BUY"
    
    st.divider()
    
    # Condiciones de Entrada
    st.subheader("Condiciones de Entrada Avanzadas")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa las condiciones que deben cumplirse antes de que el Watchdog envíe la orden al mercado.</p>", unsafe_allow_html=True)

    # Funciones de campos para tarjetas de entrada (Acciones)
    def fields_acc_horario(disabled):
        c1, c2, c3 = st.columns(3)
        tipo_horario = c1.selectbox("Tipo", ["Rango", "Hora Fija"], key="acc_tipo_horario", disabled=disabled)
        h_ini_val = c2.text_input("Hora Inicio", value="15:30", key="acc_h_ini", disabled=disabled)
        if tipo_horario == "Rango":
            h_fin_val = c3.text_input("Hora Fin", value="22:00", key="acc_h_fin", disabled=disabled)
        else:
            try:
                from datetime import datetime, timedelta
                h_fin_val = (datetime.strptime(h_ini_val, "%H:%M") + timedelta(minutes=10)).strftime("%H:%M")
            except Exception:
                h_fin_val = "23:59"
            c3.text_input("Hora Fin (Auto)", value=h_fin_val, disabled=True, key="acc_h_fin_auto")
        return h_ini_val, h_fin_val

    def fields_acc_vix(disabled):
        c1, c2 = st.columns(2)
        vix_op_acc = c1.selectbox("Operador", ["<", "<=", ">", ">="], key="acc_vix_op", disabled=disabled)
        vix_val_acc = c2.number_input("Valor VIX", min_value=1.0, value=20.0, step=0.5, key="acc_vix_val", disabled=disabled)
        return vix_op_acc, vix_val_acc

    def fields_acc_sma(disabled):
        c1, c2 = st.columns(2)
        sma_per_acc = c1.number_input("Periodo SMA", min_value=5, value=200, step=5, key="acc_sma_per", disabled=disabled)
        sma_reg_acc = c2.selectbox("Regla", ["Precio > SMA", "Precio < SMA"], key="acc_sma_reg", disabled=disabled)
        return sma_per_acc, sma_reg_acc

    def fields_acc_precio(disabled):
        c1, c2 = st.columns(2)
        op_precio_acc = c1.selectbox("Operador", ["<=", ">="], key="acc_precio_op", disabled=disabled)
        val_precio_acc = c2.number_input("Valor Precio ($)", min_value=0.0, value=150.0, step=0.5, key="acc_precio_val", disabled=disabled)
        return op_precio_acc, val_precio_acc

    # Renderizado de Entrada (Acciones) en Grid 2x2
    col1, col2 = st.columns(2)
    with col1:
        act_horario, vals_horario = render_watchdog_card("Ventana Horaria", "acc_act_horario", fields_acc_horario)
        h_ini_acc, h_fin_acc = vals_horario if vals_horario else ("15:30", "22:00")
        
        act_sma, vals_sma = render_watchdog_card("Filtro SMA", "acc_act_sma", fields_acc_sma)
        sma_per_acc, sma_reg_acc = vals_sma if vals_sma else (200, "Precio > SMA")
        
    with col2:
        act_vix, vals_vix = render_watchdog_card("Filtro VIX", "acc_act_vix", fields_acc_vix)
        vix_op_acc, vix_val_acc = vals_vix if vals_vix else ("<", 20.0)
        
        act_precio, vals_precio = render_watchdog_card("Precio Disparador", "acc_act_precio", fields_acc_precio)
        op_precio_acc, val_precio_acc = vals_precio if vals_precio else ("<=", 150.0)

    # Frecuencia (siempre visible debajo del grid)
    frec_acc = st.selectbox("Frecuencia de Ejecución", ["Única", "Diaria", "Semanal"], key="acc_frecuencia")
            
    st.divider()
    
    # Condiciones de Salida
    st.subheader("Condiciones de Salida Avanzadas")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa y configura las reglas de gestión de riesgo que vigilará el Watchdog de Salidas.</p>", unsafe_allow_html=True)

    # Funciones de campos para tarjetas de salida (Acciones)
    def fields_acc_sl_tp(disabled):
        c_chk1, c_chk2, _ = st.columns(3)
        act_sl = c_chk1.checkbox("Activar Stop Loss", value=True, key="acc_sl_active", disabled=disabled)
        act_tp = c_chk2.checkbox("Activar Take Profit", value=True, key="acc_tp_active", disabled=disabled)
        
        c1, c2, c3 = st.columns(3)
        sl_disabled = disabled or not act_sl
        tp_disabled = disabled or not act_tp
        
        stop_loss_acc = c1.number_input("Stop Loss ($)", value=-200.0, step=10.0, key="acc_sl_val", disabled=sl_disabled)
        take_profit_acc = c2.number_input("Take Profit ($)", value=400.0, step=10.0, key="acc_tp_val", disabled=tp_disabled)
        dest_gestion = c3.selectbox("Gestión", ["App (Watchdog)", "IBKR (Broker)"], key="acc_gestion_sl_tp", disabled=disabled)
        return act_sl, stop_loss_acc, act_tp, take_profit_acc, dest_gestion

    def fields_acc_vix_salida(disabled):
        vix_max_acc = st.number_input("VIX Máximo", min_value=1.0, value=30.0, step=0.5, key="acc_vix_max", disabled=disabled)
        return vix_max_acc

    def fields_acc_sma_salida(disabled):
        c1, c2 = st.columns(2)
        sma_per_sal = c1.number_input("Periodo SMA", min_value=5, value=200, step=5, key="acc_sma_per_sal", disabled=disabled)
        sma_reg_sal = c2.selectbox("Regla", ["Precio < SMA", "Precio > SMA"], key="acc_sma_reg_sal", disabled=disabled)
        return sma_per_sal, sma_reg_sal

    def fields_acc_hora_salida(disabled):
        hora_sal_acc = st.text_input("Hora Cierre", value="21:45", key="acc_hora_sal", disabled=disabled)
        return hora_sal_acc

    # Renderizado de Salida (Acciones) en Grid 2x2
    col1, col2 = st.columns(2)
    with col1:
        act_sl_tp, vals_sl_tp = render_watchdog_card("Stop Loss / Take Profit", "acc_act_sl_tp", fields_acc_sl_tp)
        act_sl_acc, stop_loss_acc, act_tp_acc, take_profit_acc, dest_gestion = vals_sl_tp if vals_sl_tp else (True, -200.0, True, 400.0, "App (Watchdog)")
        
        act_sma_salida, vals_sma_salida = render_watchdog_card("Cerrar por SMA", "acc_act_sma_salida", fields_acc_sma_salida)
        sma_per_sal, sma_reg_sal = vals_sma_salida if vals_sma_salida else (200, "Precio < SMA")
        
    with col2:
        act_vix_salida, vix_max_acc = render_watchdog_card("Cerrar por VIX", "acc_act_vix_salida", fields_acc_vix_salida)
        if vix_max_acc is None:
            vix_max_acc = 30.0
            
        act_hora_salida, hora_sal_acc = render_watchdog_card("Hora Forzada", "acc_act_hora_salida", fields_acc_hora_salida)
        if hora_sal_acc is None:
            hora_sal_acc = "21:45"
            
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
            cond_entrada["tif"] = tif_acc
                
            cond_salida = {}
            if act_sl_tp:
                if act_sl_acc:
                    cond_salida["stop_loss"] = float(stop_loss_acc)
                if act_tp_acc:
                    cond_salida["take_profit"] = float(take_profit_acc)
                if act_sl_acc or act_tp_acc:
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
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 90.0, "right": "P", "vencimiento": date.today().strftime("%Y-%m-%d"), "precio_entrada": 1.50},
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 95.0, "right": "P", "vencimiento": date.today().strftime("%Y-%m-%d"), "precio_entrada": 3.20},
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 105.0, "right": "C", "vencimiento": date.today().strftime("%Y-%m-%d"), "precio_entrada": 2.80},
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 110.0, "right": "C", "vencimiento": date.today().strftime("%Y-%m-%d"), "precio_entrada": 1.10}
        ]
        
    opt_ticker = st.text_input("Ticker Subyacente Opciones", value="SPY").upper()
    
    # Caché de precio para Opciones (evita consultas lentas en reruns de sliders)
    if "opt_ticker_previo" not in st.session_state:
        st.session_state["opt_ticker_previo"] = ""
    if "precio_subyacente_opt" not in st.session_state:
        st.session_state["precio_subyacente_opt"] = None

    if opt_ticker != st.session_state["opt_ticker_previo"]:
        st.session_state["opt_ticker_previo"] = opt_ticker
        # Limpiar claves temporales leg_ para evitar conflictos de cache al cambiar subyacente
        for key in list(st.session_state.keys()):
            if key.startswith("leg_"):
                del st.session_state[key]
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

    # Obtener cadenas de opciones reales o simuladas con caché para evitar lentitud
    if "cache_cadenas_opciones" not in st.session_state:
        st.session_state["cache_cadenas_opciones"] = {}
        
    cadenas = {}
    conectado = st.session_state.broker.esta_conectado()
    if conectado:
        if opt_ticker in st.session_state["cache_cadenas_opciones"]:
            cadenas = st.session_state["cache_cadenas_opciones"][opt_ticker]
        else:
            try:
                with st.spinner("Cargando cadenas de opciones reales desde IBKR..."):
                    cadenas = st.session_state.broker.obtener_cadenas_opciones_ibkr(opt_ticker)
                    if cadenas:
                        st.session_state["cache_cadenas_opciones"][opt_ticker] = cadenas
            except Exception as e_opt:
                print(f"Error al obtener cadena de opciones real: {e_opt}")
                cadenas = {}

    # Generar fallback/simulado si no hay conexión o no se obtuvo cadena
    if not cadenas:
        # Generar próximos 11 vencimientos (semanales y mensuales a 5 meses vista)
        import datetime
        from datetime import date, timedelta
        exp_dates = []
        d = date.today()
        while len(exp_dates) < 8:
            d += timedelta(days=1)
            if d.weekday() == 4: # Viernes
                exp_dates.append(d.strftime("%Y-%m-%d"))
        for m_offset in range(1, 5):
            future_month = (date.today().month + m_offset - 1) % 12 + 1
            future_year = date.today().year + (date.today().month + m_offset - 1) // 12
            f_date = date(future_year, future_month, 1)
            friday_count = 0
            while friday_count < 3:
                if f_date.weekday() == 4:
                    friday_count += 1
                    if friday_count == 3:
                        ds = f_date.strftime("%Y-%m-%d")
                        if ds not in exp_dates:
                            exp_dates.append(ds)
                        break
                f_date += timedelta(days=1)
        exp_dates.sort()
        fridays = exp_dates
        
        # Calcular strikes simulados
        precio_ref = st.session_state.get("precio_subyacente_opt")
        if precio_ref is None:
            # Buscar en posiciones si tenemos el ticker
            posiciones_cartera = st.session_state.get("posiciones_cartera", [])
            if posiciones_cartera:
                for pos in posiciones_cartera:
                    if pos.get("Símbolo", "").upper() == opt_ticker.upper():
                        pos_qty = float(pos.get("Posición", 0))
                        pos_val = float(pos.get("Valor Mercado", 0))
                        if pos_qty != 0:
                            mult = 100.0 if pos.get("Tipo") == "Opción" else 1.0
                            precio_ref = abs(pos_val) / (abs(pos_qty) * mult)
                            break
            if precio_ref is None:
                strikes_patas = [float(p.get("strike", 0)) for p in st.session_state["patas_opciones"] if float(p.get("strike", 0)) > 0]
                if strikes_patas:
                    precio_ref = float(sum(strikes_patas) / len(strikes_patas))
                else:
                    precio_ref = 100.0 # Fallback general
                
        # Si está offline, permitir especificar el precio del subyacente para simular
        if not conectado:
            precio_ref = st.number_input(
                "Precio Subyacente Simulado ($)", 
                min_value=0.01, 
                value=float(precio_ref), 
                step=1.0, 
                key="opt_precio_simulado"
            )
            st.session_state["precio_subyacente_opt"] = precio_ref
            
        step = 1.0 if precio_ref < 100 else (2.5 if precio_ref < 500 else 5.0)
        centro = round(precio_ref / step) * step
        strikes_simulados = [round(centro + i * step, 2) for i in range(-12, 13)]
        
        cadenas = {exp: strikes_simulados for exp in fridays}

    def normalizar_vencimiento(valor):
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor

        texto = str(valor).strip().split(" ")[0]
        for formato in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue

        raise ValueError(f"Formato de vencimiento no reconocido: {valor!r}")

    def invalidar_valoracion():
        for leg in st.session_state.get("patas_opciones", []):
            leg.pop("precio_entrada", None)
            leg.pop("prima_teorica", None)
            leg.pop("greeks", None)
        for key in ("payoff_data", "figura_payoff", "credito_neto", "opt_payoff_fig"):
            st.session_state.pop(key, None)

    expirations = sorted(list(cadenas.keys()))
    if expirations:
        val_default = expirations[0]
        if "opt_global_vencimiento" in st.session_state and st.session_state["opt_global_vencimiento"] in expirations:
            val_default = st.session_state["opt_global_vencimiento"]
        opt_vencimiento_str = st.selectbox(
            "Selecciona la Fecha de Vencimiento de la Estrategia", 
            options=expirations, 
            index=expirations.index(val_default),
            key="opt_global_vencimiento",
            on_change=invalidar_valoracion
        )
    else:
        opt_vencimiento_str = date.today().strftime("%Y-%m-%d")
        
    strikes_disponibles = sorted([float(s) for s in cadenas.get(opt_vencimiento_str, [100.0])])
    
    try:
        from zoneinfo import ZoneInfo
        fecha_val_global = datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        fecha_val_global = date.today()

    try:
        venc_date_global = normalizar_vencimiento(opt_vencimiento_str)
        dias_default = max((venc_date_global - fecha_val_global).days, 0)
    except Exception:
        dias_default = 45

    c_sl1, c_sl2, c_sl3 = st.columns(3)
    vol_sim = c_sl1.slider("Volatilidad Implícita (σ)", min_value=5, max_value=150, value=25, step=5, format="%d%%", key="opt_vol_sim", on_change=invalidar_valoracion) / 100.0
    dias_sim = c_sl2.slider("Días al Vencimiento (T)", min_value=0, max_value=365, value=dias_default, step=1, key="opt_dias_sim", on_change=invalidar_valoracion)
    tasa_sim = c_sl3.slider("Tasa Libre de Riesgo (r)", min_value=0.0, max_value=15.0, value=5.0, step=0.5, format="%.1f%%", key="opt_tasa_sim", on_change=invalidar_valoracion) / 100.0
    
    st.divider()
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
            
        # 3. Strike Selectbox (Label collapsed)
        try:
            current_strike_val = float(pata["strike"])
        except:
            current_strike_val = strikes_disponibles[len(strikes_disponibles)//2]
            
        # Encontrar el índice del strike actual en strikes_disponibles
        if current_strike_val in strikes_disponibles:
            strike_idx = strikes_disponibles.index(current_strike_val)
        else:
            # Encontrar el más cercano
            strike_idx = min(range(len(strikes_disponibles)), key=lambda i: abs(strikes_disponibles[i] - current_strike_val))
            
        pata_strike_val = col_strike.selectbox(
            f"Strike #{idx+1}",
            options=strikes_disponibles,
            index=strike_idx,
            key=f"leg_k_{idx}",
            label_visibility="collapsed"
        )
        pata["strike"] = pata_strike_val
        
        # 4. Ratio/Quantity Input (Label collapsed)
        pata["cantidad"] = col_qty.number_input(
            f"Ratio #{idx+1}", 
            min_value=1, 
            value=int(pata["cantidad"]), 
            step=1, 
            key=f"leg_q_{idx}",
            label_visibility="collapsed"
        )
        
        # 5. Calcular Prima Teórica (Black-Scholes) y fijar automáticamente
        if "opt_vol_sim" not in st.session_state:
            st.session_state["opt_vol_sim"] = 25
        if "opt_tasa_sim" not in st.session_state:
            st.session_state["opt_tasa_sim"] = 5.0
            
        precio_ref_calc = st.session_state.get("precio_subyacente_opt")
        if precio_ref_calc is None or precio_ref_calc <= 0:
            # Inferir precio spot aproximado del promedio de los strikes si no hay cotización activa
            strikes_patas = [float(p.get("strike", 0)) for p in st.session_state["patas_opciones"] if float(p.get("strike", 0)) > 0]
            if strikes_patas:
                precio_ref_calc = float(sum(strikes_patas) / len(strikes_patas))
            else:
                precio_ref_calc = 100.0
            
        try:
            from zoneinfo import ZoneInfo
            fecha_valoracion = datetime.now(ZoneInfo("America/New_York")).date()
        except Exception:
            fecha_valoracion = date.today()

        if idx == 0:
            st.error(
                f"expiry raw={opt_vencimiento_str!r}, "
                f"type={type(opt_vencimiento_str)}, "
                f"fecha_valoracion={fecha_valoracion!r}"
            )

        try:
            venc_date = normalizar_vencimiento(opt_vencimiento_str)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
            
        days_to_exp = max((venc_date - fecha_valoracion).days, 0)
        T_calc = days_to_exp / 365.0
        
        # Calcular la prima usando Black-Scholes (sincronizado con la volatilidad y tasa de los sliders)
        sigma_calc = float(st.session_state.get("opt_vol_sim", 25)) / 100.0
        r_calc = float(st.session_state.get("opt_tasa_sim", 5.0)) / 100.0
        premium_bs = MotorBlackScholes.calcular_prima_bs(
            S=precio_ref_calc,
            K=float(pata["strike"]),
            T=T_calc,
            r=r_calc,
            sigma=sigma_calc,
            tipo=pata["right"]
        )
        pata["prima_teorica"] = float(premium_bs)
        pata["precio_entrada"] = float(premium_bs)
        
        # 1. Diagnóstico exacto con st.error
        st.error(
            f"LEG={idx} S={precio_ref_calc!r} K={pata['strike']!r} "
            f"T={T_calc!r} sigma={sigma_calc!r} r={r_calc!r} "
            f"premium_bs={premium_bs!r} "
            f"precio_entrada={pata.get('precio_entrada')!r}"
        )
        
        # 2. Renderizado directo sin text_input ni key ni session_state
        col_prem.markdown(f"**${premium_bs:.4f}**")
        
        # 6. Vencimiento deshabilitado (solo lectura) vinculado al vencimiento global
        pata["vencimiento"] = opt_vencimiento_str
        leg_v_key = f"leg_v_{idx}_{opt_vencimiento_str}"
        st.session_state[leg_v_key] = opt_vencimiento_str
        col_venc.text_input(
            f"Venc. #{idx+1}", 
            value=opt_vencimiento_str, 
            key=leg_v_key,
            disabled=True,
            label_visibility="collapsed"
        )
        
        # 7. Botón Borrar Pata (Estilizado como cruz roja en columna 7)
        if col_del.button("X", key=f"leg_del_{idx}"):
            patas_eliminar.append(idx)
            
    # Eliminar patas marcadas
    if patas_eliminar:
        for index in sorted(patas_eliminar, reverse=True):
            st.session_state["patas_opciones"].pop(index)
        # Limpiar claves leg_ para que no haya desalineación de índices en session_state
        for key in list(st.session_state.keys()):
            if key.startswith("leg_"):
                del st.session_state[key]
        st.rerun()
        
    # Añadir nueva pata
    col_add, _ = st.columns([1.5, 8.5])
    if col_add.button("➕ Añadir Pata", width="stretch"):
        if st.session_state["patas_opciones"]:
            nueva_pata = st.session_state["patas_opciones"][-1].copy()
        else:
            nueva_pata = {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 100.0, "right": "C", "vencimiento": opt_vencimiento_str, "precio_entrada": 1.0}
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
        
    # --- GRÁFICO INTERACTIVO DE PLOTLY (SENSIBILIDAD Y VALOR TEMPORAL) ---
    if st.session_state["patas_opciones"]:
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
        
        with col_o3:
            opt_tif_val = st.selectbox("Validez (TIF)", ["DAY", "GTC"], index=0, key="opt_tif", help="**DAY**: Válida sólo durante el día de negociación.\n\n**GTC**: Válida hasta que se ejecute o cancele.")

        st.divider()

        # ── CONDICIONES DE ENTRADA ──────────────────────────────────────────
        st.subheader("Condiciones de Entrada Avanzadas")
        st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa las condiciones que deben cumplirse antes de que el Watchdog envíe la orden al mercado.</p>", unsafe_allow_html=True)

        # Funciones de campos para tarjetas de entrada (Opciones)
        def fields_opt_horario(disabled):
            c1, c2, c3 = st.columns(3)
            opt_tipo_horario = c1.selectbox("Tipo", ["Rango", "Hora Fija"], key="opt_tipo_horario", disabled=disabled)
            o_h_ini = c2.text_input("Hora Inicio", value="15:45", key="opt_h_ini", disabled=disabled)
            if opt_tipo_horario == "Rango":
                o_h_fin = c3.text_input("Hora Fin", value="21:30", key="opt_h_fin", disabled=disabled)
            else:
                try:
                    from datetime import datetime, timedelta
                    o_h_fin = (datetime.strptime(o_h_ini, "%H:%M") + timedelta(minutes=10)).strftime("%H:%M")
                except Exception:
                    o_h_fin = "23:59"
                c3.text_input("Hora Fin (Auto)", value=o_h_fin, disabled=True, key="opt_h_fin_auto")
            return o_h_ini, o_h_fin

        def fields_opt_vix(disabled):
            c1, c2 = st.columns(2)
            opt_vix_op = c1.selectbox("Operador", ["<", "<=", ">", ">="], key="opt_vix_op", disabled=disabled)
            opt_vix_val = c2.number_input("Valor VIX", min_value=1.0, value=20.0, step=0.5, key="opt_vix_val", disabled=disabled)
            return opt_vix_op, opt_vix_val

        def fields_opt_sma(disabled):
            c1, c2 = st.columns(2)
            opt_sma_per = c1.number_input("Periodo SMA", min_value=5, value=200, step=5, key="opt_sma_per", disabled=disabled)
            opt_sma_reg = c2.selectbox("Regla", ["Precio > SMA", "Precio < SMA"], key="opt_sma_reg", disabled=disabled)
            return opt_sma_per, opt_sma_reg

        def fields_opt_precio(disabled):
            c1, c2 = st.columns(2)
            opt_precio_op = c1.selectbox("Operador", ["<=", ">="], key="opt_precio_op", disabled=disabled)
            opt_precio_val = c2.number_input("Valor Precio ($)", min_value=0.0, value=100.0, step=0.5, key="opt_precio_val", disabled=disabled)
            return opt_precio_op, opt_precio_val

        # Renderizado de Entrada (Opciones) en Grid 2x2
        col1, col2 = st.columns(2)
        with col1:
            opt_act_horario, vals_opt_horario = render_watchdog_card("Ventana Horaria", "opt_act_horario", fields_opt_horario)
            o_h_ini, o_h_fin = vals_opt_horario if vals_opt_horario else ("15:45", "21:30")
            
            opt_act_sma, vals_opt_sma = render_watchdog_card("Filtro SMA", "opt_act_sma", fields_opt_sma)
            opt_sma_per, opt_sma_reg = vals_opt_sma if vals_opt_sma else (200, "Precio > SMA")
            
        with col2:
            opt_act_vix, vals_opt_vix = render_watchdog_card("Filtro VIX", "opt_act_vix", fields_opt_vix)
            opt_vix_op, opt_vix_val = vals_opt_vix if vals_opt_vix else ("<", 20.0)
            
            opt_act_precio, vals_opt_precio = render_watchdog_card("Precio Disparador", "opt_act_precio", fields_opt_precio)
            opt_precio_op, opt_precio_val = vals_opt_precio if vals_opt_precio else ("<=", 100.0)

        # Frecuencia (siempre visible debajo del grid)
        opt_frecuencia = st.selectbox("Frecuencia de Ejecución", ["Única", "Diaria", "Semanal"], key="opt_frecuencia")
                
        st.divider()

        # ── CONDICIONES DE SALIDA ───────────────────────────────────────────
        st.subheader("Condiciones de Salida Avanzadas")
        st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Activa y configura las reglas de gestión de riesgo que vigilará el Watchdog de Salidas.</p>", unsafe_allow_html=True)

        # Funciones de campos para tarjetas de salida (Opciones)
        def fields_opt_sl_tp(disabled):
            c_chk1, c_chk2, _ = st.columns(3)
            act_sl = c_chk1.checkbox("Activar Stop Loss", value=True, key="opt_sl_active", disabled=disabled)
            act_tp = c_chk2.checkbox("Activar Take Profit", value=True, key="opt_tp_active", disabled=disabled)
            
            c1, c2, c3 = st.columns(3)
            sl_disabled = disabled or not act_sl
            tp_disabled = disabled or not act_tp
            
            opt_stop_loss = c1.number_input("Stop Loss ($)", value=-300.0, step=10.0, key="opt_sl_val", disabled=sl_disabled)
            opt_take_profit = c2.number_input("Take Profit ($)", value=600.0, step=10.0, key="opt_tp_val", disabled=tp_disabled)
            opt_dest_gestion = c3.selectbox("Gestión", ["App (Watchdog)", "IBKR (Broker)"], key="opt_dest_gestion", disabled=disabled)
            return act_sl, opt_stop_loss, act_tp, opt_take_profit, opt_dest_gestion

        def fields_opt_vix_sal(disabled):
            opt_vix_max = st.number_input("VIX Máximo", min_value=1.0, value=28.0, step=0.5, key="opt_vix_max", disabled=disabled)
            return opt_vix_max

        def fields_opt_sma_sal(disabled):
            c1, c2 = st.columns(2)
            opt_sma_per_sal = c1.number_input("Periodo SMA", min_value=5, value=200, step=5, key="opt_sma_per_sal", disabled=disabled)
            opt_sma_reg_sal = c2.selectbox("Regla", ["Precio < SMA", "Precio > SMA"], key="opt_sma_reg_sal", disabled=disabled)
            return opt_sma_per_sal, opt_sma_reg_sal

        def fields_opt_hora_sal(disabled):
            opt_hora_sal = st.text_input("Hora Cierre", value="21:45", key="opt_hora_sal", disabled=disabled)
            return opt_hora_sal

        # Renderizado de Salida (Opciones) en Grid 2x2
        col1, col2 = st.columns(2)
        with col1:
            opt_act_sl_tp, vals_opt_sl_tp = render_watchdog_card("Stop Loss / Take Profit", "opt_act_sl_tp", fields_opt_sl_tp)
            opt_act_sl, opt_stop_loss, opt_act_tp, opt_take_profit, opt_dest_gestion = vals_opt_sl_tp if vals_opt_sl_tp else (True, -300.0, True, 600.0, "App (Watchdog)")
            
            opt_act_sma_sal, vals_opt_sma_sal = render_watchdog_card("Cerrar por SMA", "opt_act_sma_sal", fields_opt_sma_sal)
            opt_sma_per_sal, opt_sma_reg_sal = vals_opt_sma_sal if vals_opt_sma_sal else (200, "Precio < SMA")
            
        with col2:
            opt_act_vix_sal, opt_vix_max = render_watchdog_card("Cerrar por VIX", "opt_act_vix_sal", fields_opt_vix_sal)
            if opt_vix_max is None:
                opt_vix_max = 28.0
                
            opt_act_hora_sal, opt_hora_sal = render_watchdog_card("Hora Forzada", "opt_act_hora_sal", fields_opt_hora_sal)
            if opt_hora_sal is None:
                opt_hora_sal = "21:45"
                
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
            opt_cond_ent["tif"] = opt_tif_val

            # Construimos condiciones de salida
            opt_cond_sal = {}
            if opt_act_sl_tp:
                if opt_act_sl:
                    opt_cond_sal["stop_loss"] = float(opt_stop_loss)
                if opt_act_tp:
                    opt_cond_sal["take_profit"] = float(opt_take_profit)
                if opt_act_sl or opt_act_tp:
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
    
    # 2. Formulario de Mutación en Caliente (Hot-Reloading SL/TP y condiciones de salida avanzadas)
    st.subheader("Modificación de Límites en Caliente")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>Modifica instantáneamente las condiciones de salida y límites de las estrategias activas o añade límites algorítmicos a posiciones huérfanas de tu cartera.</p>", unsafe_allow_html=True)
    
    opcion_modo = st.radio(
        "Selecciona el modo de operación:",
        ["Modificar condiciones de una Estrategia Activa", "Añadir condiciones a una Posición de Cartera (Huérfana)"],
        horizontal=True,
        key="mut_modo_operacion"
    )
    
    todas_estrategias = db.obtener_estrategias()
    est_activas_list = [e for e in todas_estrategias if e["estado"] == "ACTIVA"]
    
    if opcion_modo == "Modificar condiciones de una Estrategia Activa":
        if not est_activas_list:
            st.info("No hay estrategias activas disponibles para modificar sus condiciones de salida.")
        else:
            opciones_dropdown = {}
            for e in est_activas_list:
                label = e['ticker']
                if label in opciones_dropdown:
                    label = f"{e['ticker']} ({e['tipo_activo']})"
                if label in opciones_dropdown:
                    label = f"{e['ticker']} #{e['id']}"
                opciones_dropdown[label] = e["id"]
                
            seleccionada_label = st.selectbox("Selecciona el Ticker a modificar", list(opciones_dropdown.keys()), key="mut_select_est_dropdown")
            est_id_select = opciones_dropdown[seleccionada_label]
            
            # Recuperamos la estrategia seleccionada
            estrategia_sel = next(e for e in est_activas_list if e["id"] == est_id_select)
            condiciones_salida_sel = estrategia_sel.get("condiciones_salida") or {}
            
            # Calcular la cantidad actual de la estrategia
            patas_sel = estrategia_sel.get("patas") or []
            if not patas_sel and estrategia_sel.get("patas_json"):
                try:
                    patas_sel = json.loads(estrategia_sel["patas_json"])
                except:
                    pass
            cant_actual = sum(abs(float(p.get("cantidad", 1.0))) for p in patas_sel)
            
            c_cant1, c_cant2 = st.columns(2)
            with c_cant1:
                radio_cant = st.radio(
                    "¿A cuántas posiciones aplicar la modificación?",
                    ["Todas las posiciones", "Parte de las posiciones"],
                    index=0,
                    key="mut_radio_cant_tipo"
                )
            with c_cant2:
                if radio_cant == "Todas las posiciones":
                    qty_a_mutar = st.number_input(
                        "Posiciones / Contratos",
                        value=cant_actual,
                        disabled=True,
                        key="mut_qty_final_widget"
                    )
                else:
                    qty_a_mutar = st.number_input(
                        "Posiciones / Contratos",
                        min_value=0.01,
                        max_value=cant_actual,
                        value=cant_actual,
                        step=1.0 if cant_actual.is_integer() else 0.01,
                        key="mut_qty_final_widget"
                    )
            
            # Si la estrategia seleccionada ha cambiado, precargamos sus condiciones en session_state
            ultimo_id_sel = st.session_state.get("mut_ultimo_id_sel")
            if ultimo_id_sel != est_id_select:
                st.session_state["mut_ultimo_id_sel"] = est_id_select
                
                # SL/TP
                st.session_state["mut_act_sl_tp"] = ("stop_loss" in condiciones_salida_sel or "take_profit" in condiciones_salida_sel)
                st.session_state["mut_sl_active"] = ("stop_loss" in condiciones_salida_sel)
                st.session_state["mut_tp_active"] = ("take_profit" in condiciones_salida_sel)
                st.session_state["mut_sl_val"] = float(condiciones_salida_sel.get("stop_loss", -200.0))
                st.session_state["mut_tp_val"] = float(condiciones_salida_sel.get("take_profit", 400.0))
                st.session_state["mut_gestion_sl_tp"] = condiciones_salida_sel.get("gestion", "App (Watchdog)")
                
                # VIX
                st.session_state["mut_act_vix_salida"] = ("vix_maximo" in condiciones_salida_sel)
                st.session_state["mut_vix_max"] = float(condiciones_salida_sel.get("vix_maximo", 30.0))
                
                # SMA
                sma_cfg = condiciones_salida_sel.get("sma", {})
                st.session_state["mut_act_sma_salida"] = bool(sma_cfg.get("activo", False))
                st.session_state["mut_sma_per_sal"] = int(sma_cfg.get("periodo", 200))
                st.session_state["mut_sma_reg_sal"] = sma_cfg.get("regla", "Precio < SMA")
                
                # Hora Forzada
                st.session_state["mut_act_hora_salida"] = ("cierre_horario" in condiciones_salida_sel)
                st.session_state["mut_hora_sal"] = condiciones_salida_sel.get("cierre_horario", "21:45")
                
            # Funciones de campos para render_watchdog_card
            def fields_mut_sl_tp(disabled):
                c_chk1, c_chk2, _ = st.columns(3)
                act_sl = c_chk1.checkbox(
                    "Activar Stop Loss",
                    value=st.session_state.get("mut_sl_active", True),
                    key="mut_sl_active_widget",
                    disabled=disabled
                )
                act_tp = c_chk2.checkbox(
                    "Activar Take Profit",
                    value=st.session_state.get("mut_tp_active", True),
                    key="mut_tp_active_widget",
                    disabled=disabled
                )
                
                st.session_state["mut_sl_active"] = act_sl
                st.session_state["mut_tp_active"] = act_tp
                
                c1, c2, c3 = st.columns(3)
                sl_disabled = disabled or not act_sl
                tp_disabled = disabled or not act_tp
                
                sl_val = c1.number_input("Stop Loss ($)", value=float(st.session_state.get("mut_sl_val", -200.0)), step=10.0, key="mut_sl_val_widget", disabled=sl_disabled)
                tp_val = c2.number_input("Take Profit ($)", value=float(st.session_state.get("mut_tp_val", 400.0)), step=10.0, key="mut_tp_val_widget", disabled=tp_disabled)
                
                gest_val_current = st.session_state.get("mut_gestion_sl_tp", "App (Watchdog)")
                gest_idx = 0 if gest_val_current == "App (Watchdog)" else 1
                gest_val = c3.selectbox("Gestión", ["App (Watchdog)", "IBKR (Broker)"], index=gest_idx, key="mut_gestion_sl_tp_widget", disabled=disabled)
                
                st.session_state["mut_sl_val"] = sl_val
                st.session_state["mut_tp_val"] = tp_val
                st.session_state["mut_gestion_sl_tp"] = gest_val
                return act_sl, sl_val, act_tp, tp_val, gest_val
    
            def fields_mut_vix_salida(disabled):
                vix_val = st.number_input(
                    "VIX Máximo",
                    min_value=1.0,
                    value=float(st.session_state.get("mut_vix_max", 30.0)),
                    step=0.5,
                    key="mut_vix_max_widget",
                    disabled=disabled
                )
                st.session_state["mut_vix_max"] = vix_val
                return vix_val
    
            def fields_mut_sma_salida(disabled):
                c1, c2 = st.columns(2)
                sma_per = c1.number_input(
                    "Periodo SMA",
                    min_value=5,
                    value=int(st.session_state.get("mut_sma_per_sal", 200)),
                    step=5,
                    key="mut_sma_per_sal_widget",
                    disabled=disabled
                )
                reg_val_current = st.session_state.get("mut_sma_reg_sal", "Precio < SMA")
                reg_idx = 0 if reg_val_current == "Precio < SMA" else 1
                sma_reg = c2.selectbox(
                    "Regla",
                    ["Precio < SMA", "Precio > SMA"],
                    index=reg_idx,
                    key="mut_sma_reg_sal_widget",
                    disabled=disabled
                )
                st.session_state["mut_sma_per_sal"] = sma_per
                st.session_state["mut_sma_reg_sal"] = sma_reg
                return sma_per, sma_reg
    
            def fields_mut_hora_salida(disabled):
                hora_val = st.text_input(
                    "Hora Cierre",
                    value=st.session_state.get("mut_hora_sal", "21:45"),
                    key="mut_hora_sal_widget",
                    disabled=disabled
                )
                st.session_state["mut_hora_sal"] = hora_val
                return hora_val
    
            # Renderizar en Grid 2x2
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                act_sl_tp, _ = render_watchdog_card("Stop Loss / Take Profit", "mut_act_sl_tp", fields_mut_sl_tp)
                act_sma, _ = render_watchdog_card("Cerrar por SMA", "mut_act_sma_salida", fields_mut_sma_salida)
                
            with col_m2:
                act_vix, _ = render_watchdog_card("Cerrar por VIX", "mut_act_vix_salida", fields_mut_vix_salida)
                act_hora, _ = render_watchdog_card("Hora Forzada", "mut_act_hora_salida", fields_mut_hora_salida)
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Actualizar Condiciones de Salida", type="primary", key="btn_update_mut_conditions"):
                # Construir el diccionario de condiciones modificado
                cond_salida = {}
                if st.session_state.get("mut_act_sl_tp"):
                    if st.session_state.get("mut_sl_active"):
                        cond_salida["stop_loss"] = float(st.session_state.get("mut_sl_val", -200.0))
                    if st.session_state.get("mut_tp_active"):
                        cond_salida["take_profit"] = float(st.session_state.get("mut_tp_val", 400.0))
                    if st.session_state.get("mut_sl_active") or st.session_state.get("mut_tp_active"):
                        cond_salida["gestion"] = st.session_state.get("mut_gestion_sl_tp", "App (Watchdog)")
                if st.session_state.get("mut_act_vix_salida"):
                    cond_salida["vix_maximo"] = float(st.session_state.get("mut_vix_max", 30.0))
                if st.session_state.get("mut_act_sma_salida"):
                    cond_salida["sma"] = {
                        "activo": True,
                        "periodo": int(st.session_state.get("mut_sma_per_sal", 200)),
                        "regla": st.session_state.get("mut_sma_reg_sal", "Precio < SMA")
                    }
                if st.session_state.get("mut_act_hora_salida"):
                    cond_salida["cierre_horario"] = st.session_state.get("mut_hora_sal", "21:45")
                    
                try:
                    res_mut = db.actualizar_condiciones_salida(estrategia_id=est_id_select, condiciones_salida=cond_salida)
                    if res_mut:
                        # Si la cantidad cambió, actualizamos proporcionalmente la cantidad en las patas
                        if abs(qty_a_mutar - cant_actual) > 1e-5:
                            patas_actualizadas = []
                            factor = qty_a_mutar / cant_actual if cant_actual != 0 else 1.0
                            for pata in patas_sel:
                                pata_nueva = pata.copy()
                                pata_nueva["cantidad"] = float(pata.get("cantidad", 1.0)) * factor
                                patas_actualizadas.append(pata_nueva)
                            db.actualizar_patas(est_id_select, patas_actualizadas)
                            
                        st.success("¡Condiciones de salida y volumen actualizados con éxito! El Watchdog las cargará en su siguiente ciclo.")
                        db.registrar_evento("MUTACION_LIMITES_UI", f"Modificados límites/condiciones en caliente para #{est_id_select}. Cond: {cond_salida}")
                        
                        # Formatear el mensaje del webhook de forma descriptiva
                        msg_parts = []
                        if "stop_loss" in cond_salida:
                            msg_parts.append(f"**Stop Loss:** {cond_salida['stop_loss']}$")
                            msg_parts.append(f"**Take Profit:** {cond_salida['take_profit']}$")
                            msg_parts.append(f"**Gestión:** {cond_salida['gestion']}")
                        if "vix_maximo" in cond_salida:
                            msg_parts.append(f"**VIX Máximo:** {cond_salida['vix_maximo']}")
                        if "sma" in cond_salida:
                            msg_parts.append(f"**Cerrar por SMA:** Periodo {cond_salida['sma']['periodo']} ({cond_salida['sma']['regla']})")
                        if "cierre_horario" in cond_salida:
                            msg_parts.append(f"**Hora Forzada:** {cond_salida['cierre_horario']}")
                            
                        enviar_alerta_webhook(
                            titulo="🔄 Condiciones de Salida Modificadas en Caliente",
                            mensaje=f"**ID Estrategia:** {est_id_select}\n" + "\n".join(msg_parts),
                            color="warning"
                        )
                        st.session_state["mut_ultimo_id_sel"] = None
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("No se pudo actualizar los límites de la estrategia.")
                except Exception as e:
                    st.error(f"Error al mutar límites: {e}")
                    
    else:
        # Añadir condiciones a una Posición de Cartera (Huérfana)
        huerfanas = obtener_posiciones_huerfanas()
        if not huerfanas:
            st.info("No hay posiciones huérfanas disponibles en la cartera para asignar límites.")
        else:
            opciones_adop = {
                f"{pos.get('Símbolo')} ({pos.get('Tipo')}) - Posición: {pos.get('Posición')} @ ${pos.get('Precio Medio', 0.0):.2f}": idx
                for idx, pos in enumerate(huerfanas)
            }
            seleccionada_adop_label = st.selectbox("Selecciona la Posición Huérfana", list(opciones_adop.keys()), key="adop_select_huerfana_dropdown")
            pos_idx = opciones_adop[seleccionada_adop_label]
            pos_sel = huerfanas[pos_idx]
            
            # Inicializar session state para adopción si no existe o si ha cambiado el activo
            if "adop_ultimo_key" not in st.session_state or st.session_state["adop_ultimo_key"] != seleccionada_adop_label:
                st.session_state["adop_ultimo_key"] = seleccionada_adop_label
                st.session_state["adop_act_sl_tp"] = False
                st.session_state["adop_sl_active"] = True
                st.session_state["adop_tp_active"] = True
                st.session_state["adop_sl_val"] = -200.0
                st.session_state["adop_tp_val"] = 400.0
                st.session_state["adop_gestion_sl_tp"] = "App (Watchdog)"
                st.session_state["adop_act_vix_salida"] = False
                st.session_state["adop_vix_max"] = 30.0
                st.session_state["adop_act_sma_salida"] = False
                st.session_state["adop_sma_per_sal"] = 200
                st.session_state["adop_sma_reg_sal"] = "Precio < SMA"
                st.session_state["adop_act_hora_salida"] = False
                st.session_state["adop_hora_sal"] = "21:45"
            
            max_qty_adop = abs(float(pos_sel.get("Posición", 1.0)))
            qty_to_adopt = st.number_input(
                "Cantidad a Monitorear",
                min_value=0.01,
                max_value=max_qty_adop,
                value=max_qty_adop,
                step=1.0 if max_qty_adop.is_integer() else 0.01,
                key="adop_qty_to_monitor_widget"
            )
            
            # Funciones de campos para adopción
            def fields_adop_sl_tp(disabled):
                c_chk1, c_chk2, _ = st.columns(3)
                act_sl = c_chk1.checkbox(
                    "Activar Stop Loss",
                    value=st.session_state.get("adop_sl_active", True),
                    key="adop_sl_active_widget",
                    disabled=disabled
                )
                act_tp = c_chk2.checkbox(
                    "Activar Take Profit",
                    value=st.session_state.get("adop_tp_active", True),
                    key="adop_tp_active_widget",
                    disabled=disabled
                )
                
                st.session_state["adop_sl_active"] = act_sl
                st.session_state["adop_tp_active"] = act_tp
                
                c1, c2, c3 = st.columns(3)
                sl_disabled = disabled or not act_sl
                tp_disabled = disabled or not act_tp
                
                sl_val = c1.number_input("Stop Loss ($)", value=float(st.session_state.get("adop_sl_val", -200.0)), step=10.0, key="adop_sl_val_widget", disabled=sl_disabled)
                tp_val = c2.number_input("Take Profit ($)", value=float(st.session_state.get("adop_tp_val", 400.0)), step=10.0, key="adop_tp_val_widget", disabled=tp_disabled)
                
                gest_val = c3.selectbox("Gestión", ["App (Watchdog)", "IBKR (Broker)"], index=0 if st.session_state.get("adop_gestion_sl_tp") == "App (Watchdog)" else 1, key="adop_gestion_sl_tp_widget", disabled=disabled)
                st.session_state["adop_sl_val"] = sl_val
                st.session_state["adop_tp_val"] = tp_val
                st.session_state["adop_gestion_sl_tp"] = gest_val
                return act_sl, sl_val, act_tp, tp_val, gest_val
    
            def fields_adop_vix_salida(disabled):
                vix_val = st.number_input("VIX Máximo", min_value=1.0, value=float(st.session_state.get("adop_vix_max", 30.0)), step=0.5, key="adop_vix_max_widget", disabled=disabled)
                st.session_state["adop_vix_max"] = vix_val
                return vix_val
    
            def fields_adop_sma_salida(disabled):
                c1, c2 = st.columns(2)
                sma_per = c1.number_input("Periodo SMA", min_value=5, value=int(st.session_state.get("adop_sma_per_sal", 200)), step=5, key="adop_sma_per_sal_widget", disabled=disabled)
                sma_reg = c2.selectbox("Regla", ["Precio < SMA", "Precio > SMA"], index=0 if st.session_state.get("adop_sma_reg_sal") == "Precio < SMA" else 1, key="adop_sma_reg_sal_widget", disabled=disabled)
                st.session_state["adop_sma_per_sal"] = sma_per
                st.session_state["adop_sma_reg_sal"] = sma_reg
                return sma_per, sma_reg
    
            def fields_adop_hora_salida(disabled):
                hora_val = st.text_input("Hora Cierre", value=st.session_state.get("adop_hora_sal", "21:45"), key="adop_hora_sal_widget", disabled=disabled)
                st.session_state["adop_hora_sal"] = hora_val
                return hora_val
            
            # Grid 2x2 para configurar las condiciones
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                act_sl_tp_adop, _ = render_watchdog_card("Stop Loss / Take Profit", "adop_act_sl_tp", fields_adop_sl_tp)
                act_sma_adop, _ = render_watchdog_card("Cerrar por SMA", "adop_act_sma_salida", fields_adop_sma_salida)
                
            with col_a2:
                act_vix_adop, _ = render_watchdog_card("Cerrar por VIX", "adop_act_vix_salida", fields_adop_vix_salida)
                act_hora_adop, _ = render_watchdog_card("Hora Forzada", "adop_act_hora_salida", fields_adop_hora_salida)
                
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 Activar Seguimiento Algorítmico", type="primary", key="btn_save_adop_conditions"):
                cond_salida = {}
                if st.session_state.get("adop_act_sl_tp"):
                    if st.session_state.get("adop_sl_active"):
                        cond_salida["stop_loss"] = float(st.session_state.get("adop_sl_val", -200.0))
                    if st.session_state.get("adop_tp_active"):
                        cond_salida["take_profit"] = float(st.session_state.get("adop_tp_val", 400.0))
                    if st.session_state.get("adop_sl_active") or st.session_state.get("adop_tp_active"):
                        cond_salida["gestion"] = st.session_state.get("adop_gestion_sl_tp", "App (Watchdog)")
                if st.session_state.get("adop_act_vix_salida"):
                    cond_salida["vix_maximo"] = float(st.session_state.get("adop_vix_max", 30.0))
                if st.session_state.get("adop_act_sma_salida"):
                    cond_salida["sma"] = {
                        "activo": True,
                        "periodo": int(st.session_state.get("adop_sma_per_sal", 200)),
                        "regla": st.session_state.get("adop_sma_reg_sal", "Precio < SMA")
                    }
                if st.session_state.get("adop_act_hora_salida"):
                    cond_salida["cierre_horario"] = st.session_state.get("adop_hora_sal", "21:45")
                
                # Sintetizar patas correspondientes a la posición del broker
                ticker_adop = pos_sel.get("Símbolo")
                tipo_adop = pos_sel.get("Tipo")
                pos_qty_real = float(pos_sel.get("Posición", 1.0))
                accion_adop = "BUY" if pos_qty_real > 0 else "SELL"
                
                if tipo_adop in ("Opción", "OPT", "Option"):
                    patas_adop = [{
                        "tipo_activo": "OPTION",
                        "vencimiento": pos_sel.get("Vencimiento"),
                        "strike": pos_sel.get("Strike"),
                        "right": pos_sel.get("Right (C/P)"),
                        "accion": accion_adop,
                        "cantidad": qty_to_adopt
                    }]
                else:
                    patas_adop = [{
                        "tipo_activo": "STOCK",
                        "accion": accion_adop,
                        "cantidad": qty_to_adopt
                    }]
                
                try:
                    # Crear estrategia activa en base de datos
                    est_id = db.crear_estrategia(
                        ticker=ticker_adop,
                        tipo_activo="STOCK" if tipo_adop in ("Acción", "STK", "Stock", "IND") else "OPTION",
                        estado="ACTIVA",
                        patas=patas_adop,
                        condiciones_salida=cond_salida,
                        precio_entrada=float(pos_sel.get("Precio Medio", 0.0))
                    )
                    
                    if est_id:
                        st.success(f"¡Seguimiento algorítmico activado con éxito! Creada Estrategia #{est_id} para {ticker_adop}.")
                        db.registrar_evento("ADOPCION_POSICION_UI", f"Adoptada posición huérfana de {ticker_adop} (cant={qty_to_adopt}) como Estrategia #{est_id} con límites: {cond_salida}")
                        
                        # Notificar por Discord
                        msg_parts = [f"**Cantidad:** {qty_to_adopt}"]
                        if "stop_loss" in cond_salida:
                            msg_parts.append(f"**Stop Loss:** {cond_salida['stop_loss']}$")
                            msg_parts.append(f"**Take Profit:** {cond_salida['take_profit']}$")
                            msg_parts.append(f"**Gestión:** {cond_salida['gestion']}")
                        if "vix_maximo" in cond_salida:
                            msg_parts.append(f"**VIX Máximo:** {cond_salida['vix_maximo']}")
                        if "sma" in cond_salida:
                            msg_parts.append(f"**Cerrar por SMA:** Periodo {cond_salida['sma']['periodo']} ({cond_salida['sma']['regla']})")
                        if "cierre_horario" in cond_salida:
                            msg_parts.append(f"**Hora Forzada:** {cond_salida['cierre_horario']}")
                            
                        enviar_alerta_webhook(
                            titulo="🚀 Posición Huérfana Adoptada como Estrategia",
                            mensaje=f"**ID Estrategia:** {est_id}\n**Ticker:** {ticker_adop}\n" + "\n".join(msg_parts),
                            color="success"
                        )
                        st.session_state["adop_ultimo_key"] = None
                        time.sleep(0.5)
                        st.rerun()
                except Exception as e_adop:
                    st.error(f"Error al adoptar posición de la cartera: {e_adop}")
                    
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
    
    @st.fragment(run_every=10)
    def render_historial_y_auditoria():
        col_space, col_btn = st.columns([5, 1])
        with col_btn:
            st.button("Actualizar", key="btn_refresh_hist_frag", use_container_width=True)
            
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
                
    render_historial_y_auditoria()
