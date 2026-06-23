import asyncio
from ib_insync import IB, Stock

async def main():
    ib = IB()
    def onError(reqId, errorCode, errorString, contract):
        print(f"TWS ERROR - reqId {reqId}, Code {errorCode}: {errorString}")
        
    ib.errorEvent += onError
    
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=130)
        contrato = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato)
        
        # Habilitar datos retardados (Delayed)
        ib.reqMarketDataType(3)
        
        print("Solicitando ticker...")
        tickers = await ib.reqTickersAsync(contrato)
        if tickers:
            t = tickers[0]
            print("Ticker obtenido:")
            print(f" - Last: {t.last}")
            print(f" - Close: {t.close}")
            print(f" - Bid: {t.bid}")
            print(f" - Ask: {t.ask}")
            print(f" - Market Price: {t.marketPrice()}")
            
            # Cancelar la suscripción de mercado para evitar acumular streams en el servidor
            print("Cancelando suscripción de mercado...")
            ib.cancelMktData(contrato)
        else:
            print("No se pudo obtener el ticker.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()
        print("Desconectado.")

if __name__ == '__main__':
    asyncio.run(main())
