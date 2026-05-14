# 🎯 NUEVA HOJA DE RUTA — TFG Opciones Financieras
**Documento único y definitivo. Reemplaza TODO.md y HOJA_RUTA.md.**
**Fecha de creación:** 14/05/2026 | **Feature Freeze:** 21/05/2026 | **Entrega:** ~11/06/2026

---

## PARTE 1 — EVALUACIÓN CRÍTICA (modo tribunal)

### ✅ Hitos con Alto Valor Académico (destacar en la memoria)

Estos son los que el tribunal valorará porque demuestran **dominio de ingeniería real**, no solo código funcional.

| Hito | Por qué impresiona al tribunal |
|---|---|
| **Patrón Bulk Session (micro-sesiones)** | Demuestra comprensión profunda de la concurrencia. Resolver el conflicto Streamlit+asyncio con `nest_asyncio` + `IB()` efímero por flujo es un diseño arquitectónico no trivial. Documéntalo como tu mayor contribución de diseño. |
| **Cálculo Bid/Ask real sobre 4 patas simultáneas** | Es técnicamente correcto: ingreso = `Short_Put_Bid + Short_Call_Bid`, coste = `Long_Put_Ask + Long_Call_Ask`. El batch qualifying + batch snapshot en una sola sesión es eficiente. Tiene valor directo en el capítulo de Implementación. |
| **Filtro SMA con Pandas + lógica de decisión algorítmica** | Demuestra uso de análisis técnico cuantitativo. El patrón `evaluar_condicion_sma()` es demostrable, reproducible y explicable. Es tu "algoritmo" de entrada al mercado. |
| **Envío de orden BAG (Iron Condor completo)** | `placeOrder()` con `LimitOrder(lmtPrice=-credito)` sobre un combo de 4 patas es lo que distingue este TFG de un simple visor de datos. Muy pocos TFGs llegan a transmitir órdenes reales a una API de broker. |
| **Arquitectura Flat MVC + SQLite auditada** | Login seguro (SHA-256), control de sesión, registro de operaciones con 12 columnas: demuestra pensamiento de sistema completo. |
| **Panel de cancelación + posiciones de cartera** | Cierra el ciclo completo: enviar → ver → cancelar. Muy difícil de refutar en defensa. |
| **Heatmap de sensibilidad B-S** *(nuevo)* | Una figura que muestra cómo varía el ratio B/R al mover strikes demuestra pensamiento cuantitativo avanzado. Alta densidad visual en la memoria. |
| **Greeks (Δ, Θ, Vega)** *(nuevo)* | Mostrar Delta, Theta y Vega calculados con Black-Scholes eleva el rigor financiero del TFG al nivel de un sistema profesional. Coste marginal casi cero si ya tienes B-S implementado para el heatmap. |

### ⚠️ Deuda Técnica y Riesgos Reales para la Presentación

Sé honesto sobre esto antes de que el tribunal lo sea.

| Riesgo | Severidad | Mitigación |
|---|---|---|
| **No hay tests automatizados** (`pytest`) | 🔴 Alta | El tribunal puede preguntar "¿cómo has verificado que esto funciona?". Sin tests, solo puedes responder "manualmente". Esto es lo más urgente. |
| **clientIds hardcodeados** (93, 94, 95, 96, 97, 99) | 🟡 Media | Si dos flujos coinciden en el tiempo, hay colisión de IDs. Documentar como limitación conocida y justificar con el contexto de "aplicación monousuario de investigación". |
| **`status` captura solo el estado inicial** (`Submitted`) | 🟡 Media | Ya documentado. Defenderlo como limitación de scope es suficiente. No lo toques. |
| **Sin `requirements.txt`** | 🔴 Alta | El tribunal o el corrector puede intentar reproducir el proyecto. Sin este fichero, es un suspenso técnico. |
| **Sin `README.md` con pasos de ejecución claros** | 🔴 Alta | Ídem. Reproducibilidad = rigor científico. |
| **Fallback Bid/Ask usa `close`** (precio de cierre) | 🟢 Baja | Es una decisión de diseño válida para mercado cerrado. Solo documéntala. |
| **`random.randint` para `clientId` en `conectar()`** | 🟢 Baja | Riesgo teórico de colisión 1/9000. No es un riesgo real en demo. Documentar. |

---

## PARTE 2 — DECISIONES DE PODA (qué NO se hace)

Estas funcionalidades se **descartan definitivamente** del alcance del TFG. Están aquí para justificarlas en la memoria como "trabajo futuro".

### ✅ Features añadidas (revisión con IA de copiloto)

| Funcionalidad | Tiempo estimado con IA | Valor académico |
|---|---|---|
| **Heatmap estático B-S** | ~3 h | ⭐⭐⭐⭐ — figura estrella de la memoria |
| **Greeks (Δ, Θ, Vega) con B-S** | ~1 h extra (reutiliza código B-S) | ⭐⭐⭐⭐ — eleva el rigor financiero |
| **Export CSV del historial** | ~30 min | ⭐⭐ — refuerza trazabilidad |
| **CI con GitHub Actions** | ~30 min | ⭐⭐ — badge profesional en README |

### ❌ Descartado definitivamente

| Funcionalidad Descartada | Razón |
|---|---|
| ~~Backtest con serie histórica~~ | Datos históricos de opciones son de pago o inviables vía IBKR. |
| ~~Equity curve / Drawdown chart~~ | Depende del backtest. Sin datos, no hay curva real. |
| ~~Simulador de slippage~~ | Vacío sin backtest real. Mención en trabajo futuro. |
| ~~Notificaciones Telegram~~ | Feature de producto, no de TFG académico. |
| ~~Refactor a subcarpetas~~ | La Flat MVC ya es una decisión documentada. Romper ahora = riesgo innecesario. |
| ~~`conexion_ibkr_mock.py` completo~~ | Sustituido por mocks en los tests (más rápido). |
| ~~`results_fragment.tex` autogenerado~~ | Las figuras se insertan manualmente. No compensa el tiempo. |

---

## PARTE 3 — PLAN FEATURE FREEZE (7 días)

> **Regla de oro:** Si una tarea no está en esta lista, **NO se implementa**.
> El código debe estar 100% terminado y congelado el **21 de mayo de 2026**.
> **Con IA de copiloto** los tiempos son reales: README = 1 prompt + pulir, tests = copy-paste + ejecutar.

### 📅 Día 1 (14 Mayo) — Infraestructura base (~2 h con IA)

- [ ] `requirements.txt` — `pip freeze > requirements.txt` + limpiar manualmente. Añadir `scipy` (necesario para B-S).
- [ ] `README.md` — 1 prompt a la IA con el contexto del proyecto → pulir resultado. Secciones: Descripción, Prerequisitos, Instalación, Ejecución, Credenciales, Reglas operativas (strikes ×100, SPXW).
- [ ] `.env.example` — `IBKR_HOST=127.0.0.1` / `IBKR_PORT=4002`.
- [ ] Verificar `.gitignore`: `tfg_trading.db` debe estar versionado (demuestra historial de auditoría).

### 📅 Día 2 (15 Mayo) — Tests + CI (~2 h con IA)

**Tests:** Crear `tests/test_motor_logica.py` (código ya en el documento anterior — copy-paste directo).

```python
# tests/test_motor_logica.py
import pytest
from motor_logica import MotorEstrategias

class GestorMock:
    def obtener_datos_estrategia_completa(self, ticker, vencimiento, strikes):
        return [
            {"bid": 2.10, "ask": 2.30},  # P_Long
            {"bid": 5.50, "ask": 5.70},  # P_Short
            {"bid": 4.80, "ask": 5.00},  # C_Short
            {"bid": 1.90, "ask": 2.10},  # C_Long
        ]
    def obtener_historico_diario(self, ticker, dias):
        return [5200.0, 5210.0, 5190.0, 5205.0, 5215.0]

def test_credito_neto_positivo():
    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
        GestorMock(), 'SPX', '20260620', 5000, 5100, 5300, 5400)
    assert resultado["credito_neto"] > 0

def test_credito_neto_calculo_correcto():
    # ingreso=10.30, coste=4.40, neto=5.90
    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
        GestorMock(), 'SPX', '20260620', 5000, 5100, 5300, 5400)
    assert resultado["credito_neto"] == 5.90

def test_metricas_iron_condor():
    r = MotorEstrategias.calcular_metricas_iron_condor(5000, 5100, 5300, 5400, 5.90)
    assert r["max_beneficio"] == 590.0
    assert r["max_riesgo"] > 0
    assert r["ratio_rb"] > 0

def test_sma_autoriza():
    r = MotorEstrategias.evaluar_condicion_sma(GestorMock(), 'SPX', 5, 'Precio > SMA', 9999.0)
    assert r["autorizado"] is True

def test_sma_error_datos_insuficientes():
    class SinDatos:
        def obtener_historico_diario(self, t, d): return [5200.0]
    with pytest.raises(ValueError):
        MotorEstrategias.evaluar_condicion_sma(SinDatos(), 'SPX', 20, 'Precio > SMA', 5200.0)
```

- [ ] Ejecutar `pytest tests/ -v` → 5 tests en verde.
- [ ] **CI — `.github/workflows/tests.yml`** (~30 min, 1 prompt a la IA):

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install pandas pytest
      - run: pytest tests/ -v
```

> Nota: `ib_insync` no se instala en CI (requiere Gateway). Los tests usan `GestorMock`, por lo que pasan sin conexión.

- [ ] Hacer push → verificar que el badge aparece verde en GitHub → añadir badge al `README.md`.

### 📅 Día 3-4 (16–17 Mayo) — Heatmap B-S + Greeks (~4 h con IA)

**Objetivo:** Añadir módulo `motor_bs.py` con Black-Scholes y dos features visuales.

Crear `motor_bs.py` (la IA lo genera completo en 1 prompt):
- `calcular_prima_bs(S, K, T, r, sigma, tipo)` → precio teórico de la opción
- `calcular_greeks(S, K, T, r, sigma, tipo)` → dict con `delta`, `theta`, `vega`
- `generar_heatmap_ic(S, r, sigma, vencimiento, strikes_put, strikes_call)` → `matplotlib` figure con malla de ratio B/R

Integrar en `app_web.py`:
- [ ] **Pestaña Estrategia**: añadir sección colapsable "📐 Greeks (Black-Scholes)" que muestre Δ, Θ, Vega de cada pata al calcular el crédito.
- [ ] **Pestaña Análisis** *(nueva o dentro de Estrategia)*: botón "Generar Heatmap" → renderiza `st.pyplot(fig)` con el mapa de calor.
- [ ] Guardar la figura como `figures/fig_heatmap_sensibilidad.png`.

### 📅 Día 5 (18 Mayo) — Export CSV (~1 h con IA)

**Objetivo:** Cerrar el ciclo de trazabilidad con un botón de descarga.

En la pestaña de Monitorización, añadir:
```python
import pandas as pd
df = pd.DataFrame(obtener_operaciones())  # ya existe en base_datos.py
csv = df.to_csv(index=False).encode('utf-8')
st.download_button("⬇️ Exportar historial CSV", csv, "historial_operaciones.csv", "text/csv")
```

- [ ] Verificar que el CSV descargado tiene las 12 columnas correctas.

### 📅 Día 6 (19–20 Mayo) — Captura de Evidencias para la Memoria

Crear carpeta `figures/` con:

- [ ] `fig_arquitectura.png` — diagrama Flat MVC (draw.io / Excalidraw)
- [ ] `fig_login.png` — captura pantalla de login
- [ ] `fig_estrategia_resultado.png` — crédito neto + métricas de riesgo
- [ ] `fig_greeks.png` — sección Greeks con Δ, Θ, Vega visibles
- [ ] `fig_sma_filtro.png` — filtro SMA activo
- [ ] `fig_heatmap_sensibilidad.png` — heatmap B-S generado desde la UI
- [ ] `fig_orden_enviada.png` — orderId capturado post-envío
- [ ] `fig_monitorizacion.png` — historial SQLite + botón export CSV
- [ ] `fig_posiciones.png` — panel de posiciones de cartera
- [ ] `fig_pytest_output.png` — terminal con 5 tests en verde
- [ ] `fig_ci_badge.png` — captura del badge verde en GitHub

### 📅 Día 7 (21 Mayo) — Feature Freeze

- [ ] Revisar que todos los métodos públicos tienen docstring.
- [ ] Eliminar `print()` de depuración residuales en `app_web.py`.
- [ ] Verificación end-to-end: navegar todos los tabs, sin excepciones en consola.
- [ ] Commit de congelación:
  ```bash
  git add .
  git commit -m "chore: feature freeze v1.0 — TFG Opciones Financieras"
  git tag v1.0-tfg
  git push --tags
  ```

### 📅 Día 1-2 (14–15 Mayo) — Hardening de Infraestructura

**Objetivo: Que cualquier persona pueda ejecutar el proyecto desde cero.**

- [ ] **`requirements.txt`**: Generar con `pip freeze > requirements.txt` y limpiar paquetes irrelevantes. Mínimo: `streamlit`, `ib_insync`, `nest_asyncio`, `pandas`, `pytest`.
- [ ] **`README.md`**: Reescribir con secciones: Descripción, Prerequisitos (IBKR Gateway en puerto 4002), Instalación, Ejecución (`streamlit run app_web.py`), Credenciales (admin/admin2026), Reglas operativas (strikes múltiplos de 100, vencimientos SPXW semanales).
- [ ] **`.env.example`**: Crear con `IBKR_HOST=127.0.0.1`, `IBKR_PORT=4002`. Documentar que el hash SHA-256 está hardcodeado por simplicidad de demo.
- [ ] **Verificar `.gitignore`**: El fichero `tfg_trading.db` debe estar versionado para demostrar el historial de auditoría.

### 📅 Día 3-4 (16–17 Mayo) — Tests Mínimos Verificables

**Objetivo: Responder "sí" a la pregunta del tribunal "¿tienes tests?".**

Crear carpeta `tests/` con `test_motor_logica.py`:

```python
# tests/test_motor_logica.py
import pytest
from motor_logica import MotorEstrategias

class GestorMock:
    def obtener_datos_estrategia_completa(self, ticker, vencimiento, strikes):
        return [
            {"bid": 2.10, "ask": 2.30},  # P_Long
            {"bid": 5.50, "ask": 5.70},  # P_Short
            {"bid": 4.80, "ask": 5.00},  # C_Short
            {"bid": 1.90, "ask": 2.10},  # C_Long
        ]
    def obtener_historico_diario(self, ticker, dias):
        return [5200.0, 5210.0, 5190.0, 5205.0, 5215.0]

def test_credito_neto_positivo():
    gestor = GestorMock()
    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
        gestor, 'SPX', '20260620', 5000, 5100, 5300, 5400
    )
    assert resultado["credito_neto"] > 0

def test_credito_neto_calculo_correcto():
    # ingreso = 5.50 + 4.80 = 10.30 | coste = 2.30 + 2.10 = 4.40 | neto = 5.90
    gestor = GestorMock()
    resultado = MotorEstrategias.calcular_credito_real_iron_condor(
        gestor, 'SPX', '20260620', 5000, 5100, 5300, 5400
    )
    assert resultado["credito_neto"] == 5.90

def test_metricas_iron_condor():
    resultado = MotorEstrategias.calcular_metricas_iron_condor(
        p_long=5000, p_short=5100, c_short=5300, c_long=5400, credito_neto=5.90
    )
    assert resultado["max_beneficio"] == 590.0   # 5.90 * 100
    assert resultado["max_riesgo"] > 0
    assert resultado["ratio_rb"] > 0

def test_sma_autoriza_si_precio_mayor():
    gestor = GestorMock()
    resultado = MotorEstrategias.evaluar_condicion_sma(
        gestor, 'SPX', 5, 'Precio > SMA', 9999.0
    )
    assert resultado["autorizado"] is True

def test_sma_bloquea_si_datos_insuficientes():
    class GestorSinDatos:
        def obtener_historico_diario(self, ticker, dias):
            return [5200.0]  # 1 dato para periodo 20 → debe lanzar error
    with pytest.raises(ValueError):
        MotorEstrategias.evaluar_condicion_sma(
            GestorSinDatos(), 'SPX', 20, 'Precio > SMA', 5200.0
        )
```

- [ ] Ejecutar `pytest tests/ -v` y confirmar que los 5 tests pasan en verde.
- [ ] Hacer screenshot de la salida del pytest → guardar como `figures/fig_pytest_output.png`.

### 📅 Día 5-6 (18–19 Mayo) — Captura de Evidencias para la Memoria

**Objetivo: Tener todos los assets visuales listos antes de escribir la memoria.**

Crear carpeta `figures/` con los siguientes archivos:

- [ ] **`fig_arquitectura.png`** — Diagrama de la arquitectura Flat MVC (capas: UI → Motor → Conexión → BD). Hacerlo en draw.io, Excalidraw, o similar.
- [ ] **`fig_login.png`** — Captura de la pantalla de login.
- [ ] **`fig_estrategia_resultado.png`** — Captura con un cálculo real de Iron Condor (crédito neto + métricas de riesgo visibles).
- [ ] **`fig_sma_filtro.png`** — Captura de la UI mostrando el filtro SMA activo (luz verde o roja).
- [ ] **`fig_orden_enviada.png`** — Captura del panel de confirmación y del orderId capturado tras el envío.
- [ ] **`fig_monitorizacion.png`** — Captura de la pestaña de monitorización con el historial en SQLite.
- [ ] **`fig_posiciones.png`** — Captura del panel de posiciones abiertas de la cartera.
- [ ] **`fig_pytest_output.png`** — Captura de terminal con los 5 tests en verde.

### 📅 Día 7 (20–21 Mayo) — Feature Freeze + Revisión Final

**Objetivo: El código queda congelado. No se toca más.**

- [ ] **Docstrings**: Verificar que cada método público en `motor_logica.py`, `conexion_ibkr.py` y `base_datos.py` tiene docstring. Los existentes son suficientes; solo añadir donde falten.
- [ ] **Limpieza de `app_web.py`**: Eliminar cualquier `print()` de depuración residual.
- [ ] **Commit de congelación**:
  ```bash
  git add .
  git commit -m "chore: feature freeze v1.0 — TFG Opciones Financieras"
  git tag v1.0-tfg
  ```
- [ ] **Verificación end-to-end**: Ejecutar la aplicación completa y navegar por todos los tabs. Confirmar que no hay excepciones no capturadas ni errores en consola.

---

## PARTE 4 — CALENDARIO SEMANAS 2–4 (Memoria LaTeX)

> A partir del **22/05/2026**, cero código nuevo. Solo memoria.

| Semana | Fechas | Objetivo |
|---|---|---|
| **Semana 2** | 22–28 Mayo | Redactar: Introducción, Estado del Arte, Diseño del Sistema |
| **Semana 3** | 29 Mayo – 4 Jun | Redactar: Implementación, Pruebas, Resultados |
| **Semana 4** | 5–11 Jun | Redactar: Conclusiones, revisión completa, PDF final, 10 slides |

### Estructura de Capítulos Recomendada

```
1. Introducción y Motivación
2. Estado del Arte
   2.1 Opciones Financieras y la Estrategia Iron Condor
   2.2 APIs de Broker (Interactive Brokers / ib_insync)
   2.3 Frameworks Web para Aplicaciones de Datos (Streamlit)
3. Diseño del Sistema
   3.1 Arquitectura Flat MVC
   3.2 El Patrón Bulk Session (gestión de concurrencia asíncrona)
   3.3 Esquema de Base de Datos (SQLite)
4. Implementación
   4.1 Capa de Conectividad (GestorIBKR)
   4.2 Motor de Estrategias (MotorEstrategias + Filtro SMA)
   4.3 Modelo Black-Scholes: Pricing Teórico y Greeks (Δ, Θ, Vega)
   4.4 Análisis de Sensibilidad: Heatmap de Strikes
   4.5 Capa de Presentación (app_web.py)
   4.6 Ciclo de Vida de una Orden: Envío, Monitorización y Cancelación
5. Validación y Pruebas
   5.1 Tests Unitarios (pytest) + CI con GitHub Actions
   5.2 Pruebas de Integración en Entorno Paper Trading
6. Resultados y Discusión
7. Conclusiones y Trabajo Futuro
   - Polling de estado de órdenes post-envío
   - Backtest histórico con datos de opciones reales
   - Despliegue en servidor remoto con autenticación robusta
Anexos: Código relevante, capturas de pantalla, salida de pytest, heatmap
```

---

## ESTADO DEL PROYECTO (resumen ejecutivo)

```
✅ Fase 1 — Arquitectura y Conectividad:           COMPLETADA
✅ Fase 2 — Motor Lógico y Financiero:             COMPLETADA
✅ Fase 3 — Seguridad y Persistencia:              COMPLETADA
✅ Fase 4 — Ejecución y Ciclo de Vida Orden:       COMPLETADA
🔄 Fase 5 — Hardening + Tests + B-S + Heatmap:    EN CURSO (Feature Freeze: 21/05)
⏳ Fase 6 — Memoria LaTeX:                         PENDIENTE (inicio: 22/05)
```

---

*Este documento es la fuente única de verdad hasta la entrega del TFG.*
*Última actualización: 14/05/2026 — Revisión v2: timelines con IA, heatmap B-S, Greeks, export CSV, CI/GitHub Actions añadidos.*
