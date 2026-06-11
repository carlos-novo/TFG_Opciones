import numpy as np
from scipy.stats import norm
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
        
        pdf_d1 = norm.pdf(d1)
        vega = (S * pdf_d1 * np.sqrt(T_max)) / 100.0

        if tipo.upper() == 'C':
            delta = norm.cdf(d1)
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
            precio_ent = float(pata.get("precio_entrada", 0.0))
            
            dir_mult = 1 if accion == "BUY" else -1
            
            if tipo == "STOCK":
                pnl_v = dir_mult * (S_rango - precio_ent) * cantidad
                pnl_vencimiento += pnl_v
                pnl_temporal += pnl_v  # Acciones son lineales
            else:
                strike = float(pata.get("strike", 0.0))
                right = pata.get("right", "C").upper()
                
                if right == "C":
                    payoff_v = np.maximum(S_rango - strike, 0)
                else:
                    payoff_v = np.maximum(strike - S_rango, 0)
                
                pnl_v = dir_mult * (payoff_v - precio_ent) * cantidad * 100
                pnl_vencimiento += pnl_v
                
                if T <= 0:
                    pnl_temporal += pnl_v
                else:
                    v_bs = np.array([
                        MotorBlackScholes.calcular_prima_bs(s, strike, T, r, sigma, right)
                        for s in S_rango
                    ])
                    pnl_t = dir_mult * (v_bs - precio_ent) * cantidad * 100
                    pnl_temporal += pnl_t
                    
        return {
            "S": S_rango.tolist(),
            "pnl_vencimiento": pnl_vencimiento.tolist(),
            "pnl_temporal": pnl_temporal.tolist()
        }

    @staticmethod
    def generar_heatmap_ic(S, r, sigma, dias_vencimiento, base_strikes):
        """
        Genera un Heatmap del Ratio Beneficio/Riesgo (B/R) simulando desplazamientos
        en los strikes del Iron Condor.
        """
        T = max(dias_vencimiento / 365.0, 1e-5)
        offsets = [-100, -50, 0, 50, 100]
        matriz_ratio = np.zeros((len(offsets), len(offsets)))
        p_long_base, p_short_base, c_short_base, c_long_base = base_strikes
        
        for i, offset_put in enumerate(offsets):
            for j, offset_call in enumerate(offsets):
                p_short = p_short_base + offset_put
                p_long = p_long_base + offset_put
                c_short = c_short_base + offset_call
                c_long = c_long_base + offset_call
                
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

        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        fig, ax = plt.subplots(figsize=(7, 5))
        cmap = mcolors.LinearSegmentedColormap.from_list("rg", ["red", "yellow", "green"])
        cax = ax.matshow(matriz_ratio, cmap=cmap)
        fig.colorbar(cax, label="Ratio Beneficio / Riesgo")
        
        ax.set_xticks(np.arange(len(offsets)))
        ax.set_yticks(np.arange(len(offsets)))
        ax.set_xticklabels([f"{c_short_base + o}" for o in offsets])
        ax.set_yticklabels([f"{p_short_base + o}" for o in offsets])
        
        plt.xlabel('Desplazamiento Call Short')
        plt.ylabel('Desplazamiento Put Short')
        plt.title('Heatmap: Sensibilidad del Ratio B/R a Cambios de Strike', pad=20)
        
        for i in range(len(offsets)):
            for j in range(len(offsets)):
                ax.text(j, i, f"{matriz_ratio[i, j]:.2f}",
                               ha="center", va="center", color="black" if 0.5 < matriz_ratio[i,j] < 1.5 else "white", 
                               fontsize=9, fontweight='bold')
                
        fig.tight_layout()
        return fig

    @staticmethod
    def generar_payoff_ic(strikes, credito_neto):
        """
        Genera el gráfico de Perfil de Pagos a Vencimiento para Iron Condor (Wrapper compatible).
        """
        p_long, p_short, c_short, c_long = strikes
        precio_min = p_long * 0.8
        precio_max = c_long * 1.2
        S = np.linspace(precio_min, precio_max, 500)
        
        payoff_p_long = np.maximum(p_long - S, 0)
        payoff_p_short = -np.maximum(p_short - S, 0)
        payoff_c_short = -np.maximum(S - c_short, 0)
        payoff_c_long = np.maximum(S - c_long, 0)
        
        payoff_total = payoff_p_long + payoff_p_short + payoff_c_short + payoff_c_long + credito_neto
        bep_inferior = p_short - credito_neto
        bep_superior = c_short + credito_neto
        
        import matplotlib.pyplot as plt
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(8, 4))
        
        ax.plot(S, payoff_total, color='white', linewidth=2, label="P&L Total")
        ax.axhline(0, color='gray', linestyle='--', linewidth=1)
        ax.fill_between(S, payoff_total, 0, where=(payoff_total > 0), facecolor='green', alpha=0.4, label='Zona de Ganancia')
        ax.fill_between(S, payoff_total, 0, where=(payoff_total < 0), facecolor='red', alpha=0.4, label='Zona de Pérdida')
        
        ax.axvline(bep_inferior, color='yellow', linestyle=':', linewidth=1)
        ax.axvline(bep_superior, color='yellow', linestyle=':', linewidth=1)
        
        ax.text(bep_inferior, min(payoff_total)*0.2, f' BEP: {bep_inferior:.2f}', color='yellow', verticalalignment='top', horizontalalignment='right')
        ax.text(bep_superior, min(payoff_total)*0.2, f' BEP: {bep_superior:.2f}', color='yellow', verticalalignment='top', horizontalalignment='left')
        
        ax.set_title("Perfil de Pagos a Vencimiento (Iron Condor)", pad=15)
        ax.set_xlabel("Precio del Subyacente al Vencimiento")
        ax.set_ylabel("P&L ($)")
        ax.legend()
        
        fig.tight_layout()
        plt.style.use('default') 
        return fig
