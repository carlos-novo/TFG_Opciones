import pytest
import os
import sys

# Aseguramos que el directorio raíz está en el PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from motor_logica import MotorSalida

# ---------------------------------------------------------------------------
# Fixtures de referencia
# ---------------------------------------------------------------------------
# Escenario base:
#   Crédito inicial cobrado: $590 (5.90$/acción × 100 acciones)
#   Take Profit al 50%  → cerrar si P&L ≥ +$295
#   Stop Loss al 200%   → cerrar si P&L ≤  -$1180
CREDITO  = 590.0
PCT_TP   = 50.0
PCT_SL   = 200.0
UMBRAL_TP = (PCT_TP / 100.0) * CREDITO      #  +295.0
UMBRAL_SL = -(PCT_SL / 100.0) * CREDITO    # -1180.0


# ---------------------------------------------------------------------------
# Tests de umbrales calculados
# ---------------------------------------------------------------------------

def test_umbrales_calculados_correctamente():
    """Los umbrales en dólares deben coincidir exactamente con la fórmula."""
    r = MotorSalida.evaluar_condicion_salida(0.0, CREDITO, PCT_TP, PCT_SL)
    assert r['umbral_tp_usd'] == 295.0,  f"TP esperado $295.0, obtenido {r['umbral_tp_usd']}"
    assert r['umbral_sl_usd'] == -1180.0, f"SL esperado -$1180.0, obtenido {r['umbral_sl_usd']}"


# ---------------------------------------------------------------------------
# Tests de la lógica de decisión
# ---------------------------------------------------------------------------

def test_tp_alcanzado():
    """P&L por encima del umbral TP → acción TAKE_PROFIT."""
    r = MotorSalida.evaluar_condicion_salida(300.0, CREDITO, PCT_TP, PCT_SL)
    assert r['accion'] == 'TAKE_PROFIT'

def test_sl_alcanzado():
    """P&L por debajo del umbral SL → acción STOP_LOSS."""
    r = MotorSalida.evaluar_condicion_salida(-1200.0, CREDITO, PCT_TP, PCT_SL)
    assert r['accion'] == 'STOP_LOSS'

def test_mantener_en_zona_segura():
    """P&L entre umbrales → acción MANTENER (no se cierra)."""
    r = MotorSalida.evaluar_condicion_salida(100.0, CREDITO, PCT_TP, PCT_SL)
    assert r['accion'] == 'MANTENER'

def test_mantener_con_pnl_negativo_tolerable():
    """P&L negativo pero dentro del margen SL → acción MANTENER."""
    r = MotorSalida.evaluar_condicion_salida(-500.0, CREDITO, PCT_TP, PCT_SL)
    assert r['accion'] == 'MANTENER'


# ---------------------------------------------------------------------------
# Tests de casos límite (boundary conditions)
# ---------------------------------------------------------------------------

def test_tp_exactamente_en_umbral():
    """P&L exactamente igual al umbral TP → acción TAKE_PROFIT (límite incluido)."""
    r = MotorSalida.evaluar_condicion_salida(UMBRAL_TP, CREDITO, PCT_TP, PCT_SL)
    assert r['accion'] == 'TAKE_PROFIT', \
        f"En el umbral exacto de TP debe cerrar. Obtenido: {r['accion']}"

def test_sl_exactamente_en_umbral():
    """P&L exactamente igual al umbral SL → acción STOP_LOSS (límite incluido)."""
    r = MotorSalida.evaluar_condicion_salida(UMBRAL_SL, CREDITO, PCT_TP, PCT_SL)
    assert r['accion'] == 'STOP_LOSS', \
        f"En el umbral exacto de SL debe cerrar. Obtenido: {r['accion']}"


# ---------------------------------------------------------------------------
# Tests de integridad del retorno
# ---------------------------------------------------------------------------

def test_retorno_contiene_todas_las_claves():
    """El dict retornado siempre debe incluir las 4 claves del contrato."""
    r = MotorSalida.evaluar_condicion_salida(50.0, CREDITO, PCT_TP, PCT_SL)
    assert 'accion'        in r
    assert 'umbral_tp_usd' in r
    assert 'umbral_sl_usd' in r
    assert 'pnl_actual'    in r

def test_pnl_actual_se_redondea_a_dos_decimales():
    """El P&L retornado debe estar redondeado a 2 decimales."""
    r = MotorSalida.evaluar_condicion_salida(123.456789, CREDITO, PCT_TP, PCT_SL)
    assert r['pnl_actual'] == 123.46
