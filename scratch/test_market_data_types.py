import asyncio
from ib_insync import IB, Stock

async def test_type(mkt_data_type):
    ib = IB()
    errors = []
    def onError(reqId, errorCode, errorString, contract):
        errors.append(f"TWS ERROR - Code {errorCode}: {errorString}")
        
    ib.errorEvent += onError
    
    try:
        print(f"\n=========================================")
        print(f"PROBANDO MARKET DATA TYPE: {mkt_data_type}")
        print(f"=========================================")
        await ib.connectAsync('127.0.0.1', 4002, clientId=101 + mkt_data_type)
        ib.reqMarketDataType(mkt_data_type)
        
        contrato = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato)
        
        # 1. Ticker
        print("Solicitando ticker...")
        tickers = await ib.reqTickersAsync(contrato)
        if tickers:
            t = tickers[0]
            print(f"Ticker SPY -> Last: {t.last}, Close: {t.close}, MarketPrice: {t.marketPrice()}")
        else:
            print("Ticker SPY -> No devuelto")
            
        # 2. Historical
        print("Solicitando historical (5 D, 1 day)...")
        try:
            task = ib.reqHistoricalDataAsync(
                contrato,
                endDateTime='',
                durationStr='5 D',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            barras = await asyncio.wait_for(task, timeout=5.0)
            print(f"Historical SPY -> Éxito, {len(barras)} barras")
        except asyncio.TimeoutError:
            print("Historical SPY -> TIMEOUT")
            
        print(f"Errores reportados para tipo {mkt_data_type}:")
        for err in errors:
            print(f"  - {err}")
            
    except Exception as e:
        print(f"Error en prueba: {e}")
    finally:
        ib.disconnect()

async def main():
    for t in [1, 2, 3, 4]:
        await test_type(t)

if __name__ == '__main__':
    asyncio.run(main())
