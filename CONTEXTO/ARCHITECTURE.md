# ARCHITECTURE.md: Manual de Reglas Técnicas y Arquitectura

**ATENCIÓN DESARROLLADORES Y ASISTENTES DE IA:** Este documento define las directrices arquitectónicas estrictas del proyecto. Cualquier modificación, refactorización o adición de código **DEBE** cumplir obligatoriamente con las reglas aquí estipuladas. Violar estas restricciones comprometerá la estabilidad del sistema, la integridad de los datos de Streamlit o la conectividad con el bróker.

---

## 1. Estructura del Proyecto (Flat MVC)

El proyecto utiliza una **Estructura Plana (Flat Structure)** en el directorio raíz. Está estrictamente **PROHIBIDO** anidar estos archivos en subcarpetas (como `/src`, `/backend` o `/frontend`) para evitar colisiones de rutas y fallos de resolución de dependencias inherentes al servidor de Streamlit.

Cada archivo tiene una responsabilidad única y aislada:

* **`app_web.py` (Presentación / Estado):** Punto de entrada. Su responsabilidad es renderizar la UI de las 4 pestañas, capturar inputs, gestionar el estado de sesión y orquestar a los demás módulos. **Cero** lógica de cálculo o llamadas directas a red en las vistas.
* **`conexion_ibkr.py` (Middleware / Red IBKR):** Gestor exclusivo de la comunicación asíncrona con la API de Interactive Brokers a través de `ib_insync`. Mantiene la instancia `GestorIBKR` y construye contratos de acciones (STK) e índices/combos (BAG).
* **`motor_logica.py` (Lógica Cuantitativa y Reglas):** El cerebro algorítmico. Evalúa las reglas condicionales de entrada (Evaluador Lógico AND) y las reglas de salida por Stop Loss, Take Profit o filtros (Evaluador Lógico OR).
* **`motor_bs.py` (Motor Cuantitativo de Black-Scholes):** Calcula primas teóricas y Griegas ($\Delta, \Theta, \mathcal{V}$) para contratos de opciones sobre la distribución normal acumulada.
* **`watchdogs.py` (Autómatas de Background):** Hilos secundarios daemon (`threading.Thread`) que ejecutan en segundo plano los bucles del Watchdog de Entradas y Watchdog de Salidas, reconciliación de cartera y alertas a Discord.
* **`base_datos.py` (Persistencia / Auditoría / Caché):** Gestor único de operaciones E/S contra disco (`tfg_trading.db` en SQLite). Administra el esquema de estrategias (JSON), auditoría y la tabla `session_cache`.

---

## 2. Restricciones del Frontend (Streamlit)

La interfaz web funciona bajo el paradigma reactivo de Streamlit, el cual exige respetar las siguientes reglas inmutables:

* **Recarga Descendente:** En cada interacción del usuario (click, cambio de input), el script `app_web.py` se re-ejecuta de arriba a abajo.
* **Estado de Variables:** Es **OBLIGATORIO** el uso de `st.session_state` para mantener cualquier variable o conexión activa entre recargas. Las variables globales estándar en el archivo principal están prohibidas.
* **Control de Diálogos Modales (`@st.dialog`):** Las ventanas modales emergentes (como la confirmación de liquidación o cotizaciones) deben invocarse utilizando **flags de estado** en `st.session_state` (ej. `show_cotizacion_dialog`) fuera de los bloques condicionales de botones. Esto evita que el modal se cierre involuntariamente debido al rerun del script.
* **Bloqueo del Hilo Principal:** Queda terminantemente **PROHIBIDO** el uso de bucles infinitos (`while True`), pausas largas (`time.sleep()`) o escuchas de sockets bloqueantes dentro de `app_web.py`.

---

## 3. Restricciones del Middleware (IBKR API y Resiliencia)

La integración con Interactive Brokers (vía `ib_insync`) debe adaptarse a la arquitectura multihilo y a la tolerancia a fallos de red:

* **Compatibilidad Asíncrona:** Es **OBLIGATORIO** invocar `nest_asyncio.apply()` antes de inicializar cualquier bucle de eventos o conexión de red para evitar el error *Event loop is already running*.
* **Conexión Persistente y Hilos Background:** A diferencia de las micro-sesiones efímeras, la plataforma administra la conexión de forma persistente en `st.session_state.broker` y a través de los hilos Watchdog. 
* **Modo Resiliente y Caché de Sesión (`session_cache`):** Si la conexión con IBKR se interrumpe o la plataforma arranca sin bróker (modo offline), el sistema **NO** falla. Lee prioritariamente los snapshots de cuenta y posiciones almacenados en la tabla `session_cache` de SQLite.
* **REGLA DE ORO DE LOS ACTIVOS:** La API es estricta con la taxonomía financiera. Es obligatorio diferenciar explícitamente entre acciones e índices.

```python
# EJEMPLO OBLIGATORIO DE TIPOLOGÍA DE CONTRATO
if ticker.upper() == 'SPX':
    # SPX es un índice, requiere Index y exchange CBOE
    contrato = Index('SPX', 'CBOE', 'USD')
else:
    # SPY y demás activos operables estándar son Stocks
    contrato = Stock(ticker, 'SMART', 'USD')
```

* **Ejecución Atómica de Combos (BAG):** Las estrategias de opciones de hasta 4 patas deben empaquetarse en un único contrato `BAG` mediante `ComboLegs` (`construir_contrato_bag_dinamico`) para ser ejecutadas atómicamente en el bróker sin riesgo de ejecución parcial por patas (*leg risk*).

---

## 4. Restricciones de Persistencia (SQLite)

El servidor de Streamlit es susceptible a sufrir un desplazamiento del directorio de trabajo (*Working Directory Shift*) dependiendo de desde dónde lance el comando de terminal el usuario.

* **Prohibición de Rutas Relativas:** Está **PROHIBIDO** instanciar la base de datos usando strings planos (ej. `sqlite3.connect('tfg_trading.db')`), ya que provocará la creación de archivos fantasma en directorios temporales, reseteando la auditoría.
* **Uso de Rutas Absolutas (Dunder File):** El archivo `base_datos.py` **DEBE** anclar su ruta forzando la escritura en la misma carpeta donde reside el propio script utilizando `os.path.abspath(__file__)`.

```python
# IMPLEMENTACIÓN OBLIGATORIA EN base_datos.py
import os
import sqlite3

# 1. Obtener la ruta del directorio donde está base_datos.py
directorio_actual = os.path.dirname(os.path.abspath(__file__))

# 2. Construir la ruta absoluta y conectar
db_path = os.path.join(directorio_actual, 'tfg_trading.db')
conexion = sqlite3.connect(db_path)
```

* **Política de Caché `UPSERT`:** La tabla `session_cache` utiliza sentencias de actualización condicional (`INSERT OR REPLACE INTO session_cache`) para garantizar que la caché de cuenta y cartera se mantenga actualizada en cada iteración exitosa con IBKR.