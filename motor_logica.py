from datetime import date
import pandas as pd
import math

class MotorEstrategias:
    """
    Clase encargada de la lógica financiera, agregación de opciones y cálculo de riesgos.
    """

    @staticmethod
    def calcular_credito_real_iron_condor(gestor, ticker, vencimiento, p_long, p_short, c_short, c_long):
        # Llamamos a la nueva función bulk
        strikes = [p_long, p_short, c_short, c_long]
        datos = gestor.obtener_datos_estrategia_completa(ticker, vencimiento, strikes)
        
        # Mapeamos los resultados (vienen en el mismo orden)
        d_p_l, d_p_s, d_c_s, d_c_l = datos

        ingreso = d_p_s['bid'] + d_c_s['bid']
        coste = d_p_l['ask'] + d_c_l['ask']
        credito_neto = ingreso - coste
        
        # FIX: Si no hay datos de mercado, Python suma NaNs y el límite de la orden peta
        if math.isnan(credito_neto):
            credito_neto = 0.0
        
        return {
            "credito_neto": round(credito_neto, 2),
            "detalle": {
                "p_short_bid": d_p_s['bid'], "c_short_bid": d_c_s['bid'],
                "p_long_ask": d_p_l['ask'], "c_long_ask": d_c_l['ask']
            }
        }

    @staticmethod
    def calcular_metricas_iron_condor(p_long, p_short, c_short, c_long, credito_neto):
        """
        Calcula el perfil de riesgo máximo y beneficio de la estrategia agregada.
        """
        # Beneficio máximo es el crédito recibido (multiplicado por 100 acciones)
        max_beneficio = credito_neto * 100
        
        # Riesgo máximo es el ancho de la "ala" más grande menos el crédito recibido
        ancho_put = p_short - p_long
        ancho_call = c_long - c_short
        ancho_maximo = max(ancho_put, ancho_call)
        
        max_riesgo = (ancho_maximo - credito_neto) * 100
        
        # Ratio Beneficio/Riesgo
        ratio_rb = round(max_beneficio / max_riesgo if max_riesgo > 0 else 0, 2)
        
        return {
            "max_beneficio": round(max_beneficio, 2),
            "max_riesgo": round(max_riesgo, 2),
            "ratio_rb": ratio_rb
        }
    
    @staticmethod
    def evaluar_condicion_sma(gestor, ticker, periodo, regla, precio_actual):
        """
        Calcula la Media Móvil Simple (SMA) con Pandas y evalúa la regla de entrada.
        """
        # 1. Pedimos los datos históricos a la capa de red
        cierres = gestor.obtener_historico_diario(ticker, periodo)
        
        if not cierres or len(cierres) < periodo:
            raise ValueError(f"No se pudieron obtener suficientes datos para una SMA de {periodo} días.")

        # 2. Vectorización y cálculo matemático con Pandas
        df = pd.DataFrame(cierres, columns=['close'])
        
        # Calculamos la SMA usando una ventana móvil. 
        # Al pedir exactamente 'periodo' días, la media de toda la columna es nuestra SMA actual.
        sma_actual = df['close'].mean()
        
        # 3. Lógica Algorítmica de Decisión
        luz_verde = False
        if "Precio > SMA" in regla:
            luz_verde = precio_actual > sma_actual
        elif "Precio < SMA" in regla:
            luz_verde = precio_actual < sma_actual
            
        return {
            "autorizado": luz_verde,
            "valor_sma": round(sma_actual, 2),
            "precio_evaluado": precio_actual
        }