from ib_insync import *

ib = IB()
print("Conectando a TWS (Puerto 7497)...")

try:
    ib.connect('127.0.0.1', 7497, clientId=1)
    print("¡CONEXION EXITOSA! 🚀")
    
    # Activamos los datos en diferido por ser cuenta de simulación
    ib.reqMarketDataType(3)
    
    # 1. Construimos el contrato de la Opción (¡El corazón de tu TFG!)
    print("Configurando Opción CALL 0DTE para el SPY...")
    contrato_opcion = Option('SPY', '20260220', 684, 'C', 'SMART', tradingClass='SPY')
    
    # 2. Validamos que este contrato existe realmente en el mercado
    ib.qualifyContracts(contrato_opcion)
    print("¡Contrato validado! ID en IBKR:", contrato_opcion.conId)
    
    # 3. Pedimos los datos (La prima / precio de la opción)
    datos_opcion = ib.reqMktData(contrato_opcion, '', False, False)
    
    print("Esperando datos de la prima...")
    ib.sleep(2)
    
    # 4. Mostramos los resultados
    print("-" * 30)
    print("TIPO DE CONTRATO:", contrato_opcion.symbol, contrato_opcion.right, contrato_opcion.strike)
    print("Último precio (Prima):", datos_opcion.close)
    print("Mejor comprador (Bid):", datos_opcion.bid)
    print("Mejor vendedor (Ask):", datos_opcion.ask)
    print("-" * 30)

except Exception as e:
    print("Ocurrió un error:", e)

finally:
    if ib.isConnected():
        ib.disconnect()
        print("Desconectado de TWS de forma segura.")