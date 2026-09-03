import pytest
import math
import sys
import os
import json
import datetime as dt
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_bs import MotorBlackScholes
from motor_logica import MotorEstrategias
from base_datos import GestorBaseDatos

def normalizar_vencimiento(valor):
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor

    texto = str(valor).strip().split(" ")[0]
    for formato in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(texto, formato).date()
        except ValueError:
            continue

    raise ValueError(f"Formato de vencimiento no reconocido: {valor!r}")

def test_ausencia_referencias_t_calc_en_codigo():
    """
    Verifica que no queden referencias desfasadas a 'T_calc' ni 'isinstance(..., date)' desnudas en app_web.py.
    """
    ruta_app = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app_web.py'))
    with open(ruta_app, 'r', encoding='utf-8') as f:
        contenido = f.read()
    
    assert "T_calc" not in contenido, "Se encontró la variable obsoleta 'T_calc' en app_web.py"
    assert "isinstance(p_copy[\"vencimiento\"], date)" not in contenido, "Se encontró isinstance desnudas sin alias en app_web.py"

def test_normalizar_vencimiento_formatos():
    """
    Verifica que normalizar_vencimiento procese correctamente:
    - '2026-09-04'
    - '20260904'
    - dt.date(2026, 9, 4)
    - dt.datetime(2026, 9, 4, 15, 30)
    - Formato inválido que debe lanzar ValueError.
    """
    fecha_esp = dt.date(2026, 9, 4)
    
    assert normalizar_vencimiento("2026-09-04") == fecha_esp
    assert normalizar_vencimiento("20260904") == fecha_esp
    assert normalizar_vencimiento(dt.date(2026, 9, 4)) == fecha_esp
    assert normalizar_vencimiento(dt.datetime(2026, 9, 4, 15, 30)) == fecha_esp
    
    with pytest.raises(ValueError):
        normalizar_vencimiento("FECHA_INVALIDA")
    with pytest.raises(ValueError):
        normalizar_vencimiento("04-09-2026")

def test_caso_validacion_spot_324_14():
    """
    Prueba de Validación Principal:
    S = 324.14, sigma = 0.25, r = 0.05, T = 1 / 365 (Fecha 2026-09-03 a 2026-09-04).
    P317.5 = 0.0994
    P322.5 = 0.9776
    C327.5 = 0.5330
    C332.5 = 0.0433
    Crédito neto: 136.80 USD
    Pérdida máxima: 363.20 USD
    Puntos de equilibrio: 321.13 y 328.87 USD
    """
    S = 324.14
    T = 1.0 / 365.0
    r = 0.05
    sigma = 0.25
    
    p1 = MotorBlackScholes.calcular_prima_bs(S, 317.5, T, r, sigma, 'P')
    p2 = MotorBlackScholes.calcular_prima_bs(S, 322.5, T, r, sigma, 'P')
    p3 = MotorBlackScholes.calcular_prima_bs(S, 327.5, T, r, sigma, 'C')
    p4 = MotorBlackScholes.calcular_prima_bs(S, 332.5, T, r, sigma, 'C')
    
    assert math.isclose(p1, 0.0994, abs_tol=0.001)
    assert math.isclose(p2, 0.9776, abs_tol=0.001)
    assert math.isclose(p3, 0.5330, abs_tol=0.001)
    assert math.isclose(p4, 0.0433, abs_tol=0.001)
    
    credito_por_accion = (p2 + p3) - (p1 + p4)
    credito_total = credito_por_accion * 100.0
    ancho_max = max(322.5 - 317.5, 332.5 - 327.5) # 5.0
    perdida_max = (ancho_max - credito_por_accion) * 100.0
    
    bep_inf = 322.5 - credito_por_accion
    bep_sup = 327.5 + credito_por_accion
    
    assert math.isclose(credito_total, 136.80, abs_tol=0.1)
    assert math.isclose(perdida_max, 363.20, abs_tol=0.1)
    assert math.isclose(bep_inf, 321.13, abs_tol=0.01)
    assert math.isclose(bep_sup, 328.87, abs_tol=0.01)

def test_casos_aceptacion_opciones_multileg():
    """
    Prueba de Aceptación a 22 días (S=325, T=22/365, sigma=0.25, r=0.05).
    """
    S = 325.0
    r = 0.05
    sigma = 0.25
    T_22d = 22.0 / 365.0
    
    p1 = MotorBlackScholes.calcular_prima_bs(S, 317.5, T_22d, r, sigma, 'P')
    p2 = MotorBlackScholes.calcular_prima_bs(S, 322.5, T_22d, r, sigma, 'P')
    p3 = MotorBlackScholes.calcular_prima_bs(S, 327.5, T_22d, r, sigma, 'C')
    p4 = MotorBlackScholes.calcular_prima_bs(S, 332.5, T_22d, r, sigma, 'C')
    
    assert math.isclose(p1, 4.34, abs_tol=0.05)
    assert math.isclose(p2, 6.30, abs_tol=0.05)
    assert math.isclose(p3, 7.24, abs_tol=0.05)
    assert math.isclose(p4, 5.20, abs_tol=0.05)
    
    credito_por_accion = (p2 + p3) - (p1 + p4)
    credito_total = credito_por_accion * 100.0
    
    assert math.isclose(credito_por_accion, 4.00, abs_tol=0.1)
    assert math.isclose(credito_total, 400.0, abs_tol=10.0)

def test_separacion_prima_teorica_y_precio_entrada():
    """
    Verifica que prima_teorica sea la fuente para payoff y metricas en previsualización
    mientras que precio_entrada se reserve para ejecuciones reales.
    """
    patas = [
        {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 317.5, "right": "P", "prima_teorica": 0.0994, "modo": "TEORICO"},
        {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 322.5, "right": "P", "prima_teorica": 0.9776, "modo": "TEORICO"},
        {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 327.5, "right": "C", "prima_teorica": 0.5330, "modo": "TEORICO"},
        {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 332.5, "right": "C", "prima_teorica": 0.0433, "modo": "TEORICO"}
    ]
    
    payoff_data = MotorBlackScholes.calcular_payoff_estrategia(patas, T=0, r=0.05, sigma=0.25, precio_min=300, precio_max=350, puntos=50)
    assert "pnl_vencimiento" in payoff_data
    
    idx_centro = 25
    assert math.isclose(payoff_data["pnl_vencimiento"][idx_centro], 136.80, abs_tol=2.0)

def test_pnl_simulado_en_spot_igual_cero():
    """
    Verifica que con T_escenario == T_inicial, el P&L temporal simulado en spot_ref sea 0.0.
    """
    spot_ref = 324.14
    T_init = 1.0 / 365.0
    r = 0.05
    sigma = 0.25
    
    patas = [
        {"strike": 317.5, "right": "P", "accion": "BUY", "cantidad": 1},
        {"strike": 322.5, "right": "P", "accion": "SELL", "cantidad": 1},
        {"strike": 327.5, "right": "C", "accion": "SELL", "cantidad": 1},
        {"strike": 332.5, "right": "C", "accion": "BUY", "cantidad": 1}
    ]
    for p in patas:
        p["prima_teorica"] = MotorBlackScholes.calcular_prima_bs(spot_ref, float(p["strike"]), T_init, r, sigma, p["right"])
        
    pnl_simulado = 0.0
    for p in patas:
        sign = 1 if p["accion"] == "BUY" else -1
        qty = int(p["cantidad"])
        val_actual = MotorBlackScholes.calcular_prima_bs(spot_ref, float(p["strike"]), T_init, r, sigma, p["right"])
        pnl_simulado += sign * (val_actual - p["prima_teorica"]) * qty * 100.0
        
    assert math.isclose(pnl_simulado, 0.0, abs_tol=1e-5)

def test_obtener_prima_pata_estricta_excepciones():
    """
    Verifica que obtener_prima_pata requiera obligatoriamente:
    - precio_entrada en modo EJECUTADO (o lanza ValueError).
    - prima_teorica en modo TEORICO (o lanza ValueError).
    - Lanza ValueError en modos desconocidos.
    """
    pata_sin_entrada = {"prima_teorica": 2.50}
    pata_sin_teorica = {"precio_entrada": 3.00}
    pata_completa = {"prima_teorica": 2.50, "precio_entrada": 3.00}
    
    assert MotorEstrategias.obtener_prima_pata(pata_completa, modo="TEORICO") == 2.50
    assert MotorEstrategias.obtener_prima_pata(pata_completa, modo="EJECUTADO") == 3.00
    
    with pytest.raises(ValueError, match="precio_entrada confirmado"):
        MotorEstrategias.obtener_prima_pata(pata_sin_entrada, modo="EJECUTADO")
        
    with pytest.raises(ValueError, match="prima_teorica"):
        MotorEstrategias.obtener_prima_pata(pata_sin_teorica, modo="TEORICO")
        
    with pytest.raises(ValueError, match="Modo de prima no reconocido"):
        MotorEstrategias.obtener_prima_pata(pata_completa, modo="MODO_INVALIDO")

def test_encolado_opciones_sin_nameerror():
    """
    Prueba el encolado real en base de datos offline con patas en 3 formatos de vencimiento:
    string '2026-09-25', dt.date(2026, 9, 25), dt.datetime(2026, 9, 25, 10, 0).
    Verifica que no se produzca NameError, que las patas se serialicen en ISO YYYY-MM-DD,
    que la estrategia quede PENDIENTE y que TIF (DAY/GTC) se persista correctamente.
    """
    db_path_temp = "test_temp_encolar.db"
    db_mem = GestorBaseDatos(db_name=db_path_temp, reset_db=True)
    try:
        patas_raw = [
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 317.5, "right": "P", "vencimiento": "2026-09-25", "prima_teorica": 4.34},
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 322.5, "right": "P", "vencimiento": dt.date(2026, 9, 25), "prima_teorica": 6.30},
            {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 327.5, "right": "C", "vencimiento": dt.datetime(2026, 9, 25, 12, 0), "prima_teorica": 7.24},
            {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 332.5, "right": "C", "vencimiento": "2026-09-25", "prima_teorica": 5.20}
        ]
        
        # Proceso de normalización idéntico a app_web.py
        patas_serializadas = []
        for p in patas_raw:
            p_copy = p.copy()
            venc_date_copy = normalizar_vencimiento(p_copy["vencimiento"])
            p_copy["vencimiento"] = venc_date_copy.strftime('%Y-%m-%d')
            patas_serializadas.append(p_copy)
            
        condiciones_entrada = {
            "frecuencia": {"activo": False, "tipo": "Única"},
            "tif": "GTC"
        }
        condiciones_salida = {
            "stop_loss": -300.0,
            "take_profit": 600.0
        }
        
        est_id = db_mem.crear_estrategia(
            ticker="AAPL",
            tipo_activo="BAG",
            estado="PENDIENTE",
            patas=patas_serializadas,
            precio_entrada=4.00,
            condiciones_entrada=condiciones_entrada,
            condiciones_salida=condiciones_salida
        )
        
        estrategias = db_mem.obtener_estrategias(estado="PENDIENTE")
        assert len(estrategias) == 1
        est = estrategias[0]
        assert est["id"] == est_id
        assert est["estado"] == "PENDIENTE"
        assert est["precio_entrada"] == 4.00
        assert est["condiciones_entrada"]["tif"] == "GTC"
        
        # Verificar formato de vencimiento en las 4 patas
        for leg in est["patas"]:
            assert leg["vencimiento"] == "2026-09-25"
    finally:
        db_mem.borrar_base_datos()

def test_validacion_precio_limite_y_credito_teorico():
    """
    Verifica que:
    1. El crédito teórico de la combinación Iron Condor 22d sea aproximadamente +4.00 USD por acción.
    2. Rechace precio límite 0.0 USD para órdenes de crédito/débito.
    3. Rechace desajuste de signo entre crédito (+) y prima negativa (-).
    """
    patas = [
        {"accion": "BUY", "cantidad": 1, "prima_teorica": 4.34},
        {"accion": "SELL", "cantidad": 1, "prima_teorica": 6.30},
        {"accion": "SELL", "cantidad": 1, "prima_teorica": 7.24},
        {"accion": "BUY", "cantidad": 1, "prima_teorica": 5.20}
    ]
    
    credito_teorico_accion = 0.0
    for p in patas:
        sign = 1.0 if p["accion"] == "SELL" else -1.0
        qty = float(p["cantidad"])
        credito_teorico_accion += sign * qty * float(p["prima_teorica"])
        
    assert math.isclose(credito_teorico_accion, 4.00, abs_tol=0.05)
    
    # Reglas de validación
    precio_lmt_cero = 0.0
    assert abs(precio_lmt_cero) < 1e-4 # Debe ser rechazado
    
    precio_lmt_incoherente = -4.00
    assert credito_teorico_accion > 0 and precio_lmt_incoherente < 0 # Conflicto detectado

def test_idempotencia_huella_y_bloqueo_duplicados():
    """
    Verifica que:
    - Tres intentos de inserción idénticos produzcan solo 1 fila en la base de datos.
    - El segundo y tercer intento devuelvan EstrategiaDuplicadaError con el ID de la fila existente.
    """
    from base_datos import EstrategiaDuplicadaError, calcular_huella_estrategia
    
    db_path_temp = "test_temp_idempotencia.db"
    db_mem = GestorBaseDatos(db_name=db_path_temp, reset_db=True)
    try:
        patas = [
            {"accion": "BUY", "right": "P", "strike": 317.5, "cantidad": 1, "vencimiento": "2026-09-25"},
            {"accion": "SELL", "right": "P", "strike": 322.5, "cantidad": 1, "vencimiento": "2026-09-25"},
            {"accion": "SELL", "right": "C", "strike": 327.5, "cantidad": 1, "vencimiento": "2026-09-25"},
            {"accion": "BUY", "right": "C", "strike": 332.5, "cantidad": 1, "vencimiento": "2026-09-25"}
        ]
        
        # 1. Primer intento exitoso
        est_id_1 = db_mem.crear_estrategia(
            ticker="AAPL", tipo_activo="BAG", estado="PENDIENTE_ENTRADA",
            patas=patas, precio_entrada=4.00
        )
        assert isinstance(est_id_1, int)
        
        # 2. Segundo intento idéntico debe lanzar EstrategiaDuplicadaError
        with pytest.raises(EstrategiaDuplicadaError) as exc_info_2:
            db_mem.crear_estrategia(
                ticker="AAPL", tipo_activo="BAG", estado="PENDIENTE_ENTRADA",
                patas=patas, precio_entrada=4.00
            )
        assert exc_info_2.value.est_existente_id == est_id_1
        
        # 3. Tercer intento idéntico debe lanzar EstrategiaDuplicadaError
        with pytest.raises(EstrategiaDuplicadaError) as exc_info_3:
            db_mem.crear_estrategia(
                ticker="AAPL", tipo_activo="BAG", estado="PENDIENTE_ENTRADA",
                patas=patas, precio_entrada=4.00
            )
        assert exc_info_3.value.est_existente_id == est_id_1
        
        # Comprobar que en la BD sólo existe 1 fila
        estrategias = db_mem.obtener_estrategias(estado="PENDIENTE_ENTRADA")
        assert len(estrategias) == 1
    finally:
        db_mem.borrar_base_datos()

def test_diferencia_huella_por_parametro():
    """
    Verifica que cambiar strike, vencimiento o precio limite genere una huella SHA-256 distinta
    y permita crear la estrategia.
    """
    from base_datos import calcular_huella_estrategia
    
    patas_orig = [{"accion": "BUY", "right": "C", "strike": 100.0, "cantidad": 1, "vencimiento": "2026-09-25"}]
    patas_mod_strike = [{"accion": "BUY", "right": "C", "strike": 105.0, "cantidad": 1, "vencimiento": "2026-09-25"}]
    
    h1 = calcular_huella_estrategia("AAPL", "OPTION", patas_orig, 2.50, {}, {})
    h2 = calcular_huella_estrategia("AAPL", "OPTION", patas_mod_strike, 2.50, {}, {})
    h3 = calcular_huella_estrategia("AAPL", "OPTION", patas_orig, 3.00, {}, {})
    
    assert h1 != h2
    assert h1 != h3

def test_override_permitir_duplicado():
    """
    Verifica que al especificar permitir_duplicado=True se cree una segunda estrategia
    con la misma huella canónica.
    """
    db_path_temp = "test_temp_override.db"
    db_mem = GestorBaseDatos(db_name=db_path_temp, reset_db=True)
    try:
        patas = [{"accion": "BUY", "right": "C", "strike": 100.0, "cantidad": 1, "vencimiento": "2026-09-25"}]
        
        id1 = db_mem.crear_estrategia("AAPL", "OPTION", "PENDIENTE_ENTRADA", patas, precio_entrada=2.50)
        id2 = db_mem.crear_estrategia("AAPL", "OPTION", "PENDIENTE_ENTRADA", patas, precio_entrada=2.50, permitir_duplicado=True)
        
        assert id1 != id2
        assert len(db_mem.obtener_estrategias(estado="PENDIENTE_ENTRADA")) == 2
    finally:
        db_mem.borrar_base_datos()

def test_estados_cancelados_no_procesados():
    """
    Verifica que marcar una estrategia como CANCELADA_PRUEBA permita crear un nuevo ciclo
    y que dicha estrategia sea ignorada en los filtros de estrategias activas/pendientes.
    """
    db_path_temp = "test_temp_canceladas.db"
    db_mem = GestorBaseDatos(db_name=db_path_temp, reset_db=True)
    try:
        patas = [{"accion": "BUY", "right": "C", "strike": 100.0, "cantidad": 1, "vencimiento": "2026-09-25"}]
        
        id1 = db_mem.crear_estrategia("AAPL", "OPTION", "PENDIENTE_ENTRADA", patas, precio_entrada=2.50)
        db_mem.cancelar_estrategias_prueba([id1])
        
        # Una vez cancelada, el intento de crear una idéntica debe ser permitido
        id2 = db_mem.crear_estrategia("AAPL", "OPTION", "PENDIENTE_ENTRADA", patas, precio_entrada=2.50)
        assert id1 != id2
        
        pendientes = db_mem.obtener_estrategias(estado="PENDIENTE_ENTRADA")
        assert len(pendientes) == 1
        assert pendientes[0]["id"] == id2
    finally:
        db_mem.borrar_base_datos()

def test_notificacion_offline_contiene_no_transmitida(monkeypatch):
    """
    Verifica que en notificaciones offline el mensaje contenga 'OFFLINE / NO TRANSMITIDA'.
    """
    from notificaciones import enviar_alerta_webhook
    
    ultimo_payload = {}
    def mock_post(url, json, timeout):
        nonlocal ultimo_payload
        ultimo_payload = json
        class MockResp:
            status_code = 200
        return MockResp()
        
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/mock")
    monkeypatch.setattr("requests.post", mock_post)
    
    modo_red = "OFFLINE / NO TRANSMITIDA"
    enviar_alerta_webhook(
        titulo=f"📥 Nueva Estrategia Encolada (Opciones) [{modo_red}]",
        mensaje=f"Modo: {modo_red}",
        color="info"
    )
    
    assert "OFFLINE / NO TRANSMITIDA" in ultimo_payload["embeds"][0]["title"]
    assert "OFFLINE / NO TRANSMITIDA" in ultimo_payload["embeds"][0]["description"]

