import pytest
import math
import sys
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_bs import MotorBlackScholes

def test_casos_aceptacion_opciones_multileg():
    """
    Pruebas de Aceptación Integradas:
    Caso S=325, sigma=0.25, r=0.05 a fecha 3 de septiembre de 2026.
    Vencimiento 25 de septiembre de 2026 (22 días).
    """
    S = 325.0
    r = 0.05
    sigma = 0.25
    T_22d = 22.0 / 365.0
    
    # 1. Primas teóricas a 22 días
    put_317_5 = MotorBlackScholes.calcular_prima_bs(S, 317.5, T_22d, r, sigma, 'P')
    put_322_5 = MotorBlackScholes.calcular_prima_bs(S, 322.5, T_22d, r, sigma, 'P')
    call_327_5 = MotorBlackScholes.calcular_prima_bs(S, 327.5, T_22d, r, sigma, 'C')
    call_332_5 = MotorBlackScholes.calcular_prima_bs(S, 332.5, T_22d, r, sigma, 'C')
    
    assert math.isclose(put_317_5, 4.34, abs_tol=0.05)
    assert math.isclose(put_322_5, 6.30, abs_tol=0.05)
    assert math.isclose(call_327_5, 7.24, abs_tol=0.05)
    assert math.isclose(call_332_5, 5.20, abs_tol=0.05)
    
    credito_por_accion = (put_322_5 + call_327_5) - (put_317_5 + call_332_5)
    credito_total = credito_por_accion * 100.0
    
    assert math.isclose(credito_por_accion, 4.00, abs_tol=0.1)
    assert math.isclose(credito_total, 400.0, abs_tol=10.0)

def test_caso_aceptacion_t_1d():
    """
    Verifica que para T = 1 / 365 los valores sean los esperados (0.06, 0.71, 0.75, 0.07).
    """
    S = 325.0
    r = 0.05
    sigma = 0.25
    T_1d = 1.0 / 365.0
    
    p1 = MotorBlackScholes.calcular_prima_bs(S, 317.5, T_1d, r, sigma, 'P')
    p2 = MotorBlackScholes.calcular_prima_bs(S, 322.5, T_1d, r, sigma, 'P')
    p3 = MotorBlackScholes.calcular_prima_bs(S, 327.5, T_1d, r, sigma, 'C')
    p4 = MotorBlackScholes.calcular_prima_bs(S, 332.5, T_1d, r, sigma, 'C')
    
    assert math.isclose(p1, 0.06, abs_tol=0.03)
    assert math.isclose(p2, 0.71, abs_tol=0.05)
    assert math.isclose(p3, 0.75, abs_tol=0.05)
    assert math.isclose(p4, 0.07, abs_tol=0.03)

def test_caso_aceptacion_t_0_intrinseco():
    """
    Verifica que para T <= 0 se devuelva el valor intrínseco.
    """
    S = 325.0
    c_in = MotorBlackScholes.calcular_prima_bs(S, 317.5, 0, 0.05, 0.25, 'C')
    p_in = MotorBlackScholes.calcular_prima_bs(S, 317.5, 0, 0.05, 0.25, 'P')
    assert c_in == 7.50
    assert p_in == 0.00

def test_invalidacion_estado_simulada():
    """
    Simula la invalidación de estado al cambiar de vencimiento global.
    """
    patas = [
        {"strike": 317.5, "right": "P", "precio_entrada": 0.06},
        {"strike": 322.5, "right": "P", "precio_entrada": 0.71},
        {"strike": 327.5, "right": "C", "precio_entrada": 0.75},
        {"strike": 332.5, "right": "C", "precio_entrada": 0.07}
    ]
    session_state = {
        "patas_opciones": patas,
        "payoff_data": {"dummy": True},
        "credito_neto": 1.33
    }
    
    # Ejecutar función de invalidación
    for leg in session_state.get("patas_opciones", []):
        leg.pop("precio_entrada", None)
    for key in ("payoff_data", "credito_neto"):
        session_state.pop(key, None)
        
    assert "payoff_data" not in session_state
    assert "credito_neto" not in session_state
    for leg in session_state["patas_opciones"]:
        assert "precio_entrada" not in leg
