# ARCHITECTURE.md: Manual de Reglas Técnicas y Arquitectura

**ATENCIÓN DESARROLLADORES Y ASISTENTES DE IA:** Este documento define las directrices arquitectónicas estrictas del proyecto. Cualquier modificación, refactorización o adición de código **DEBE** cumplir obligatoriamente con las reglas aquí estipuladas. Violar estas restricciones comprometerá la estabilidad del sistema, la integridad de los datos de Streamlit o la conectividad con el bróker.

---

## 1. Estructura del Proyecto (Flat MVC)

El proyecto utiliza una **Estructura Plana (Flat Structure)** en el directorio raíz. Está estrictamente **PROHIBIDO** anidar estos archivos en subcarpetas (como `/src`, `/backend` o `/frontend`) para evitar colisiones de rutas y fallos de resolución de dependencias inherentes al servidor de Streamlit.

Cada archivo tiene una responsabilidad única y aislada:

* **`app_web.py` (Presentación / Estado):** Punto de entrada. Su única responsabilidad es renderizar la UI, capturar inputs, gestionar el estado de sesión y orquestar a los demás módulos. **Cero** lógica de cálculo o llamadas directas a red aquí.
* **`conexion_ibkr.py` (Middleware / Red IBKR):** Gestor exclusivo de la comunicación asíncrona con la API de Interactive Brokers.
* **`motor_logica.py` (Lógica Cuantitativa):** El cerebro de cálculo. Realiza vectorización matemática con Pandas y simulaciones de P&L. No tiene conocimiento del bróker ni de la interfaz web.
* **`base_datos.py` (Persistencia / Auditoría):** Gestor único de operaciones E/S contra disco (SQLite).
* **`opcion.py` (Data Class):** Modelo de datos puro para definir contratos y parametrizar las estrategias.

---

## 2. Restricciones del Frontend (Streamlit)

La interfaz web funciona bajo el paradigma reactivo de Streamlit, el cual exige respetar las siguientes reglas inmutables:

* **Recarga Descendente:** En cada interacción del usuario (click, cambio de input), el script `app_web.py` se re-ejecuta de arriba a abajo.
* **Estado de Variables:** Es **OBLIGATORIO** el uso de `st.session_state` para mantener cualquier variable o conexión activa entre recargas. Las variables globales estándar están prohibidas.
* **Bloqueo del Hilo Principal:** Queda terminantemente **PROHIBIDO** el uso de bucles infinitos (`while True`), pausas largas (`time.sleep()`) o escuchas de WebSockets persistentes dentro de `app_web.py`.

---

## 3. Restricciones del Middleware (IBKR API)

La integración con Interactive Brokers (vía `ib_insync`) debe adaptarse al entorno síncrono de la aplicación web:

* **Compatibilidad Asíncrona:** Es **OBLIGATORIO** invocar `nest_asyncio.apply()` antes de inicializar cualquier bucle de eventos o conexión de red para evitar el error *Event loop is already running*.
* **Patrón 'Bulk Session' (Micro-sesiones):** El sistema **NO** mantiene una conexión perenne. La conexión a IBKR se abre, se realiza la descarga en bloque de las primas (las 4 patas de la opción simultáneamente) y se cierra inmediatamente. Este patrón previene la generación de 'hilos zombis' y la saturación del puerto 4002.
* **REGLA DE ORO DE LOS ACTIVOS:** La API es estricta con la taxonomía financiera. Es obligatorio diferenciar explícitamente entre acciones e índices.

```python
# EJEMPLO OBLIGATORIO DE TIPOLOGÍA DE CONTRATO
if ticker.upper() == 'SPX':
    # SPX es un índice, requiere Index y un exchange específico
    contrato = Index('SPX', 'CBOE', 'USD')
else:
    # SPY y demás activos operables estándar son Stocks
    contrato = Stock(ticker, 'SMART', 'USD')
```
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