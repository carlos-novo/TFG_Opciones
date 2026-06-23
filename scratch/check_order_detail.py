import asyncio
from ib_insync import IB

async def main():
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 4002, clientId=145)
        print("Conectado con éxito a IBKR.")
        
        # Consultar todas las órdenes
        print("\n--- Buscando orden #639 ---")
        orders = ib.orders()
        found = False
        for o in orders:
            if o.orderId == 639:
                print(f"Encontrada en orders(): {o}")
                found = True
        
        trades = ib.trades()
        for t in trades:
            if t.order.orderId == 639:
                print(f"Encontrada en trades(): {t}")
                found = True
                
        # También podemos pedir todas las órdenes del día
        all_orders = ib.reqAllOpenOrders()
        for t in all_orders:
            if t.order.orderId == 639:
                print(f"Encontrada en reqAllOpenOrders(): {t}")
                found = True
                
        if not found:
            print("No se encontró la orden 639 en la sesión de TWS/Gateway.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
