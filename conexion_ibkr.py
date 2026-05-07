import nest_asyncio
nest_asyncio.apply() # Magia pura para evitar bloqueos entre Streamlit y asyncio

import asyncio

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
from ib_insync import IB, Stock, Index, Contract, ComboLeg, LimitOrder, Option

import random

class GestorIBKR:
    """
    Clase que actúa como capa intermedia entre el sistema y la API de Interactive Brokers.
    Gestiona la conexión, desconexión y la obtención de datos de mercado.
    """
    def __init__(self, host='127.0.0.1', port=4002, client_id=1):
        self.host = host
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
            # ib.accountSummary() devuelve una lista de objetos AccountValue
            resumen = self.ib.accountSummary()
            
            # Filtramos solo los datos que nos interesan para la interfaz
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
        
        # Instanciamos un cliente temporal con un clientId distinto (ej. 99)
        # Esto asegura que opere en el bucle de eventos de este botón en concreto.
        ib_temp = IB()
        try:
            # Nos conectamos, pedimos el dato al Gateway y preparamos la huida
            ib_temp.connect(self.host, self.port, clientId=99)
            
            # REGLA DE ORO: SPX es un índice, el resto son Stocks
            if simbolo.upper() == 'SPX':
                contrato = Index(simbolo, 'CBOE', 'USD')
            else:
                contrato = Stock(simbolo, 'SMART', 'USD')
            ib_temp.qualifyContracts(contrato)
            
            barras = ib_temp.reqHistoricalData(
                contrato,
                endDateTime='',
                durationStr='1 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=False, 
                formatDate=1
            )
            
            # Misión cumplida: nos desconectamos antes de devolver el dato
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

    def obtener_datos_estrategia_completa(self, ticker, vencimiento, strikes):
        """
        Micro-sesión de alto rendimiento: Abre una sola conexión y recupera
        los 4 contratos del Iron Condor de una sola vez.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=96)
            ib_temp.reqMarketDataType(3)
            
            # 1. Definimos los 4 contratos
            p_long, p_short, c_short, c_long = strikes
            fecha_str = vencimiento.strftime('%Y%m%d') if hasattr(vencimiento, 'strftime') else vencimiento
            
            contratos = [
                Option(ticker, fecha_str, p_long, 'P', 'SMART', currency='USD'),
                Option(ticker, fecha_str, p_short, 'P', 'SMART', currency='USD'),
                Option(ticker, fecha_str, c_short, 'C', 'SMART', currency='USD'),
                Option(ticker, fecha_str, c_long, 'C', 'SMART', currency='USD')
            ]
            
            # 2. Calificamos todos de golpe (Batch qualifying)
            ib_temp.qualifyContracts(*contratos)
            
            # 3. Solicitamos tickers (Batch snapshot)
            tickers = ib_temp.reqTickers(*contratos)
            
            # 4. Fallback: Si el mercado está cerrado y el Bid/Ask es 0, intentamos 
            # usar el precio de cierre (close) como última referencia válida.
            resultados = []
            for t in tickers:
                bid = t.bid if (t.bid and t.bid > 0) else t.close
                ask = t.ask if (t.ask and t.ask > 0) else t.close
                resultados.append({"bid": bid if bid else 0.0, "ask": ask if ask else 0.0})
            
            ib_temp.disconnect()
            return resultados # Devuelve lista con [P_Long, P_Short, C_Short, C_Long]
            
        except Exception as e:
            print(f"Error en sesión bulk: {e}")
            if ib_temp.isConnected(): ib_temp.disconnect()
            return [{"bid": 0.0, "ask": 0.0}] * 4

    def obtener_historico_diario(self, simbolo, dias):
        """
        Micro-sesión (Stateless): Descarga el histórico de precios de cierre diarios.
        Esencial para el cálculo de indicadores de Análisis Técnico (AT).
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        
        try:
            # Usamos un clientId distinto (ej. 97) para el flujo de histórico
            ib_temp.connect(self.host, self.port, clientId=97)
            
            # REGLA DE ORO: SPX es un índice, el resto son Stocks
            if simbolo.upper() == 'SPX':
                contrato = Index(simbolo, 'CBOE', 'USD')
            else:
                contrato = Stock(simbolo, 'SMART', 'USD')
            ib_temp.qualifyContracts(contrato)
            
            # Formateamos la duración. IBKR acepta 'D' (días). 
            # Pedimos los días exactos en horario regular (useRTH=True) para evitar ruido.
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
            
            # Extraemos únicamente los precios de cierre
            if barras:
                return [barra.close for barra in barras]
            return []
            
        except Exception as e:
            print(f"Error al descargar histórico para AT: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            return []

    def construir_contrato_bag(self, ticker, contratos_calificados):
        """
        Ensambla un contrato de tipo BAG (Combo) a partir de los 4 contratos
        ya calificados (con conId asignado por IBKR).

        Orden y dirección de las patas del Iron Condor:
          [0] Long Put   → BUY  (protección inferior, pagamos prima)
          [1] Short Put  → SELL (ingreso inferior, recibimos prima)
          [2] Short Call → SELL (ingreso superior, recibimos prima)
          [3] Long Call  → BUY  (protección superior, pagamos prima)
        Resultado neto: CRÉDITO (recibimos más de lo que pagamos).
        """
        acciones = ['BUY', 'SELL', 'SELL', 'BUY']
        patas = []
        for contrato, accion in zip(contratos_calificados, acciones):
            pata = ComboLeg()
            pata.conId    = contrato.conId
            pata.ratio    = 1
            pata.action   = accion
            pata.exchange = 'SMART'
            patas.append(pata)

        bag = Contract()
        bag.symbol    = ticker
        bag.secType   = 'BAG'
        bag.currency  = 'USD'
        bag.exchange  = 'SMART'
        bag.comboLegs = patas
        return bag

    def enviar_orden_iron_condor(self, ticker, vencimiento, strikes, credito_objetivo):
        """
        Micro-sesión de envío atómico del Iron Condor como orden BAG.

        Construye los 4 contratos, ensambla el BAG y transmite una LimitOrder
        con precio NEGATIVO (convención IBKR para combos a crédito en dirección BUY):
          lmtPrice = -credito_objetivo
          Ejemplo: credito = 5.20 → lmtPrice = -5.20 (recibimos $520 por contrato).

        Retorna: dict con order_id y status inicial de la orden.
        """
        self._asegurar_event_loop()
        ib_temp = IB()
        try:
            ib_temp.connect(self.host, self.port, clientId=95)
            ib_temp.reqMarketDataType(3)

            p_long, p_short, c_short, c_long = strikes
            fecha_str = (
                vencimiento.strftime('%Y%m%d')
                if hasattr(vencimiento, 'strftime')
                else str(vencimiento).replace('-', '')
            )

            # 1. Definir y calificar los 4 contratos
            contratos = [
                Option(ticker, fecha_str, p_long,  'P', 'SMART', currency='USD'),
                Option(ticker, fecha_str, p_short, 'P', 'SMART', currency='USD'),
                Option(ticker, fecha_str, c_short, 'C', 'SMART', currency='USD'),
                Option(ticker, fecha_str, c_long,  'C', 'SMART', currency='USD'),
            ]
            ib_temp.qualifyContracts(*contratos)

            # Verificación de integridad: todos deben tener conId
            for c in contratos:
                if not c.conId:
                    raise ValueError(
                        f"Contrato no calificado: {c.strike}{c.right} "
                        f"— El strike no existe para el vencimiento {fecha_str}."
                    )

            # 2. Ensamblar el contrato BAG
            bag = self.construir_contrato_bag(ticker, contratos)

            # 3. LimitOrder a crédito neto (precio negativo = recibimos dinero)
            orden = LimitOrder(
                action        = 'BUY',
                totalQuantity = 1,
                lmtPrice      = round(-credito_objetivo, 2)
            )

            # 4. Transmitir al Gateway
            trade        = ib_temp.placeOrder(bag, orden)
            ib_temp.sleep(1)  # Pausa para que el Gateway emita el ACK inicial
            order_id     = trade.order.orderId
            order_status = trade.orderStatus.status

            ib_temp.disconnect()
            return {"order_id": order_id, "status": order_status}

        except Exception as e:
            print(f"Error al enviar orden Iron Condor BAG: {e}")
            if ib_temp.isConnected():
                ib_temp.disconnect()
            raise  # Re-lanzamos para que la UI muestre el mensaje