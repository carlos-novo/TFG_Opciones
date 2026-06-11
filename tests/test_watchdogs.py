import pytest
import threading
from unittest.mock import MagicMock, patch
from watchdogs import watchdog_entradas_worker, watchdog_salidas_worker

@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('time.sleep')
def test_watchdog_entradas_ejecuta_y_lanza_orden(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    # Setup stop event
    stop_event = threading.Event()
    
    # Mock sleep sets stop_event so it only runs one loop iteration
    mock_sleep.side_effect = lambda sec: stop_event.set()
    
    db_instance = mock_db_class.return_value
    ib_instance = mock_ib_class.return_value
    
    # Mock database to return one pending strategy
    strategy_mock = {
        "id": 1,
        "ticker": "AAPL",
        "tipo_activo": "STOCK",
        "estado": "PENDIENTE_ENTRADA",
        "patas": [{"accion": "BUY", "cantidad": 10}],
        "condiciones_entrada": {"horario": {"hora_inicio": "00:00", "hora_fin": "23:59"}},
        "precio_entrada": 180.0
    }
    db_instance.obtener_estrategias.return_value = [strategy_mock]
    
    # Mock market logic and connection
    ib_instance.conectar.return_value = True
    ib_instance.obtener_precio_prueba.return_value = 180.50
    ib_instance.enviar_orden_generica.return_value = {"order_id": 12345, "status": "Submitted"}
    
    # Run the worker once
    watchdog_entradas_worker("dummy.db", 1, stop_event)
    
    # Assertions
    ib_instance.conectar.assert_called_once()
    ib_instance.obtener_precio_prueba.assert_called_with("AAPL")
    
    # Verificamos que se envió la orden con el precio límite correcto
    ib_instance.enviar_orden_generica.assert_called_once_with(
        ticker="AAPL",
        tipo_activo="STOCK",
        patas=[{"accion": "BUY", "cantidad": 10}],
        precio_limite=180.0
    )
    
    # Verificamos que se actualizó el estado a ACTIVA en la BD
    db_instance.actualizar_estado_estrategia.assert_called_once()
    db_args = db_instance.actualizar_estado_estrategia.call_args[1]
    assert db_args["estrategia_id"] == 1
    assert db_args["nuevo_estado"] == "ACTIVA"
    assert db_args["order_id_entrada"] == 12345
    assert db_args["precio_entrada"] == 180.0
    
    # Verificamos que registró el evento y notificó por Discord
    db_instance.registrar_evento.assert_called_with(
        "WATCHDOG_ENTRADA_EJECUTADA",
        "Estrategia ID 1 (AAPL) activada. OrderID: 12345. Estado: Submitted"
    )
    mock_webhook.assert_called_once()
    ib_instance.desconectar.assert_called_once()


@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('time.sleep')
def test_watchdog_salidas_monitorea_y_cierra(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda sec: stop_event.set()
    
    db_instance = mock_db_class.return_value
    ib_instance = mock_ib_class.return_value
    
    # Mock database to return one active option strategy
    strategy_mock = {
        "id": 2,
        "ticker": "SPX",
        "tipo_activo": "OPTION",
        "estado": "ACTIVA",
        "patas": [{"accion": "SELL", "strike": 5000, "right": "P"}],
        "condiciones_salida": {"stop_loss": -200.0, "take_profit": 400.0},
        "precio_entrada": 5.0
    }
    db_instance.obtener_estrategias.return_value = [strategy_mock]
    
    # Mock market metrics: PnL has reached Take Profit
    ib_instance.conectar.return_value = True
    ib_instance.calcular_pnl_estrategia.return_value = 450.0 # Supera TP de 400.0
    ib_instance.enviar_orden_cierre_generica.return_value = {"order_id": 67890, "status": "Filled"}
    
    # Run the worker once
    watchdog_salidas_worker("dummy.db", 1, stop_event)
    
    # Assertions
    ib_instance.conectar.assert_called_once()
    ib_instance.calcular_pnl_estrategia.assert_called_with(
        ticker="SPX",
        tipo_activo="OPTION",
        patas=[{"accion": "SELL", "strike": 5000, "right": "P"}]
    )
    
    # Verificamos que se lanzó el cierre
    ib_instance.enviar_orden_cierre_generica.assert_called_once_with(
        ticker="SPX",
        tipo_activo="OPTION",
        patas=[{"accion": "SELL", "strike": 5000, "right": "P"}]
    )
    
    # Verificamos que el estado pasó a CERRADA_TAKE_PROFIT en la BD
    db_instance.actualizar_estado_estrategia.assert_called_once()
    db_args = db_instance.actualizar_estado_estrategia.call_args[1]
    assert db_args["estrategia_id"] == 2
    assert db_args["nuevo_estado"] == "CERRADA_TAKE_PROFIT"
    assert db_args["order_id_salida"] == 67890
    assert db_args["pnl_realizado"] == 450.0
    
    # Registro y webhook
    db_instance.registrar_evento.assert_called_with(
        "WATCHDOG_SALIDA_EJECUTADA",
        "Estrategia ID 2 (SPX) cerrada por TAKE_PROFIT. OrderID Cierre: 67890. P&L Realizado: 450.0$"
    )
    mock_webhook.assert_called_once()
    ib_instance.desconectar.assert_called_once()


@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('time.sleep')
def test_watchdog_salidas_cierre_nativo_y_recurrencia(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda sec: stop_event.set()
    
    db_instance = mock_db_class.return_value
    ib_instance = mock_ib_class.return_value
    
    # Mock active strategy with native broker management and daily recurrence
    strategy_mock = {
        "id": 5,
        "ticker": "AAPL",
        "tipo_activo": "STOCK",
        "estado": "ACTIVA",
        "patas": [{"accion": "BUY", "cantidad": 10}],
        "condiciones_entrada": {"frecuencia": {"activo": True, "tipo": "Diaria"}},
        "condiciones_salida": {"gestion": "Gestionado por IBKR (Órdenes en Broker)", "stop_loss": -100.0, "take_profit": 200.0},
        "precio_entrada": 150.0
    }
    db_instance.obtener_estrategias.return_value = [strategy_mock]
    
    # Mock: broker returns pnl = None (meaning no active position for this stock, so it was closed natively)
    ib_instance.conectar.return_value = True
    ib_instance.calcular_pnl_estrategia.return_value = None
    
    # Run outputs watchdog worker
    watchdog_salidas_worker("dummy.db", 1, stop_event)
    
    # Verify strategy state is updated to CERRADA_BROKER
    db_instance.actualizar_estado_estrategia.assert_called_once()
    db_args = db_instance.actualizar_estado_estrategia.call_args[1]
    assert db_args["estrategia_id"] == 5
    assert db_args["nuevo_estado"] == "CERRADA_BROKER"
    
    # Verify recurrence creates a new pending strategy
    db_instance.crear_estrategia.assert_called_once_with(
        ticker="AAPL",
        tipo_activo="STOCK",
        estado="PENDIENTE_ENTRADA",
        patas=[{"accion": "BUY", "cantidad": 10}],
        condiciones_entrada={"frecuencia": {"activo": True, "tipo": "Diaria"}},
        condiciones_salida={"gestion": "Gestionado por IBKR (Órdenes en Broker)", "stop_loss": -100.0, "take_profit": 200.0},
        precio_entrada=None
    )
