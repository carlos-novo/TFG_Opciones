import numpy as np
from scipy.stats import norm
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from datetime import date

class MotorBlackScholes:
    """
    Motor de cálculo teórico para Opciones Europeas basado en el modelo Black-Scholes.
    Proporciona estimaciones de primas, Griegas (Sensibilidades) y Análisis de Sensibilidad (Heatmap).
    """

    @staticmethod
    def _calcular_d1_d2(S, K, T, r, sigma):
        # Evitamos división por cero en opciones que expiran hoy
        T = max(T, 1e-5)
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return d1, d2

    @staticmethod
    def calcular_prima_bs(S, K, T, r, sigma, tipo='C'):
        """
        Calcula el precio teórico de una opción (Call o Put).
        S: Precio del subyacente
        K: Precio de ejercicio (Strike)
        T: Tiempo al vencimiento (en años)
        r: Tasa de interés libre de riesgo (anualizada)
        sigma: Volatilidad implícita (anualizada)
        tipo: 'C' para Call, 'P' para Put
        """
        d1, d2 = MotorBlackScholes._calcular_d1_d2(S, K, T, r, sigma)
        
        if tipo.upper() == 'C':
            precio = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        elif tipo.upper() == 'P':
            precio = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        else:
            raise ValueError("El tipo debe ser 'C' (Call) o 'P' (Put)")
            
        return round(precio, 2)

    @staticmethod
    def calcular_greeks(S, K, T, r, sigma, tipo='C'):
        """
        Calcula las Griegas principales (Delta, Theta, Vega).
        Devuelve un diccionario.
        """
        d1, d2 = MotorBlackScholes._calcular_d1_d2(S, K, T, r, sigma)
        T_max = max(T, 1e-5)
        
        # N'(d1) - PDF normal estándar
        pdf_d1 = norm.pdf(d1)
        
        # Vega (igual para Call y Put). Dividimos entre 100 para interpretarlo por 1% de cambio en volatilidad.
        vega = (S * pdf_d1 * np.sqrt(T_max)) / 100.0

        if tipo.upper() == 'C':
            delta = norm.cdf(d1)
            # Theta anualizada, la dividimos por 365 para theta diaria
            theta = (-(S * pdf_d1 * sigma) / (2 * np.sqrt(T_max)) - r * K * np.exp(-r * T_max) * norm.cdf(d2)) / 365.0
        elif tipo.upper() == 'P':
            delta = norm.cdf(d1) - 1
            theta = (-(S * pdf_d1 * sigma) / (2 * np.sqrt(T_max)) + r * K * np.exp(-r * T_max) * norm.cdf(-d2)) / 365.0
        else:
            raise ValueError("El tipo debe ser 'C' (Call) o 'P' (Put)")
            
        return {
            "delta": round(delta, 4),
            "theta": round(theta, 4),
            "vega": round(vega, 4)
        }

    @staticmethod
    def generar_heatmap_ic(S, r, sigma, dias_vencimiento, base_strikes):
        """
        Genera un Heatmap del Ratio Beneficio/Riesgo (B/R) simulando desplazamientos
        en los strikes del Iron Condor.
        base_strikes: [put_long, put_short, call_short, call_long] base.
        """
        T = max(dias_vencimiento / 365.0, 1e-5)
        
        # Malla de desplazamientos (offset en puntos sobre el centro)
        offsets = [-100, -50, 0, 50, 100]
        
        matriz_ratio = np.zeros((len(offsets), len(offsets)))
        
        p_long_base, p_short_base, c_short_base, c_long_base = base_strikes
        
        for i, offset_put in enumerate(offsets):
            for j, offset_call in enumerate(offsets):
                # Desplazamos las alas de Put y Call manteniendo el ancho relativo
                p_short = p_short_base + offset_put
                p_long = p_long_base + offset_put
                c_short = c_short_base + offset_call
                c_long = c_long_base + offset_call
                
                # Calculamos primas teóricas B-S
                prima_p_long = MotorBlackScholes.calcular_prima_bs(S, p_long, T, r, sigma, 'P')
                prima_p_short = MotorBlackScholes.calcular_prima_bs(S, p_short, T, r, sigma, 'P')
                prima_c_short = MotorBlackScholes.calcular_prima_bs(S, c_short, T, r, sigma, 'C')
                prima_c_long = MotorBlackScholes.calcular_prima_bs(S, c_long, T, r, sigma, 'C')
                
                credito = (prima_p_short + prima_c_short) - (prima_p_long + prima_c_long)
                
                ancho_put = p_short - p_long
                ancho_call = c_long - c_short
                ancho_maximo = max(ancho_put, ancho_call)
                riesgo = ancho_maximo - credito
                
                if riesgo > 0 and credito > 0:
                    matriz_ratio[i, j] = round(credito / riesgo, 2)
                else:
                    matriz_ratio[i, j] = 0.0

        # Crear figura Matplotlib
        fig, ax = plt.subplots(figsize=(7, 5))
        
        # Custom colormap
        cmap = mcolors.LinearSegmentedColormap.from_list("rg", ["red", "yellow", "green"])
        
        cax = ax.matshow(matriz_ratio, cmap=cmap)
        fig.colorbar(cax, label="Ratio Beneficio / Riesgo")
        
        # Configurar ejes
        ax.set_xticks(np.arange(len(offsets)))
        ax.set_yticks(np.arange(len(offsets)))
        ax.set_xticklabels([f"{c_short_base + o}" for o in offsets])
        ax.set_yticklabels([f"{p_short_base + o}" for o in offsets])
        
        plt.xlabel('Desplazamiento Call Short')
        plt.ylabel('Desplazamiento Put Short')
        plt.title('Heatmap: Sensibilidad del Ratio B/R a Cambios de Strike', pad=20)
        
        # Anotar los valores en las celdas
        for i in range(len(offsets)):
            for j in range(len(offsets)):
                texto = ax.text(j, i, f"{matriz_ratio[i, j]:.2f}",
                               ha="center", va="center", color="black" if 0.5 < matriz_ratio[i,j] < 1.5 else "white", 
                               fontsize=9, fontweight='bold')
                
        fig.tight_layout()
        return fig
