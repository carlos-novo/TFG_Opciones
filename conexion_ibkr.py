import nest_asyncio
nest_asyncio.apply() # Magia pura para evitar bloqueos entre Streamlit y asyncio

import asyncio

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
from ib_insync import IB, Stock, Index, Contract, ComboLeg, LimitOrder, Option, MarketOrder, StopOrder

import random

class GestorIBKR:
    """
    Clase que actúa como capa intermedia entre el sistema y la API de Interactive Brokers.
    Gestiona la conexión, desconexión y la obtención de datos de mercado para
    acciones direccionales simples y combos de opciones multileg.
    """
    def __init__(self, host=None, port=4002, client_id=1):
        import os
        self.host = host or os.environ.get('IBKR_HOST', '127.0.0.1')
        self.port = port
        self.client_id = client_id
        self.ib = IB()

    def _asegurar_event_loop(self):
        """
        Garantiza que exista un bucle de eventos asíncrono activo en el hilo actual.
        Crítico para evitar conflictos con la ejecución síncrona de Streamlit.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    def conectar(self):
        """Intenta establecer conexión con IBKR Gateway usando un ID dinámico."""
        if not self.esta_conectado():
            self._asegurar_event_loop()
            try:
                # CRÍTICO: Generamos un ID aleatorio entre 1 y 9000. 
                # Así evitamos el error silencioso de "Client ID already in use" del Gateway.
                cid_dinamico = random.randint(1, 9000)
                self.ib.connect(self.host, self.port, clientId=cid_dinamico)
                return True
            except Exception as e:
                print(f"Error al conectar con IBKR: {e}")
                return False
        return True

    def desconectar(self):
        """Cierra la conexión y purga el objeto para permitir reconexiones limpias."""
        if self.esta_conectado():
            self.ib.disconnect()
            self.ib.sleep(0.1) # Pausa milimétrica para que el SO libere el puerto
            
        # CRÍTICO: Matamos al "cadáver" y creamos un objeto IB completamente nuevo
        # Esto soluciona que no te dejara reconectar por segunda vez.
        self.ib = IB()

    def esta_conectado(self):
        """Devuelve el estado actual de la conexión."""
        return self.ib.isConnected()

    def obtener_resumen_cuenta(self):
        """
        Solicita los datos de la cuenta (Paper Trading).
        Filtra y devuelve solo las métricas clave para el Dashboard.
        """
        if not self.esta_conectado():
            return None

        self._asegurar_event_loop()
        
        try:
            resumen = self.ib.accountSummary()
            
            datos_cuenta = {
                "NetLiquidation": "0.00",
                "BuyingPower": "0.00",
                "DailyPnL": "0.00"
            }
            
            for item in resumen:
                if item.tag == 'NetLiquidation':
                    datos_cuenta["NetLiquidation"] = item.value
                elif item.tag == 'BuyingPower':
                    datos_cuenta["BuyingPower"] = item.value
                elif item.tag == 'DailyPnL':
                    datos_cuenta["DailyPnL"] = item.value
                    
            return datos_cuenta
            
        except Exception as e:
            print(f"Error al obtener el resumen de cuenta: {e}")
            return None

    def obtener_precio_prueba(self, simbolo):
        """
        Versión Micro-sesión (Stateless): Crea una conexión efímera exclusiva 
        para el hilo actual de Streamlit, evitando el cuelgue de sockets.
        """
        self._asegurar_event_loop()
        
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=99)
            
            # REGLA DE ORO: SPX es un índice, el resto son Stocks
            if simbolo.upper() == 'SPX':
                contrato = Index(simbolo, 'CBOE', 'USD')
            else:
                contrato = Stock(simbolo, 'SMART', 'USD')
            ib_temp.qualifyContracts(contrato)
            ib_temp.reqMarketDataType(3)  # Habilitar tipo de datos retardados (Delayed) si no hay suscripción en tiempo real
            
            barras = ib_temp.reqHistoricalData(
                contrato,
                endDateTime='',
                durationStr='1 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=False, 
                formatDate=1
            )
            
            ib_temp.disconnect() 
            
            if barras and len(barras) > 0:
                return barras[-1].close
            else:
                return None
                
        except Exception as e:
            print(f"Error en consulta de precio (Micro-sesión): {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return None

    def obtener_historico_diario(self, simbolo, dias):
        """
        Micro-sesión (Stateless): Descarga el histórico de precios de cierre diarios.
        Esencial para el cálculo de indicadores de Análisis Técnico (AT).
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        
        try:
            ib_temp.connect(self.host, self.port, clientId=97)
            
            if simbolo.upper() == 'SPX':
                contrato = Index(simbolo, 'CBOE', 'USD')
            else:
                contrato = Stock(simbolo, 'SMART', 'USD')
            ib_temp.qualifyContracts(contrato)
            ib_temp.reqMarketDataType(3)  # Habilitar tipo de datos retardados (Delayed) si no hay suscripción en tiempo real
            
            barras = ib_temp.reqHistoricalData(
                contrato,
                endDateTime='',
                durationStr=f'{dias} D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True, 
                formatDate=1
            )
            
            ib_temp.disconnect()
            
            if barras:
                return [barra.close for barra in barras]
            return []
            
        except Exception as e:
            print(f"Error al descargar histórico para AT: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return []

    def obtener_posiciones_cartera(self):
        """
        Micro-sesión Read-Only: Solicita el portfolio actual de la cuenta Paper Trading.
        Retorna una lista de diccionarios listos para st.dataframe().
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=94)

            items = ib_temp.portfolio()  # Lista de PortfolioItem
            posiciones = []

            for item in items:
                c = item.contract
                if c.secType == 'OPT':
                    mult = float(c.multiplier) if (c.multiplier and c.multiplier.strip()) else 100.0
                    posiciones.append({
                        "Símbolo":       c.symbol,
                        "Tipo":          "Opción",
                        "Vencimiento":   c.lastTradeDateOrContractMonth,
                        "Strike":        c.strike,
                        "Right (C/P)":   c.right,
                        "Posición":      item.position,
                        "Precio Medio":  round(item.averageCost / mult, 4),
                        "Valor Mercado": round(item.marketValue, 2),
                        "P&L No Real.":  round(item.unrealizedPNL, 2),
                    })
                else:
                    posiciones.append({
                        "Símbolo":       c.symbol,
                        "Tipo":          c.secType,
                        "Vencimiento":   "—",
                        "Strike":        "—",
                        "Right (C/P)":   "—",
                        "Posición":      item.position,
                        "Precio Medio":  round(item.averageCost, 4),
                        "Valor Mercado": round(item.marketValue, 2),
                        "P&L No Real.":  round(item.unrealizedPNL, 2),
                    })

            ib_temp.disconnect()
            return posiciones

        except Exception as e:
            print(f"Error al obtener posiciones de cartera: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return []

    def cancelar_orden(self, order_id):
        """
        Micro-sesión de cancelación: Localiza la orden y emite la cancelación.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=93)
            ordenes_abiertas = ib_temp.reqAllOpenOrders()
            ib_temp.sleep(1)

            orden_objetivo = None
            for trade in ordenes_abiertas:
                if trade.order.orderId == order_id:
                    orden_objetivo = trade
                    break

            if orden_objetivo is None:
                ib_temp.disconnect()
                return {
                    "exito": False,
                    "mensaje": f"Orden #{order_id} no encontrada entre las órdenes abiertas."
                }

            ib_temp.cancelOrder(orden_objetivo.order)
            ib_temp.sleep(1)

            ib_temp.disconnect()
            return {
                "exito": True,
                "mensaje": f"Solicitud de cancelación enviada para la orden #{order_id}."
            }

        except Exception as e:
            print(f"Error al cancelar orden #{order_id}: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return {
                "exito": False,
                "mensaje": f"Error técnico al cancelar la orden #{order_id}: {e}"
            }

    def consultar_estado_ordenes(self):
        """
        Micro-sesión de polling: Obtiene todas las órdenes abiertas y ejecuciones del día.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        estados = {}
        try:
            ib_temp.connect(self.host, self.port, clientId=92)
            
            open_orders = ib_temp.reqAllOpenOrders()
            for trade in open_orders:
                estados[trade.order.orderId] = trade.orderStatus.status
                
            executions = ib_temp.reqExecutions()
            for fill in executions:
                estados[fill.execution.orderId] = 'Filled'
                
            ib_temp.disconnect()
            return estados
        except Exception as e:
            print(f"Error en polling de órdenes: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return {}

    # ==========================================
    # NUEVA CAPA DINÁMICA MULTILEG Y DIRECCIONAL
    # ==========================================

    def calificar_y_obtener_contratos(self, ib_client, ticker, patas):
        """
        Dada una lista de patas, crea los contratos de ib_insync (Option o Stock)
        y los califica de golpe usando qualifyContracts.
        Retorna la lista de contratos calificados.
        """
        contratos = []
        for pata in patas:
            tipo = pata.get("tipo_activo", "OPTION").upper()
            if tipo == "STOCK":
                contratos.append(Stock(ticker, 'SMART', 'USD'))
            elif tipo == "INDEX":
                contratos.append(Index(ticker, 'CBOE', 'USD'))
            else:
                vencimiento = pata.get("vencimiento")
                fecha_str = vencimiento.strftime('%Y%m%d') if hasattr(vencimiento, 'strftime') else str(vencimiento).replace('-', '')
                contratos.append(Option(ticker, fecha_str, float(pata.get("strike")), pata.get("right"), 'SMART', currency='USD'))
                
        ib_client.qualifyContracts(*contratos)
        return contratos

    def obtener_datos_patas(self, ticker, patas):
        """
        Micro-sesión genérica: Abre una sola conexión, califica los N contratos 
        y recupera los precios bid/ask/last de todos ellos en un solo batch.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=96)
            ib_temp.reqMarketDataType(3)
            
            contratos = self.calificar_y_obtener_contratos(ib_temp, ticker, patas)
            tickers = ib_temp.reqTickers(*contratos)
            
            resultados = []
            for t in tickers:
                bid = t.bid if (t.bid and t.bid > 0) else t.close
                ask = t.ask if (t.ask and t.ask > 0) else t.close
                last = t.last if (t.last and t.last > 0) else (t.close if t.close else 0.0)
                resultados.append({
                    "bid": bid if bid else 0.0,
                    "ask": ask if ask else 0.0,
                    "last": last if last else 0.0
                })
            
            ib_temp.disconnect()
            return resultados
        except Exception as e:
            print(f"Error en sesión bulk dinámica: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return [{"bid": 0.0, "ask": 0.0, "last": 0.0}] * len(patas)

    def construir_contrato_bag_dinamico(self, ticker, contratos_calificados, patas):
        """
        Ensambla un contrato BAG (Combo) a partir de los contratos calificados
        e inyecta la dirección (BUY/SELL) y ratio correspondiente de cada pata.
        """
        legs = []
        for contrato, pata in zip(contratos_calificados, patas):
            leg = ComboLeg()
            leg.conId = contrato.conId
            leg.ratio = int(pata.get("cantidad", 1))
            leg.action = pata.get("accion", "BUY").upper()
            leg.exchange = 'SMART'
            legs.append(leg)

        bag = Contract()
        bag.symbol = ticker
        bag.secType = 'BAG'
        bag.currency = 'USD'
        bag.exchange = 'SMART'
        bag.comboLegs = legs
        return bag

    def enviar_orden_generica(self, ticker, tipo_activo, patas, precio_limite=None):
        """
        Envía una orden al mercado (Stock simple, opción simple o combo BAG de N-patas).
        Soporta el "Modo Mock Defensa TFG" si las definiciones de contratos fallan.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=95)
            ib_temp.reqMarketDataType(3)

            contratos = self.calificar_y_obtener_contratos(ib_temp, ticker, patas)

            # Si algún contrato no pudo calificarse, activamos la simulación teórica de la defensa
            if not all(c.conId for c in contratos):
                print(f"Modo Defensa TFG Activado: Simulando orden para {ticker}")
                ib_temp.disconnect()
                return {
                    "order_id": random.randint(100000, 999999), 
                    "status": "Submitted (Mock Defensa TFG)"
                }

            # Enviar orden según tipo
            if tipo_activo.upper() == "STOCK" or len(patas) == 1:
                pata = patas[0]
                contrato = contratos[0]
                accion = pata.get("accion", "BUY").upper()
                cantidad = int(pata.get("cantidad", 1))
                
                if precio_limite is not None:
                    orden = LimitOrder(action=accion, totalQuantity=cantidad, lmtPrice=round(precio_limite, 2))
                else:
                    orden = MarketOrder(action=accion, totalQuantity=cantidad)
                    
                trade = ib_temp.placeOrder(contrato, orden)
            else:
                # Combo Multileg (BAG)
                bag = self.construir_contrato_bag_dinamico(ticker, contratos, patas)
                
                lmt_price = round(precio_limite, 2) if precio_limite is not None else 0.0
                
                # Regla deInteractive Brokers: si es combo a crédito (precio positivo de cobro),
                # para una orden BUY, el precio límite se especifica negativo.
                if lmt_price > 0:
                    lmt_price = -lmt_price
                    
                orden = LimitOrder(
                    action='BUY',
                    totalQuantity=1,
                    lmtPrice=lmt_price
                )
                trade = ib_temp.placeOrder(bag, orden)

            ib_temp.sleep(1) # Espera de confirmación inicial
            order_id = trade.order.orderId
            order_status = trade.orderStatus.status

            ib_temp.disconnect()
            return {"order_id": order_id, "status": order_status}

        except Exception as e:
            print(f"Error al enviar orden genérica: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            raise

    def enviar_orden_cierre_generica(self, ticker, tipo_activo, patas, precio_cierre=None):
        """
        Envía una orden inversa para cerrar la posición de un Stock, opción simple o BAG combo.
        Invierte lógicamente las patas (BUY -> SELL, SELL -> BUY).
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=90)
            ib_temp.reqMarketDataType(3)

            # Invertimos la dirección de las patas para el cierre
            patas_cierre = []
            for pata in patas:
                accion_inversa = "SELL" if pata.get("accion", "BUY").upper() == "BUY" else "BUY"
                pata_inv = pata.copy()
                pata_inv["accion"] = accion_inversa
                patas_cierre.append(pata_inv)

            contratos = self.calificar_y_obtener_contratos(ib_temp, ticker, patas_cierre)

            # Modo Mock Defensa TFG para cierre
            if not all(c.conId for c in contratos):
                print(f"Modo Mock Cierre TFG Activado: Simulando cierre para {ticker}")
                ib_temp.disconnect()
                return {
                    "order_id": random.randint(100000, 999999),
                    "status": "Filled (Mock Cierre TFG)"
                }

            # Si no se indica precio de cierre, estimamos el precio medio operativo (Mid Price)
            if precio_cierre is None:
                tickers_mkt = ib_temp.reqTickers(*contratos)
                precio_cierre = 0.0
                for t in tickers_mkt:
                    mid = None
                    if t.bid and t.ask and t.bid > 0 and t.ask > 0:
                        mid = (t.bid + t.ask) / 2.0
                    elif t.close and t.close > 0:
                        mid = t.close
                    if mid:
                        precio_cierre += mid
                precio_cierre = round(max(precio_cierre, 0.01), 2)

            # Enviar orden de cierre
            if tipo_activo.upper() == "STOCK" or len(patas_cierre) == 1:
                pata = patas_cierre[0]
                contrato = contratos[0]
                accion = pata["accion"]
                cantidad = int(pata.get("cantidad", 1))
                
                orden = LimitOrder(action=accion, totalQuantity=cantidad, lmtPrice=round(precio_cierre, 2))
                trade = ib_temp.placeOrder(contrato, orden)
            else:
                bag = self.construir_contrato_bag_dinamico(ticker, contratos, patas_cierre)
                orden = LimitOrder(
                    action='SELL',
                    totalQuantity=1,
                    lmtPrice=round(precio_cierre, 2)
                )
                trade = ib_temp.placeOrder(bag, orden)

            ib_temp.sleep(1)
            order_id = trade.order.orderId
            order_status = trade.orderStatus.status

            ib_temp.disconnect()
            return {"order_id": order_id, "status": order_status}

        except Exception as e:
            print(f"Error al enviar orden de cierre genérica: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            raise

    def obtener_pnl_posiciones_filtrado(self, ticker_filtro=None, tipo_activo_filtro=None):
        """
        Suma el P&L no realizado de la cuenta de trading filtrado por subyacente e instrumentación.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=91)
            items = ib_temp.portfolio()
            ib_temp.disconnect()

            pnl_total = 0.0
            hay_posiciones = False

            for item in items:
                c = item.contract
                
                # Filtrado por tipo de activo ('STOCK' -> 'STK', 'OPTION' -> 'OPT')
                if tipo_activo_filtro:
                    tipo_mkt = "STK" if tipo_activo_filtro.upper() == "STOCK" else "OPT"
                    if c.secType != tipo_mkt:
                        continue
                else:
                    if c.secType not in ('OPT', 'STK'):
                        continue

                if ticker_filtro and c.symbol.upper() != ticker_filtro.upper():
                    continue

                pnl_total += item.unrealizedPNL
                hay_posiciones = True

            return round(pnl_total, 2) if hay_posiciones else None

        except Exception as e:
            print(f"Error al obtener P&L de posiciones: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return None

    def calcular_pnl_estrategia(self, ticker, tipo_activo, patas):
        """
        Calcula el P&L no realizado acumulado de una estrategia específica
        emparejando sus patas teóricas de forma proporcional con las posiciones reales del bróker.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        
        def normalizar_fecha(f_str):
            if not f_str:
                return ""
            cleaned = str(f_str).replace("-", "").replace("/", "").strip()
            if len(cleaned) == 8:
                return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
            return cleaned

        try:
            ib_temp.connect(self.host, self.port, clientId=93)
            items = ib_temp.portfolio()
            ib_temp.disconnect()

            pnl_total = 0.0
            hay_coincidencias = False

            for leg in patas:
                # Cantidad firmada teórica en base de datos
                leg_cant = int(leg.get("cantidad", 1))
                if leg.get("accion", "BUY").upper() == "SELL":
                    leg_cant = -leg_cant

                # Buscar en la cartera
                for item in items:
                    c = item.contract
                    
                    if tipo_activo.upper() == "STOCK":
                        if c.secType == 'STK' and c.symbol.upper() == ticker.upper():
                            tws_pos = float(item.position)
                            if tws_pos != 0.0:
                                pnl_total += item.unrealizedPNL * (leg_cant / tws_pos)
                                hay_coincidencias = True
                                break
                    else:
                        # Opciones o BAG combos
                        if c.secType == 'OPT' and c.symbol.upper() == ticker.upper():
                            leg_strike = float(leg.get("strike", 0.0))
                            leg_right = leg.get("right", "C").upper()
                            if leg_right == "CALL":
                                leg_right = "C"
                            elif leg_right == "PUT":
                                leg_right = "P"
                            else:
                                leg_right = leg_right[0] if leg_right else "C"
                            
                            leg_venc = normalizar_fecha(leg.get("vencimiento", ""))
                            
                            c_right = c.right.upper()[0] if c.right else ""
                            c_strike = float(c.strike)
                            c_venc = normalizar_fecha(c.lastTradeDateOrContractMonth)
                            
                            if c_right == leg_right and c_strike == leg_strike and c_venc == leg_venc:
                                tws_pos = float(item.position)
                                if tws_pos != 0.0:
                                    pnl_total += item.unrealizedPNL * (leg_cant / tws_pos)
                                    hay_coincidencias = True
                                    break

            return round(pnl_total, 2) if hay_coincidencias else None

        except Exception as e:
            print(f"Error al calcular P&L de estrategia: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return None

    # ==========================================
    # MÉTODOS DE COMPATIBILIDAD CON IRON CONDOR
    # ==========================================

    def obtener_datos_estrategia_completa(self, ticker, vencimiento, strikes):
        """
        Wrapper compatible con la lógica anterior del Iron Condor estático.
        """
        p_long, p_short, c_short, c_long = strikes
        patas = [
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_long, "right": "P"},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_short, "right": "P"},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_short, "right": "C"},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_short, "right": "C"},  # Repetir para evitar IndexError si strikes cambian
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_long, "right": "C"}
        ]
        # Nos aseguramos de recortar o usar exactamente 4 patas
        patas_ic = [
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_long, "right": "P"},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_short, "right": "P"},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_short, "right": "C"},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_long, "right": "C"}
        ]
        return self.obtener_datos_patas(ticker, patas_ic)

    def construir_contrato_bag(self, ticker, contratos_calificados):
        """
        Wrapper compatible con la construcción estática del Iron Condor de 4 patas.
        """
        patas_mock = [
            {"accion": "BUY", "cantidad": 1},
            {"accion": "SELL", "cantidad": 1},
            {"accion": "SELL", "cantidad": 1},
            {"accion": "BUY", "cantidad": 1}
        ]
        return self.construir_contrato_bag_dinamico(ticker, contratos_calificados, patas_mock)

    def enviar_orden_iron_condor(self, ticker, vencimiento, strikes, credito_objetivo):
        """
        Wrapper compatible para enviar órdenes Iron Condor antiguas.
        """
        p_long, p_short, c_short, c_long = strikes
        patas = [
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_long, "right": "P", "accion": "BUY", "cantidad": 1},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_short, "right": "P", "accion": "SELL", "cantidad": 1},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_short, "right": "C", "accion": "SELL", "cantidad": 1},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_long, "right": "C", "accion": "BUY", "cantidad": 1}
        ]
        return self.enviar_orden_generica(ticker, "BAG", patas, precio_limite=credito_objetivo)

    def obtener_pnl_posiciones_opciones(self, ticker_filtro=None):
        """
        Wrapper compatible para recuperar el P&L agregado de opciones.
        """
        return self.obtener_pnl_posiciones_filtrado(ticker_filtro=ticker_filtro, tipo_activo_filtro="OPTION")

    def enviar_orden_cierre_iron_condor(self, ticker, vencimiento, strikes):
        """
        Wrapper compatible para cerrar órdenes Iron Condor antiguas.
        """
        p_long, p_short, c_short, c_long = strikes
        patas = [
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_long, "right": "P", "accion": "BUY", "cantidad": 1},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": p_short, "right": "P", "accion": "SELL", "cantidad": 1},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_short, "right": "C", "accion": "SELL", "cantidad": 1},
            {"tipo_activo": "OPTION", "vencimiento": vencimiento, "strike": c_long, "right": "C", "accion": "BUY", "cantidad": 1}
        ]
        return self.enviar_orden_cierre_generica(ticker, "BAG", patas)

    def enviar_ordenes_proteccion_ibkr(self, ticker, accion_entrada, cantidad, precio_entrada, stop_loss_usd, take_profit_usd):
        """
        Envía órdenes de Stop Loss y Take Profit directamente al Broker (IBKR)
        asociadas a una posición existente de acciones.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=89)
            contrato = Stock(ticker, 'SMART', 'USD')
            ib_temp.qualifyContracts(contrato)
            
            accion_salida = "SELL" if accion_entrada.upper() == "BUY" else "BUY"
            res_ordenes = {}
            
            # 1. Stop Loss
            if stop_loss_usd is not None:
                perdida_por_accion = float(stop_loss_usd) / int(cantidad)
                if accion_entrada.upper() == "BUY":
                    precio_sl = precio_entrada + perdida_por_accion
                else:
                    precio_sl = precio_entrada - perdida_por_accion
                    
                precio_sl = round(max(precio_sl, 0.01), 2)
                orden_sl = StopOrder(action=accion_salida, totalQuantity=int(cantidad), stopPrice=precio_sl)
                trade_sl = ib_temp.placeOrder(contrato, orden_sl)
                res_ordenes["stop_loss"] = {"order_id": trade_sl.order.orderId, "precio": precio_sl}
                
            # 2. Take Profit
            if take_profit_usd is not None:
                ganancia_por_accion = float(take_profit_usd) / int(cantidad)
                if accion_entrada.upper() == "BUY":
                    precio_tp = precio_entrada + ganancia_por_accion
                else:
                    precio_tp = precio_entrada - ganancia_por_accion
                    
                precio_tp = round(max(precio_tp, 0.01), 2)
                orden_tp = LimitOrder(action=accion_salida, totalQuantity=int(cantidad), lmtPrice=precio_tp)
                trade_tp = ib_temp.placeOrder(contrato, orden_tp)
                res_ordenes["take_profit"] = {"order_id": trade_tp.order.orderId, "precio": precio_tp}
                
            ib_temp.sleep(1)
            ib_temp.disconnect()
            return res_ordenes
        except Exception as e:
            print(f"Error al enviar órdenes de protección a IBKR: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            raise
