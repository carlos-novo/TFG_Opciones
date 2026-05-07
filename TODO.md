# 📋 ESTADO DEL PROYECTO Y HOJA DE RUTA (`TODO.md`)

**Última actualización:** 07/05/2026 — 13:01 (commit final pre-entrega)

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
- [x] Tabla `operaciones` en SQLite: `registrar_operacion()` y `obtener_operaciones()` en `base_datos.py`. Historial con 12 columnas + métricas acumuladas en pestaña de Monitorización.

### Fase 5: Pulido y Calidad de Código (Pre-entrega)
- [x] Corregido bug crítico `st.warning(...)` — el argumento `Ellipsis` se sustituó por el mensaje real de bloqueo AT.
- [x] Eliminados `st.stop()` y `st.toast()` duplicados en el flujo de validación SMA.
- [x] Reemplazado `use_container_width=True` → `width='stretch'` en sidebar button (deprecación Streamlit).
- [x] Eliminado método huérfano `obtener_precio_spy()` de `conexion_ibkr.py` — referenciaba `simbolo` indefinido. Su sustituto funcional es `obtener_precio_prueba(simbolo)`.
- 📌 **Limitación conocida documentada:** El campo `status` en tabla `operaciones` captura el estado inicial (`Submitted`), no el estado final de ejecución. El seguimiento post-orden (polling de fills) queda fuera del alcance del TFG.

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

## 🚀 3. ROADMAP POST-TFG (Mejoras Futuras)

- [x] ~~Empaquetado, Middleware, Gestión, UI y Registro~~ → Todos completados ↑
- ✅ **FASE 4 COMPLETADA AL 100%**

### Mejoras Identificadas para Versión Futura
- [ ] 🔄 **Seguimiento de Estado de Orden (Polling):** Implementar un mecanismo de consulta periódica del estado de la orden tras su envío (`ib.reqOpenOrders()` o suscripción a eventos `Trade`). Actualizar el campo `status` en la tabla `operaciones` cuando la orden pase de `Submitted` a `Filled`, `PartiallyFilled` o `Cancelled`. Requiere gestión de callbacks asíncronos en el patrón de micro-sesión.
- [ ] 📊 **Panel de Posiciones Abiertas:** Mostrar las opciones en cartera en tiempo real mediante `ib.portfolio()` en la pestaña de Dashboard.
- [ ] ❌ **Función de Cancelación de Orden:** Añadir `ib.cancelOrder(orderId)` con confirmación en la UI para órdenes en estado `Submitted`.

---

## 🛠️ Notas de Mantenimiento
- Revisar logs de la terminal ante cualquier error `200: No security definition found`.
- Mantener el archivo `tfg_trading.db` en el mismo nivel que los scripts para evitar redundancias.