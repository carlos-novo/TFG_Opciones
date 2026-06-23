import asyncio
from ib_insync import IB, Stock

async def test_query(what_to_show):
    ib = IB()
    try:
        print(f"\n--- Probando con whatToShow='{what_to_show}' ---")
        await ib.connectAsync('127.0.0.1', 4002, clientId=96)
        contrato = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato)
        ib.reqMarketDataType(3)  # Delayed
        
        task = ib.reqHistoricalDataAsync(
            contrato,
            endDateTime='',
            durationStr='5 D',
            barSizeSetting='1 day',
            whatToShow=what_to_show,
            useRTH=True,
            formatDate=1
        )
        barras = await asyncio.wait_for(task, timeout=8.0)
        print(f"¡Éxito! Se obtuvieron {len(barras)} barras.")
        return True
    except asyncio.TimeoutError:
        print(f"TIMEOUT con '{what_to_show}'")
        return False
    except Exception as e:
        print(f"ERROR con '{what_to_show}': {e}")
        return False
    finally:
        ib.disconnect()

async def main():
    # Probar TRADES primero, luego DELAYED_TRADES
    await test_query('TRADES')
    await test_query('DELAYED_TRADES')
    await test_query('MIDPOINT')

if __name__ == '__main__':
    asyncio.run(main())
