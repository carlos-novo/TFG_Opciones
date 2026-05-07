# 📋 ESTADO DEL PROYECTO Y HOJA DE RUTA (`TODO.md`)

**Última actualización:** 07/05/2026 — 12:48 (Fase 4 en curso, commit intermedio)

Este documento registra el progreso actual del TFG, los errores críticos que requieren atención inmediata y la planificación de las próximas fases de desarrollo.

---

## 🟢 1. HITOS COMPLETADOS (Definition of Done)

### Fase 1: Arquitectura y Conectividad Base
- [x] Implementación de estructura plana (Flat MVC) para compatibilidad con Streamlit.
- [x] Configuración de comunicación asíncrona con IBKR Gateway (Puerto 4002).
- [x] Integración de `nest_asyncio` para la gestión del event loop.
- [x] Desarrollo del patrón 'Bulk Session' para consultas de mercado eficientes.

### Fase 2: Motor Lógico y Financiero
- [x] Creación de lógica para el cálculo de crédito neto real (Spread Bid/Ask).
- [x] Implementación de métricas de riesgo: Beneficio Máximo y Riesgo Máximo.
- [x] Integración de `pandas` para el cálculo de Media Móvil Simple (SMA).

### Fase 3: Seguridad y Persistencia
- [x] Sistema de login con hashing SHA-256 (admin/admin2026).
- [x] Control de flujo de sesión mediante `st.session_state` y `st.stop()`.
- [x] Creación del esquema de base de datos SQLite para auditoría.
- [x] Consola de monitorización visual en la pestaña 3 de la UI.

### Fase 4: Ejecución de Órdenes (Parcial)
- [x] `construir_contrato_bag()` — contrato `BAG` con 4 `ComboLeg` [BUY, SELL, SELL, BUY].
- [x] `enviar_orden_iron_condor()` — micro-sesión que califica, ensambla y transmite `LimitOrder(lmtPrice=-crédito)`.
- [x] `ib.placeOrder()` integrado, captura `orderId` y `status` inicial.
- [x] UI de confirmación con `st.warning` + botón `CONFIRMAR Y EJECUTAR` (patrón `session_state`).

---

## 🔴 2. BUGS ACTIVOS (Prioridad Crítica)

*Estos errores deben corregirse antes de proceder a la ejecución de órdenes reales.*

1. ~~**Bug de Identificación de Activos (IBKR API)**~~
   - ~~**Síntoma:** Error `Unknown contract: Stock('SPX')` al intentar consultar el índice.~~
   - ~~**Causa:** El sistema intenta instanciar `SPX` como `Stock` en lugar de `Index`.~~
   - ✅ **RESUELTO [07/05/2026]:** `Index` importado y bloque `if/else` aplicado en `obtener_precio_prueba()` y `obtener_historico_diario()` de `conexion_ibkr.py`.

2. ~~**Bug de Persistencia (Rutas SQLite)**~~
   - ~~**Síntoma:** La base de datos no registra logs o crea archivos vacíos tras el reinicio.~~
   - ~~**Causa:** Streamlit desplaza el directorio de ejecución y usa rutas relativas.~~
   - ✅ **RESUELTO [07/05/2026]:** `os.path.abspath(__file__)` implementado en `GestorBaseDatos.__init__()` de `base_datos.py`. Conexión migrada a `self.db_path`.

3. ~~**Bug de Datos Inexistentes (Efecto Fin de Semana / Strike inválido)**~~
   - ~~**Síntoma:** Resultados `NaN` en el cálculo de crédito real. Error 200 en strikes no listados.~~
   - ~~**Causa:** El strike/vencimiento solicitado no tiene contrato listado en IBKR.~~
   - ✅ **RESUELTO [07/05/2026]:** Validado con `20260515` + strikes `4800/4900/5100/5200` → las 4 patas obtuvieron `conId`. No es un bug de código.
   - 📌 **Regla operativa documentada:** Los strikes de SPX/SPXW deben ser **múltiplos exactos de 100**. Los incrementos de 50 pts (ej. 5350) no están listados. Usar vencimientos semanales SPXW con strikes en rango ±200-300 pts del spot actual.

---

## 🚀 3. PRÓXIMOS PASOS (Fase 4: Ejecución)

- [x] ~~Empaquetado, Middleware, Gestión y UI~~ → Movidos a **Hitos Completados** ↑
- [ ] 🔧 **[PENDIENTE] Registro de Operaciones:** Crear tabla `operaciones` en SQLite para historial de órdenes ejecutadas (no solo logs de auditoría).

---

## 🛠️ Notas de Mantenimiento
- Revisar logs de la terminal ante cualquier error `200: No security definition found`.
- Mantener el archivo `tfg_trading.db` en el mismo nivel que los scripts para evitar redundancias.