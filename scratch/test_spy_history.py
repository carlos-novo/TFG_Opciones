import asyncio
from ib_insync import IB, Stock

async def main():
    ib = IB()
    
    # Registrar manejador de eventos de error para ver todos los mensajes detallados de TWS
    def onError(reqId, errorCode, errorString, contract):
        print(f"TWS ERROR - reqId: {reqId}, Code: {errorCode}, Message: {errorString}, Contract: {contract}")
        
    ib.errorEvent += onError

    try:
        print("Intentando conectar a IBKR...")
        await ib.connectAsync('127.0.0.1', 4002, clientId=95)
        print("Conectado con éxito a IBKR.")
        
        # Crear contrato SPY
        contrato = Stock('SPY', 'SMART', 'USD')
        print("Cualificando contrato...")
        res = await ib.qualifyContractsAsync(contrato)
        if not res:
            print("Fallo al cualificar con SMART, intentando NYSE...")
            contrato.primaryExchange = 'NYSE'
            res = await ib.qualifyContractsAsync(contrato)
            
        if not res:
            print("Fallo total al cualificar contrato.")
            return
            
        contrato = res[0]
        print(f"Contrato cualificado: {contrato}")
        
        # Activar datos retrasados
        print("Configurando tipo de datos a 3 (Delayed)...")
        ib.reqMarketDataType(3)
        
        print("Solicitando datos históricos (bars) de SPY...")
        # Intentamos con un timeout de 10 segundos para ver si responde o qué error lanza
        task = ib.reqHistoricalDataAsync(
            contrato,
            endDateTime='',
            durationStr='5 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        
        try:
            barras = await asyncio.wait_for(task, timeout=10.0)
            print(f"¡Éxito! Se obtuvieron {len(barras)} barras.")
            for b in barras:
                print(f"Fecha: {b.date}, Cierre: {b.close}")
        except asyncio.TimeoutError:
            print("TIMEOUT - reqHistoricalDataAsync no respondió en 10 segundos.")
            
    except Exception as e:
        print(f"Excepción en el script: {e}")
    finally:
        print("Desconectando...")
        ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
