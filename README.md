# 🦅 OptiTrack-IBKR: Plataforma Algorítmica de Negociación Multileg y Direccional

[![Tests](https://github.com/carlos-novo/TFG_Opciones/actions/workflows/tests.yml/badge.svg)](https://github.com/carlos-novo/TFG_Opciones/actions)

**OptiTrack-IBKR** es un sistema de trading algorítmico de alta fidelidad optimizado para la gestión y ejecución automatizada tanto de estrategias de acciones direccionales simples como de combos multileg de opciones financieras. La plataforma actúa como un middleware avanzado entre el analista cuantitativo y el mercado real a través de la infraestructura de **Interactive Brokers (IBKR)**.

Desarrollado por **Carlos Novo** como **Trabajo de Fin de Grado en Ingeniería Telemática**, este proyecto implementa patrones de diseño robustos para concurrencia asíncrona, bucles daemon de monitorización reactiva y un motor matemático avanzado para la valoración de derivados financieros.

---

## 🚀 Características Principales

*   **Trading Multiactivo Flexible**: Soporte completo para compra/venta direccional de acciones (STK) y estrategias de opciones financieras de hasta 4 patas (BAG combos, Iron Condor, spreads, etc.).
*   **Calculadora Financiera de Griegas**: Integración de un motor matemático de Black-Scholes para estimar en tiempo real las variables de control financiero: Delta (Δ), Theta (Θ) y Vega (V) netas agregadas para la cartera de opciones.
*   **Arquitectura Dual de Watchdogs**:
    *   **Watchdog de Entradas**: Evalúa condiciones avanzadas del mercado (umbrales del índice de volatilidad VIX, cruces de media móvil simple SMA, precio del subyacente y ventanas de horarios). Encola órdenes y gestiona su ciclo de vida y validez.
    *   **Watchdog de Salidas**: Monitoriza en tiempo real las posiciones activas para ejecutar el cierre automático (Take Profit, Stop Loss, filtro VIX, filtro SMA, cierre horario o expiración natural del contrato).
*   **Gestión Inteligente de Validez (TIF: DAY / GTC)**:
    *   **DAY**: Órdenes válidas durante el día de negociación. El Watchdog ejecuta una **rutina de limpieza offline** al iniciar la plataforma para cancelar y alertar sobre órdenes DAY del día anterior no ejecutadas.
    *   **GTC (Good-Til-Canceled)**: Órdenes persistentes que sobreviven al cierre de mercado y a las desconexiones temporales de la plataforma.
*   **Modo Defensa TFG (Mock Fallback)**: Sistema defensivo inteligente ante la falta de cotización o mercados cerrados. Si falla la definición del contrato, simula ejecuciones exitosas para asegurar la continuidad de la demostración visual frente al tribunal.
*   **Auditoría y Seguridad**:
    *   Control de acceso cifrado mediante hash **SHA-256**.
    *   Registro inmutable de logs en base de datos local SQLite para transacciones, conexiones e incidencias.
    *   Notificación instantánea de cambios de estado a través de Webhooks de Discord.

---

## 🛠️ Stack Tecnológico

-   **Lenguaje**: Python (v3.13)
-   **Frontend**: Streamlit con estilos personalizados premium Glassmorphism (Modo Oscuro)
-   **Backend & Concurrencia**: `ib_insync`, `asyncio`, `nest_asyncio` (Bucle de eventos asíncronos desacoplado)
-   **Cálculo Científico**: `numpy`, `scipy`, `pandas` (Black-Scholes, Griegas, SMA)
-   **Persistencia**: `sqlite3`
-   **Seguridad**: `hashlib` (SHA-256)
-   **Comunicaciones**: Integración HTTP Webhooks (Discord API)
-   **DevOps y Calidad**: `docker`, `docker-compose`, `pytest`

---

## ⚙️ Instalación y Configuración

### Prerrequisitos
1.  **Python 3.13** (o compatible v3.11+).
2.  **Interactive Brokers (IBKR) Gateway o TWS** activo en Paper Trading (puerto predeterminado `4002`). Asegurar que está marcada la opción *"Enable ActiveX and Socket Clients"* en la configuración del bróker.

### Ejecución Local

1.  **Clonar el repositorio y preparar el entorno virtual:**
    ```bash
    git clone https://github.com/carlos-novo/TFG_Opciones.git
    cd TFG_Opciones
    python -m venv .venv
    
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

2.  **Instalar dependencias de ejecución:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configurar variables de entorno:**
    Copia el archivo de variables de entorno de muestra y ajusta las credenciales:
    ```bash
    cp .env.example .env
    ```

4.  **Lanzar la interfaz web (Streamlit):**
    ```bash
    streamlit run app_web.py
    ```

---

## 🐳 Ejecución con Docker (Recomendado)

Si prefieres ejecutar el sistema de forma aislada y contenerizada mediante Docker Desktop:
```bash
docker-compose up --build
```
La aplicación web estará disponible en: `http://localhost:8501`.

### 🔐 Credenciales de Acceso por Defecto
*   **Usuario**: `admin`
*   **Contraseña**: `admin2026`

---

## 🧪 Pruebas Unitarias

La plataforma cuenta con un completo juego de pruebas unitarias que simulan mediante Mocks la interacción con Interactive Brokers, eliminando la necesidad de conexión activa al bróker para verificar la integridad del código:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

El repositorio utiliza integración continua (GitHub Actions) para compilar y testear de forma automatizada cada commit subido a la rama principal.

---

*Trabajo de Fin de Grado — Universidad 2025/2026.*