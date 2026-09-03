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

def test_iron_condor_22d_acceptance():
    """
    Prueba de Aceptación 1: Caso Iron Condor a 22 días vista.
    S=325, sigma=0.25, r=0.05, T=22/365.
    Put 317.5 ~= 4.34
    Put 322.5 ~= 6.30
    Call 327.5 ~= 7.24
    Call 332.5 ~= 5.20
    Crédito Neto ~= 4.00 USD/acción (400 USD total).
    """
    S = 325.0
    T = 22.0 / 365.0
    r = 0.05
    sigma = 0.25
    
    p1 = MotorBlackScholes.calcular_prima_bs(S, 317.5, T, r, sigma, 'P')
    p2 = MotorBlackScholes.calcular_prima_bs(S, 322.5, T, r, sigma, 'P')
    p3 = MotorBlackScholes.calcular_prima_bs(S, 327.5, T, r, sigma, 'C')
    p4 = MotorBlackScholes.calcular_prima_bs(S, 332.5, T, r, sigma, 'C')
    
    assert math.isclose(p1, 4.34, abs_tol=0.05)
    assert math.isclose(p2, 6.30, abs_tol=0.05)
    assert math.isclose(p3, 7.24, abs_tol=0.05)
    assert math.isclose(p4, 5.20, abs_tol=0.05)
    
    credito_neto = (p2 + p3) - (p1 + p4)
    assert math.isclose(credito_neto, 4.00, abs_tol=0.1)
    assert math.isclose(credito_neto * 100, 400.0, abs_tol=10.0)

def test_iron_condor_1d_acceptance():
    """
    Prueba de Aceptación 2: Caso T=1/365.
    Put 317.5 ~= 0.06
    Put 322.5 ~= 0.71
    Call 327.5 ~= 0.75
    Call 332.5 ~= 0.07
    """
    S = 325.0
    T = 1.0 / 365.0
    r = 0.05
    sigma = 0.25
    
    p1 = MotorBlackScholes.calcular_prima_bs(S, 317.5, T, r, sigma, 'P')
    p2 = MotorBlackScholes.calcular_prima_bs(S, 322.5, T, r, sigma, 'P')
    p3 = MotorBlackScholes.calcular_prima_bs(S, 327.5, T, r, sigma, 'C')
    p4 = MotorBlackScholes.calcular_prima_bs(S, 332.5, T, r, sigma, 'C')
    
    assert math.isclose(p1, 0.06, abs_tol=0.03)
    assert math.isclose(p2, 0.71, abs_tol=0.05)
    assert math.isclose(p3, 0.75, abs_tol=0.05)
    assert math.isclose(p4, 0.07, abs_tol=0.03)

def test_valor_intrinseco_t0():
    """
    Prueba de Aceptación 3: Verificar valor intrínseco cuando T <= 0.
    """
    S = 325.0
    assert MotorBlackScholes.calcular_prima_bs(S, 317.5, 0, 0.05, 0.25, 'C') == 7.50
    assert MotorBlackScholes.calcular_prima_bs(S, 317.5, 0, 0.05, 0.25, 'P') == 0.00
    assert MotorBlackScholes.calcular_prima_bs(S, 330.0, 0, 0.05, 0.25, 'C') == 0.00
    assert MotorBlackScholes.calcular_prima_bs(S, 330.0, -0.1, 0.05, 0.25, 'P') == 5.00

def test_put_call_parity():
    """
    Prueba de Aceptación 4: Paridad Put-Call (C - P = S - K * exp(-r*T)).
    """
    S, K, T, r, sigma = 325.0, 317.5, 22/365.0, 0.05, 0.25
    call_val = MotorBlackScholes.calcular_prima_bs(S, K, T, r, sigma, 'C')
    put_val = MotorBlackScholes.calcular_prima_bs(S, K, T, r, sigma, 'P')
    
    lhs = call_val - put_val
    rhs = S - K * math.exp(-r * T)
    assert math.isclose(lhs, rhs, abs_tol=1e-5)

def test_input_validation():
    """
    Verifica validación de entradas inválidas.
    """
    with pytest.raises(ValueError):
        MotorBlackScholes.calcular_prima_bs(-100, 100, 1, 0.05, 0.2, 'C')
    with pytest.raises(ValueError):
        MotorBlackScholes.calcular_prima_bs(100, -100, 1, 0.05, 0.2, 'C')
    with pytest.raises(ValueError):
        MotorBlackScholes.calcular_prima_bs(100, 100, 1, 0.05, -0.2, 'C')
    with pytest.raises(ValueError):
        MotorBlackScholes.calcular_prima_bs(100, 100, 1, 0.05, 0.2, 'INVALID')

def test_calcular_greeks():
    griegas = MotorBlackScholes.calcular_greeks(100, 100, 1, 0.05, 0.2, 'C')
    assert 'delta' in griegas and 'theta' in griegas and 'vega' in griegas
    assert 0 < griegas['delta'] < 1
    assert griegas['vega'] > 0

def test_calcular_payoff_estrategia():
    patas = [{"tipo_activo": "STOCK", "accion": "BUY", "cantidad": 10, "precio_entrada": 150.0}]
    resultado = MotorBlackScholes.calcular_payoff_estrategia(patas, T=0, r=0.05, sigma=0.2, precio_min=140, precio_max=160, puntos=5)
    assert len(resultado["S"]) == 5
    assert resultado["pnl_vencimiento"][0] == -100.0
    assert resultado["pnl_vencimiento"][-1] == 100.0
