import time
import threading
from datetime import datetime
from base_datos import GestorBaseDatos
from conexion_ibkr import GestorIBKR
from motor_logica import MotorEstrategias, MotorSalida
from notificaciones import enviar_alerta_webhook

# Eventos de parada globales para control limpio de hilos
stop_entradas = threading.Event()
stop_salidas = threading.Event()

def watchdog_entradas_worker(db_name, interval, stop_event):
    """
    Worker del Watchdog de Entradas:
    Vigila estrategias en estado 'PENDIENTE_ENTRADA'. Evalúa condiciones
    de mercado y lanza órdenes de entrada reales al cumplirse las reglas.
    """
    db = GestorBaseDatos(db_name=db_name)
    broker = GestorIBKR()
    
    print("[WATCHDOG ENTRADAS] Iniciado correctamente.")
    
    while not stop_event.is_set():
        try:
            # 1. Obtener estrategias pendientes de entrada
            pendientes = db.obtener_estrategias(estado="PENDIENTE_ENTRADA")
            
            if pendientes:
                # Nos conectamos a IBKR solo si hay tareas pendientes
                if broker.conectar():
                    for est in pendientes:
                        ticker = est["ticker"]
                        tipo_activo = est["tipo_activo"]
                        condiciones = est["condiciones_entrada"]
                        precio_entrada_target = est["precio_entrada"]
                        
                        # Obtener precio actual de mercado del subyacente
                        precio_actual = broker.obtener_precio_prueba(ticker)
                        
                        if precio_actual is None:
                            print(f"[WATCHDOG ENTRADAS] No se pudo obtener precio para {ticker}. Reintentando en el próximo ciclo.")
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
                    
                    broker.desconectar()
                    
        except Exception as e:
            print(f"[WATCHDOG ENTRADAS] Error en ciclo: {e}")
            
        # Esperar hasta el próximo ciclo
        time.sleep(interval)

def _procesar_recurrencia_si_aplica(db, est):
    frecuencia_cfg = est.get("condiciones_entrada", {}).get("frecuencia")
    if frecuencia_cfg and frecuencia_cfg.get("activo", False):
        tipo_frecuencia = frecuencia_cfg.get("tipo", "Diaria")
        try:
            nueva_id = db.crear_estrategia(
                ticker=est["ticker"],
                tipo_activo=est["tipo_activo"],
                estado="PENDIENTE_ENTRADA",
                patas=est["patas"],
                condiciones_entrada=est["condiciones_entrada"],
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

def watchdog_salidas_worker(db_name, interval, stop_event):
    """
    Worker del Watchdog de Salidas:
    Vigila estrategias en estado 'ACTIVA'. Monitorea P&L en tiempo real y
    ejecuta el cierre automático (TP/SL/VIX/Horario).
    Consulta la BD en cada ciclo para atrapar modificaciones en caliente de SL/TP.
    """
    db = GestorBaseDatos(db_name=db_name)
    broker = GestorIBKR()
    
    print("[WATCHDOG SALIDAS] Iniciado correctamente.")
    
    while not stop_event.is_set():
        try:
            # 1. Obtener estrategias activas
            activas = db.obtener_estrategias(estado="ACTIVA")
            
            if activas:
                if broker.conectar():
                    for est in activas:
                        ticker = est["ticker"]
                        tipo_activo = est["tipo_activo"]
                        condiciones = est["condiciones_salida"]
                        
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
                                
                    broker.desconectar()
                    
        except Exception as e:
            print(f"[WATCHDOG SALIDAS] Error en ciclo: {e}")
            
        time.sleep(interval)

    print("[WATCHDOG SALIDAS] Hilo finalizado.")

# ==========================================
# MÉTODOS PÚBLICOS DE LANZAMIENTO
# ==========================================

def iniciar_watchdog_entradas(db_name="tfg_trading.db", interval=30):
    """
    Inicia el Watchdog de Entradas en un hilo de segundo plano (daemon).
    """
    stop_entradas.clear()
    hilo = threading.Thread(
        target=watchdog_entradas_worker,
        args=(db_name, interval, stop_entradas),
        name="WatchdogEntradas",
        daemon=True
    )
    hilo.start()
    return hilo

def iniciar_watchdog_salidas(db_name="tfg_trading.db", interval=15):
    """
    Inicia el Watchdog de Salidas en un hilo de segundo plano (daemon).
    """
    stop_salidas.clear()
    hilo = threading.Thread(
        target=watchdog_salidas_worker,
        args=(db_name, interval, stop_salidas),
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
