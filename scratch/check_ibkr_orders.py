import asyncio
from ib_insync import IB

async def main():
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=141)
        print("Conectado con éxito a IBKR.")
        
        print("\n--- ÓRDENES ABIERTAS (Open Trades) ---")
        trades = ib.openTrades()
        print(f"Número de órdenes abiertas: {len(trades)}")
        for t in trades:
            print(f"OrderID: {t.order.orderId}, Contrato: {t.contract.localSymbol} ({t.contract.secType}), Acción: {t.order.action}, Cantidad: {t.order.totalQuantity}, Tipo: {t.order.orderType}, LimitPrice: {t.order.lmtPrice}, Estado: {t.orderStatus.status}")
            
        print("\n--- ÓRDENES COMPLETADAS / LLENAS ---")
        completed = ib.trades()
        print(f"Número total de trades en sesión: {len(completed)}")
        for t in completed:
            if t.orderStatus.status == 'Filled':
                print(f"OrderID: {t.order.orderId}, Contrato: {t.contract.localSymbol} ({t.contract.secType}), Acción: {t.order.action}, Cantidad: {t.order.totalQuantity}, Estado: {t.orderStatus.status}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
