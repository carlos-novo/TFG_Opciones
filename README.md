# OptiTrack-IBKR: Plataforma Algorítmica de Negociación de Opciones

**OptiTrack-IBKR** es un sistema de trading algorítmico de alta fidelidad diseñado para la gestión y ejecución automatizada de estrategias de opciones financieras complejas, con un enfoque específico en la estructura **Iron Condor**. La plataforma actúa como un middleware avanzado entre el analista cuantitativo y el mercado real a través de la infraestructura de **Interactive Brokers (IBKR)**.

## 🛠️ Stack Tecnológico
* **Frontend / UI:** Streamlit
* **Middleware / Red:** `ib_insync`, `asyncio`, `nest_asyncio`
* **Cálculo Cuantitativo:** Pandas, Numpy
* **Persistencia:** SQLite3
* **Seguridad:** hashlib (SHA-256)

## 🎓 Justificación Académica (Ingeniería Telemática)

Este proyecto se ha desarrollado como Trabajo de Fin de Grado en **Ingeniería Telemática**, abordando desafíos críticos en la ingeniería de software distribuido y de baja latencia:

* **Concurrencia de Red y Asincronismo:** Implementación de una arquitectura no bloqueante mediante `asyncio` y `nest_asyncio`, permitiendo la convivencia de flujos de datos en tiempo real provenientes de la API de IBKR (Puerto 4002) con una interfaz de usuario reactiva.
* **Arquitectura de Micro-sesiones:** Diseño de un patrón de comunicación eficiente que gestiona de forma aislada la obtención de datos históricos, la consulta de puntas de mercado (Bid/Ask) y el envío de órdenes, evitando la saturación de sockets y la generación de hilos "zombis".
* **Persistencia y Gestión de Estado:** Implementación de un motor de persistencia local para garantizar la integridad de los datos y la recuperación del estado del sistema ante desconexiones de red.
* **Seguridad Telemática:** Aplicación de protocolos de control de acceso basados en estándares criptográficos para la protección de la operativa financiera.

## 📈 Flujo de Negocio (Core Logic)

El sistema opera bajo un flujo determinista basado en reglas para minimizar el riesgo operativo y maximizar la precisión en la entrada:

1.  **Evaluación de Condiciones Algorítmicas:** El motor utiliza la librería `Pandas` para procesar series temporales de precios históricos, calculando la **Media Móvil Simple (SMA)**. La estrategia solo se autoriza si el precio actual respeta la regla técnica definida (p. ej., Precio > SMA 200).
2.  **Extracción de Puntas de Mercado:** Se realiza una consulta simultánea de las primas reales (**Bid/Ask**) para las cuatro patas que componen el Iron Condor (Long Put, Short Put, Short Call, Long Call).
3.  **Cálculo Cuantitativo de Riesgo:** Basándose en los diferenciales reales de mercado, el sistema calcula el **Crédito Neto**, el **Beneficio Máximo** y el **Riesgo Máximo**. Este paso es crítico para descartar estrategias donde el *spread* de mercado degrada la relación Riesgo/Beneficio.
4.  **Ejecución de Orden Combo:** Una vez validada la estrategia, el sistema construye una orden compleja de tipo **BAG (Combo)**, garantizando que las cuatro operaciones se ejecuten de forma atómica para evitar el riesgo de ejecución parcial.

## 🔐 Seguridad y Auditoría

Dada la naturaleza financiera del proyecto, se han integrado capas de seguridad siguiendo los principios de las normativas **Fintech**:

* **Autenticación Blindada:** El acceso a la plataforma está restringido mediante un sistema de credenciales que utiliza **hashing SHA-256**. El sistema nunca almacena contraseñas en texto plano, comparando únicamente los hashes unidireccionales para autorizar la sesión.
* **Audit Trail Inmutable:** Todas las acciones críticas (accesos de usuario, validaciones del algoritmo, bloqueos por condiciones técnicas y ejecuciones) se registran en una base de datos **SQLite**. Este registro de auditoría es inmutable y proporciona una trazabilidad completa para el análisis post-operativo y el cumplimiento de requisitos de transparencia.
* **Aislamiento de Sesiones:** La plataforma gestiona estados de sesión volátiles, forzando la re-autenticación y el cierre seguro de sockets en caso de reinicios o pérdida de foco de la aplicación.

---

## 📌 Documentación Adjunta y Directrices de Desarrollo

El punto de entrada principal del sistema es `app_web.py` (ejecutado vía `streamlit run app_web.py`). 

**Nota obligatoria para IAs de Programación y Desarrolladores:** Al realizar modificaciones en el código, respete siempre la arquitectura de separación de capas (MVC) y asegúrese de que cualquier nueva funcionalidad de red se implemente de forma asíncrona. 
* Consulte **`ARCHITECTURE.md`** para conocer las restricciones estrictas del código y del entorno Streamlit.
* Consulte **`TODO.md`** para el seguimiento de bugs activos y próximos hitos.