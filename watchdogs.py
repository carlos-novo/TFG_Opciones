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
                # 1. Obtener estrategias pendientes de entrada o con orden enviada
                pendientes = db.obtener_estrategias(estado="PENDIENTE_ENTRADA")
                enviadas = db.obtener_estrategias(estado="ORDEN_ENVIADA")
                
                # 1a. Limpieza offline de órdenes DAY expiradas (incluso si el bróker está desconectado)
                if enviadas:
                    for est in list(enviadas):
                        if stop_event.is_set():
                            break
                        condiciones = est.get("condiciones_entrada") or {}
                        tif_val = condiciones.get("tif", "DAY").upper()
                        
                        if tif_val == "DAY":
                            fecha_creacion_str = est.get("fecha_creacion")
                            if fecha_creacion_str:
                                try:
                                    fecha_creacion_dt = datetime.fromisoformat(fecha_creacion_str)
                                    if datetime.now().date() > fecha_creacion_dt.date():
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="CANCELADA"
                                        )
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_EXPIRADA_OFFLINE",
                                            f"Estrategia ID {est['id']} ({est['ticker']}) marcada como CANCELADA por expiración offline (orden DAY del día anterior)."
                                        )
                                        enviar_alerta_webhook(
                                            titulo="⏰ Orden de Entrada Expirada (Offline)",
                                            mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {est['ticker']}\n**OrderID:** {est.get('order_id_entrada')}\nLa orden DAY del día anterior expiró al finalizar el día (detectado offline).",
                                            color="warning"
                                        )
                                        # La removemos de la lista local para evitar procesarla en modo conectado en este ciclo
                                        enviadas.remove(est)
                                except Exception as ex_exp:
                                    print(f"[WATCHDOG ENTRADAS] Error al evaluar expiración offline de ID {est['id']}: {ex_exp}")

                candidatas_rec = []
                try:
                    candidatas_rec = [
                        e for e in db.obtener_estrategias()
                        if e["estado"] in ("ORDEN_ENVIADA", "CANCELADA")
                    ]
                except Exception as e_cnd:
                    print(f"[WATCHDOG ENTRADAS] Error al buscar candidatas de reconciliación: {e_cnd}")

                if pendientes or enviadas or candidatas_rec:
                    # Nos conectamos a IBKR solo si hay tareas (o si ya está conectado en modo compartido)
                    if (es_compartido and broker.esta_conectado()) or (not es_compartido and broker.conectar()):
                        conectado = True
                        
                        # Reconciliación con la cartera real
                        try:
                            reconciliar_estrategias_con_cartera(db, broker)
                        except Exception as ex_rec:
                            print(f"[WATCHDOG ENTRADAS] Error al reconciliar cartera: {ex_rec}")
                        
                        # 1b. Procesar estrategias en estado ORDEN_ENVIADA
                        for est in enviadas:
                            if stop_event.is_set():
                                break
                            if est.get("estado") != "ORDEN_ENVIADA":
                                continue
                            oid = est.get("order_id_entrada")
                            if not oid:
                                continue
                            ticker = est["ticker"]
                            tipo_activo = est["tipo_activo"]
                            
                            try:
                                res_estado = broker.obtener_estado_orden(oid)
                                if res_estado:
                                    status = res_estado["status"]
                                    avg_fill = res_estado["avg_fill_price"]
                                    
                                    if status == "Filled":
                                        pr_entrada = avg_fill if avg_fill is not None and avg_fill != 0.0 else est["precio_entrada"]
                                        if pr_entrada is not None and tipo_activo in ("BAG", "OPTION"):
                                            pr_entrada = abs(pr_entrada)
                                            
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="ACTIVA",
                                            precio_entrada=pr_entrada
                                        )
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_EJECUTADA",
                                            f"Estrategia ID {est['id']} ({ticker}) activada tras ejecución completa de orden. OrderID: {oid}. Precio Ejecución: {pr_entrada}"
                                        )
                                        enviar_alerta_webhook(
                                            titulo="🚀 Estrategia Activada (Orden Ejecutada)",
                                            mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Tipo Activo:** {tipo_activo}\n**Precio/Prima Entrada:** {pr_entrada}$\n**OrderID:** {oid}",
                                            color="success"
                                        )
                                        
                                        # Si es de tipo STOCK y la gestión de salida es en el bróker, colocamos SL y TP allí
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
                                                
                                    elif status in ("Cancelled", "Inactive", "Rejected") or "Cancelled" in str(status) or "Rejected" in str(status):
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="CANCELADA"
                                        )
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_CANCELADA",
                                            f"Estrategia ID {est['id']} ({ticker}) cancelada en bróker. Estado: {status}"
                                        )
                                        enviar_alerta_webhook(
                                            titulo="⚠️ Orden de Entrada Cancelada/Rechazada",
                                            mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**OrderID:** {oid}\n**Estado bróker:** {status}",
                                            color="warning"
                                        )
                                else:
                                    # Si res_estado es None, significa que la orden no se encuentra en la sesión activa del bróker.
                                    # Evaluamos según el TIF configurado:
                                    condiciones = est.get("condiciones_entrada") or {}
                                    tif_val = condiciones.get("tif", "DAY").upper()
                                    
                                    if tif_val == "DAY":
                                        fecha_creacion_str = est.get("fecha_creacion")
                                        if fecha_creacion_str:
                                            try:
                                                # Parsear fecha de creación (ej. '2026-06-16T20:06:27.206346')
                                                # Tomamos sólo la fecha YYYY-MM-DD
                                                fecha_creacion_dt = datetime.fromisoformat(fecha_creacion_str)
                                                if datetime.now().date() > fecha_creacion_dt.date():
                                                    db.actualizar_estado_estrategia(
                                                        estrategia_id=est["id"],
                                                        nuevo_estado="CANCELADA"
                                                    )
                                                    db.registrar_evento(
                                                        "WATCHDOG_ENTRADA_EXPIRADA",
                                                        f"Estrategia ID {est['id']} ({ticker}) marcada como CANCELADA por expiración (orden DAY del día anterior no encontrada)."
                                                    )
                                                    enviar_alerta_webhook(
                                                        titulo="⏰ Orden de Entrada Expirada",
                                                        mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**OrderID:** {oid}\nLa orden no se ejecutó y expiró al finalizar el día.",
                                                        color="warning"
                                                    )
                                            except Exception as ex_exp:
                                                print(f"[WATCHDOG ENTRADAS] Error al evaluar expiración temporal de ID {est['id']}: {ex_exp}")
                                    elif tif_val == "GTC":
                                        # Si es GTC y ya no está activa ni en sesión, asumimos que fue cancelada por desconexión o manualmente.
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="CANCELADA"
                                        )
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_NO_ENCONTRADA_GTC",
                                            f"Estrategia ID {est['id']} ({ticker}) marcada como CANCELADA (orden GTC no encontrada en el bróker)."
                                        )
                                        enviar_alerta_webhook(
                                            titulo="⚠️ Orden GTC Cancelada/No Encontrada",
                                            mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**OrderID:** {oid}\nLa orden GTC no se encontró en el bróker y se ha marcado como CANCELADA.",
                                            color="warning"
                                        )
                            except Exception as ex_status:
                                print(f"[WATCHDOG ENTRADAS] Error al obtener estado de orden {oid} para ID {est['id']}: {ex_status}")

                        # 1c. Procesar estrategias en estado PENDIENTE_ENTRADA
                        for est in pendientes:
                            if stop_event.is_set():
                                break
                            if est.get("estado") != "PENDIENTE_ENTRADA":
                                continue
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
                            
                            if evaluar_condiciones_entrada := evaluacion["autorizado"]:
                                print(f"[WATCHDOG ENTRADAS] Condiciones CUMPLIDAS para Estrategia ID {est['id']} ({ticker})")
                                
                                # Enviar orden genérica
                                try:
                                    condiciones = est.get("condiciones_entrada") or {}
                                    tif_val = condiciones.get("tif", "DAY")
                                    res_orden = broker.enviar_orden_generica(
                                        ticker=ticker,
                                        tipo_activo=tipo_activo,
                                        patas=est["patas"],
                                        precio_limite=precio_entrada_target,
                                        tif=tif_val
                                    )
                                    
                                    oid = res_orden["order_id"]
                                    status = res_orden["status"]
                                    
                                    # Si la orden se transmite con éxito
                                    # Calcular precio_entrada de control (pr_entrada)
                                    pr_entrada = precio_entrada_target
                                    if pr_entrada is None:
                                        if tipo_activo in ("BAG", "OPTION"):
                                            # Calcular prima neta teórica sumando las patas
                                            teorico = 0.0
                                            for p in est["patas"]:
                                                cant = int(p.get("cantidad", 1))
                                                px = float(p.get("precio_entrada") or 0.0)
                                                signo = 1.0 if p.get("accion", "BUY").upper() == "SELL" else -1.0
                                                teorico += signo * px * cant
                                            pr_entrada = round(teorico, 2)
                                        else:
                                            pr_entrada = precio_actual
                                    
                                    # Si la orden se llena inmediatamente (ej. Mocks de pruebas)
                                    if status in ("Filled", "Submitted (Mock Defensa TFG)", "Filled (Mock Cierre TFG)") or "Mock" in str(status) or "Filled" in str(status):
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="ACTIVA",
                                            order_id_entrada=oid,
                                            precio_entrada=pr_entrada,
                                            fecha_ejecucion=datetime.now().isoformat()
                                        )
                                        
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_EJECUTADA",
                                            f"Estrategia ID {est['id']} ({ticker}) activada inmediatamente. OrderID: {oid}. Estado: {status}"
                                        )
                                        
                                        # Alerta Webhook
                                        enviar_alerta_webhook(
                                            titulo="🚀 Estrategia Lanzada y Activada por Watchdog",
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
                                    elif status in ("Cancelled", "Inactive", "Rejected") or "Cancelled" in str(status) or "Rejected" in str(status):
                                        # Si la orden es rechazada o cancelada inmediatamente por el bróker
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="CANCELADA",
                                            order_id_entrada=oid,
                                            precio_entrada=pr_entrada,
                                            fecha_ejecucion=datetime.now().isoformat()
                                        )
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_CANCELADA",
                                            f"Estrategia ID {est['id']} ({ticker}) rechazada/cancelada inmediatamente por el bróker. OrderID: {oid}. Estado: {status}"
                                        )
                                        enviar_alerta_webhook(
                                            titulo="⚠️ Orden de Estrategia Rechazada/Cancelada",
                                            mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Tipo Activo:** {tipo_activo}\n**OrderID:** {oid}\n**Estado Orden:** {status}",
                                            color="warning"
                                        )
                                    else:
                                        # Si la orden queda pendiente/trabajando en el mercado (TWS real), pasa a ORDEN_ENVIADA
                                        db.actualizar_estado_estrategia(
                                            estrategia_id=est["id"],
                                            nuevo_estado="ORDEN_ENVIADA",
                                            order_id_entrada=oid,
                                            precio_entrada=pr_entrada,
                                            fecha_ejecucion=datetime.now().isoformat()
                                        )
                                        
                                        db.registrar_evento(
                                            "WATCHDOG_ENTRADA_ENVIADA",
                                            f"Estrategia ID {est['id']} ({ticker}) enviada al mercado. Esperando confirmación de ejecución (Fill). OrderID: {oid}. Estado: {status}"
                                        )
                                        
                                        # Alerta Webhook
                                        enviar_alerta_webhook(
                                            titulo="📥 Orden de Estrategia Enviada al Mercado",
                                            mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Tipo Activo:** {tipo_activo}\n**Prima Entrada Objetivo:** {pr_entrada}$\n**OrderID:** {oid}\n**Estado actual:** {status}",
                                            color="info"
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


def reconciliar_estrategias_con_cartera(db, broker):
    """
    Reconcilia las estrategias en la base de datos con las posiciones reales en la cartera de IBKR.
    Si una estrategia en estado 'ORDEN_ENVIADA' o 'CANCELADA' tiene posiciones reales correspondientes
    en el bróker (porque la orden se ejecutó con el software inactivo), transiciona su estado a 'ACTIVA'
    y actualiza su precio de entrada con el precio medio de la cartera.
    """
    import json
    # 1. Obtener posiciones reales de la cartera
    posiciones = broker.obtener_posiciones_cartera()
    if not posiciones:
        return
        
    # 2. Obtener estrategias que podrían haber sido ejecutadas (por ejemplo, 'ORDEN_ENVIADA' o 'CANCELADA')
    try:
        estrategias_candidatas = [
            e for e in db.obtener_estrategias() 
            if e["estado"] in ("ORDEN_ENVIADA", "CANCELADA")
        ]
    except Exception as e:
        print(f"[RECONCILIACIÓN] Error al obtener estrategias para reconciliación: {e}")
        return

    for est in estrategias_candidatas:
        ticker = est["ticker"]
        tipo_activo = est["tipo_activo"]
        patas = est.get("patas") or []
        if not patas and est.get("patas_json"):
            try:
                patas = json.loads(est["patas_json"])
            except:
                continue
                
        if not patas:
            continue
            
        # Comprobar si hay una posición coincidente en la cartera
        coincide = False
        avg_cost_accum = 0.0
        
        # Para STOCK
        if tipo_activo.upper() == "STOCK":
            for pos in posiciones:
                if pos.get("Tipo") in ("Acción", "STK", "Stock", "IND") and pos.get("Símbolo", "").upper() == ticker.upper():
                    qty_leg = float(patas[0].get("cantidad", 1))
                    if patas[0].get("accion", "BUY").upper() == "SELL":
                        qty_leg = -qty_leg
                        
                    qty_pos = float(pos.get("Posición", 0.0))
                    if (qty_leg > 0 and qty_pos > 0) or (qty_leg < 0 and qty_pos < 0):
                        coincide = True
                        avg_cost_accum = float(pos.get("Precio Medio", 0.0))
                        break
        # Para OPCIÓN o BAG
        else:
            patas_coincidentes = 0
            total_avg_cost = 0.0
            for leg in patas:
                leg_right = leg.get("right", "C")[0].upper() if leg.get("right") else "C"
                leg_strike = float(leg.get("strike", 0.0))
                
                def normalizar_fecha(f_str):
                    if not f_str: return ""
                    cleaned = str(f_str).replace("-", "").replace("/", "").strip()
                    if len(cleaned) == 8: return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
                    return cleaned
                
                leg_venc = normalizar_fecha(leg.get("vencimiento", ""))
                
                for pos in posiciones:
                    if pos.get("Tipo") in ("Opción", "OPT", "Option") and pos.get("Símbolo", "").upper() == ticker.upper():
                        pos_right = pos.get("Right (C/P)", "C")[0].upper() if pos.get("Right (C/P)") else "C"
                        pos_strike = float(pos.get("Strike", 0.0))
                        pos_venc = normalizar_fecha(pos.get("Vencimiento", ""))
                        
                        if pos_right == leg_right and pos_strike == leg_strike and pos_venc == leg_venc:
                            qty_leg = float(leg.get("cantidad", 1))
                            if leg.get("accion", "BUY").upper() == "SELL":
                                qty_leg = -qty_leg
                            qty_pos = float(pos.get("Posición", 0.0))
                            
                            if (qty_leg > 0 and qty_pos > 0) or (qty_leg < 0 and qty_pos < 0):
                                patas_coincidentes += 1
                                total_avg_cost += float(pos.get("Precio Medio", 0.0))
                                break
            
            if len(patas) > 0 and patas_coincidentes == len(patas):
                coincide = True
                avg_cost_accum = total_avg_cost / len(patas)

        if coincide:
            print(f"[RECONCILIACIÓN] ¡Estrategia #{est['id']} ({ticker}) reconciliada con éxito! Activando...")
            db.actualizar_estado_estrategia(
                estrategia_id=est["id"],
                nuevo_estado="ACTIVA",
                precio_entrada=avg_cost_accum
            )
            db.registrar_evento(
                "RECONCILIACION_POSICION_EJECUTADA",
                f"Estrategia ID {est['id']} ({ticker}) sincronizada y activada automáticamente a partir de la cartera física de IBKR. Coste medio: {avg_cost_accum}$"
            )
            enviar_alerta_webhook(
                titulo="🚀 Estrategia Activada por Reconciliación",
                mensaje=f"**ID Estrategia:** {est['id']}\n**Ticker:** {ticker}\n**Tipo Activo:** {tipo_activo}\n**Precio Entrada (Cartera):** {avg_cost_accum}$\nSincronizada automáticamente tras detectar la ejecución en la cartera física de IBKR.",
                color="success"
            )
