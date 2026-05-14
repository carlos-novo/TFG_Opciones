import pytest
import os
import sys

# Aseguramos que el directorio raíz está en el PYTHONPATH para poder importar módulos del proyecto
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_logica import MotorEstrategias

class GestorMock:
    """
    Simula las respuestas de la API de IBKR para poder testear el motor lógico
    sin necesidad de una conexión activa a internet ni al Gateway.
    """
    def obtener_datos_estrategia_completa(self, ticker, vencimiento, strikes):
        return [
            {"bid": 2.10, "ask": 2.30},  # P_Long
            {"bid": 5.50, "ask": 5.70},  # P_Short
            {"bid": 4.80, "ask": 5.00},  # C_Short
            {"bid": 1.90, "ask": 2.10},  # C_Long
        ]
        
    def obtener_historico_diario(self, ticker, dias):
        return [5200.0, 5210.0, 5190.0, 5205.0, 5215.0]

def test_credito_neto_positivo():
    """El crédito neto de una Iron Condor con datos válidos debe ser positivo."""
    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
        GestorMock(), 'SPX', '20260620', 5000, 5100, 5300, 5400)
    assert resultado["credito_neto"] > 0

def test_credito_neto_calculo_correcto():
    """Verifica la fórmula: ingreso(bid_short) - coste(ask_long)."""
    # ingreso = 5.50 + 4.80 = 10.30 
    # coste = 2.30 + 2.10 = 4.40 
    # neto = 10.30 - 4.40 = 5.90
    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
        GestorMock(), 'SPX', '20260620', 5000, 5100, 5300, 5400)
    assert resultado["credito_neto"] == 5.90

def test_metricas_iron_condor():
    """Verifica beneficio máximo, riesgo máximo y que el ratio sea mayor a 0."""
    r = MotorEstrategias.calcular_metricas_iron_condor(5000, 5100, 5300, 5400, 5.90)
    assert r["max_beneficio"] == 590.0
    assert r["max_riesgo"] > 0
    assert r["ratio_rb"] > 0

def test_sma_autoriza_si_precio_mayor():
    """Con precio actual > SMA, la regla 'Precio > SMA' debe autorizar la operación."""
    r = MotorEstrategias.evaluar_condicion_sma(GestorMock(), 'SPX', 5, 'Precio > SMA', 9999.0)
    assert bool(r["autorizado"]) is True

def test_sma_bloquea_si_datos_insuficientes():
    """Debe lanzar ValueError si IBKR devuelve menos datos históricos del periodo solicitado."""
    class GestorSinDatos:
        def obtener_historico_diario(self, t, d): 
            return [5200.0] # Solo 1 dato devuelto
            
    with pytest.raises(ValueError):
        MotorEstrategias.evaluar_condicion_sma(GestorSinDatos(), 'SPX', 20, 'Precio > SMA', 5200.0)
