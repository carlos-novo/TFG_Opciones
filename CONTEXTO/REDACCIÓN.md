# Documentación Técnica y Memoria del Trabajo de Fin de Grado (TFG)

## Plataforma Algorítmica de Negociación Multileg y Direccional (OptiTrack-IBKR)

**Autor:** Carlos Novo  
**Grado:** Ingeniería Telemática  
**Tutoría y Centro:** Escuela Politécnica Superior — Universidad de Alcalá (UAH)  
**Proyecto:** Trabajo de Fin de Grado (TFG)  

---

## 1. Introducción y Objetivos

### 1.1. Definición del Problema y Motivación
El desarrollo de los mercados financieros contemporáneos requiere sistemas con una velocidad de procesamiento de datos, precisión matemática y disciplina operativa que superan las capacidades de la ejecución humana manual. En el ámbito de los derivados financieros —especialmente en opciones sobre acciones e índices— la complejidad computacional aumenta al gestionar combinaciones de múltiples patas (estrategias *multileg* como *Spreads*, *Iron Condors* o *Straddles*). La gestión manual de estas operativas expone al usuario a problemas telemáticos y financieros críticos:
*   **Deslizamiento de Precios (*Slippage*):** Latencia en la transmisión de órdenes que degrada el precio de ejecución respecto al cotizado.
*   **Errores Operativos Humanos:** Fallos en el enrutamiento de tipos de contrato, cantidades o límites.
*   **Imposibilidad de Monitorización Continua:** Dificultad para mantener bucles de supervisión 24/7 sobre variables de volatilidad implícita ($VIX$), medias móviles ($SMA$) y límites financieros ($Stop\ Loss$ / $Take\ Profit$).

La motivación de este Trabajo de Fin de Grado reside en el diseño e implementación de un *middleware* algorítmico local de grado profesional. La plataforma automatiza el análisis cuantitativo, la valoración teórica, la ejecución asíncrona de órdenes y el control de riesgo reactivo mediante la infraestructura API del bróker institucional **Interactive Brokers (IBKR)**.

### 1.2. Objetivos Técnicos y Funcionales
Para responder a los requisitos de la titulación de **Ingeniería Telemática**, el proyecto se estructura en los siguientes objetivos:

#### Objetivos Técnicos (Ingeniería de Software y Redes):
1.  **Ejecución Asíncrona y Baja Latencia:** Diseñar una arquitectura desacoplada basada en bucles de eventos asíncronos (`asyncio`) e hilos daemon en segundo plano (*Watchdogs*) para la transmisión eficiente de datos financieros sobre sockets TCP/IP.
2.  **Resiliencia y Persistencia Dual:** Garantizar la tolerancia a fallos ante caídas de red o desconexiones de la API de IBKR mediante una base de datos **SQLite** con motor de caché de sesión (`session_cache`).
3.  **Seguridad Telemática:** Implementar un subsistema de autenticación mediante hashing criptográfico **SHA-256** y registro inmutable de auditoría para todas las transacciones.
4.  **Verificación y Calidad de Código:** Desarrollar una suite completa de pruebas unitarias (`pytest`) para validar la robustez del backend en entornos simulados y sin dependencias externas.

#### Objetivos Funcionales (Lógica de Negocio):
1.  **Operativa Direccional y Multileg:** Soportar la negociación automatizada de acciones direccionales simples (STK) y combos de opciones de hasta 4 patas (BAG).
2.  **Motor Cuantitativo de Valoración:** Integrar el modelo matemático de **Black-Scholes** para tarificar primas teóricas en tiempo real y evaluar las Griegas agregadas ($\Delta, \Theta, \mathcal{V}$).
3.  **Gestión de Validez de Orden (TIF):** Incorporar soporte nativo para órdenes `DAY` y `GTC` (*Good-Til-Canceled*), con rutinas de conciliación de cartera y limpieza offline.

---

## 2. Contexto Teórico y Estado del Arte

### 2.1. Marco Financiero para la Contextualización Técnica
A modo de contextualización estricta sobre el dominio de aplicación del software:
*   **Acciones (Equity):** Activos de renta variable con relación lineal respecto a la variación de precio del subyacente.
*   **Opciones Financieras (Derivados):** Contratos asimétricos que otorgan el derecho de compra (*Call*) o venta (*Put*) de un subyacente a un precio fijado (*Strike*) y fecha límite (*Vencimiento*).
    *   *Prima Teórica:* El valor de mercado de una opción combina su *valor intrínseco* y su *valor temporal*.
    *   *Griegas principales:* Miden la sensibilidad del precio de la opción respecto al subyacente (Delta $\Delta$), el paso del tiempo (Theta $\Theta$) y la volatilidad (Vega $\mathcal{V}$).
*   **Modelo Black-Scholes (1973):** Ecuación diferencial parcial empleada en la plataforma para determinar el precio justo teórico de opciones europeas:

$$C = S \cdot N(d_1) - K \cdot e^{-rT} \cdot N(d_2)$$

$$P = K \cdot e^{-rT} \cdot N(-d_2) - S \cdot N(-d_1)$$

$$\text{donde } d_1 = \frac{\ln(S/K) + (r + \frac{\sigma^2}{2})T}{\sigma \sqrt{T}} \quad \text{y} \quad d_2 = d_1 - \sigma \sqrt{T}$$

### 2.2. Protocolos de Integración Financiera y Estado del Arte
La evolución del trading algorítmico ha estado ligada al desarrollo de protocolos de comunicaciones e interfaces de programación:
1.  **Protocolo FIX (Financial Information eXchange):** Protocolo estándar de capa de aplicación para el intercambio electrónico de transacciones financieras. Aunque altamente eficiente, su complejidad exige intermediación por motores de gateway.
2.  **APIs Socket TCP/IP Nativas de Brókers:** Estándar adoptado por brókers institucionales como Interactive Brokers. Proporcionan un flujo binario/texto de baja latencia sobre sockets TCP en puertos dedicados (`4002` para Paper Trading / `7497` para producción).
3.  **Capas de Abstracción Asíncronas (`ib_insync`):** Biblioteca moderna sobre Python `asyncio` que encapsula la API basada en callbacks de IBKR en corrutinas no bloqueantes, solucionando los cuellos de botella de sincronización entre el hilo principal de la UI y las respuestas del bróker.

---

## 3. Diseño y Arquitectura del Sistema (El Núcleo Telemático)

### 3.1. Topología de la Solución y Diseño de Red Local
La arquitectura está diseñada como una topología local desacoplada por capas donde el middleware se comunica con el servidor de la pasarela mediante sockets de red:

```
+-----------------------------------------------------------------------+
|                    CAPA DE PRESENTACIÓN (Streamlit)                   |
|          Dashboard | Acciones | Constructor Opciones | Control Room   |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                      CAPA DE GESTIÓN Y PERSISTENCIA                   |
|             Base de Datos SQLite (tfg_trading.db & session_cache)     |
+-----------------------------------+-----------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                 MOTOR ALGORÍTMICO Y LÓGICA EN BACKGROUND              |
|      Watchdog Entradas (Daemon Thread) | Watchdog Salidas (Daemon Thread) |
|      Motor Black-Scholes (Py)          | Motor de Reglas Lógicas          |
+-----------------------------------+-----------------------------------+
                                    |
                                    v (Llamadas asíncronas asyncio)
+-----------------------------------------------------------------------+
|                      CLIENTE API Y CONEXIÓN BRÓKER                    |
|             Biblioteca ib_insync (Conexión Asíncrona TCP)              |
+-----------------------------------+-----------------------------------+
                                    | Socket TCP/IP (Puerto 4002 / 7497)
                                    v
+-----------------------------------------------------------------------+
|                PASARELA BRÓKER (TWS / IBKR Gateway)                   |
+-----------------------------------------------------------------------+
```

### 3.2. Integración con la API de IBKR vía `ib_insync`
La conexión con Interactive Brokers se administra en `conexion_ibkr.py` a través de la clase `GestorIBKR`:
*   **Bucle de Eventos Asíncrono (`nest_asyncio`):** Permite ejecutar corrutinas de `ib_insync` dentro del hilo ejecutor de Streamlit sin bloquear el refresco de la pantalla.
*   **Cadenas de Opciones Reales (`reqSecDefOptParams`):** Consume los parámetros de definición de contratos reales desde IBKR para obtener strikes y vencimientos vigentes en el mercado.
*   **Contratos BAG Dinámicos:** Método `construir_contrato_bag_dinamico` que empaqueta múltiples patas en un único objeto `Contract` de tipo `BAG` con `ComboLegs`, garantizando la ejecución atómica de la combinación en el bróker.

### 3.3. Modelado de Datos en SQLite y Caché de Sesión
La persistencia se gestiona mediante la clase `GestorBaseDatos` en `base_datos.py`:
*   **Tabla `estrategias`:** Almacena parámetros de entrada, JSON de condiciones, estado de la orden (`PENDIENTE_ENTRADA`, `ORDEN_ENVIADA`, `ACTIVA`, `CANCELADA`, `CERRADA_...`) y referencias TIF.
*   **Tabla `auditoria`:** Registro inmutable de transacciones, ejecuciones y errores.
*   **Tabla `session_cache` (Mecanismo Resiliente):** Diseñada bajo sintaxis `UPSERT` (`INSERT OR REPLACE INTO session_cache`), guarda los snapshots de cuenta y cartera cuando la plataforma está conectada a IBKR. En caso de desconexión o arranque offline, el sistema lee de esta tabla para alimentar la UI sin recurrir a datos ficticios.

### 3.4. Mecanismos de Seguridad y Autenticación SHA-256
El acceso al sistema está protegido en `app_web.py` mediante el formulario `login_form`:
*   **Hash SHA-256:** La contraseña del usuario se procesa con `hashlib.sha256()`. El hash resultante se compara de forma segura con las credenciales configuradas en las variables de entorno.
*   **Trazabilidad de Accesos:** Cada intento genera automáticamente un registro en la tabla SQL de auditoría con la etiqueta `LOGIN_EXITOSO` o `LOGIN_FALLIDO` y sello temporal preciso.

---

## 4. Implementación y Desarrollo de Software

### 4.1. Justificación del Stack Tecnológico
*   **Python (v3.13):** Seleccionado como lenguaje principal por su manejo avanzado de concurrencia multihilo (`threading`), corrutinas (`asyncio`) y librerías científicas (`numpy`, `scipy`).
*   **Streamlit (Reactivo & Glassmorphism):** Empleado para construir el frontend web. Mediante la inyección de estilos CSS personalizados (`st.markdown`), se diseñó un tema visual *Glassmorphic Dark Mode* que ofrece una experiencia fluida al usuario.

### 4.2. Flujo de Desarrollo Asistido por IA (IDE Antigravity)
El desarrollo del proyecto se ejecutó en el entorno **Antigravity IDE**, aprovechando el flujo de trabajo en pareja (*pair programming*) con agentes de inteligencia artificial avanzados. Esta metodología permitió:
*   **Refactorización Guiada:** Aceleración en el diseño de clases desacopladas y refactorizaciones críticas del motor asíncrono.
*   **Resolución de Bugs Complejos:** Diagnóstico de carreras de crítico (*race conditions*) en Streamlit, resolviendo el problema de re-ejecución involuntaria de diálogos modales mediante flags de estado en `st.session_state`.
*   **Generación de Tests:** Creación automatizada de Mocks para pruebas unitarias sin requerir conexión real a socket bróker.

### 4.3. Ingeniería de Backend: Hilos Daemon (Watchdogs) y Sincronización

La plataforma utiliza dos hilos secundarios independientes iniciados como daemons (`threading.Thread(daemon=True)`):

#### A. Watchdog de Entradas (Evaluación Lógica AND)
Implementado en `MotorEstrategias.evaluar_condiciones_entrada` ([motor_logica.py](file:///c:/Users/canol/Desktop/Universidad/2025-2026/2-Cuatrimestre/TFG_Opciones/motor_logica.py#L80-L201)), aplica una **lógica condicional AND**. Exige que todas las condiciones activas se cumplan para autorizar la entrada:

$$\text{Autorizado} = \text{Condición}_{\text{Horario}} \land \text{Condición}_{\text{VIX}} \land \text{Condición}_{\text{SMA}} \land \text{Condición}_{\text{Precio}}$$

*   **Rutina Offline de Limpieza TIF `DAY`:** Si el bróker está desconectado, busca estrategias `ORDEN_ENVIADA` con validez `DAY` de días anteriores y las transiciona a `CANCELADA` por expiración diaria.
*   **Reconciliación de Cartera:** Función `reconciliar_estrategias_con_cartera` que asocia ejecuciones reales detectadas en TWS con órdenes locales enviadas/canceladas, reactivándolas como `ACTIVA`.

#### B. Watchdog de Salidas (Evaluación Lógica OR)
Implementado en `MotorSalida.evaluar_condiciones_salida` ([motor_logica.py](file:///c:/Users/canol/Desktop/Universidad/2025-2026/2-Cuatrimestre/TFG_Opciones/motor_logica.py#L233-L325)), aplica una **lógica condicional OR (red de seguridad reactiva)**:

$$\text{Acción Salida} = \text{Trigger}_{\text{TP}} \lor \text{Trigger}_{\text{SL}} \lor \text{Trigger}_{\text{VIX\_Max}} \lor \text{Trigger}_{\text{Hora\_Cierre}} \lor \text{Trigger}_{\text{SMA\_Salida}}$$

*   Si el P&L actual o los filtros técnicos alcanzan cualquier límite, el motor emite la orden de salida inmediata, ejecuta la liquidación en el bróker y envía una alerta vía Discord Webhook.

---

## 5. Interfaz de Usuario y Flujos Operativos

La consola web se organiza en cuatro pestañas principales:

### 5.1. Dashboard (Consola Principal)
*   **Métricas y Cartera Limpia:** Visualiza NLV, Efectivo y Buying Power. La tabla de cartera filtra automáticamente cualquier activo con posición igual a cero ($\le 1e-5$).
*   **Liquidación Dinámica (Modal Dialogs):** Permite cerrar posiciones mediante diálogos modales (`@st.dialog`) controlados por flags de sesión para evitar cierres accidentales.
*   **Gráficos Plotly:** Renderiza gráficos interactivos de evolución histórica del NLV, asignación de activos (Donut Chart) y exposición por subyacente.

### 5.2. Pestaña Acciones (Orden Direccional)
*   Configuración de órdenes para acciones con selección de TIF (`DAY` / `GTC`).
*   Filtros avanzados de entrada (VIX, SMA, Precio disparador, Ventana horaria y Frecuencia).
*   **Stop Loss y Take Profit Independientes:** Checkboxes independientes para configurar uno o ambos límites a la vez.

### 5.3. Pestaña Opciones (Trading Multileg)
*   **Vencimiento Global:** Selección de la fecha de expiración común para toda la combinación.
*   **Leg Builder:** Construcción de hasta 4 patas con strikes reales/simulados y **Prima Teórica Inmodificable (Black-Scholes)** calculada dinámicamente.
*   **Calculadora de Griegas Netas:** Cálculo en tiempo real de $\Delta, \Theta, \mathcal{V}$ netos del combo.
*   **Superficie de Sensibilidad Plotly:** Gráfico interactivo con sliders de Volatilidad ($\sigma$), Tiempo ($T$) y Tasa ($r$) comparando la curva a vencimiento ($T=0$) y la curva temporal ($T=X$).

### 5.4. Pestaña Control Room (Supervisión)
*   Monitor de estado de hilos daemon (Watchdogs).
*   Grid de modificación de Stop Loss y Take Profit en caliente organizados por Ticker.
*   **Adopción de Posiciones Huérfanas:** Permite seleccionar activos de la cartera de TWS abiertos externamente e inyectarles reglas de salida algorítmicas.
*   Registro de auditoría filtrable.

---

## 6. Pruebas y Validación

La plataforma cuenta con un sistema completo de verificación local basado en `pytest`, diseñado para asegurar el correcto funcionamiento del software sin requerir conexión a mercado real:

### 6.1. Suite de Pruebas Unitarias (`pytest`)
Se han diseñado **47 pruebas unitarias** divididas en 6 módulos de test:
```text
tests\test_base_datos.py ......                                          [ 12%]
tests\test_conexion_ibkr.py ............                                 [ 38%]
tests\test_motor_bs.py .....                                             [ 48%]
tests\test_motor_logica.py ........                                      [ 65%]
tests\test_motor_salida.py .........                                     [ 85%]
tests\test_watchdogs.py .......                                          [100%]

======================== 47 passed, 1 warning in 2.36s ========================
```

### 6.2. Estrategias de Validación Evaluadas
1.  **Pruebas de Conexión y Mocks (`test_conexion_ibkr.py`):** Simulación de respuestas de socket IBKR para verificar el filtrado de posiciones con saldo `0.0` (`test_obtener_posiciones_cartera_filtra_cero`) y la reconciliación de órdenes (`test_reconciliar_estrategias_con_cartera`).
2.  **Precisión del Motor Cuantitativo (`test_motor_bs.py`):** Validación matemática de los precios de primas y Griegas de Black-Scholes comparando contra valores analíticos tabulados.
3.  **Lógica Condicional (`test_motor_logica.py` y `test_motor_salida.py`):** Comprobación del evaluador AND para entradas y del evaluador OR para salidas bajo diversas combinaciones de VIX, SMA y límites de P&L.
4.  **Robustez de Watchdogs y Modo Defensa (`test_watchdogs.py`):** Verificación de la rutina offline de cancelación de órdenes `DAY` caducadas y simulación defensiva ante desconexiones.
5.  **Fiabilidad de Alertas (Discord Webhooks):** Pruebas de integración HTTP para comprobar el formateo correcto de los JSON de notificación ante eventos de trading.

---

## 7. Conclusiones y Trabajo Futuro

### 7.1. Conclusiones Técnicas y Evaluaciones de Objetivos
*   **Cumplimiento de Requisitos Telemáticos:** Se ha demostrado la viabilidad de construir un *middleware* algorítmico local desacoplado, asíncrono y tolerante a fallos, utilizando la API de Interactive Brokers sobre sockets TCP/IP.
*   **Eficiencia en la Gestión de Riesgos:** La separación de responsabilidades entre el Watchdog de Entradas (evaluación restrictiva AND) y el Watchdog de Salidas (red de seguridad reactiva OR) garantiza un control de riesgos continuo y sin cuellos de botella en la ejecución.
*   **Resiliencia y Persistencia:** El uso de SQLite con caché de sesión (`session_cache`) y la lógica de reconciliación automática resuelven eficazmente los problemas de pérdida de estado tras cortes de red o reinicios de la aplicación.

### 7.2. Trabajo Futuro y Líneas de Investigación
*   **Modelos Binomiales para Opciones Americanas:** Incorporar el modelo de Cox-Ross-Rubinstein para la valoración exacta del riesgo de ejercicio anticipado.
*   **Superficie Real de Volatilidad Implícita (Volatility Skew):** Sustituir el parámetro de volatilidad constante por la lectura directa del *skew* de volatilidad de la cadena de opciones de IBKR.
*   **Módulo de Backtesting Histórico y Monte Carlo:** Integrar la capacidad de realizar pruebas retrospectivas sobre datos históricos de *tick data* antes del despliegue en mercado real.
*   **Despliegue Contenerizado en la Nube:** Empaquetar la aplicación completa en contenedores **Docker** sobre instancias de la nube (AWS / GCP) para garantizar su disponibilidad 24/7.
