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
