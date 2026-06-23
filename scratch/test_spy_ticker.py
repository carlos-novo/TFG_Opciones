import asyncio
from ib_insync import IB, Stock

async def main():
    ib = IB()
    try:
        print("Intentando conectar a IBKR...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=98)
        print("Conectado con éxito a IBKR.")
        
        contrato = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato)
        print(f"Contrato cualificado: {contrato}")
        
        # Configurar tipo de datos a 3 (Delayed)
        ib.reqMarketDataType(3)
        print("Solicitando ticker de SPY vía reqTickers...")
        
        # reqTickers es asíncrono y devuelve los datos actuales de mercado inmediatamente
        tickers = await ib.reqTickersAsync(contrato)
        if tickers:
            ticker = tickers[0]
            print(f"Éxito al obtener Ticker:")
            print(f" - Last: {ticker.last}")
            print(f" - Close: {ticker.close}")
            print(f" - Bid: {ticker.bid}")
            print(f" - Ask: {ticker.ask}")
            print(f" - Market Price: {ticker.marketPrice()}")
        else:
            print("No se obtuvieron tickers.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
