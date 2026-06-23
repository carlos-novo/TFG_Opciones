import pytest
import threading
from unittest.mock import MagicMock, patch
from watchdogs import watchdog_entradas_worker, watchdog_salidas_worker

@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('threading.Event.wait')
def test_watchdog_entradas_ejecuta_y_lanza_orden(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    # Setup stop event
    stop_event = threading.Event()
    
    # Mock sleep sets stop_event so it only runs one loop iteration
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()
    
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
        precio_limite=180.0,
        tif="DAY"
    )
    
    # Verificamos que se actualizó el estado a ORDEN_ENVIADA en la BD
    db_instance.actualizar_estado_estrategia.assert_called_once()
    db_args = db_instance.actualizar_estado_estrategia.call_args[1]
    assert db_args["estrategia_id"] == 1
    assert db_args["nuevo_estado"] == "ORDEN_ENVIADA"
    assert db_args["order_id_entrada"] == 12345
    assert db_args["precio_entrada"] == 180.0
    
    # Verificamos que registró el evento y notificó por Discord
    db_instance.registrar_evento.assert_called_with(
        "WATCHDOG_ENTRADA_ENVIADA",
        "Estrategia ID 1 (AAPL) enviada al mercado. Esperando confirmación de ejecución (Fill). OrderID: 12345. Estado: Submitted"
    )
    mock_webhook.assert_called_once()
    ib_instance.desconectar.assert_called_once()


@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('threading.Event.wait')
def test_watchdog_entradas_ejecuta_y_activa_inmediatamente(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    # Setup stop event
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()

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

    # Mock market logic and connection (instant Fill)
    ib_instance.conectar.return_value = True
    ib_instance.obtener_precio_prueba.return_value = 180.50
    ib_instance.enviar_orden_generica.return_value = {"order_id": 12345, "status": "Filled"}

    # Run the worker once
    watchdog_entradas_worker("dummy.db", 1, stop_event)

    # Assertions
    ib_instance.conectar.assert_called_once()
    ib_instance.enviar_orden_generica.assert_called_once()

    # Verificamos que se actualizó el estado a ACTIVA en la BD inmediatamente
    db_instance.actualizar_estado_estrategia.assert_called_once()
    db_args = db_instance.actualizar_estado_estrategia.call_args[1]
    assert db_args["estrategia_id"] == 1
    assert db_args["nuevo_estado"] == "ACTIVA"
    assert db_args["order_id_entrada"] == 12345
    assert db_args["precio_entrada"] == 180.0

    db_instance.registrar_evento.assert_called_with(
        "WATCHDOG_ENTRADA_EJECUTADA",
        "Estrategia ID 1 (AAPL) activada inmediatamente. OrderID: 12345. Estado: Filled"
    )
    mock_webhook.assert_called_once()
    ib_instance.desconectar.assert_called_once()


@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('threading.Event.wait')
def test_watchdog_salidas_monitorea_y_cierra(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()
    
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
@patch('threading.Event.wait')
def test_watchdog_salidas_cierre_nativo_y_recurrencia(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()
    
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
    db_instance.crear_estrategia.assert_called_once()
    crear_args = db_instance.crear_estrategia.call_args[1]
    assert crear_args["ticker"] == "AAPL"
    assert crear_args["tipo_activo"] == "STOCK"
    assert crear_args["estado"] == "PENDIENTE_ENTRADA"
    assert crear_args["patas"] == [{"accion": "BUY", "cantidad": 10}]
    assert crear_args["condiciones_salida"] == {"gestion": "Gestionado por IBKR (Órdenes en Broker)", "stop_loss": -100.0, "take_profit": 200.0}
    assert crear_args["precio_entrada"] is None
    
    cond_ent = crear_args["condiciones_entrada"]
    assert cond_ent["frecuencia"]["activo"] is True
    assert cond_ent["frecuencia"]["tipo"] == "Diaria"
    assert "proxima_ejecucion" in cond_ent["frecuencia"]



@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('watchdogs.datetime')
@patch('threading.Event.wait')
def test_watchdog_salidas_procesa_expiracion(mock_sleep, mock_datetime, mock_webhook, mock_ib_class, mock_db_class):
    from datetime import datetime as real_datetime
    
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()
    
    # Mock datetime.now() y strptime
    mock_datetime.now.return_value = real_datetime(2026, 6, 12, 10, 30)
    mock_datetime.strptime.side_effect = lambda *args, **kwargs: real_datetime.strptime(*args, **kwargs)
    
    db_instance = mock_db_class.return_value
    ib_instance = mock_ib_class.return_value
    
    # Estrategia que expiró ayer (2026-06-11)
    strategy_mock = {
        "id": 10,
        "ticker": "SPX",
        "tipo_activo": "OPTION",
        "estado": "ACTIVA",
        "patas": [
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 7250.0, "right": "P", "vencimiento": "2026-06-11", "precio_entrada": 23.0},
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 7230.0, "right": "P", "vencimiento": "2026-06-11", "precio_entrada": 12.0}
        ],
        "condiciones_salida": {},
        "precio_entrada": 11.0
    }
    db_instance.obtener_estrategias.return_value = [strategy_mock]
    
    ib_instance.conectar.return_value = True
    # mock obtener_precio_cierre_en_fecha devuelve 7300.0 (ambas put vencen OTM, sin valor)
    ib_instance.obtener_precio_cierre_en_fecha.return_value = 7300.0
    
    # Ejecutamos el worker una vez
    watchdog_salidas_worker("dummy.db", 1, stop_event)
    
    # Verificamos que se llamó a actualizar el estado a CERRADA_VENCIMIENTO y se calculó el P&L final
    db_instance.actualizar_estado_estrategia.assert_called_once()
    db_args = db_instance.actualizar_estado_estrategia.call_args[1]
    assert db_args["estrategia_id"] == 10
    assert db_args["nuevo_estado"] == "CERRADA_VENCIMIENTO"
    assert db_args["precio_salida"] == 7300.0
    # P&L = (23 - 0)*100 - (12 - 0)*100 = 1100.0 (beneficio neto del spread)
    assert db_args["pnl_realizado"] == 1100.0
    
    # Verificamos registro del evento
    db_instance.registrar_evento.assert_called_with(
        "WATCHDOG_SALIDA_EXPIRACION",
        "Estrategia ID 10 (SPX) expirada en fecha 2026-06-11. Precio Cierre: 7300.0$. P&L Realizado: 1100.0$"
    )
    # Verificamos que se envió la notificación
    mock_webhook.assert_called_once()
    ib_instance.desconectar.assert_called_once()


@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('threading.Event.wait')
def test_watchdog_entradas_ignora_por_frecuencia(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()
    
    db_instance = mock_db_class.return_value
    ib_instance = mock_ib_class.return_value
    
    # Estrategia clonada con frecuencia Semanal, cuya proxima_ejecucion es en el futuro
    from datetime import datetime, timedelta
    strategy_mock = {
        "id": 150,
        "ticker": "AAPL",
        "tipo_activo": "STOCK",
        "estado": "PENDIENTE_ENTRADA",
        "fecha_creacion": datetime.now().isoformat(),
        "patas": [{"accion": "BUY", "cantidad": 10}],
        "condiciones_entrada": {
            "frecuencia": {
                "activo": True,
                "tipo": "Semanal",
                "proxima_ejecucion": (datetime.now() + timedelta(days=7)).isoformat()
            }
        },
        "precio_entrada": 150.0
    }
    db_instance.obtener_estrategias.return_value = [strategy_mock]
    
    ib_instance.conectar.return_value = True
    
    # Ejecutamos el worker
    watchdog_entradas_worker("dummy.db", 1, stop_event)
    
    # Assertions: No debe haberse conectado a obtener precio ni enviado orden porque se ignoró
    ib_instance.obtener_precio_prueba.assert_not_called()
    ib_instance.enviar_orden_generica.assert_not_called()
    db_instance.actualizar_estado_estrategia.assert_not_called()


@patch('watchdogs.GestorBaseDatos')
@patch('watchdogs.GestorIBKR')
@patch('watchdogs.enviar_alerta_webhook')
@patch('threading.Event.wait')
def test_watchdog_entradas_contrato_invalido(mock_sleep, mock_webhook, mock_ib_class, mock_db_class):
    # Setup stop event
    stop_event = threading.Event()
    mock_sleep.side_effect = lambda *args, **kwargs: stop_event.set()
    
    db_instance = mock_db_class.return_value
    ib_instance = mock_ib_class.return_value
    
    # Mock database to return one pending strategy with invalid contract/ticker
    strategy_mock = {
        "id": 99,
        "ticker": "INVALID_TICKER",
        "tipo_activo": "STOCK",
        "estado": "PENDIENTE_ENTRADA",
        "patas": [{"accion": "BUY", "cantidad": 10}],
        "condiciones_entrada": {},
        "precio_entrada": 100.0
    }
    db_instance.obtener_estrategias.return_value = [strategy_mock]
    
    # Mock connection to return True, and obtener_precio_prueba to raise ValueError (qualification failed)
    ib_instance.conectar.return_value = True
    ib_instance.obtener_precio_prueba.side_effect = ValueError("Ticker no válido o requiere exchange específico: INVALID_TICKER")
    
    # Run the worker once
    watchdog_entradas_worker("dummy.db", 1, stop_event)
    
    # Assertions
    ib_instance.conectar.assert_called_once()
    ib_instance.obtener_precio_prueba.assert_called_with("INVALID_TICKER")
    
    # Verify the strategy status is updated to "Contrato Inválido" in DB
    db_instance.actualizar_estado_estrategia.assert_called_once_with(
        estrategia_id=99,
        nuevo_estado="Contrato Inválido"
    )
    
    # Verify the event log was written and Discord webhook was alerted
    db_instance.registrar_evento.assert_called_with(
        "WATCHDOG_ENTRADA_ERROR_CONTRATO",
        "Estrategia ID 99 (INVALID_TICKER) marcada como 'Contrato Inválido' debido a error: Ticker no válido o requiere exchange específico: INVALID_TICKER"
    )
    mock_webhook.assert_called_once()
