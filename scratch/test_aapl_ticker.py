import asyncio
from ib_insync import IB, Stock

async def main():
    ib = IB()
    try:
        print("Intentando conectar a IBKR...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=87)
        print("Conectado con éxito a IBKR.")
        
        # Probar AAPL (que está en cartera)
        contrato_aapl = Stock('AAPL', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato_aapl)
        
        # Probar SPY (que NO está en cartera)
        contrato_spy = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato_spy)
        
        # Configurar tipo de datos a 3 (Delayed)
        ib.reqMarketDataType(3)
        
        print("\n--- Consultando ticker de AAPL (En Cartera) ---")
        tickers_aapl = await ib.reqTickersAsync(contrato_aapl)
        if tickers_aapl:
            t = tickers_aapl[0]
            print(f"AAPL - Last: {t.last}, Close: {t.close}, MarketPrice: {t.marketPrice()}")
            
        print("\n--- Consultando ticker de SPY (Fuera de Cartera) ---")
        tickers_spy = await ib.reqTickersAsync(contrato_spy)
        if tickers_spy:
            t = tickers_spy[0]
            print(f"SPY - Last: {t.last}, Close: {t.close}, MarketPrice: {t.marketPrice()}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
