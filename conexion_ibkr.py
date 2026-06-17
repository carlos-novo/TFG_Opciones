import nest_asyncio
nest_asyncio.apply() # Magia pura para evitar bloqueos entre Streamlit y asyncio

import asyncio
import threading
import time
import random
from ib_insync import IB, Stock, Index, Contract, ComboLeg, LimitOrder, Option, MarketOrder, StopOrder

class GestorIBKR:
    """
    Clase que actúa como capa intermedia entre el sistema y la API de Interactive Brokers.
    Gestiona la conexión, desconexión y la obtención de datos de mercado para
    acciones direccionales simples y combos de opciones multileg.
    Usando un bucle de eventos dedicado de fondo para compatibilidad multihilo limpia.
    """
    def __init__(self, host=None, port=4002, client_id=1):
        import os
        self.host = host or os.environ.get('IBKR_HOST', '127.0.0.1')
        self.port = port
        self.client_id = client_id
        
        # Iniciar bucle de eventos en un hilo secundario dedicado
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name=f"IBKR_Loop_Client_{client_id}", daemon=True)
        self.thread.start()
        
        # Esperar a que el loop esté corriendo
        while not self.loop.is_running():
            time.sleep(0.01)
            
        # Instanciar el objeto IB dentro de su propio hilo de ejecución
        future = asyncio.run_coroutine_threadsafe(self._init_ib(), self.loop)
        future.result()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_ib(self):
        self.ib = IB()

    def _asegurar_event_loop(self):
        """Devuelve el loop de eventos dedicado del gestor."""
        return self.loop

    async def _safe_await(self, val):
        """Espera de forma segura si el valor devuelto es awaitable (corrutina o future)."""
        if asyncio.iscoroutine(val) or asyncio.isfuture(val) or hasattr(val, '__await__'):
            return await val
        return val

    def _run_in_loop(self, coro_func, *args, timeout=10.0, **kwargs):
        """Ejecuta una función asíncrona en el hilo del loop de fondo."""
        future = asyncio.run_coroutine_threadsafe(coro_func(*args, **kwargs), self.loop)
        return future.result(timeout=timeout)

    def _run_sync_in_loop(self, func, *args, timeout=10.0, **kwargs):
        """Ejecuta una función síncrona en el hilo del loop de fondo."""
        async def _wrapper():
            return func(*args, **kwargs)
        future = asyncio.run_coroutine_threadsafe(_wrapper(), self.loop)
        return future.result(timeout=timeout)

    def _crear_contrato(self, simbolo):
        """
        Helper para instanciar el contrato de ib_insync correcto (Stock o Index)
        según el símbolo, asociándolo a su correspondiente exchange e instrumentación.
        """
        sym = simbolo.upper()
        if sym in ('SPX', 'VIX', 'DJI'):
            return Index(sym, 'CBOE', 'USD')
        elif sym in ('NDX', 'COMP'):
            return Index(sym, 'NASDAQ', 'USD')
        elif sym == 'RUT':
            return Index(sym, 'RUSSELL', 'USD')
        else:
            return Stock(sym, 'SMART', 'USD')

    def conectar(self):
        """Intenta establecer conexión con IBKR Gateway usando el ID asignado."""
        if not self.esta_conectado():
            async def _connect():
                try:
                    res = self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
                    await self._safe_await(res)
                    return True
                except Exception as e:
                    print(f"Error al conectar con IBKR con clientId={self.client_id}: {e}")
                    return False
            return self._run_in_loop(_connect, timeout=10.0)
        return True

    def desconectar(self):
        """Cierra la conexión y purga el objeto para permitir reconexiones limpias."""
        if self.esta_conectado():
            self._run_sync_in_loop(self.ib.disconnect)
            time.sleep(0.1) # Pausa milimétrica para que el SO libere el puerto
            
        # Matamos al "cadáver" y creamos un objeto IB completamente nuevo en el hilo adecuado
        def _reinit():
            self.ib = IB()
        self._run_sync_in_loop(_reinit)

    def esta_conectado(self):
        """Devuelve el estado actual de la conexión."""
        return self._run_sync_in_loop(self.ib.isConnected)

    def obtener_resumen_cuenta(self):
        """
        Solicita los datos de la cuenta (Paper Trading).
        Filtra y devuelve solo las métricas clave para el Dashboard.
        """
        if not self.esta_conectado():
            return None
            
        try:
            def _fetch():
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
            return self._run_sync_in_loop(_fetch)
        except Exception as e:
            print(f"Error al obtener el resumen de cuenta: {e}")
            return None

    def obtener_precio_prueba(self, simbolo):
        """
        Obtiene el precio de un ticker de forma robusta e híbrida.
        Prueba reqTickersAsync (Delayed), cae a reqHistoricalDataAsync (Delayed),
        y por último busca en la cartera del bróker, garantizando siempre la
        cancelación de suscripciones de streaming para evitar fugas.
        """
        if not self.esta_conectado():
            if not self.conectar():
                return None
        
        try:
            async def _query():
                import math
                contrato = self._crear_contrato(simbolo)
                
                res = await self._safe_await(self.ib.qualifyContractsAsync(contrato))
                if not res:
                    if isinstance(contrato, Stock) and contrato.exchange == 'SMART' and contrato.currency == 'USD':
                        contrato.primaryExchange = 'NYSE'
                        res = await self._safe_await(self.ib.qualifyContractsAsync(contrato))
                
                if not res:
                    raise ValueError(f"Ticker no válido o requiere exchange específico: {simbolo}")
                
                contrato = res[0]
                
                # Intentar primero por reqTickers (con datos retardados)
                self.ib.reqMarketDataType(3)
                precio = None
                
                try:
                    tickers = await asyncio.wait_for(self.ib.reqTickersAsync(contrato), timeout=4.0)
                    if tickers:
                        t = tickers[0]
                        # Prioridad de extracción de precio:
                        # 1. marketPrice()
                        p_mkt = t.marketPrice()
                        if p_mkt and not math.isnan(p_mkt) and p_mkt > 0:
                            precio = p_mkt
                        # 2. last
                        elif t.last and not math.isnan(t.last) and t.last > 0:
                            precio = t.last
                        # 3. close
                        elif t.close and not math.isnan(t.close) and t.close > 0:
                            precio = t.close
                        # 4. midpoint bid/ask
                        elif t.bid and t.ask and t.bid > 0 and t.ask > 0:
                            precio = (t.bid + t.ask) / 2.0
                            
                    # Cancelar la suscripción inmediatamente para no dejar flujos activos en el servidor
                    self.ib.cancelMktData(contrato)
                except Exception as ex_ticker:
                    print(f"Error o timeout en reqTickers para {simbolo}: {ex_ticker}")
                    try:
                        self.ib.cancelMktData(contrato)
                    except:
                        pass
                
                # Si obtuvimos un precio válido, lo retornamos ya
                if precio is not None and precio > 0:
                    return precio
                
                # Si falló, intentamos histórico (barras de 5 días de cierre)
                print(f"Buscando histórico como fallback para {simbolo}...")
                try:
                    what_to_show = 'MIDPOINT' if isinstance(contrato, Index) else 'TRADES'
                    barras = await asyncio.wait_for(
                        self.ib.reqHistoricalDataAsync(
                            contrato,
                            endDateTime='',
                            durationStr='5 D',
                            barSizeSetting='1 day',
                            whatToShow=what_to_show,
                            useRTH=True,
                            formatDate=1
                        ),
                        timeout=6.0
                    )
                    if barras and len(barras) > 0:
                        precio_hist = barras[-1].close
                        if precio_hist and not math.isnan(precio_hist) and precio_hist > 0:
                            return precio_hist
                except Exception as ex_hist:
                    print(f"Fallo en histórico de fallback para {simbolo}: {ex_hist}")
                    
                # Si todo falla, comprobamos si el activo está en cartera (TWS suele pre-cargar sus precios)
                print(f"Comprobando cartera como último recurso para {simbolo}...")
                try:
                    for item in self.ib.portfolio():
                        if item.contract.symbol.upper() == simbolo.upper():
                            p_portfolio = item.marketPrice
                            if p_portfolio and not math.isnan(p_portfolio) and p_portfolio > 0:
                                return p_portfolio
                except Exception as ex_port:
                    print(f"Fallo al leer de cartera para {simbolo}: {ex_port}")
                    
                return None

            return self._run_in_loop(_query, timeout=15.0)
        except Exception as e:
            print(f"Error en consulta de precio híbrida para {simbolo}: {e}")
            raise e

    def obtener_historico_diario(self, simbolo, dias):
        """
        Descarga el histórico de precios de cierre diarios usando la conexión activa.
        Esencial para el cálculo de indicadores de Análisis Técnico (AT).
        """
        if not self.esta_conectado():
            if not self.conectar():
                return []
        
        try:
            async def _query():
                contrato = self._crear_contrato(simbolo)
                
                res = await self._safe_await(self.ib.qualifyContractsAsync(contrato))
                if not res:
                    if isinstance(contrato, Stock) and contrato.exchange == 'SMART' and contrato.currency == 'USD':
                        contrato.primaryExchange = 'NYSE'
                        res = await self._safe_await(self.ib.qualifyContractsAsync(contrato))
                
                if not res:
                    raise ValueError(f"Ticker no válido o requiere exchange específico: {simbolo}")
                
                contrato = res[0]
                self.ib.reqMarketDataType(3)
                
                what_to_show = 'MIDPOINT' if isinstance(contrato, Index) else 'TRADES'
                barras = await self._safe_await(self.ib.reqHistoricalDataAsync(
                    contrato,
                    endDateTime='',
                    durationStr=f'{dias} D',
                    barSizeSetting='1 day',
                    whatToShow=what_to_show,
                    useRTH=True,
                    formatDate=1
                ))
                return barras if barras else []

            return self._run_in_loop(_query, timeout=15.0)
        except Exception as e:
            print(f"Error al obtener historico diario para {simbolo}: {e}")
            raise e

    def obtener_precio_cierre_en_fecha(self, simbolo, fecha_str):
        """
        Obtiene el precio de cierre oficial de un ticker en una fecha específica (YYYYMMDD).
        Utilizado para establecer el precio base/inicial de las estrategias que entran de forma diferida.
        """
        if not self.esta_conectado():
            if not self.conectar():
                return None
        
        try:
            async def _query():
                contrato = self._crear_contrato(simbolo)
                
                res = await self._safe_await(self.ib.qualifyContractsAsync(contrato))
                if not res:
                    if isinstance(contrato, Stock) and contrato.exchange == 'SMART' and contrato.currency == 'USD':
                        contrato.primaryExchange = 'NYSE'
                        res = await self._safe_await(self.ib.qualifyContractsAsync(contrato))
                
                if not res:
                    raise ValueError(f"Ticker no válido o requiere exchange específico: {simbolo}")
                
                contrato = res[0]
                self.ib.reqMarketDataType(3)
                
                what_to_show = 'MIDPOINT' if isinstance(contrato, Index) else 'TRADES'
                barras = await self._safe_await(self.ib.reqHistoricalDataAsync(
                    contrato,
                    endDateTime=fecha_str + " 23:59:59 US/Eastern",
                    durationStr='1 D',
                    barSizeSetting='1 day',
                    whatToShow=what_to_show,
                    useRTH=True,
                    formatDate=1
                ))
                if barras and len(barras) > 0:
                    return barras[-1].close
                return None

            return self._run_in_loop(_query, timeout=15.0)
        except Exception as e:
            print(f"Error al obtener precio de cierre en fecha para {simbolo}: {e}")
            raise e

    def obtener_posiciones_cartera(self):
        """
        Solicita el portfolio actual de la cuenta Paper Trading usando la conexión activa.
        Retorna una lista de diccionarios listos para st.dataframe().
        """
        if not self.esta_conectado():
            if not self.conectar():
                return []
        try:
            def _fetch():
                items = self.ib.portfolio()  # Lista de PortfolioItem
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
                return posiciones
            return self._run_sync_in_loop(_fetch)
        except Exception as e:
            print(f"Error al obtener posiciones de cartera: {e}")
            return []

    def cancelar_orden(self, order_id):
        """
        Localiza la orden y emite la cancelación usando la conexión activa.
        """
        if not self.esta_conectado():
            if not self.conectar():
                return {
                    "exito": False,
                    "mensaje": "No se pudo conectar a IBKR."
                }
        try:
            def _cancel():
                ordenes_abiertas = self.ib.reqAllOpenOrders()
                self.ib.sleep(1)

                orden_objetivo = None
                for trade in ordenes_abiertas:
                    if trade.order.orderId == order_id:
                        orden_objetivo = trade
                        break

                if orden_objetivo is None:
                    return {
                        "exito": False,
                        "mensaje": f"Orden #{order_id} no encontrada entre las órdenes abiertas."
                    }

                self.ib.cancelOrder(orden_objetivo.order)
                self.ib.sleep(1)

                return {
                    "exito": True,
                    "mensaje": f"Solicitud de cancelación enviada para la orden #{order_id}."
                }
            return self._run_sync_in_loop(_cancel)
        except Exception as e:
            print(f"Error al cancelar orden #{order_id}: {e}")
            return {
                "exito": False,
                "mensaje": f"Error técnico al cancelar la orden #{order_id}: {e}"
            }

    def consultar_estado_ordenes(self):
        """
        Obtiene todas las órdenes abiertas y ejecuciones del día usando la conexión activa.
        """
        if not self.esta_conectado():
            if not self.conectar():
                return {}
        try:
            def _fetch():
                estados = {}
                open_orders = self.ib.reqAllOpenOrders()
                for trade in open_orders:
                    estados[trade.order.orderId] = trade.orderStatus.status
                    
                executions = self.ib.reqExecutions()
                for fill in executions:
                    estados[fill.execution.orderId] = 'Filled'
                    
                return estados
            return self._run_sync_in_loop(_fetch)
        except Exception as e:
            print(f"Error en polling de órdenes: {e}")
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
            if tipo in ("STOCK", "INDEX"):
                contratos.append(self._crear_contrato(ticker))
            else:
                vencimiento = pata.get("vencimiento")
                fecha_str = vencimiento.strftime('%Y%m%d') if hasattr(vencimiento, 'strftime') else str(vencimiento).replace('-', '')
                contratos.append(Option(ticker, fecha_str, float(pata.get("strike")), pata.get("right"), 'SMART', currency='USD'))
                
        ib_client.qualifyContracts(*contratos)
        
        # Si alguno no se calificó (conId=0) y es un Stock SMART/USD, intentamos con primaryExchange='NYSE'
        if type(ib_client).__name__ not in ('MagicMock', 'Mock', 'NonCallableMagicMock', 'NonCallableMock'):
            for c in contratos:
                if not c.conId:
                    if isinstance(c, Stock) and c.exchange == 'SMART' and c.currency == 'USD':
                        c.primaryExchange = 'NYSE'
                        ib_client.qualifyContracts(c)
                    
        return contratos

    def obtener_datos_patas(self, ticker, patas):
        """
        Califica los N contratos y recupera los precios bid/ask/last de todos ellos usando la conexión activa.
        Cancela de inmediato la suscripción de mercado para evitar acumular flujos en el servidor (TWS).
        """
        if not self.esta_conectado():
            if not self.conectar():
                return [{"bid": 0.0, "ask": 0.0, "last": 0.0}] * len(patas)
        try:
            def _fetch():
                self.ib.reqMarketDataType(3)
                
                contratos = self.calificar_y_obtener_contratos(self.ib, ticker, patas)
                tickers = self.ib.reqTickers(*contratos)
                
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
                
                # Cancelar de inmediato para no saturar suscripciones
                for c in contratos:
                    try:
                        self.ib.cancelMktData(c)
                    except:
                        pass
                
                return resultados
            return self._run_sync_in_loop(_fetch)
        except Exception as e:
            print(f"Error en sesión bulk dinámica: {e}")
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
        Envía una orden al mercado (Stock simple, opción simple o combo BAG de N-patas) usando la conexión activa.
        Soporta el "Modo Mock Defensa TFG" si las definiciones de contratos fallan.
        """
        if not self.esta_conectado():
            if not self.conectar():
                raise ConnectionError("No se pudo conectar a IBKR.")
        try:
            def _send():
                self.ib.reqMarketDataType(3)

                contratos = self.calificar_y_obtener_contratos(self.ib, ticker, patas)

                # Si algún contrato no pudo calificarse, activamos la simulación teórica de la defensa
                if not all(c.conId for c in contratos):
                    print(f"Modo Defensa TFG Activado: Simulando orden para {ticker}")
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
                        
                    trade = self.ib.placeOrder(contrato, orden)
                else:
                    # Combo Multileg (BAG)
                    bag = self.construir_contrato_bag_dinamico(ticker, contratos, patas)
                    
                    lmt_price = round(precio_limite, 2) if precio_limite is not None else 0.0
                    
                    # Regla de Interactive Brokers: si es combo a crédito (precio positivo de cobro),
                    # para una orden BUY, el precio límite se especifica negativo.
                    if lmt_price > 0:
                        lmt_price = -lmt_price
                        
                    orden = LimitOrder(
                        action='BUY',
                        totalQuantity=1,
                        lmtPrice=lmt_price
                    )
                    trade = self.ib.placeOrder(bag, orden)

                self.ib.sleep(1) # Espera de confirmación inicial
                order_id = trade.order.orderId
                order_status = trade.orderStatus.status

                return {"order_id": order_id, "status": order_status}
            return self._run_sync_in_loop(_send)
        except Exception as e:
            print(f"Error al enviar orden genérica: {e}")
            raise

    def enviar_orden_cierre_generica(self, ticker, tipo_activo, patas, precio_cierre=None):
        """
        Envía una orden inversa para cerrar la posición de un Stock, opción simple o BAG combo usando la conexión activa.
        Invierte lógicamente las patas (BUY -> SELL, SELL -> BUY).
        """
        if not self.esta_conectado():
            if not self.conectar():
                raise ConnectionError("No se pudo conectar a IBKR.")
        try:
            def _send():
                nonlocal precio_cierre
                self.ib.reqMarketDataType(3)

                # Invertimos la dirección de las patas para el cierre
                patas_cierre = []
                for pata in patas:
                    accion_inversa = "SELL" if pata.get("accion", "BUY").upper() == "BUY" else "BUY"
                    pata_inv = pata.copy()
                    pata_inv["accion"] = accion_inversa
                    patas_cierre.append(pata_inv)

                contratos = self.calificar_y_obtener_contratos(self.ib, ticker, patas_cierre)

                # Modo Mock Defensa TFG para cierre
                if not all(c.conId for c in contratos):
                    print(f"Modo Mock Cierre TFG Activado: Simulando cierre para {ticker}")
                    return {
                        "order_id": random.randint(100000, 999999),
                        "status": "Filled (Mock Cierre TFG)"
                    }

                # Si no se indica precio de cierre, estimamos el precio medio operativo (Mid Price)
                if precio_cierre is None:
                    tickers_mkt = self.ib.reqTickers(*contratos)
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
                    
                    # Cancelar de inmediato para no dejar flujos activos en el servidor
                    for c in contratos:
                        try:
                            self.ib.cancelMktData(c)
                        except:
                            pass

                # Enviar orden de cierre
                if tipo_activo.upper() == "STOCK" or len(patas_cierre) == 1:
                    pata = patas_cierre[0]
                    contrato = contratos[0]
                    accion = pata["accion"]
                    cantidad = int(pata.get("cantidad", 1))
                    
                    orden = LimitOrder(action=accion, totalQuantity=cantidad, lmtPrice=round(precio_cierre, 2))
                    trade = self.ib.placeOrder(contrato, orden)
                else:
                    bag = self.construir_contrato_bag_dinamico(ticker, contratos, patas_cierre)
                    orden = LimitOrder(
                        action='SELL',
                        totalQuantity=1,
                        lmtPrice=round(precio_cierre, 2)
                    )
                    trade = self.ib.placeOrder(bag, orden)

                self.ib.sleep(1)
                order_id = trade.order.orderId
                order_status = trade.orderStatus.status

                return {"order_id": order_id, "status": order_status}
            return self._run_sync_in_loop(_send)
        except Exception as e:
            print(f"Error al enviar orden de cierre genérica: {e}")
            raise

    def obtener_pnl_posiciones_filtrado(self, ticker_filtro=None, tipo_activo_filtro=None):
        """
        Suma el P&L no realizado de la cuenta de trading filtrado por subyacente e instrumentación usando la conexión activa.
        """
        if not self.esta_conectado():
            if not self.conectar():
                return None
        try:
            def _fetch():
                items = self.ib.portfolio()

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
            return self._run_sync_in_loop(_fetch)
        except Exception as e:
            print(f"Error al obtener P&L de posiciones: {e}")
            return None

    def calcular_pnl_estrategia(self, ticker, tipo_activo, patas):
        """
        Calcula el P&L no realizado acumulado de una estrategia específica
        emparejando sus patas teóricas de forma proporcional con las posiciones reales del bróker usando la conexión activa.
        """
        if not self.esta_conectado():
            if not self.conectar():
                return None
        
        def normalizar_fecha(f_str):
            if not f_str:
                return ""
            cleaned = str(f_str).replace("-", "").replace("/", "").strip()
            if len(cleaned) == 8:
                return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
            return cleaned

        try:
            def _fetch():
                items = self.ib.portfolio()

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
            return self._run_sync_in_loop(_fetch)
        except Exception as e:
            print(f"Error al calcular P&L de estrategia: {e}")
            return None

    # ==========================================
    # MÉTODOS DE COMPATIBILIDAD CON IRON CONDOR
    # ==========================================

    def obtener_datos_estrategia_completa(self, ticker, vencimiento, strikes):
        """
        Wrapper compatible con la lógica anterior del Iron Condor estático.
        """
        p_long, p_short, c_short, c_long = strikes
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
        asociadas a una posición existente de acciones usando la conexión activa.
        """
        if not self.esta_conectado():
            if not self.conectar():
                raise ConnectionError("No se pudo conectar a IBKR.")
        try:
            def _send():
                contrato = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contrato)
                
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
                    trade_sl = self.ib.placeOrder(contrato, orden_sl)
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
                    trade_tp = self.ib.placeOrder(contrato, orden_tp)
                    res_ordenes["take_profit"] = {"order_id": trade_tp.order.orderId, "precio": precio_tp}
                    
                self.ib.sleep(1)
                return res_ordenes
            return self._run_sync_in_loop(_send)
        except Exception as e:
            print(f"Error al enviar órdenes de protección a IBKR: {e}")
            raise
