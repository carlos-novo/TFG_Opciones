import asyncio
from ib_insync import IB, Option

async def main():
    ib = IB()
    try:
        print("Intentando conectar a IBKR Gateway/TWS en 127.0.0.1:4002 con clientId=99...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=99)
        print("Conectado con éxito.")
        
        # Las 4 patas de la estrategia #224
        ticker = 'SPY'
        vencimiento = '20260619' # Hoy, 19 de Junio de 2026
        
        patas = [
            Option(ticker, vencimiento, 715.0, 'P', 'SMART', currency='USD'),
            Option(ticker, vencimiento, 720.0, 'P', 'SMART', currency='USD'),
            Option(ticker, vencimiento, 775.0, 'C', 'SMART', currency='USD'),
            Option(ticker, vencimiento, 780.0, 'C', 'SMART', currency='USD'),
        ]
        
        print("\nCualificando contratos...")
        qualified = await ib.qualifyContractsAsync(*patas)
        
        print(f"\nResultado de la cualificación (se obtuvieron {len(qualified)} contratos):")
        for i, c in enumerate(patas):
            print(f"Pata {i+1}: Strike {c.strike} | Right {c.right} | conId = {c.conId}")
            if not c.conId:
                print(f"  ❌ ERROR: El contrato {c.symbol} {c.right}{c.strike} expiring {c.lastTradeDateOrContractMonth} no pudo cualificarse.")
                
    except Exception as e:
        print(f"\n❌ Error durante la ejecución: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\nDesconectado de IBKR.")

if __name__ == "__main__":
    asyncio.run(main())
