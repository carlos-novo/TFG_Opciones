import asyncio
from ib_insync import IB

async def main():
    ib = IB()
    try:
        # Intentamos conectar a TWS / Gateway en el puerto default de la app (4002)
        await ib.connectAsync('127.0.0.1', 4002, clientId=99)
        print("Conectado con éxito a IBKR.")
        portfolio = ib.portfolio()
        print(f"Número de posiciones en cartera: {len(portfolio)}")
        for item in portfolio:
            c = item.contract
            print(f"Contrato: {c.symbol} ({c.secType}), Posicion: {item.position}, Precio Medio: {item.averageCost}, Precio Mercado: {item.marketPrice}, Valor Mercado: {item.marketValue}, P&L No Realizado: {item.unrealizedPNL}")
        
        # También consultamos los detalles de la cuenta
        summary = ib.accountSummary()
        for item in summary:
            if item.tag in ['NetLiquidation', 'DailyPnL', 'BuyingPower']:
                print(f"Cuenta - {item.tag}: {item.value}")
    except Exception as e:
        print(f"Error al conectar o consultar: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
