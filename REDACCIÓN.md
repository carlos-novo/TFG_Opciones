# Documentación y Redacción Técnica del Software para el TFG

Este documento proporciona una guía detallada y estructurada de la arquitectura, componentes y funcionamiento del software desarrollado para la Plataforma Algorítmica Multileg y Direccional. Este archivo sirve como base teórica y descriptiva para la redacción de la memoria del Trabajo de Fin de Grado (TFG).

---

## 1. Arquitectura Tecnológica y Stack de Software

El sistema está desarrollado como una plataforma de trading algorítmico local de grado profesional, optimizada para interactuar en tiempo real con la API de **Interactive Brokers** (mediante **IBKR Gateway** o **TWS**).

### Stack de Software Principal:
*   **Lenguaje**: Python (v3.13), aprovechando su ecosistema para análisis de datos y concurrencia.
*   **Frontend**: Streamlit, empleado para renderizar una interfaz web interactiva rápida, fluida y con estilos personalizados (Glassmorphism de modo oscuro) mediante inserciones de CSS (`st.markdown`).
*   **Base de Datos**: SQLite (`tfg_trading.db`), utilizada para persistencia local de estrategias, logs de auditoría y estados.
*   **Integración de API de Trading**: `ib_insync`, biblioteca asíncrona construida sobre la API nativa de Interactive Brokers, permitiendo manejar bucles de eventos asíncronos (`asyncio`) de manera robusta.
*   **Cálculo Financiero**: Motor matemático de Black-Scholes para evaluar primas teóricas y griegas (Delta, Theta, Vega) de opciones financieras.
*   **Alertas**: Webhooks de Discord en formato JSON para monitorización de estados en tiempo real.

---

## 2. Acceso y Seguridad (Login de Usuario)

El acceso al software está protegido por una pantalla de inicio de sesión (`login_form` en `app_web.py`):
*   **Autenticación Hash**: Las credenciales no se almacenan ni evalúan en texto plano. La contraseña ingresada por el usuario es hasheada dinámicamente mediante el algoritmo criptográfico **SHA-256** antes de compararla con las credenciales autorizadas.
*   **Auditoría de Acceso**: Cada intento exitoso o fallido de inicio de sesión se registra automáticamente en la tabla de auditorías de la base de datos local con fecha y hora exacta (`LOGIN_EXITOSO`).

---

## 3. Estructura de la Interfaz: Las 4 Pestañas Principales

La interfaz gráfica principal está organizada en cuatro pestañas de control enfocadas en diferentes flujos operativos de la plataforma:

### Pestaña 1: Dashboard (Consola Principal)
Es el centro de control financiero de la cuenta de trading. Permite ver el estado actual del balance y portafolio en tiempo real:
*   **Métricas de Cuenta**: Muestra la Liquidación Neta (NLV), Efectivo Disponible y Poder de Compra (Margin / Buying Power) sincronizados con la sesión activa de IBKR.
*   **Tabla de Cartera**: Lista todas las posiciones abiertas, clasificándolas en acciones (STK) u opciones (OPT). Muestra la cantidad, coste medio de adquisición, valor de mercado actual y el P&L no realizado de cada posición.
*   **Liquidación Dinámica**: Permite hacer clic en un botón de liquidación para cerrar posiciones de forma total o parcial. El flujo incluye una ventana emergente (modal dialog) de confirmación que calcula dinámicamente el valor en dólares correspondiente al número de títulos o al importe introducido.
*   **Gráficos Interactivos**:
    *   *Evolución de Balance*: Gráfico de línea interactivo (Plotly) que muestra la evolución histórica del Net Liquidation Value contra el capital depositado.
    *   *Distribución de Activos*: Gráfico de tarta (Donut chart) que muestra la asignación porcentual de la cartera.
    *   *Diversificación por Subyacente*: Gráfico de barras horizontales indicando la exposición por símbolos (ej. AAPL, SPY, MSFT).

### Pestaña 2: Acciones (Orden Direccional)
Permite planificar y encolar estrategias sobre acciones con condiciones avanzadas de mercado:
*   **Parámetros de Orden**: Ticker del activo, Cantidad de acciones, Tipo de orden (Mercado o Límite) y **Validez de Orden (Time in Force - TIF)** configurable como `DAY` (expira al cierre de mercado) o `GTC` (válida hasta cancelarse).
*   **Condiciones de Entrada Avanzadas (Watchdog de Entradas)**:
    *   *Filtro VIX*: Permite condicionar el envío a que el índice de volatilidad VIX esté por encima o por debajo de cierto umbral.
    *   *Fila SMA*: Filtro de media móvil simple (SMA) evaluada históricamente (ej. precio > SMA 50).
    *   *Precio Disparador*: Condición de cruce de precio en el subyacente.
    *   *Horario*: Establece un rango horario operativo (ej. 15:30 a 22:00) o una hora fija.
    *   *Frecuencia*: Define si la orden es única o recurrente (Diaria / Semanal) para reprogramarse automáticamente tras ejecutarse.
*   **Condiciones de Salida (Watchdog de Salidas)**:
    *   *Stop Loss y Take Profit*: Se puede elegir si gestionarlo de manera nativa en el bróker (órdenes automáticas enviadas a TWS) o mediante el Watchdog local en caliente.
    *   *Salida por VIX, SMA o Cierre Horario*: Cierra la posición si el VIX se dispara, si el precio cruza una media móvil o si se llega a una hora específica.

### Pestaña 3: Opciones (Trading Multileg)
Permite construir complejas combinaciones multileg de opciones financieras:
*   **Leg Builder**: Constructor de hasta 4 patas operativas donde se define la acción (BUY/SELL), tipo (CALL/PUT), strike, vencimiento y cantidad para cada pata.
*   **Griego Net Calculator**: Sincroniza en tiempo real el precio medio bid/ask y calcula de manera teórica el **Delta (Δ)**, **Theta (Θ)** y **Vega (V)** neto de la combinación completa utilizando la volatilidad implícita y el motor de Black-Scholes.
*   **Parámetros Algorítmicos**: Define el precio neto de entrada (Débito o Crédito) y la validez TIF (`DAY` o `GTC`) para el combo completo.
*   **Condiciones de Entrada/Salida**: Permite aplicar los mismos filtros avanzados de volatilidad (VIX), medias móviles (SMA) y horarios que en la pestaña de acciones.

### Pestaña 4: Control Room (Monitorización del Sistema)
Es el panel de supervisión interna de los procesos del sistema:
*   **Consola de Watchdogs**: Muestra visualmente si los hilos daemon de Entradas y Salidas están corriendo en el backend.
*   **Grid de Estrategias**: Tabla que recopila todas las estrategias activas, pendientes o cerradas. Permite a los usuarios cambiar parámetros de SL/TP en caliente o liquidar manualmente una estrategia directamente desde la base de datos.
*   **Registro de Auditoría**: Visualizador interactivo de la tabla SQL de logs, mostrando alertas de Discord, órdenes enviadas, ejecuciones confirmadas e incidencias.

---

## 4. Funcionamiento del Motor de Watchdogs en Background

Los watchdogs son hilos secundarios (`threading.Thread` en modo daemon) que se inician junto al servidor web y ejecutan bucles continuos:

1.  **Watchdog de Entradas**:
    *   Monitorea estrategias en estado `PENDIENTE_ENTRADA`.
    *   Si el bróker está desconectado, aplica una **rutina offline**: busca estrategias `ORDEN_ENVIADA` con validez `DAY` creadas en días anteriores y las marca inmediatamente como `CANCELADA` por expiración temporal diaria.
    *   Si el bróker está conectado, evalúa las condiciones de entrada de las pendientes mediante `MotorEstrategias.evaluar_condiciones_entrada`.
    *   Si se cumplen, llama a `enviar_orden_generica` pasando el TIF asignado y transiciona el estado a `ORDEN_ENVIADA`.
    *   Si detecta que la orden de entrada se llenó (`Filled`), pasa el estado a `ACTIVA` y lanza alertas de Discord. Si la orden ya no existe y es `DAY`, la expira; si es `GTC`, la cancela debido a la caída de conexión o acción manual del usuario.
2.  **Watchdog de Salidas**:
    *   Monitorea estrategias en estado `ACTIVA`.
    *   Calcula en tiempo real el P&L agregado de la combinación mediante `broker.calcular_pnl_estrategia`.
    *   Evalúa reglas de salida (`MotorSalida.evaluar_condiciones_salida`) relativas a límites financieros (Stop Loss / Take Profit), filtros técnicos (SMA), volatilidad (VIX) o vencimiento natural (expiración de contratos en opciones).
    *   Al activarse un disparador, envía la orden de cierre al bróker, liquida la posición, actualiza el estado a `CERRADA_...` y reprograma la recurrencia si procede.
