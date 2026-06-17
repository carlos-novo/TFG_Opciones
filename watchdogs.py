import time
import threading
from datetime import datetime, timedelta
from base_datos import GestorBaseDatos
from conexion_ibkr import GestorIBKR
from motor_logica import MotorEstrategias, MotorSalida
from notificaciones import enviar_alerta_webhook

# Eventos de parada globales para control limpio de hilos
stop_entradas = threading.Event()
stop_salidas = threading.Event()

def watchdog_entradas_worker(db_name, interval, stop_event, broker=None):
    """
    Worker del Watchdog de Entradas:
    Vigila estrategias en estado 'PENDIENTE_ENTRADA'. Evalúa condiciones
    de mercado y lanza órdenes de entrada reales al cumplirse las reglas.
    """
    db = GestorBaseDatos(db_name=db_name)
    es_compartido = (broker is not None)
    if not es_compartido:
        broker = GestorIBKR(client_id=2)
    
    print(f"[WATCHDOG ENTRADAS] Iniciado correctamente (compartido={es_compartido}).")
    
    conectado = False
    try:
        while not stop_event.is_set():
            try:
                # 1. Obtener estrategias pendientes de entrada
                pendientes = db.obtener_estrategias(estado="PENDIENTE_ENTRADA")
                
                if pendientes:
                    # Nos conectamos a IBKR solo si hay tareas pendientes (o si ya está conectado en modo compartido)
                    if (es_compartido and broker.esta_conectado()) or (not es_compartido and broker.conectar()):
                        conectado = True
                        for est in pendientes:
                            if stop_event.is_set():
                                break
                            ticker = est["ticker"]
                            tipo_activo = est["tipo_activo"]
                            condiciones = est["condiciones_entrada"]
                            precio_entrada_target = est["precio_entrada"]
                            
                            # --- FILTRADO POR FRECUENCIA / RECURRENCIA ---
                            frecuencia_cfg = condiciones.get("frecuencia") if condiciones else None
                            if frecuencia_cfg and frecuencia_cfg.get("activo", False):
                                proxima_ejecucion_str = frecuencia_cfg.get("proxima_ejecucion")
                                if proxima_ejecucion_str:
                                    try:
                                        proxima_dt = datetime.fromisoformat(proxima_ejecucion_str)
                                        if datetime.now() < proxima_dt:
                                            # Aún no corresponde evaluar esta estrategia recurrente
                                            continue
                                    except Exception as ex_freq:
                                        print(f"[WATCHDOG ENTRADAS] Error al calcular delay de frecuencia para ID {est['id']}: {ex_freq}")
                            
                            # Obtener precio actual de mercado del subyacente
                            try:
                                precio_actual = broker.obtener_precio_prueba(ticker)
                                if precio_actual is None:
                                    print(f"[WATCHDOG ENTRADAS] No se pudo obtener precio para {ticker}. Reintentando en el próximo ciclo.")
                                    continue
                            except Exception as e:
                                err_msg = str(e)
                                # Si es por falta de definición (o cualquier error de contrato no calificado)
                                if "Ticker no válido" in err_msg or "Contrato no válido" in err_msg or "No security definition" in err_msg:
                                    print(f"[WATCHDOG ENTRADAS] Contrato inválido detectado para {ticker}. Marcando estrategia #{est['id']} en error.")
                                    db.actualizar_estado_estrategia(
                                        estrategia_id=est["id"],
                                        nuevo_estado="Contrato Inválido"
                                    )
                                    db.registrar_evento(
                                        "WATCHDOG_ENTRADA_ERROR_CONTRATO",
                                        f"Estrategia ID {est['id']} ({ticker}) marcada como 'Contrato Inválido' debido a error: {err_msg}"
                                    )
                                    enviar_alerta_webhook(
                                        titulo="⚠️ Error de Contrato en Watchdog",
                                        mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Error:** {err_msg}\nLa estrategia ha sido marcada como 'Contrato Inválido' y no se seguirá evaluando.",
                                        color="warning"
                                    )
                                else:
                                    print(f"[WATCHDOG ENTRADAS] Error al obtener precio para {ticker}: {e}")
                                continue
                                
                            # Evaluar condiciones
                            evaluacion = MotorEstrategias.evaluar_condiciones_entrada(
                                gestor_ibkr=broker,
                                ticker=ticker,
                                condiciones_entrada=condiciones,
                                precio_actual=precio_actual
                            )
                            
                            if evaluacion["autorizado"]:
                                print(f"[WATCHDOG ENTRADAS] Condiciones CUMPLIDAS para Estrategia ID {est['id']} ({ticker})")
                                
                                # Enviar orden genérica
                                try:
                                    res_orden = broker.enviar_orden_generica(
                                        ticker=ticker,
                                        tipo_activo=tipo_activo,
                                        patas=est["patas"],
                                        precio_limite=precio_entrada_target
                                    )
                                    
                                    oid = res_orden["order_id"]
                                    status = res_orden["status"]
                                    
                                    # Si la orden se transmite con éxito
                                    # Nota: Usamos el precio de entrada target o el actual
                                    pr_entrada = precio_entrada_target if precio_entrada_target is not None else precio_actual
                                    
                                    db.actualizar_estado_estrategia(
                                        estrategia_id=est["id"],
                                        nuevo_estado="ACTIVA",
                                        order_id_entrada=oid,
                                        precio_entrada=pr_entrada,
                                        fecha_ejecucion=datetime.now().isoformat()
                                    )
                                    
                                    db.registrar_evento(
                                        "WATCHDOG_ENTRADA_EJECUTADA",
                                        f"Estrategia ID {est['id']} ({ticker}) activada. OrderID: {oid}. Estado: {status}"
                                    )
                                    
                                    # Alerta Webhook
                                    enviar_alerta_webhook(
                                        titulo="🚀 Estrategia Lanzada por Watchdog",
                                        mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Tipo Activo:** {tipo_activo}\n**Precio/Prima Entrada:** {pr_entrada}$\n**OrderID:** {oid}\n**Estado Orden:** {status}",
                                        color="success"
                                    )
                                    
                                    # Si es de tipo STOCK y la gestión de salida es en el bróker, colocamos SL y TP allí de inmediato
                                    if tipo_activo == "STOCK" and est.get("condiciones_salida", {}).get("gestion") == "Gestionado por IBKR (Órdenes en Broker)":
                                        try:
                                            res_prot = broker.enviar_ordenes_proteccion_ibkr(
                                                ticker=ticker,
                                                accion_entrada=est["patas"][0]["accion"],
                                                cantidad=est["patas"][0]["cantidad"],
                                                precio_entrada=pr_entrada,
                                                stop_loss_usd=est["condiciones_salida"].get("stop_loss"),
                                                take_profit_usd=est["condiciones_salida"].get("take_profit")
                                            )
                                            db.registrar_evento(
                                                "IBKR_PROTECTION_ORDERS_SENT",
                                                f"Enviadas órdenes de protección en bróker para Estrategia #{est['id']}. Detalles: {res_prot}"
                                            )
                                        except Exception as ex_prot:
                                            db.registrar_evento(
                                                "IBKR_PROTECTION_ORDERS_ERROR",
                                                f"Error al enviar órdenes de protección en bróker para Estrategia #{est['id']}: {ex_prot}"
                                            )
                                    
                                except Exception as ex_orden:
                                    db.registrar_evento(
                                        "WATCHDOG_ENTRADA_ERROR_ORDEN",
                                        f"Error al enviar orden de entrada para ID {est['id']} ({ticker}): {ex_orden}"
                                    )
                                    print(f"[WATCHDOG ENTRADAS] Error al enviar orden para ID {est['id']}: {ex_orden}")
                            else:
                                # No autorizado, seguimos esperando
                                pass
                        
                        if not es_compartido:
                            broker.desconectar()
                            conectado = False
                        
            except Exception as e:
                print(f"[WATCHDOG ENTRADAS] Error en ciclo: {e}")
                
            # Esperar hasta el próximo ciclo
            stop_event.wait(interval)
    finally:
        print("[WATCHDOG ENTRADAS] Hilo finalizado, desconectando bróker si no es compartido...")
        if not es_compartido and conectado:
            broker.desconectar()

def _procesar_recurrencia_si_aplica(db, est):
    frecuencia_cfg = est.get("condiciones_entrada", {}).get("frecuencia")
    if frecuencia_cfg and frecuencia_cfg.get("activo", False):
        tipo_frecuencia = frecuencia_cfg.get("tipo", "Diaria")
        try:
            cond_ent = est["condiciones_entrada"].copy() if est.get("condiciones_entrada") else {}
            freq_cfg = cond_ent.get("frecuencia", {}).copy()
            
            if tipo_frecuencia == "Diaria":
                delay = timedelta(days=1)
            elif tipo_frecuencia == "Semanal":
                delay = timedelta(days=7)
            else:
                delay = timedelta(days=1)
                
            freq_cfg["proxima_ejecucion"] = (datetime.now() + delay).isoformat()
            cond_ent["frecuencia"] = freq_cfg
            
            nueva_id = db.crear_estrategia(
                ticker=est["ticker"],
                tipo_activo=est["tipo_activo"],
                estado="PENDIENTE_ENTRADA",
                patas=est["patas"],
                condiciones_entrada=cond_ent,
                condiciones_salida=est["condiciones_salida"],
                precio_entrada=None
            )
            db.registrar_evento(
                "REPROGRAMACION_ESTRATEGIA",
                f"Estrategia #{est['id']} reprogramada por frecuencia {tipo_frecuencia}. Creada nueva Estrategia #{nueva_id} en estado PENDIENTE_ENTRADA."
            )
            enviar_alerta_webhook(
                titulo="🔄 Estrategia Reprogramada",
                mensaje=f"**ID anterior:** {est['id']} -> **Nueva ID:** {nueva_id}\n**Frecuencia:** {tipo_frecuencia}\n**Ticker:** {est['ticker']}",
                color="info"
            )
        except Exception as ex_rep:
            print(f"Error al reprogramar estrategia #{est['id']}: {ex_rep}")

def watchdog_salidas_worker(db_name, interval, stop_event, broker=None):
    """
    Worker del Watchdog de Salidas:
    Vigila estrategias en estado 'ACTIVA'. Monitorea P&L en tiempo real y
    ejecuta el cierre automático (TP/SL/VIX/Horario).
    Consulta la BD en cada ciclo para atrapar modificaciones en caliente de SL/TP.
    """
    db = GestorBaseDatos(db_name=db_name)
    es_compartido = (broker is not None)
    if not es_compartido:
        broker = GestorIBKR(client_id=3)
    
    print(f"[WATCHDOG SALIDAS] Iniciado correctamente (compartido={es_compartido}).")
    
    conectado = False
    try:
        while not stop_event.is_set():
            try:
                # 1. Obtener estrategias activas
                activas = db.obtener_estrategias(estado="ACTIVA")
                
                if activas:
                    if (es_compartido and broker.esta_conectado()) or (not es_compartido and broker.conectar()):
                        conectado = True
                        for est in activas:
                            if stop_event.is_set():
                                break
                            ticker = est["ticker"]
                            tipo_activo = est["tipo_activo"]
                            condiciones = est["condiciones_salida"]
                            
                            # --- DETECTAR Y PROCESAR EXPIRACIÓN DE OPCIONES ---
                            es_opcion = (tipo_activo == "OPTION")
                            if es_opcion and est.get("patas"):
                                venc_str = est["patas"][0].get("vencimiento")
                                if venc_str:
                                    try:
                                        venc_clean = str(venc_str).replace("-", "").replace("/", "").strip()
                                        fecha_venc = datetime.strptime(venc_clean, "%Y%m%d").date()
                                        ahora_fecha = datetime.now().date()
                                        
                                        if ahora_fecha > fecha_venc:
                                            print(f"[WATCHDOG SALIDAS] Estrategia #{est['id']} ({ticker}) ha expirado en fecha {venc_str}. Liquidando...")
                                            precio_cierre_exp = broker.obtener_precio_cierre_en_fecha(ticker, venc_clean)
                                            if precio_cierre_exp is None:
                                                precio_cierre_exp = broker.obtener_precio_prueba(ticker) or 0.0
                                                
                                            pnl_realizado = 0.0
                                            for pata in est["patas"]:
                                                cant = int(pata.get("cantidad", 1))
                                                accion_pata = pata.get("accion", "BUY").upper()
                                                strike = float(pata.get("strike", 0.0))
                                                right = pata.get("right", "C").upper()
                                                pr_entrada = float(pata.get("precio_entrada", 0.0))
                                                
                                                val_venc = 0.0
                                                if right in ("C", "CALL"):
                                                    val_venc = max(precio_cierre_exp - strike, 0.0)
                                                elif right in ("P", "PUT"):
                                                    val_venc = max(strike - precio_cierre_exp, 0.0)
                                                    
                                                if accion_pata == "BUY":
                                                    pnl_pata = (val_venc - pr_entrada) * 100.0 * cant
                                                else:
                                                    pnl_pata = (pr_entrada - val_venc) * 100.0 * cant
                                                pnl_realizado += pnl_pata
                                                
                                            pnl_realizado = round(pnl_realizado, 2)
                                            
                                            db.actualizar_estado_estrategia(
                                                estrategia_id=est["id"],
                                                nuevo_estado="CERRADA_VENCIMIENTO",
                                                precio_salida=precio_cierre_exp,
                                                pnl_realizado=pnl_realizado,
                                                fecha_cierre=datetime.now().isoformat()
                                            )
                                            
                                            db.registrar_evento(
                                                "WATCHDOG_SALIDA_EXPIRACION",
                                                f"Estrategia ID {est['id']} ({ticker}) expirada en fecha {venc_str}. Precio Cierre: {precio_cierre_exp}$. P&L Realizado: {pnl_realizado}$"
                                            )
                                            
                                            enviar_alerta_webhook(
                                                titulo="🛑 Estrategia Expirada",
                                                mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Motivo:** Expiración de contrato ({venc_str})\n**Precio Cierre Subyacente:** {precio_cierre_exp}$\n**P&L Realizado:** {pnl_realizado}$",
                                                color="info"
                                            )
                                            
                                            _procesar_recurrencia_si_aplica(db, est)
                                            continue
                                    except Exception as ex_exp:
                                        print(f"[WATCHDOG SALIDAS] Error al evaluar expiración para estrategia #{est['id']}: {ex_exp}")
                            
                            # Consultar P&L de las posiciones correspondientes a esta estrategia
                            pnl = broker.calcular_pnl_estrategia(
                                ticker=ticker,
                                tipo_activo=tipo_activo,
                                patas=est["patas"]
                            )
                            
                            if pnl is None:
                                if tipo_activo == "STOCK" and condiciones.get("gestion") == "Gestionado por IBKR (Órdenes en Broker)":
                                    db.actualizar_estado_estrategia(
                                        estrategia_id=est["id"],
                                        nuevo_estado="CERRADA_BROKER",
                                        order_id_salida=est.get("order_id_salida") or 0,
                                        precio_salida=0.0,
                                        pnl_realizado=0.0,
                                        fecha_cierre=datetime.now().isoformat()
                                    )
                                    db.registrar_evento(
                                        "WATCHDOG_SALIDA_BROKER",
                                        f"Estrategia ID {est['id']} ({ticker}) cerrada de forma nativa en el bróker (ejecución de SL/TP)."
                                    )
                                    enviar_alerta_webhook(
                                        titulo="🛑 Estrategia Cerrada por Bróker (Nativo)",
                                        mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Motivo:** Ejecutado por IBKR",
                                        color="success"
                                    )
                                    _procesar_recurrencia_si_aplica(db, est)
                                continue
                                
                            # Evaluar condiciones de salida
                            precio_actual = broker.obtener_precio_prueba(ticker)
                            evaluacion = MotorSalida.evaluar_condiciones_salida(
                                gestor_ibkr=broker,
                                ticker=ticker,
                                condiciones_salida=condiciones,
                                pnl_actual=pnl,
                                precio_actual=precio_actual
                            )
                            
                            accion = evaluacion["accion"]
                            
                            if accion != "MANTENER":
                                print(f"[WATCHDOG SALIDAS] Disparador de SALIDA ({accion}) activado para Estrategia ID {est['id']} ({ticker})")
                                
                                # Enviar orden de cierre (invirtiendo las patas)
                                try:
                                    res_cierre = broker.enviar_orden_cierre_generica(
                                        ticker=ticker,
                                        tipo_activo=tipo_activo,
                                        patas=est["patas"]
                                    )
                                    
                                    oid_salida = res_cierre["order_id"]
                                    status_salida = res_cierre["status"]
                                    
                                    # Transicionar estado de la estrategia
                                    nuevo_estado = f"CERRADA_{accion}"
                                    
                                    db.actualizar_estado_estrategia(
                                        estrategia_id=est["id"],
                                        nuevo_estado=nuevo_estado,
                                        order_id_salida=oid_salida,
                                        precio_salida=0.0, # Se actualizará por polling o ejecución posterior
                                        pnl_realizado=pnl,
                                        fecha_cierre=datetime.now().isoformat()
                                    )
                                    
                                    db.registrar_evento(
                                        "WATCHDOG_SALIDA_EJECUTADA",
                                        f"Estrategia ID {est['id']} ({ticker}) cerrada por {accion}. OrderID Cierre: {oid_salida}. P&L Realizado: {pnl}$"
                                    )
                                    
                                    # Alerta Webhook
                                    color_alerta = "success" if accion == "TAKE_PROFIT" else "error"
                                    enviar_alerta_webhook(
                                        titulo=f"🛑 Estrategia Cerrada por Watchdog ({accion})",
                                        mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Motivo:** {evaluacion['motivo']}\n**P&L Final Realizado:** {pnl}$\n**OrderID Cierre:** {oid_salida}",
                                        color=color_alerta
                                    )
                                    
                                    # Procesar frecuencia/recurrencia al cerrarse
                                    _procesar_recurrencia_si_aplica(db, est)
                                    
                                except Exception as ex_cierre:
                                    db.registrar_evento(
                                        "WATCHDOG_SALIDA_ERROR_CIERRE",
                                        f"Fallo al enviar orden de cierre para ID {est['id']} ({ticker}): {ex_cierre}"
                                    )
                                    print(f"[WATCHDOG SALIDAS] Error al cerrar ID {est['id']}: {ex_cierre}")
                                    
                        if not es_compartido:
                                broker.desconectar()
                                conectado = False
                        
            except Exception as e:
                print(f"[WATCHDOG SALIDAS] Error en ciclo: {e}")
                
            stop_event.wait(interval)
    finally:
        print("[WATCHDOG SALIDAS] Hilo finalizado, desconectando bróker si no es compartido...")
        if not es_compartido and conectado:
            broker.desconectar()

# ==========================================
# MÉTODOS PÚBLICOS DE LANZAMIENTO
# ==========================================

def iniciar_watchdog_entradas(db_name="tfg_trading.db", interval=30, broker=None):
    """
    Inicia el Watchdog de Entradas en un hilo de segundo plano (daemon).
    """
    stop_entradas.clear()
    hilo = threading.Thread(
        target=watchdog_entradas_worker,
        args=(db_name, interval, stop_entradas, broker),
        name="WatchdogEntradas",
        daemon=True
    )
    hilo.start()
    return hilo

def iniciar_watchdog_salidas(db_name="tfg_trading.db", interval=15, broker=None):
    """
    Inicia el Watchdog de Salidas en un hilo de segundo plano (daemon).
    """
    stop_salidas.clear()
    hilo = threading.Thread(
        target=watchdog_salidas_worker,
        args=(db_name, interval, stop_salidas, broker),
        name="WatchdogSalidas",
        daemon=True
    )
    hilo.start()
    return hilo

def detener_watchdogs():
    """
    Detiene de forma limpia ambos watchdogs enviando señales de parada.
    """
    stop_entradas.set()
    stop_salidas.set()
