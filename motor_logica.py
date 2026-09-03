from datetime import date
import pandas as pd
import math

class MotorEstrategias:
    """
    Clase encargada de la lógica financiera, agregación de opciones y cálculo de riesgos.
    """

    @staticmethod
    def obtener_prima_pata(pata, modo="TEORICO"):
        """
        Obtiene la prima de referencia de una pata en función del modo de operación:
        - modo="EJECUTADO": Requiere precio_entrada confirmado.
        - modo="TEORICO": Requiere prima_teorica calculada.
        """
        modo = str(modo).upper()
        if modo == "EJECUTADO":
            if pata.get("precio_entrada") is None:
                raise ValueError("Una pata ejecutada requiere precio_entrada confirmado")
            return float(pata["precio_entrada"])
        if modo == "TEORICO":
            if pata.get("prima_teorica") is None:
                raise ValueError("La previsualización requiere prima_teorica")
            return float(pata["prima_teorica"])
        raise ValueError(f"Modo de prima no reconocido: {modo}")

    @staticmethod
    def calcular_credito_real_iron_condor(gestor, ticker, vencimiento, p_long, p_short, c_short, c_long):
        # Llamamos a la función bulk de mercado
        strikes = [p_long, p_short, c_short, c_long]
        datos = gestor.obtener_datos_estrategia_completa(ticker, vencimiento, strikes)
        
        # Mapeamos los resultados (vienen en el mismo orden)
        d_p_l, d_p_s, d_c_s, d_c_l = datos

        ingreso = d_p_s['bid'] + d_c_s['bid']
        coste = d_p_l['ask'] + d_c_l['ask']
        credito_neto = ingreso - coste
        
        if math.isnan(credito_neto):
            credito_neto = 0.0
        
        return {
            "credito_neto": round(credito_neto, 2),
            "detalle": {
                "p_short_bid": d_p_s['bid'], "c_short_bid": d_c_s['bid'],
                "p_long_ask": d_p_l['ask'], "c_long_ask": d_c_l['ask']
            }
        }

    @staticmethod
    def calcular_metricas_iron_condor(p_long, p_short, c_short, c_long, credito_neto):
        """
        Calcula el perfil de riesgo máximo y beneficio de la estrategia agregada.
        """
        max_beneficio = credito_neto * 100
        
        ancho_put = p_short - p_long
        ancho_call = c_long - c_short
        ancho_maximo = max(ancho_put, ancho_call)
        
        max_riesgo = (ancho_maximo - credito_neto) * 100
        ratio_rb = round(max_beneficio / max_riesgo if max_riesgo > 0 else 0, 2)
        
        return {
            "max_beneficio": round(max_beneficio, 2),
            "max_riesgo": round(max_riesgo, 2),
            "ratio_rb": ratio_rb
        }
    
    @staticmethod
    def evaluar_condicion_sma(gestor, ticker, periodo, regla, precio_actual):
        """
        Calcula la Media Móvil Simple (SMA) con Pandas y evalúa la regla de entrada.
        """
        cierres = gestor.obtener_historico_diario(ticker, periodo)
        
        if not cierres or len(cierres) < periodo:
            raise ValueError(f"No se pudieron obtener suficientes datos para una SMA de {periodo} días.")

        df = pd.DataFrame(cierres, columns=['close'])
        sma_actual = df['close'].mean()
        
        luz_verde = False
        if "Precio > SMA" in regla:
            luz_verde = precio_actual > sma_actual
        elif "Precio < SMA" in regla:
            luz_verde = precio_actual < sma_actual
            
        return {
            "autorizado": luz_verde,
            "valor_sma": round(sma_actual, 2),
            "precio_evaluado": precio_actual
        }

    @staticmethod
    def evaluar_condiciones_entrada(gestor_ibkr, ticker, condiciones_entrada, precio_actual):
        """
        Evalúa de forma genérica si se cumplen todas las condiciones de entrada configuradas.
        Las condiciones pueden incluir: SMA, VIX y Horarios.
        
        Args:
            gestor_ibkr: Instancia de GestorIBKR para consultar datos si es necesario (ej. histórico de SMA o VIX).
            ticker: Símbolo subyacente a evaluar (ej. 'SPX').
            condiciones_entrada: Diccionario con la configuración de entrada.
            precio_actual: Precio de mercado actual del subyacente.
            
        Returns:
            dict con:
              - 'autorizado' (bool): True si todas las condiciones se cumplen, False si alguna falla.
              - 'detalles' (dict): Resumen de los valores evaluados y sus resultados.
        """
        if not condiciones_entrada:
            return {"autorizado": True, "detalles": {"info": "Sin condiciones de entrada"}}
            
        autorizado = True
        detalles = {}
        
        # 1. Validación de Horarios
        horario = condiciones_entrada.get("horario")
        if horario and horario.get("activo", True):
            hora_inicio_str = horario.get("hora_inicio")
            hora_fin_str = horario.get("hora_fin")
            if hora_inicio_str and hora_fin_str:
                from datetime import datetime
                ahora_time = datetime.now().time()
                try:
                    h_inicio = datetime.strptime(hora_inicio_str, "%H:%M").time()
                    h_fin = datetime.strptime(hora_fin_str, "%H:%M").time()
                    if h_inicio <= h_fin:
                        cumple_hora = (h_inicio <= ahora_time <= h_fin)
                    else:
                        cumple_hora = (ahora_time >= h_inicio or ahora_time <= h_fin)
                        
                    detalles["horario"] = {"cumple": cumple_hora, "actual": ahora_time.strftime("%H:%M"), "rango": f"{hora_inicio_str}-{hora_fin_str}"}
                    if not cumple_hora:
                        autorizado = False
                except Exception as ex_hora:
                    detalles["horario"] = {"error": str(ex_hora), "cumple": False}
                    autorizado = False

        # 2. Validación de VIX
        vix_cfg = condiciones_entrada.get("vix")
        if vix_cfg and vix_cfg.get("activo", True):
            vix_valor = vix_cfg.get("valor")
            vix_operador = vix_cfg.get("operador", "<")
            if vix_valor is not None:
                try:
                    vix_actual = gestor_ibkr.obtener_precio_prueba("VIX")
                    if vix_actual is not None:
                        cumple_vix = False
                        if vix_operador == "<":
                            cumple_vix = vix_actual < vix_valor
                        elif vix_operador == "<=":
                            cumple_vix = vix_actual <= vix_valor
                        elif vix_operador == ">":
                            cumple_vix = vix_actual > vix_valor
                        elif vix_operador == ">=":
                            cumple_vix = vix_actual >= vix_valor
                            
                        detalles["vix"] = {"cumple": cumple_vix, "actual": vix_actual, "limite": vix_valor, "operador": vix_operador}
                        if not cumple_vix:
                            autorizado = False
                    else:
                        detalles["vix"] = {"error": "No se pudo obtener precio de VIX", "cumple": False}
                        autorizado = False
                except Exception as ex_vix:
                    detalles["vix"] = {"error": str(ex_vix), "cumple": False}
                    autorizado = False
                    
        # 3. Validación de SMA
        sma_cfg = condiciones_entrada.get("sma")
        if sma_cfg and sma_cfg.get("activo", True):
            sma_periodo = sma_cfg.get("periodo")
            sma_regla = sma_cfg.get("regla")
            if sma_periodo and sma_regla:
                try:
                    res_sma = MotorEstrategias.evaluar_condicion_sma(
                        gestor_ibkr, ticker, int(sma_periodo), sma_regla, precio_actual
                    )
                    detalles["sma"] = {
                        "cumple": res_sma["autorizado"],
                        "actual": res_sma.get("precio_evaluado", precio_actual),
                        "valor_sma": res_sma["valor_sma"],
                        "regla": sma_regla
                    }
                    if not res_sma["autorizado"]:
                        autorizado = False
                except Exception as ex_sma:
                    detalles["sma"] = {"error": str(ex_sma), "cumple": False}
                    autorizado = False
                    
        # 4. Validación de Precio Disparador (Trigger Price)
        precio_cfg = condiciones_entrada.get("precio_disparador")
        if precio_cfg and precio_cfg.get("activo", True):
            limite_precio = precio_cfg.get("valor")
            operador_precio = precio_cfg.get("operador", "<=")
            if limite_precio is not None:
                cumple_precio = False
                if operador_precio == "<":
                    cumple_precio = precio_actual < limite_precio
                elif operador_precio == "<=":
                    cumple_precio = precio_actual <= limite_precio
                elif operador_precio == ">":
                    cumple_precio = precio_actual > limite_precio
                elif operador_precio == ">=":
                    cumple_precio = precio_actual >= limite_precio
                    
                detalles["precio_disparador"] = {
                    "cumple": cumple_precio,
                    "actual": precio_actual,
                    "limite": limite_precio,
                    "operador": operador_precio
                }
                if not cumple_precio:
                    autorizado = False
                    
        return {"autorizado": autorizado, "detalles": detalles}



class MotorSalida:
    """
    Motor de salida algorítmica para posiciones de trading.
    """

    @staticmethod
    def evaluar_condicion_salida(pnl_actual: float, credito_inicial: float, pct_tp: float, pct_sl: float) -> dict:
        """
        Decide si se debe cerrar la posición basándose en el P&L actual (Wrapper compatible).
        """
        umbral_tp = (pct_tp / 100.0) * credito_inicial
        umbral_sl = -(pct_sl / 100.0) * credito_inicial

        if pnl_actual >= umbral_tp:
            accion = 'TAKE_PROFIT'
        elif pnl_actual <= umbral_sl:
            accion = 'STOP_LOSS'
        else:
            accion = 'MANTENER'

        return {
            'accion':        accion,
            'umbral_tp_usd': round(umbral_tp, 2),
            'umbral_sl_usd': round(umbral_sl, 2),
            'pnl_actual':    round(pnl_actual, 2),
        }

    @staticmethod
    def evaluar_condiciones_salida(gestor_ibkr, ticker, condiciones_salida, pnl_actual, precio_actual=None):
        """
        Evalúa de forma genérica si se cumple alguna regla de salida (SL, TP, VIX máximo, horario).
        
        Args:
            gestor_ibkr: Instancia de GestorIBKR para consultar datos del mercado si es necesario.
            ticker: Símbolo subyacente.
            condiciones_salida: Diccionario con la configuración de salida.
            pnl_actual: P&L no realizado acumulado actual de la posición en USD.
            precio_actual: Opcional. Precio actual del subyacente.
            
        Returns:
            dict con:
              - 'accion' (str): 'MANTENER' | 'TAKE_PROFIT' | 'STOP_LOSS' | 'CIERRE_HORARIO' | 'VIX_MAXIMO'
              - 'motivo' (str): Explicación de la decisión tomada.
              - 'detalles' (dict): Detalle de valores y límites evaluados.
        """
        if not condiciones_salida:
            return {"accion": "MANTENER", "motivo": "Sin condiciones de salida", "detalles": {}}
            
        # 1. Validación de Take Profit (TP) y Stop Loss (SL) en USD
        tp = condiciones_salida.get("take_profit")
        sl = condiciones_salida.get("stop_loss")
        
        if tp is not None and pnl_actual >= float(tp):
            return {
                "accion": "TAKE_PROFIT", 
                "motivo": f"PnL actual ({pnl_actual}$) alcanzó o superó el Take Profit ({tp}$)",
                "detalles": {"pnl_actual": pnl_actual, "tp": tp}
            }
            
        if sl is not None and pnl_actual <= float(sl):
            return {
                "accion": "STOP_LOSS", 
                "motivo": f"PnL actual ({pnl_actual}$) alcanzó o cayó por debajo del Stop Loss ({sl}$)",
                "detalles": {"pnl_actual": pnl_actual, "sl": sl}
            }
            
        # 2. Validación de VIX Máximo
        vix_maximo = condiciones_salida.get("vix_maximo")
        if vix_maximo is not None:
            try:
                vix_actual = gestor_ibkr.obtener_precio_prueba("VIX")
                if vix_actual is not None and vix_actual > float(vix_maximo):
                    return {
                        "accion": "STOP_LOSS", 
                        "motivo": f"VIX actual ({vix_actual}) superó el máximo tolerado ({vix_maximo})",
                        "detalles": {"vix_actual": vix_actual, "vix_max": vix_maximo}
                    }
            except Exception as ex_vix:
                print(f"Error al evaluar VIX de salida: {ex_vix}")

        # 3. Validación de Cierre Horario
        cierre_horario = condiciones_salida.get("cierre_horario")
        if cierre_horario:
            from datetime import datetime
            try:
                h_cierre = datetime.strptime(cierre_horario, "%H:%M").time()
                ahora_time = datetime.now().time()
                if ahora_time >= h_cierre:
                    return {
                        "accion": "CIERRE_HORARIO",
                        "motivo": f"Hora actual ({ahora_time.strftime('%H:%M')}) superó la hora de cierre forzado ({cierre_horario})",
                        "detalles": {"actual": ahora_time.strftime("%H:%M"), "limite": cierre_horario}
                    }
            except Exception as ex_hora:
                print(f"Error al evaluar hora de salida: {ex_hora}")
                
        # 4. Validación de SMA de salida
        sma_cfg = condiciones_salida.get("sma")
        if sma_cfg and sma_cfg.get("activo", True):
            sma_periodo = sma_cfg.get("periodo")
            sma_regla = sma_cfg.get("regla")
            if sma_periodo and sma_regla and precio_actual is not None:
                try:
                    res_sma = MotorEstrategias.evaluar_condicion_sma(
                        gestor_ibkr, ticker, int(sma_periodo), sma_regla, precio_actual
                    )
                    if res_sma["autorizado"]:
                        return {
                            "accion": "STOP_LOSS",
                            "motivo": f"SMA de salida activada: {sma_regla} (Valor SMA: {res_sma['valor_sma']})",
                            "detalles": {"precio_actual": precio_actual, "sma": res_sma["valor_sma"], "regla": sma_regla}
                        }
                except Exception as ex_sma:
                    print(f"Error al evaluar SMA de salida: {ex_sma}")
                    
        return {
            "accion": "MANTENER",
            "motivo": "No se cumplió ninguna condición de salida",
            "detalles": {"pnl_actual": pnl_actual}
        }

    @staticmethod
    def calcular_pnl_expiracion(patas, precio_cierre):
        """
        Calcula el P&L realizado final y el desglose de liquidación pata por pata
        para una estrategia de opciones en su fecha de vencimiento.
        """
        pnl_neto_usd = 0.0
        detalles_patas = []
        
        for idx, pata in enumerate(patas):
            tipo = pata.get("tipo_activo", "OPTION").upper()
            if tipo == "STOCK":
                # Las acciones no expiran por tiempo
                continue
                
            strike = float(pata.get("strike", 0.0))
            right = pata.get("right", "C").upper()
            cantidad = int(pata.get("cantidad", 1))
            accion = pata.get("accion", "BUY").upper()
            
            precio_entrada_pata = MotorEstrategias.obtener_prima_pata(pata, modo=pata.get("modo", "TEORICO"))
            
            # Payoff unitario en la fecha de liquidación
            payoff_unitario = 0.0
            if right in ("C", "CALL"):
                payoff_unitario = max(0.0, precio_cierre - strike)
            elif right in ("P", "PUT"):
                payoff_unitario = max(0.0, strike - precio_cierre)
                
            # Calcular P&L neto para esta pata (multiplicador 100 estándar para opciones de EE. UU.)
            multiplicador = 100.0
            if accion == "BUY":
                pnl_pata = (payoff_unitario - precio_entrada_pata) * cantidad * multiplicador
            else: # SELL
                pnl_pata = (precio_entrada_pata - payoff_unitario) * cantidad * multiplicador
                
            pnl_neto_usd += pnl_pata
            estado_pata = "ITM" if payoff_unitario > 0.0 else "OTM"
            
            detalles_patas.append({
                "num_pata": idx + 1,
                "strike": strike,
                "right": right,
                "accion": accion,
                "cantidad": cantidad,
                "precio_entrada": precio_entrada_pata,
                "payoff_unitario": round(payoff_unitario, 4),
                "estado": estado_pata,
                "liquidada_total": round(pnl_pata, 2)
            })
            
        return {
            "pnl_realizado": round(pnl_neto_usd, 2),
            "detalles": detalles_patas
        }

    @staticmethod
    def detectar_nombre_estrategia(tipo_activo, patas):
        """
        Analiza las patas para identificar y devolver el nombre estándar de la estrategia de opciones.
        """
        if tipo_activo.upper() == "STOCK":
            return "Acciones Direccionales"
            
        opciones = [p for p in patas if p.get("tipo_activo", "OPTION").upper() in ("OPTION", "OPT", "BAG")]
        if not opciones:
            return "Acciones"
            
        n = len(opciones)
        if n == 1:
            p = opciones[0]
            accion = "Compra" if p.get("accion", "BUY").upper() == "BUY" else "Venta"
            tipo_opt = "Call" if p.get("right", "C").upper() in ("C", "CALL") else "Put"
            return f"{accion} de {tipo_opt}"
            
        elif n == 2:
            p1, p2 = opciones[0], opciones[1]
            r1, r2 = p1.get("right", "C").upper()[0], p2.get("right", "C").upper()[0]
            a1, a2 = p1.get("accion", "BUY").upper(), p2.get("accion", "BUY").upper()
            k1, k2 = float(p1.get("strike", 0.0)), float(p2.get("strike", 0.0))
            
            if r1 == "P" and r2 == "P": # Ambos Puts
                if a1 != a2: # Un Buy y un Sell -> Put Spread
                    sell_strike = k1 if a1 == "SELL" else k2
                    buy_strike = k1 if a1 == "BUY" else k2
                    if sell_strike > buy_strike:
                        return "Bull Put Spread (Credit)"
                    else:
                        return "Bear Put Spread (Debit)"
                elif a1 == "BUY" and a2 == "BUY":
                    if k1 == k2:
                        return "Double Long Put"
                    return "Long Put Strangle/Spread"
                return "Put Spread"
                
            elif r1 == "C" and r2 == "C": # Ambos Calls
                if a1 != a2: # Un Buy y un Sell -> Call Spread
                    sell_strike = k1 if a1 == "SELL" else k2
                    buy_strike = k1 if a1 == "BUY" else k2
                    if sell_strike < buy_strike:
                        return "Bear Call Spread (Credit)"
                    else:
                        return "Bull Call Spread (Debit)"
                return "Call Spread"
                
            elif r1 != r2: # Uno Call y otro Put
                if a1 == a2:
                    if k1 == k2:
                        accion = "Long" if a1 == "BUY" else "Short"
                        return f"{accion} Straddle"
                    else:
                        accion = "Long" if a1 == "BUY" else "Short"
                        return f"{accion} Strangle"
                return "Combo Call/Put"
                
        elif n == 4:
            calls = [p for p in opciones if p.get("right", "C").upper()[0] == "C"]
            puts = [p for p in opciones if p.get("right", "C").upper()[0] == "P"]
            if len(calls) == 2 and len(puts) == 2:
                c_actions = [p.get("accion", "BUY").upper() for p in calls]
                p_actions = [p.get("accion", "BUY").upper() for p in puts]
                if "BUY" in c_actions and "SELL" in c_actions and "BUY" in p_actions and "SELL" in p_actions:
                    return "Iron Condor"
            return "Mariposa / Condor / Multileg"
            
        return "Estrategia Multileg Combo"