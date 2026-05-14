# 🦅 OptiTrack-IBKR: Plataforma Algorítmica de Negociación de Opciones

[![Tests](https://github.com/USER/OptiTrack-IBKR/actions/workflows/tests.yml/badge.svg)](https://github.com/USER/OptiTrack-IBKR/actions)

**OptiTrack-IBKR** es un sistema de trading algorítmico de alta fidelidad diseñado para la gestión y ejecución automatizada de estrategias de opciones financieras, con un enfoque específico en la estructura **Iron Condor**. La plataforma actúa como un middleware avanzado entre el analista cuantitativo y el mercado real a través de la infraestructura de **Interactive Brokers (IBKR)**.

Desarrollado como **Trabajo de Fin de Grado en Ingeniería Telemática**, este proyecto aborda desafíos críticos en la ingeniería de software distribuido, manejo de concurrencia asíncrona (patrón *Bulk Session*) y sistemas de baja latencia.

---

## 🚀 Prerrequisitos

Para ejecutar este proyecto, necesitas:

1. **Python 3.11+**
2. **Interactive Brokers (IBKR) Gateway o TWS** activo y configurado para aceptar conexiones API.
   - Puerto de conexión: `4002` (Paper Trading).
   - *Activar la opción "Enable ActiveX and Socket Clients" en los ajustes de la API.*

---

## ⚙️ Instalación y Configuración

1. **Clonar el repositorio y preparar el entorno virtual:**
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd TFG_Opciones
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. **Instalar las dependencias de ejecución:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar las variables de entorno:**
   Copia el archivo de ejemplo y asegúrate de que los parámetros de conexión son correctos.
   ```bash
   cp .env.example .env
   ```

---

## 🏃‍♂️ Ejecución

El proyecto utiliza **Streamlit** como frontend reactivo. Para levantar la aplicación:

```bash
streamlit run app_web.py
```

### 🔐 Credenciales de Acceso
El sistema incorpora control de acceso mediante hashing SHA-256. 
- **Usuario:** `admin`
- **Contraseña:** `admin2026`

---

## 📐 Reglas Operativas (Importante)

Debido a las restricciones de la API de IBKR y a la estructura del mercado de opciones, debes respetar las siguientes reglas al operar en el simulador:

- **Activos Soportados:** Principalmente diseñado para operar sobre el índice **SPX**.
- **Strikes (Precios de Ejercicio):** Los strikes introducidos deben ser **múltiplos exactos de 100** (ej. 5300, 5400). Los incrementos de 50 puntos (ej. 5350) no están soportados de forma generalizada en los históricos simulados.
- **Vencimientos:** Es obligatorio utilizar vencimientos semanales (**SPXW**), preferiblemente con strikes en un rango de ±200-300 puntos respecto al precio *spot* actual para asegurar liquidez simulada.

---

## 🛠️ Stack Tecnológico

- **Frontend:** Streamlit (Arquitectura Flat MVC)
- **Red / Concurrencia:** `ib_insync`, `asyncio`, `nest_asyncio` (diseño *Bulk Session* con micro-sesiones efímeras)
- **Motor Financiero:** `pandas`, `numpy`, `scipy` (Filtros Algorítmicos SMA, Black-Scholes y Greeks)
- **Persistencia:** `sqlite3` (Audit Trail Inmutable)
- **Seguridad:** `hashlib` (SHA-256)

---

## 🧪 Testing y CI

Para ejecutar la batería de pruebas localmente (no requiere conexión a IBKR, inyecta objetos Mock):

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
El repositorio cuenta con integración continua (GitHub Actions) que automatiza estas pruebas en cada commit.

---

*Proyecto académico — Universidad 2025/2026.*