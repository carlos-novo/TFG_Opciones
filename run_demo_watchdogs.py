import time
import os
import sys
from unittest.mock import patch
from datetime import datetime

# Asegurar importación de nuestros módulos locales
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from base_datos import GestorBaseDatos
from conexion_ibkr import GestorIBKR
import watchdogs

# Variable global para simular P&L creciente en la demo
simulated_pnl = -100.0

def mock_pnl_positions(self, ticker_filtro=None, tipo_activo_filtro=None):
    """Función mock para simular P&L irrealizado que sube en cada ciclo."""
    global simulated_pnl
    simulated_pnl += 150.0  # Sube 150$ cada 15 segundos
    print(f"[DEMO SIMULACIÓN] Consultando P&L para {ticker_filtro} ({tipo_activo_filtro}). P&L Simulado actual: {simulated_pnl}$")
    return simulated_pnl

def main():
    print("================================================================")
    # 1. Limpiar base de datos para la demo
    print("[1] Inicializando base de datos limpia para la demostración...")
    db = GestorBaseDatos(reset_db=True)
    
    # 2. Insertar estrategia de prueba en estado 'PENDIENTE_ENTRADA'
    print("[2] Insertando estrategia de prueba (AAPL, Stock) en cola...")
    patas = [{"accion": "BUY", "cantidad": 10, "tipo_activo": "STOCK"}]
    condiciones_entrada = {
        "horario": {"hora_inicio": "00:00", "hora_fin": "23:59", "activo": True},
        "vix": {"activo": False},
        "sma": {"activo": False}
    }
    condiciones_salida = {
        "take_profit": 300.0,  # TP a +300$
        "stop_loss": -200.0   # SL a -200$
    }
    
    est_id = db.crear_estrategia(
        ticker="AAPL",
        tipo_activo="STOCK",
        estado="PENDIENTE_ENTRADA",
        patas=patas,
        condiciones_entrada=condiciones_entrada,
        condiciones_salida=condiciones_salida
    )
    db.actualizar_estado_estrategia(est_id, "PENDIENTE_ENTRADA", precio_entrada=180.00)
    print(f"    Estrategia creada con ID: {est_id}")
    
    # 3. Lanzar Watchdogs interceptando P&L e IBKR con Mocks para modo Offline
    print("[3] Lanzando los hilos daemon de los Watchdogs en modo offline...")
    patchers = [
        patch('conexion_ibkr.GestorIBKR.conectar', return_value=True),
        patch('conexion_ibkr.GestorIBKR.desconectar', return_value=None),
        patch('conexion_ibkr.GestorIBKR.obtener_precio_prueba', return_value=180.50),
        patch('conexion_ibkr.GestorIBKR.enviar_orden_generica', return_value={"order_id": 12345, "status": "Submitted (Mock)"}),
        patch('conexion_ibkr.GestorIBKR.enviar_orden_cierre_generica', return_value={"order_id": 67890, "status": "Filled (Mock)"}),
        patch('conexion_ibkr.GestorIBKR.obtener_pnl_posiciones_filtrado', mock_pnl_positions)
    ]
    for p in patchers:
        p.start()
    
    # Iniciamos los watchdogs locales con ciclos rápidos para la demo (Vix/SMA desactivado)
    h_entradas = watchdogs.iniciar_watchdog_entradas(interval=5) # 5s
    h_salidas = watchdogs.iniciar_watchdog_salidas(interval=5)   # 5s
    
    print("\n>>> DEMO INICIADA. Observa el flujo de consola. Se detendrá al cerrarse la estrategia.")
    print("================================================================\n")
    
    # 4. Esperar a que la estrategia complete su ciclo de vida
    ciclos = 0
    try:
        while ciclos < 20:
            time.sleep(3)
            # Consultamos la BD para ver el estado actual de la estrategia
            est = db.obtener_estrategia(est_id)
            if est:
                estado_actual = est["estado"]
                print(f"--> [BD CHECK] Estado actual de la estrategia en base de datos: '{estado_actual}'")
                
                if estado_actual.startswith("CERRADA"):
                    print(f"\n================================================================")
                    print(f"🎉 ÉXITO: La estrategia ha sido CERRADA automáticamente por el Watchdog.")
                    print(f"Detalles finales en BD:")
                    print(f" - Estado: {est['estado']}")
                    print(f" - OrderID Entrada: {est['order_id_entrada']}")
                    print(f" - OrderID Salida: {est['order_id_salida']}")
                    print(f" - P&L Realizado: {est['pnl_realizado']}$")
                    print(f"================================================================")
                    break
            ciclos += 1
    except KeyboardInterrupt:
        print("\nDemo interrumpida por el usuario.")
    finally:
        # Detener hilos y parches
        watchdogs.detener_watchdogs()
        for p in patchers:
            p.stop()
        print("\n[5] Watchdogs detenidos y recursos liberados.")

if __name__ == "__main__":
    main()
