import asyncio
from ib_insync import IB, Stock

async def main():
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=120)
        contrato = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato)
        
        for mkt_type in [1, 2, 3, 4]:
            print(f"\n--- Probando MarketDataType {mkt_type} ---")
            ib.reqMarketDataType(mkt_type)
            
            # Solicitar ticker
            tickers = await ib.reqTickersAsync(contrato)
            if tickers:
                t = tickers[0]
                print(f"  Ticker Object: {t}")
                print(f"  dict: {t.__dict__}")
                print(f"  marketPrice(): {t.marketPrice()}")
            else:
                print("  No se obtuvo ticker.")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
