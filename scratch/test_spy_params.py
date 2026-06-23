import asyncio
from ib_insync import IB, Stock

async def test_param(use_rth, duration, bar_size, what_to_show):
    ib = IB()
    try:
        print(f"\n--- Probando useRTH={use_rth}, duration={duration}, bar_size={bar_size}, whatToShow={what_to_show} ---")
        await ib.connectAsync('127.0.0.1', 4002, clientId=97)
        contrato = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato)
        ib.reqMarketDataType(3)  # Delayed
        
        task = ib.reqHistoricalDataAsync(
            contrato,
            endDateTime='',
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1
        )
        barras = await asyncio.wait_for(task, timeout=5.0)
        print(f"¡Éxito! Se obtuvieron {len(barras)} barras.")
        return True
    except asyncio.TimeoutError:
        print("TIMEOUT")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        ib.disconnect()

async def main():
    # Probar diferentes combinaciones
    await test_param(use_rth=False, duration='5 D', bar_size='1 day', what_to_show='TRADES')
    await test_param(use_rth=True, duration='1 D', bar_size='1 hour', what_to_show='TRADES')
    await test_param(use_rth=False, duration='1 D', bar_size='1 hour', what_to_show='TRADES')
    await test_param(use_rth=True, duration='5 D', bar_size='1 day', what_to_show='MIDPOINT')
    await test_param(use_rth=False, duration='5 D', bar_size='1 day', what_to_show='MIDPOINT')

if __name__ == '__main__':
    asyncio.run(main())
