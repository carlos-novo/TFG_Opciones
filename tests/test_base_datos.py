import os
import pytest
from base_datos import GestorBaseDatos

TEST_DB_NAME = "tfg_trading_test.db"

@pytest.fixture
def gestor_db():
    # Inicializa el gestor con una base de datos limpia para pruebas
    gestor = GestorBaseDatos(db_name=TEST_DB_NAME, reset_db=True)
    yield gestor
    # Al terminar la prueba, limpiamos la base de datos de test física
    gestor.borrar_base_datos()

def test_creacion_tablas(gestor_db):
    # Verifica que la base de datos se ha creado físicamente
    assert os.path.exists(gestor_db.db_path)
    
    # Verifica que podemos conectarnos y consultar las tablas
    conexion = gestor_db._conectar()
    cursor = conexion.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='estrategias';")
    assert cursor.fetchone() is not None
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auditoria';")
    assert cursor.fetchone() is not None
    
    conexion.close()

def test_crear_y_obtener_estrategia(gestor_db):
    patas = [
        {"action": "BUY", "quantity": 10, "tipo_activo": "STOCK"},
        {"action": "SELL", "quantity": 5, "tipo_activo": "STOCK"}
    ]
    condiciones_entrada = {
        "vix_max": 25.0,
        "sma_filter": {"period": 20, "condition": "Precio > SMA"}
    }
    condiciones_salida = {
        "stop_loss": -200.0,
        "take_profit": 400.0
    }
    
    est_id = gestor_db.crear_estrategia(
        ticker="AAPL",
        tipo_activo="STOCK",
        estado="PENDIENTE_ENTRADA",
        patas=patas,
        condiciones_entrada=condiciones_entrada,
        condiciones_salida=condiciones_salida
    )
    
    assert est_id is not None
    assert est_id > 0
    
    # Recuperamos la estrategia y validamos la deserialización JSON
    estrategia = gestor_db.obtener_estrategia(est_id)
    assert estrategia is not None
    assert estrategia["id"] == est_id
    assert estrategia["ticker"] == "AAPL"
    assert estrategia["tipo_activo"] == "STOCK"
    assert estrategia["estado"] == "PENDIENTE_ENTRADA"
    
    # Validar deserialización de JSON a tipos nativos
    assert isinstance(estrategia["patas"], list)
    assert len(estrategia["patas"]) == 2
    assert estrategia["patas"][0]["action"] == "BUY"
    
    assert isinstance(estrategia["condiciones_entrada"], dict)
    assert estrategia["condiciones_entrada"]["vix_max"] == 25.0
    
    assert isinstance(estrategia["condiciones_salida"], dict)
    assert estrategia["condiciones_salida"]["stop_loss"] == -200.0
    assert estrategia["condiciones_salida"]["take_profit"] == 400.0

def test_actualizar_estado_estrategia(gestor_db):
    patas = [{"action": "BUY", "quantity": 100}]
    est_id = gestor_db.crear_estrategia("TSLA", "STOCK", "PENDIENTE_ENTRADA", patas)
    
    # Cambiamos estado a activa y asignamos order_id y precio de entrada
    fecha_ej = "2026-05-27T12:00:00"
    exito = gestor_db.actualizar_estado_estrategia(
        estrategia_id=est_id,
        nuevo_estado="ACTIVA",
        order_id_entrada=12345,
        precio_entrada=180.50,
        fecha_ejecucion=fecha_ej
    )
    
    assert exito is True
    
    estrategia = gestor_db.obtener_estrategia(est_id)
    assert estrategia["estado"] == "ACTIVA"
    assert estrategia["order_id_entrada"] == 12345
    assert estrategia["precio_entrada"] == 180.50
    assert estrategia["fecha_ejecucion"] == fecha_ej
    assert estrategia["fecha_cierre"] is None

def test_actualizar_limites_sl_tp(gestor_db):
    patas = [{"action": "SELL", "right": "C", "strike": 5200}]
    condiciones_salida = {
        "stop_loss": -300.0,
        "take_profit": 500.0,
        "vix_limite": 30.0
    }
    
    est_id = gestor_db.crear_estrategia("SPX", "OPTION", "PENDIENTE_ENTRADA", patas, condiciones_salida=condiciones_salida)
    
    # Simulamos que el usuario cambia el SL y TP desde la web
    exito = gestor_db.actualizar_limites_sl_tp(estrategia_id=est_id, stop_loss=-150.0, take_profit=600.0)
    assert exito is True
    
    estrategia = gestor_db.obtener_estrategia(est_id)
    # Validamos que se actualizaron los límites pero se preservó 'vix_limite'
    assert estrategia["condiciones_salida"]["stop_loss"] == -150.0
    assert estrategia["condiciones_salida"]["take_profit"] == 600.0
    assert estrategia["condiciones_salida"]["vix_limite"] == 30.0

def test_obtener_estrategias_filtrado(gestor_db):
    # Insertar varias estrategias en diferentes estados
    gestor_db.crear_estrategia("MSFT", "STOCK", "PENDIENTE_ENTRADA", [])
    gestor_db.crear_estrategia("NVDA", "STOCK", "ACTIVA", [])
    gestor_db.crear_estrategia("NFLX", "STOCK", "CERRADA_TP", [])
    
    pendientes = gestor_db.obtener_estrategias(estado="PENDIENTE_ENTRADA")
    assert len(pendientes) == 1
    assert pendientes[0]["ticker"] == "MSFT"
    
    activas = gestor_db.obtener_estrategias(estado="ACTIVA")
    assert len(activas) == 1
    assert activas[0]["ticker"] == "NVDA"
    
    todas = gestor_db.obtener_estrategias()
    assert len(todas) == 3

def test_auditoria_logs(gestor_db):
    gestor_db.registrar_evento("TEST_EVENTO", "Detalles de prueba de auditoría")
    
    logs_df = gestor_db.obtener_logs(limit=5)
    assert not logs_df.empty
    assert len(logs_df) >= 1
    
    # Comprobar columnas devueltas en Pandas DataFrame
    assert "fecha" in logs_df.columns
    assert "evento" in logs_df.columns
    assert "detalles" in logs_df.columns
    
    ultimo_evento = logs_df.iloc[0]["evento"]
    # El último evento debería ser el registro de la inserción de la estrategia del test anterior,
    # o el evento explícito si es el único. Validamos que el evento de prueba esté registrado.
    eventos = logs_df["evento"].tolist()
    assert "TEST_EVENTO" in eventos
    
    detalles = logs_df[logs_df["evento"] == "TEST_EVENTO"].iloc[0]["detalles"]
    assert detalles == "Detalles de prueba de auditoría"
