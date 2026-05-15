import os
import requests
from datetime import datetime

def enviar_alerta_webhook(titulo, mensaje, color="info"):
    """
    Día 13: Envía una alerta telemétrica por HTTP POST a un Webhook (ej. Discord).
    Maneja el protocolo de capa de aplicación (HTTP) para notificar a sistemas externos.
    """
    # Leer URL desde variables de entorno (por defecto, None)
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        # Modo silencioso/debug si el usuario no ha configurado el .env
        print(f"[WEBHOOK SIMULADO - {color.upper()}] {titulo}: {mensaje}")
        return False
        
    # Paleta de colores decimales para Discord Embeds
    colores = {
        "info": 3447003,    # Azul
        "success": 3066993, # Verde
        "warning": 16776960,# Amarillo
        "error": 15158332   # Rojo
    }
    
    payload = {
        "embeds": [{
            "title": titulo,
            "description": mensaje,
            "color": colores.get(color, colores["info"]),
            "footer": {
                "text": f"TFG Opciones Telemática • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }]
    }
    
    try:
        # Ejecutamos el POST asíncrono o con timeout ultracorto para no bloquear
        # el hilo principal ni la interfaz de Streamlit si la red de Discord va lenta.
        response = requests.post(webhook_url, json=payload, timeout=2.5)
        return response.status_code in [200, 204]
    except requests.exceptions.RequestException as e:
        print(f"[ALERTA] Fallo de red al intentar conectar con el Webhook: {e}")
        return False
