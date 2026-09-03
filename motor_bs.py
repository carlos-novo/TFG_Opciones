import numpy as np
from scipy.stats import norm
from datetime import date

class MotorBlackScholes:
    """
    Motor de cálculo teórico para Opciones Europeas basado en el modelo Black-Scholes.
    Proporciona estimaciones de primas, Griegas (Sensibilidades) y Análisis de Sensibilidad.
    """

    @staticmethod
    def _calcular_d1_d2(S, K, T, r, sigma):
        T_max = max(T, 1e-5)
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T_max) / (sigma * np.sqrt(T_max))
        d2 = d1 - sigma * np.sqrt(T_max)
        return d1, d2

    @staticmethod
    def calcular_prima_bs(S, K, T, r, sigma, tipo='C'):
        """
        Calcula el precio teórico sin redondear internamente de una opción europea (Call o Put).
        S: Precio del subyacente (S > 0)
        K: Precio de ejercicio (K > 0)
        T: Tiempo al vencimiento en años
        r: Tasa de interés libre de riesgo (anualizada)
        sigma: Volatilidad implícita (sigma >= 0)
        tipo: 'C'/'CALL' o 'P'/'PUT'
        """
        tipo_upper = str(tipo).upper().strip()
        if tipo_upper not in ['C', 'P', 'CALL', 'PUT']:
            raise ValueError("El tipo debe ser 'C'/'CALL' o 'P'/'PUT'")
            
        if S <= 0 or K <= 0:
            raise ValueError("S y K deben ser estrictamente mayores que cero.")
        if sigma < 0:
            raise ValueError("La volatilidad (sigma) debe ser mayor o igual a cero.")
            
        # Para T <= 0, devolver el valor intrínseco exacto sin descuento de tiempo
        if T <= 0:
            if tipo_upper in ['C', 'CALL']:
                return float(max(S - K, 0.0))
            else:
                return float(max(K - S, 0.0))
                
        # Si la volatilidad es 0, devolver el valor intrínseco descontado a la tasa libre de riesgo
        if sigma == 0:
            if tipo_upper in ['C', 'CALL']:
                return float(max(S - K * np.exp(-r * T), 0.0))
            else:
                return float(max(K * np.exp(-r * T) - S, 0.0))

        d1, d2 = MotorBlackScholes._calcular_d1_d2(S, K, T, r, sigma)
        
        if tipo_upper in ['C', 'CALL']:
            precio = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:
            precio = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            
        return float(precio)

    @staticmethod
    def calcular_greeks(S, K, T, r, sigma, tipo='C'):
        """
        Calcula las Griegas principales (Delta, Theta, Vega).
        Devuelve un diccionario con números de punto flotante sin redondear.
        """
        tipo_upper = str(tipo).upper().strip()
        if tipo_upper not in ['C', 'P', 'CALL', 'PUT']:
            raise ValueError("El tipo debe ser 'C'/'CALL' o 'P'/'PUT'")
        if S <= 0 or K <= 0 or sigma < 0:
            raise ValueError("S, K y sigma deben ser válidos.")

        if T <= 0 or sigma == 0:
            if tipo_upper in ['C', 'CALL']:
                delta = 1.0 if S > K else (0.5 if S == K else 0.0)
            else:
                delta = -1.0 if S < K else (-0.5 if S == K else 0.0)
            return {"delta": float(delta), "theta": 0.0, "vega": 0.0}

        d1, d2 = MotorBlackScholes._calcular_d1_d2(S, K, T, r, sigma)
        T_max = max(T, 1e-5)
        
        pdf_d1 = norm.pdf(d1)
        vega = (S * pdf_d1 * np.sqrt(T_max)) / 100.0

        if tipo_upper in ['C', 'CALL']:
            delta = norm.cdf(d1)
            theta = (-(S * pdf_d1 * sigma) / (2 * np.sqrt(T_max)) - r * K * np.exp(-r * T_max) * norm.cdf(d2)) / 365.0
        else:
            delta = norm.cdf(d1) - 1.0
            theta = (-(S * pdf_d1 * sigma) / (2 * np.sqrt(T_max)) + r * K * np.exp(-r * T_max) * norm.cdf(-d2)) / 365.0
            
        return {
            "delta": float(delta),
            "theta": float(theta),
            "vega": float(vega)
        }

    @staticmethod
    def calcular_payoff_estrategia(patas, T, r, sigma, precio_min, precio_max, puntos=200):
        """
        Calcula el P&L teórico para un rango de precios del subyacente S
        para una combinación de patas genéricas (opciones y/o acciones),
        tanto a vencimiento (T=0) como antes de vencimiento (T > 0).
        """
        S_rango = np.linspace(precio_min, precio_max, puntos)
        pnl_vencimiento = np.zeros_like(S_rango)
        pnl_temporal = np.zeros_like(S_rango)
        
        for pata in patas:
            tipo = pata.get("tipo_activo", "OPTION").upper()
            accion = pata.get("accion", "BUY").upper()
            cantidad = int(pata.get("cantidad", 1))
            precio_ent = float(pata.get("prima_teorica") if pata.get("prima_teorica") is not None else pata.get("precio_entrada", 0.0))
            
            dir_mult = 1 if accion == "BUY" else -1
            
            if tipo == "STOCK":
                pnl_v = dir_mult * (S_rango - precio_ent) * cantidad
                pnl_vencimiento += pnl_v
                pnl_temporal += pnl_v  # Acciones son lineales
            else:
                strike = float(pata.get("strike", 0.0))
                right = pata.get("right", "C").upper()
                
                if right in ["C", "CALL"]:
                    payoff_v = np.maximum(S_rango - strike, 0)
                else:
                    payoff_v = np.maximum(strike - S_rango, 0)
                
                pnl_v = dir_mult * (payoff_v - precio_ent) * cantidad * 100
                pnl_vencimiento += pnl_v
                
                # Curva PnL temporal (T > 0 o T=0)
                if T <= 0:
                    pnl_temporal += pnl_v
                else:
                    precios_t = np.array([
                        MotorBlackScholes.calcular_prima_bs(s, strike, T, r, sigma, right)
                        for s in S_rango
                    ])
                    pnl_t = dir_mult * (precios_t - precio_ent) * cantidad * 100
                    pnl_temporal += pnl_t

        return {
            "S": S_rango,
            "pnl_vencimiento": pnl_vencimiento,
            "pnl_temporal": pnl_temporal
        }
