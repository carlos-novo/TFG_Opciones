import pytest
from unittest.mock import MagicMock, patch
from ib_insync import Stock, Option, Contract, LimitOrder, MarketOrder
from conexion_ibkr import GestorIBKR

@pytest.fixture
def gestor():
    # Instanciamos el gestor de prueba con IB mockeado
    with patch('conexion_ibkr.IB'):
        return GestorIBKR(host="127.0.0.1", port=4002)

def test_calificar_y_obtener_contratos_stock(gestor):
    ib_mock = MagicMock()
    patas = [{"tipo_activo": "STOCK"}]
    
    contratos = gestor.calificar_y_obtener_contratos(ib_mock, "AAPL", patas)
    
    assert len(contratos) == 1
    assert isinstance(contratos[0], Stock)
    assert contratos[0].symbol == "AAPL"
    assert contratos[0].exchange == "SMART"
    assert contratos[0].currency == "USD"
    ib_mock.qualifyContracts.assert_called_once_with(*contratos)

def test_calificar_y_obtener_contratos_option(gestor):
    ib_mock = MagicMock()
    patas = [
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 150.0, "right": "C"},
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 140.0, "right": "P"}
    ]
    
    contratos = gestor.calificar_y_obtener_contratos(ib_mock, "AAPL", patas)
    
    assert len(contratos) == 2
    assert isinstance(contratos[0], Option)
    assert contratos[0].symbol == "AAPL"
    assert contratos[0].strike == 150.0
    assert contratos[0].right == "C"
    assert contratos[0].lastTradeDateOrContractMonth == "20260620"
    
    assert isinstance(contratos[1], Option)
    assert contratos[1].strike == 140.0
    assert contratos[1].right == "P"
    ib_mock.qualifyContracts.assert_called_once_with(*contratos)

def test_construir_contrato_bag_dinamico(gestor):
    # Crear dos contratos mock calificados con conId
    c1 = Stock("AAPL", "SMART", "USD")
    c1.conId = 11111
    c2 = Option("AAPL", "20260620", 150.0, "C", "SMART", currency="USD")
    c2.conId = 22222
    
    patas = [
        {"accion": "BUY", "cantidad": 2},
        {"accion": "SELL", "cantidad": 1}
    ]
    
    bag = gestor.construir_contrato_bag_dinamico("AAPL", [c1, c2], patas)
    
    assert isinstance(bag, Contract)
    assert bag.symbol == "AAPL"
    assert bag.secType == "BAG"
    assert len(bag.comboLegs) == 2
    
    assert bag.comboLegs[0].conId == 11111
    assert bag.comboLegs[0].ratio == 2
    assert bag.comboLegs[0].action == "BUY"
    
    assert bag.comboLegs[1].conId == 22222
    assert bag.comboLegs[1].ratio == 1
    assert bag.comboLegs[1].action == "SELL"

@patch('conexion_ibkr.IB')
def test_enviar_orden_generica_stock_limit(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    # Mock qualification logic
    def mock_qualify(*contracts):
        for c in contracts:
            c.conId = 12345
    ib_instance.qualifyContracts = mock_qualify
    
    trade_mock = MagicMock()
    trade_mock.order.orderId = 999
    trade_mock.orderStatus.status = "Submitted"
    ib_instance.placeOrder = MagicMock(return_value=trade_mock)
    
    patas = [{"tipo_activo": "STOCK", "accion": "BUY", "cantidad": 50}]
    
    resultado = gestor.enviar_orden_generica("TSLA", "STOCK", patas, precio_limite=180.50)
    
    assert resultado["order_id"] == 999
    assert resultado["status"] == "Submitted"
    
    # Validar que placeOrder fue llamado con el contrato correcto y LimitOrder
    ib_instance.placeOrder.assert_called_once()
    args = ib_instance.placeOrder.call_args[0]
    
    contract_arg = args[0]
    order_arg = args[1]
    
    assert isinstance(contract_arg, Stock)
    assert contract_arg.symbol == "TSLA"
    
    assert isinstance(order_arg, LimitOrder)
    assert order_arg.action == "BUY"
    assert order_arg.totalQuantity == 50
    assert order_arg.lmtPrice == 180.50

@patch('conexion_ibkr.IB')
def test_enviar_orden_generica_bag_credito(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    # Mock qualification logic
    def mock_qualify(*contracts):
        for idx, c in enumerate(contracts):
            c.conId = 1000 + idx
    ib_instance.qualifyContracts = mock_qualify
    
    trade_mock = MagicMock()
    trade_mock.order.orderId = 888
    trade_mock.orderStatus.status = "PreSubmitted"
    ib_instance.placeOrder = MagicMock(return_value=trade_mock)
    
    patas = [
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 100.0, "right": "P", "accion": "BUY", "cantidad": 1},
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 110.0, "right": "P", "accion": "SELL", "cantidad": 1}
    ]
    
    # Enviamos una orden combo con precio_limite = 3.50 (crédito positivo).
    # Debe convertirse a precio negativo (-3.50) para la orden BUY del combo en IBKR.
    resultado = gestor.enviar_orden_generica("MSFT", "BAG", patas, precio_limite=3.50)
    
    assert resultado["order_id"] == 888
    assert resultado["status"] == "PreSubmitted"
    
    ib_instance.placeOrder.assert_called_once()
    args = ib_instance.placeOrder.call_args[0]
    
    contract_arg = args[0]
    order_arg = args[1]
    
    assert isinstance(contract_arg, Contract)
    assert contract_arg.secType == "BAG"
    assert len(contract_arg.comboLegs) == 2
    
    assert isinstance(order_arg, LimitOrder)
    assert order_arg.action == "BUY"
    assert order_arg.lmtPrice == -3.50

@patch('conexion_ibkr.IB')
def test_enviar_orden_cierre_generica_invertida(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    def mock_qualify(*contracts):
        for idx, c in enumerate(contracts):
            c.conId = 5000 + idx
    ib_instance.qualifyContracts = mock_qualify
    
    trade_mock = MagicMock()
    trade_mock.order.orderId = 777
    trade_mock.orderStatus.status = "Submitted"
    ib_instance.placeOrder = MagicMock(return_value=trade_mock)
    
    # Posición inicial: Compramos Stock. Cierre debe ser Vender Stock.
    patas = [{"tipo_activo": "STOCK", "accion": "BUY", "cantidad": 100}]
    
    resultado = gestor.enviar_orden_cierre_generica("AAPL", "STOCK", patas, precio_cierre=150.0)
    
    assert resultado["order_id"] == 777
    assert resultado["status"] == "Submitted"
    
    ib_instance.placeOrder.assert_called_once()
    args = ib_instance.placeOrder.call_args[0]
    
    contract_arg = args[0]
    order_arg = args[1]
    
    assert isinstance(contract_arg, Stock)
    assert isinstance(order_arg, LimitOrder)
    # Validamos que se invirtió BUY -> SELL
    assert order_arg.action == "SELL"
    assert order_arg.totalQuantity == 100
    assert order_arg.lmtPrice == 150.0

@patch('conexion_ibkr.IB')
def test_obtener_pnl_posiciones_filtrado(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    # Mock items in portfolio
    mock_portfolio = []
    
    # AAPL Stock
    item1 = MagicMock()
    item1.contract.symbol = "AAPL"
    item1.contract.secType = "STK"
    item1.unrealizedPNL = 100.50
    mock_portfolio.append(item1)
    
    # AAPL Option
    item2 = MagicMock()
    item2.contract.symbol = "AAPL"
    item2.contract.secType = "OPT"
    item2.unrealizedPNL = -45.00
    mock_portfolio.append(item2)
    
    # TSLA Stock
    item3 = MagicMock()
    item3.contract.symbol = "TSLA"
    item3.contract.secType = "STK"
    item3.unrealizedPNL = 200.00
    mock_portfolio.append(item3)
    
    ib_instance.portfolio = MagicMock(return_value=mock_portfolio)
    
    # Filtrar solo opciones de AAPL
    pnl_opt_aapl = gestor.obtener_pnl_posiciones_filtrado(ticker_filtro="AAPL", tipo_activo_filtro="OPTION")
    assert pnl_opt_aapl == -45.00
    
    # Filtrar acciones de AAPL
    pnl_stk_aapl = gestor.obtener_pnl_posiciones_filtrado(ticker_filtro="AAPL", tipo_activo_filtro="STOCK")
    assert pnl_stk_aapl == 100.50
    
    # P&L total sin filtros (solo STK y OPT)
    pnl_total = gestor.obtener_pnl_posiciones_filtrado()
    assert pnl_total == round(100.50 - 45.00 + 200.00, 2)


@patch('conexion_ibkr.IB')
def test_enviar_orden_generica_bag_debito(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    # Mock qualification logic
    def mock_qualify(*contracts):
        for idx, c in enumerate(contracts):
            c.conId = 2000 + idx
    ib_instance.qualifyContracts = mock_qualify
    
    trade_mock = MagicMock()
    trade_mock.order.orderId = 999
    trade_mock.orderStatus.status = "PreSubmitted"
    ib_instance.placeOrder = MagicMock(return_value=trade_mock)
    
    patas = [
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 100.0, "right": "P", "accion": "BUY", "cantidad": 1},
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 110.0, "right": "P", "accion": "SELL", "cantidad": 1}
    ]
    
    # Enviamos orden combo con precio_limite = -1.50 (débito negativo).
    # Debe convertirse a precio positivo (+1.50) para la orden BUY del combo en TWS.
    resultado = gestor.enviar_orden_generica("MSFT", "BAG", patas, precio_limite=-1.50)
    
    assert resultado["order_id"] == 999
    assert resultado["status"] == "PreSubmitted"
    
    args = ib_instance.placeOrder.call_args[0]
    order_arg = args[1]
    
    assert isinstance(order_arg, LimitOrder)
    assert order_arg.action == "BUY"
    assert order_arg.lmtPrice == 1.50


@patch('conexion_ibkr.IB')
def test_enviar_orden_generica_bag_mercado(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    # Mock qualification logic
    def mock_qualify(*contracts):
        for idx, c in enumerate(contracts):
            c.conId = 3000 + idx
    ib_instance.qualifyContracts = mock_qualify
    
    trade_mock = MagicMock()
    trade_mock.order.orderId = 1001
    trade_mock.orderStatus.status = "Submitted"
    ib_instance.placeOrder = MagicMock(return_value=trade_mock)
    
    patas = [
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 100.0, "right": "P", "accion": "BUY", "cantidad": 1},
        {"tipo_activo": "OPTION", "vencimiento": "20260620", "strike": 110.0, "right": "P", "accion": "SELL", "cantidad": 1}
    ]
    
    # Enviamos orden combo a mercado (precio_limite = None).
    resultado = gestor.enviar_orden_generica("MSFT", "BAG", patas, precio_limite=None)
    
    assert resultado["order_id"] == 1001
    assert resultado["status"] == "Submitted"
    
    args = ib_instance.placeOrder.call_args[0]
    order_arg = args[1]
    
    assert isinstance(order_arg, MarketOrder)
    assert order_arg.action == "BUY"


@patch('conexion_ibkr.IB')
def test_obtener_estado_orden(mock_ib_class, gestor):
    ib_instance = mock_ib_class.return_value
    gestor.ib = ib_instance
    ib_instance.connect = MagicMock()
    ib_instance.isConnected = MagicMock(return_value=True)
    
    # 1. Test cuando está en openTrades
    trade_open = MagicMock()
    trade_open.order.orderId = 123
    trade_open.orderStatus.status = "Submitted"
    trade_open.orderStatus.avgFillPrice = 1.25
    
    ib_instance.openTrades = MagicMock(return_value=[trade_open])
    ib_instance.trades = MagicMock(return_value=[])
    
    res1 = gestor.obtener_estado_orden(123)
    assert res1 == {"status": "Submitted", "avg_fill_price": 1.25}
    
    # 2. Test cuando está en trades finalizados
    trade_closed = MagicMock()
    trade_closed.order.orderId = 456
    trade_closed.orderStatus.status = "Filled"
    trade_closed.orderStatus.avgFillPrice = 0.90
    
    ib_instance.openTrades = MagicMock(return_value=[])
    ib_instance.trades = MagicMock(return_value=[trade_closed])
    
    res2 = gestor.obtener_estado_orden(456)
    assert res2 == {"status": "Filled", "avg_fill_price": 0.90}
    
    # 3. Test cuando no se encuentra
    res3 = gestor.obtener_estado_orden(789)
    assert res3 is None
