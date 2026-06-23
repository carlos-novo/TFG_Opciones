import asyncio
from ib_insync import IB, Stock, Index

async def main():
    ib = IB()
    def onError(reqId, errorCode, errorString, contract):
        print(f"TWS ERROR - Code {errorCode}: {errorString}")
        
    ib.errorEvent += onError
    
    try:
        print("Conectando con clientId=1 (para pisar la conexión de la UI)...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=1)
        print("¡Conectado!")
        
        ib.reqMarketDataType(3)  # Delayed
        
        for ticker in ['SPY', 'SPX', 'TSLA']:
            print(f"\n=== PROBANDO {ticker} ===")
            if ticker in ('SPX', 'VIX'):
                contrato = Index(ticker, 'CBOE', 'USD')
            else:
                contrato = Stock(ticker, 'SMART', 'USD')
                
            await ib.qualifyContractsAsync(contrato)
            
            # Tickers
            print("Pidiendo ticker...")
            tickers = await ib.reqTickersAsync(contrato)
            if tickers:
                t = tickers[0]
                print(f"Ticker {ticker} -> Last: {t.last}, Close: {t.close}, MarketPrice: {t.marketPrice()}, Bid: {t.bid}, Ask: {t.ask}")
                ib.cancelMktData(contrato)
            
            # Histórico
            print("Pidiendo histórico (5 D, 1 day, TRADES)...")
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
                print(f"Histórico {ticker} (TRADES) -> {len(barras)} barras")
                if barras:
                    print(f"  Último cierre: {barras[-1].close}")
            except Exception as e:
                print(f"Error histórico TRADES para {ticker}: {e}")
                
            # Histórico MIDPOINT
            print("Pidiendo histórico (5 D, 1 day, MIDPOINT)...")
            try:
                task = ib.reqHistoricalDataAsync(
                    contrato,
                    endDateTime='',
                    durationStr='5 D',
                    barSizeSetting='1 day',
                    whatToShow='MIDPOINT',
                    useRTH=True,
                    formatDate=1
                )
                barras = await asyncio.wait_for(task, timeout=5.0)
                print(f"Histórico {ticker} (MIDPOINT) -> {len(barras)} barras")
                if barras:
                    print(f"  Último cierre: {barras[-1].close}")
            except Exception as e:
                print(f"Error histórico MIDPOINT para {ticker}: {e}")
                
    except Exception as e:
        print(f"Error general: {e}")
    finally:
        ib.disconnect()
        print("Desconectado.")

if __name__ == '__main__':
    asyncio.run(main())
