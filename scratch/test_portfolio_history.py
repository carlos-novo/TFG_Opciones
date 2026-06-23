import asyncio
from ib_insync import IB, Stock

async def test_historical(ib, contrato, name):
    print(f"\n--- Probando históricos para {name} ---")
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
        barras = await asyncio.wait_for(task, timeout=8.0)
        print(f"¡Éxito para {name}! Se obtuvieron {len(barras)} barras.")
        if barras:
            print(f"Último cierre de {name}: {barras[-1].close}")
    except asyncio.TimeoutError:
        print(f"TIMEOUT para {name}")
    except Exception as e:
        print(f"ERROR para {name}: {e}")

async def main():
    ib = IB()
    def onError(reqId, errorCode, errorString, contract):
        print(f"TWS ERROR - reqId {reqId}, Code {errorCode}: {errorString}")
        
    ib.errorEvent += onError
    
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=125)
        
        contrato_tsla = Stock('TSLA', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato_tsla)
        
        contrato_spy = Stock('SPY', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contrato_spy)
        
        ib.reqMarketDataType(3)  # Delayed
        
        # Probar TSLA
        await test_historical(ib, contrato_tsla, "TSLA (En Cartera)")
        
        # Probar SPY
        await test_historical(ib, contrato_spy, "SPY (Fuera de Cartera)")
        
    except Exception as e:
        print(f"Error general: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
