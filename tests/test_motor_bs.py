import pytest
import math
import sys
import os

# Añadir el directorio raíz para poder importar motor_bs
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_bs import MotorBlackScholes

def test_calcular_prima_call():
    """
    Test de la fórmula teórica Black-Scholes para una Call europea.
    Valores conocidos: S=100, K=100, T=1 año, r=5%, Vol=20% -> Prima ~= 10.45
    """
    prima = MotorBlackScholes.calcular_prima_bs(100, 100, 1, 0.05, 0.2, 'C')
    assert math.isclose(prima, 10.45, abs_tol=0.1)

def test_calcular_prima_put():
    """
    Test de la fórmula teórica Black-Scholes para una Put europea.
    Valores conocidos: S=100, K=100, T=1 año, r=5%, Vol=20% -> Prima ~= 5.57
    """
    prima = MotorBlackScholes.calcular_prima_bs(100, 100, 1, 0.05, 0.2, 'P')
    assert math.isclose(prima, 5.57, abs_tol=0.1)

def test_calcular_greeks_call():
    """
    Test de los límites teóricos de las Griegas para una Call.
    La Delta de una Call debe estar entre 0 y +1.
    La Vega debe ser positiva.
    """
    griegas = MotorBlackScholes.calcular_greeks(100, 100, 1, 0.05, 0.2, 'C')
    assert 'delta' in griegas
    assert 'theta' in griegas
    assert 'vega' in griegas
    
    assert 0 < griegas['delta'] < 1
    assert griegas['vega'] > 0

def test_calcular_greeks_put():
    """
    Test de los límites teóricos de las Griegas para una Put.
    La Delta de una Put debe estar entre -1 y 0.
    """
    griegas = MotorBlackScholes.calcular_greeks(100, 100, 1, 0.05, 0.2, 'P')
    assert -1 < griegas['delta'] < 0

def test_calcular_payoff_estrategia():
    # Test con una sola pata de acción (BUY 10 acciones a 150$)
    patas = [{"tipo_activo": "STOCK", "accion": "BUY", "cantidad": 10, "precio_entrada": 150.0}]
    resultado = MotorBlackScholes.calcular_payoff_estrategia(patas, T=0, r=0.05, sigma=0.2, precio_min=140, precio_max=160, puntos=5)
    
    assert len(resultado["S"]) == 5
    # En S=140, PnL = (140 - 150) * 10 = -100$
    assert resultado["pnl_vencimiento"][0] == -100.0
    # En S=160, PnL = (160 - 150) * 10 = 100$
    assert resultado["pnl_vencimiento"][-1] == 100.0
    
    # Test con una opción Call comprada (BUY 1 Call strike 150 a prima 5.0$)
    patas_opt = [{"tipo_activo": "OPTION", "accion": "BUY", "cantidad": 1, "strike": 150.0, "right": "C", "precio_entrada": 5.0}]
    res_opt = MotorBlackScholes.calcular_payoff_estrategia(patas_opt, T=0, r=0.05, sigma=0.2, precio_min=140, precio_max=160, puntos=3)
    # En S=140 (out of money), PnL = (0 - 5.0) * 1 * 100 = -500$
    assert res_opt["pnl_vencimiento"][0] == -500.0
    # En S=160 (in the money), PnL = (10 - 5.0) * 1 * 100 = 500$
    assert res_opt["pnl_vencimiento"][-1] == 500.0

