import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from conexion_ibkr import GestorIBKR

async def main():
    # Inicializar el gestor con un ID de cliente de prueba
    gestor = GestorIBKR(client_id=140)
    
    try:
        print("Intentando conectar...")
        if gestor.conectar():
            print("Conectado. Consultando precio para TSLA (En Cartera)...")
            p_tsla = gestor.obtener_precio_prueba("TSLA")
            print(f"Resultado TSLA: {p_tsla}")
            
            print("\nConsultando precio para SPY (Fuera de Cartera)...")
            p_spy = gestor.obtener_precio_prueba("SPY")
            print(f"Resultado SPY: {p_spy}")
        else:
            print("No se pudo conectar a IBKR.")
    except Exception as e:
        print(f"Error durante la prueba: {e}")
    finally:
        print("Desconectando gestor...")
        gestor.desconectar()

if __name__ == '__main__':
    asyncio.run(main())
