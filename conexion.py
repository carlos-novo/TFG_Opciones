from ib_insync import *

ib = IB()

print("Conectando a TWS (Puerto 7497)...")

try:
    ib.connect('127.0.0.1', 7497, clientId=1)
    print("¡CONEXION EXITOSA! 🚀")
    
    # 1. Definimos qué queremos buscar (Acciones de SPY)
    contrato = Stock('SPY', 'SMART', 'USD')
    
    # 2. Le pedimos a IBKR que valide si ese producto existe
    ib.qualifyContracts(contrato)
    print("Contrato encontrado:", contrato.symbol)
    
    # MAGIA PARA CUENTAS GRATUITAS: Cambiamos el tipo de datos de mercado a retrasados
    ib.reqMarketDataType(3)  # 3 = Delayed-Frozen, para datos de mercado retrasados
    print("Cambiando a datos de mercado retrasados (Delayed-Frozen)...")

    # 3. Solicitamos los datos del mercado
    datos = ib.reqMktData(contrato, '', False, False)
    
    # 4. Esperamos 2 segundos para que el servidor nos mande la info
    print("Esperando a que lleguen los precios...")
    ib.sleep(2)
    
    # 5. Mostramos el resultado
    print("-" * 30)
    print("Precio de mercado:", datos.marketPrice())
    print("Mejor comprador (Bid):", datos.bid)
    print("Mejor vendedor (Ask):", datos.ask)
    print("-" * 30)

except Exception as e:
    print("Ocurrió un error:", e)

finally:
    if ib.isConnected():
        ib.disconnect()
        print("Desconectado de TWS de forma segura.")