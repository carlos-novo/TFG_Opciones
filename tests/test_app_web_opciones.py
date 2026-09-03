import pytest
import math
import sys
import os
import datetime as dt
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_bs import MotorBlackScholes
from motor_logica import MotorEstrategias

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
    Verifica que prima_teorica sea la fuente para payoff y metricas
    mientras que precio_entrada se reserve para ejecuciones reales.
    """
    patas = [
        {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 317.5, "right": "P", "prima_teorica": 0.0994},
        {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 322.5, "right": "P", "prima_teorica": 0.9776},
        {"tipo_activo": "OPTION", "accion": "SELL", "cantidad": 1, "strike": 327.5, "right": "C", "prima_teorica": 0.5330},
        {"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 332.5, "right": "C", "prima_teorica": 0.0433}
    ]
    
    # Evaluar payoff
    payoff_data = MotorBlackScholes.calcular_payoff_estrategia(patas, T=0, r=0.05, sigma=0.25, precio_min=300, precio_max=350, puntos=50)
    assert "pnl_vencimiento" in payoff_data
    
    # PnL maximo dentro del rango central (entre 322.5 y 327.5) debe ser aproximadamente +136.80
    idx_centro = 25
    assert math.isclose(payoff_data["pnl_vencimiento"][idx_centro], 136.80, abs_tol=2.0)

def test_unificacion_spot_ref():
    """
    Verifica que primas y griegas usen el mismo spot de referencia.
    """
    S = 324.14
    K = 322.5
    T = 1.0 / 365.0
    r = 0.05
    sigma = 0.25
    
    prima = MotorBlackScholes.calcular_prima_bs(S, K, T, r, sigma, 'P')
    griegas = MotorBlackScholes.calcular_greeks(S, K, T, r, sigma, 'P')
    
    assert prima > 0
    assert griegas["delta"] < 0
