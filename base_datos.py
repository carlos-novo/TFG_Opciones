import sqlite3
import os
import json
from datetime import datetime
import pandas as pd
import hashlib

class EstrategiaDuplicadaError(Exception):
    """Excepción lanzada cuando se intenta crear una estrategia con la misma huella canónica determinista."""
    def __init__(self, mensaje, est_existente_id=None):
        super().__init__(mensaje)
        self.est_existente_id = est_existente_id

def calcular_huella_estrategia(ticker, tipo_activo, patas, precio_entrada, condiciones_entrada, condiciones_salida):
    """
    Calcula una huella canónica SHA-256 determinista para una estrategia
    ordenando patas y claves de configuración.
    """
    patas_norm = []
    if isinstance(patas, list):
        for p in patas:
            p_norm = {
                "accion": str(p.get("accion", "")).upper().strip(),
                "right": str(p.get("right", "")).upper().strip(),
                "strike": float(p.get("strike", 0.0)),
                "cantidad": int(p.get("cantidad", 1)),
                "vencimiento": str(p.get("vencimiento", "")).strip()
            }
            patas_norm.append(p_norm)
        patas_norm.sort(key=lambda x: (x["vencimiento"], x["strike"], x["right"], x["accion"], x["cantidad"]))

    payload = {
        "ticker": str(ticker).upper().strip(),
        "tipo_activo": str(tipo_activo).upper().strip(),
        "patas": patas_norm,
        "precio_entrada": round(float(precio_entrada), 2) if precio_entrada is not None else None,
        "condiciones_entrada": condiciones_entrada or {},
        "condiciones_salida": condiciones_salida or {}
    }

    canonical_json = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

class GestorBaseDatos:
    """
    Clase para gestionar la persistencia local del sistema mediante SQLite.
    Soporta una arquitectura flexible para trading multileg y direccional
    almacenando patas y condiciones en formato JSON.
    """
    def __init__(self, db_name="tfg_trading.db", reset_db=False):
        # Ruta absoluta anclada al directorio de este script para evitar problemas con Streamlit
        _dir_actual = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(_dir_actual, db_name)
        
        if reset_db:
            self.borrar_base_datos()
            
        self._crear_tablas()

    def borrar_base_datos(self):
        """Elimina físicamente el archivo de base de datos para comenzar de cero."""
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception as e:
                print(f"Error al eliminar la base de datos vieja: {e}")

    def _conectar(self):
        """Abre una conexión a la base de datos local usando ruta absoluta y modo WAL."""
        conexion = sqlite3.connect(self.db_path, timeout=10.0)
        conexion.execute("PRAGMA journal_mode=WAL;")
        conexion.execute("PRAGMA busy_timeout=5000;")
        return conexion

    def _crear_tablas(self):
        """Crea las tablas necesarias. Purga y migra de forma automática si detecta el esquema antiguo."""
        conexion = self._conectar()
        cursor = conexion.cursor()
        
        # Detectar si existe el esquema antiguo de operaciones (por ejemplo, buscando la columna 'put_long')
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='operaciones';")
        existe_operaciones_antiguo = cursor.fetchone() is not None
        
        if existe_operaciones_antiguo:
            # Borrar las tablas antiguas obsoletas
            cursor.execute("DROP TABLE IF EXISTS operaciones;")
            cursor.execute("DROP TABLE IF EXISTS cola_reintentos;")
            cursor.execute("DROP TABLE IF EXISTS auditoria;")
            conexion.commit()
            
        # Tabla de Auditoría: Registra logs históricos del bot, watchdog y eventos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                evento TEXT NOT NULL,
                detalles TEXT
            )
        ''')

        # Tabla de Estrategias: Estructura flexible unificada para multileg y acciones
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS estrategias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                tipo_activo TEXT NOT NULL,
                estado TEXT NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_ejecucion TIMESTAMP,
                fecha_cierre TIMESTAMP,
                patas_json TEXT NOT NULL,
                condiciones_entrada_json TEXT,
                condiciones_salida_json TEXT,
                order_id_entrada INTEGER,
                order_id_salida INTEGER,
                precio_entrada REAL,
                precio_salida REAL,
                pnl_realizado REAL,
                huella_hash TEXT
            )
        ''')

        # Migración automática si la tabla existía sin huella_hash
        cursor.execute("PRAGMA table_info(estrategias);")
        columnas = [row[1] for row in cursor.fetchall()]
        if "huella_hash" not in columnas:
            cursor.execute("ALTER TABLE estrategias ADD COLUMN huella_hash TEXT;")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_estrategias_huella ON estrategias(huella_hash);")

        # Tabla de Caché de Sesión: Guarda el estado del bróker para modo offline
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conexion.commit()
        conexion.close()

    def registrar_evento(self, evento, detalles=""):
        """Inserta un nuevo registro en el log de auditoría."""
        conexion = self._conectar()
        cursor = conexion.cursor()
        ahora = datetime.now().isoformat()
        try:
            cursor.execute(
                "INSERT INTO auditoria (fecha, evento, detalles) VALUES (?, ?, ?)",
                (ahora, evento, detalles)
            )
            conexion.commit()
        except Exception as e:
            print(f"Error al registrar evento en BD: {e}")
        finally:
            conexion.close()

    def obtener_logs(self, limit=50):
        """
        Recupera todos los registros de auditoría ordenados por fecha descendente.
        Retorna un DataFrame de Pandas para visualización.
        """
        conexion = self._conectar()
        try:
            query = "SELECT fecha, evento, detalles FROM auditoria ORDER BY fecha DESC LIMIT ?"
            df = pd.read_sql_query(query, conexion, params=(limit,))
            return df
        except Exception as e:
            print(f"Error al obtener logs: {e}")
            return pd.DataFrame()
        finally:
            conexion.close()

    def guardar_cache(self, key, value_dict):
        """Guarda un diccionario o lista serializado en JSON en la tabla de caché."""
        import json
        conexion = self._conectar()
        cursor = conexion.cursor()
        try:
            val_str = json.dumps(value_dict)
            cursor.execute(
                "INSERT INTO session_cache (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
                (key, val_str)
            )
            conexion.commit()
        except Exception as e:
            print(f"Error al guardar caché para {key} en BD: {e}")
        finally:
            conexion.close()

    def obtener_cache(self, key):
        """Obtiene un diccionario o lista deserializado desde la caché."""
        import json
        conexion = self._conectar()
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT value FROM session_cache WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            print(f"Error al obtener caché para {key} desde BD: {e}")
            return None
        finally:
            conexion.close()

    # ==========================================
    # MÉTODOS CRUD PARA ESTRATEGIAS
    # ==========================================

    def crear_estrategia(self, ticker, tipo_activo, estado, patas, condiciones_entrada=None, condiciones_salida=None, precio_entrada=None, permitir_duplicado=False):
        """
        Inserta una nueva estrategia en la base de datos protegiendo la idempotencia mediante huella SHA-256.
        Si la estrategia ya existe en estado activo/pendiente y permitir_duplicado=False, lanza EstrategiaDuplicadaError.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        ahora = datetime.now().isoformat()
        
        huella = calcular_huella_estrategia(ticker, tipo_activo, patas, precio_entrada, condiciones_entrada, condiciones_salida)
        
        if not permitir_duplicado:
            cursor.execute('''
                SELECT id FROM estrategias 
                WHERE huella_hash = ? AND estado IN ('PENDIENTE', 'PENDIENTE_ENTRADA', 'ORDEN_ENVIADA', 'ACTIVA', 'EJECUTADA')
            ''', (huella,))
            existente = cursor.fetchone()
            if existente:
                est_id_existente = existente[0]
                conexion.close()
                raise EstrategiaDuplicadaError(
                    f"Ya existe una estrategia idéntica pendiente o activa con ID #{est_id_existente}.",
                    est_existente_id=est_id_existente
                )
        
        patas_str = json.dumps(patas)
        cond_entrada_str = json.dumps(condiciones_entrada) if condiciones_entrada is not None else None
        cond_salida_str = json.dumps(condiciones_salida) if condiciones_salida is not None else None
        
        try:
            cursor.execute('''
                INSERT INTO estrategias (
                    ticker, tipo_activo, estado, fecha_creacion,
                    patas_json, condiciones_entrada_json, condiciones_salida_json, precio_entrada, huella_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ticker, tipo_activo, estado, ahora, patas_str, cond_entrada_str, cond_salida_str, precio_entrada, huella))
            conexion.commit()
            estrategia_id = cursor.lastrowid
            self.registrar_evento("CREAR_ESTRATEGIA", f"Creada estrategia ID {estrategia_id} para {ticker} ({tipo_activo}) [Huella: {huella[:8]}]")
            return estrategia_id
        except Exception as e:
            self.registrar_evento("ERROR_CREAR_ESTRATEGIA", f"Error al insertar estrategia: {e}")
            raise e
        finally:
            conexion.close()

    def cancelar_estrategias_prueba(self, ids=[236, 237, 238, 239]):
        """Marca como CANCELADA_PRUEBA estrategias de pruebas offline para conservar trazabilidad."""
        conexion = self._conectar()
        cursor = conexion.cursor()
        ahora = datetime.now().isoformat()
        try:
            for est_id in ids:
                cursor.execute(
                    "UPDATE estrategias SET estado = 'CANCELADA_PRUEBA', fecha_cierre = ? WHERE id = ? AND estado != 'CANCELADA_PRUEBA'",
                    (ahora, est_id)
                )
            conexion.commit()
            self.registrar_evento("CANCELAR_PRUEBAS", f"Estrategias {ids} marcadas como CANCELADA_PRUEBA")
        except Exception as e:
            print(f"Error al cancelar estrategias de prueba: {e}")
        finally:
            conexion.close()

    def obtener_estrategia(self, estrategia_id):
        """
        Recupera una estrategia específica por su ID.
        Deserializa los campos JSON a colecciones nativas de Python.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        try:
            cursor.execute('''
                SELECT id, ticker, tipo_activo, estado, fecha_creacion, fecha_ejecucion, fecha_cierre,
                       patas_json, condiciones_entrada_json, condiciones_salida_json,
                       order_id_entrada, order_id_salida, precio_entrada, precio_salida, pnl_realizado
                FROM estrategias
                WHERE id = ?
            ''', (estrategia_id,))
            fila = cursor.fetchone()
            if not fila:
                return None
            
            return {
                "id": fila[0],
                "ticker": fila[1],
                "tipo_activo": fila[2],
                "estado": fila[3],
                "fecha_creacion": fila[4],
                "fecha_ejecucion": fila[5],
                "fecha_cierre": fila[6],
                "patas": json.loads(fila[7]) if fila[7] else [],
                "condiciones_entrada": json.loads(fila[8]) if fila[8] else {},
                "condiciones_salida": json.loads(fila[9]) if fila[9] else {},
                "order_id_entrada": fila[10],
                "order_id_salida": fila[11],
                "precio_entrada": fila[12],
                "precio_salida": fila[13],
                "pnl_realizado": fila[14]
            }
        except Exception as e:
            print(f"Error al obtener estrategia {estrategia_id}: {e}")
            return None
        finally:
            conexion.close()

    def obtener_estrategias(self, estado=None):
        """
        Obtiene una lista de todas las estrategias, opcionalmente filtradas por estado.
        Cada estrategia es un diccionario con los campos JSON ya deserializados.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        try:
            if estado:
                cursor.execute('''
                    SELECT id, ticker, tipo_activo, estado, fecha_creacion, fecha_ejecucion, fecha_cierre,
                           patas_json, condiciones_entrada_json, condiciones_salida_json,
                           order_id_entrada, order_id_salida, precio_entrada, precio_salida, pnl_realizado
                    FROM estrategias
                    WHERE estado = ?
                    ORDER BY fecha_creacion DESC
                ''', (estado,))
            else:
                cursor.execute('''
                    SELECT id, ticker, tipo_activo, estado, fecha_creacion, fecha_ejecucion, fecha_cierre,
                           patas_json, condiciones_entrada_json, condiciones_salida_json,
                           order_id_entrada, order_id_salida, precio_entrada, precio_salida, pnl_realizado
                    FROM estrategias
                    ORDER BY fecha_creacion DESC
                ''')
            
            filas = cursor.fetchall()
            estrategias = []
            for fila in filas:
                estrategias.append({
                    "id": fila[0],
                    "ticker": fila[1],
                    "tipo_activo": fila[2],
                    "estado": fila[3],
                    "fecha_creacion": fila[4],
                    "fecha_ejecucion": fila[5],
                    "fecha_cierre": fila[6],
                    "patas": json.loads(fila[7]) if fila[7] else [],
                    "condiciones_entrada": json.loads(fila[8]) if fila[8] else {},
                    "condiciones_salida": json.loads(fila[9]) if fila[9] else {},
                    "order_id_entrada": fila[10],
                    "order_id_salida": fila[11],
                    "precio_entrada": fila[12],
                    "precio_salida": fila[13],
                    "pnl_realizado": fila[14]
                })
            return estrategias
        except Exception as e:
            print(f"Error al obtener estrategias: {e}")
            return []
        finally:
            conexion.close()

    def obtener_estrategias_df(self, estado=None):
        """
        Devuelve las estrategias en formato de DataFrame de Pandas.
        Útil para la integración rápida con componentes Streamlit y la API REST.
        """
        estrategias = self.obtener_estrategias(estado)
        return pd.DataFrame(estrategias)

    def actualizar_estado_estrategia(self, estrategia_id, nuevo_estado, order_id_entrada=None, order_id_salida=None, precio_entrada=None, precio_salida=None, pnl_realizado=None, fecha_ejecucion=None, fecha_cierre=None):
        """
        Actualiza dinámicamente el estado y las variables de control financiero de una estrategia.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        
        updates = ["estado = ?"]
        params = [nuevo_estado]
        
        if order_id_entrada is not None:
            updates.append("order_id_entrada = ?")
            params.append(order_id_entrada)
        if order_id_salida is not None:
            updates.append("order_id_salida = ?")
            params.append(order_id_salida)
        if precio_entrada is not None:
            updates.append("precio_entrada = ?")
            params.append(precio_entrada)
        if precio_salida is not None:
            updates.append("precio_salida = ?")
            params.append(precio_salida)
        if pnl_realizado is not None:
            updates.append("pnl_realizado = ?")
            params.append(pnl_realizado)
        if fecha_ejecucion is not None:
            updates.append("fecha_ejecucion = ?")
            params.append(fecha_ejecucion)
        if fecha_cierre is not None:
            updates.append("fecha_cierre = ?")
            params.append(fecha_cierre)
            
        params.append(estrategia_id)
        query = f"UPDATE estrategias SET {', '.join(updates)} WHERE id = ?"
        
        try:
            cursor.execute(query, tuple(params))
            conexion.commit()
            self.registrar_evento("ACTUALIZAR_ESTADO_ESTRATEGIA", f"Estrategia ID {estrategia_id} actualizada a {nuevo_estado}")
            return True
        except Exception as e:
            self.registrar_evento("ERROR_ACTUALIZAR_ESTRATEGIA", f"Error al actualizar estado de ID {estrategia_id}: {e}")
            return False
        finally:
            conexion.close()

    def actualizar_condiciones_salida(self, estrategia_id, condiciones_salida):
        """
        Actualiza el campo condiciones_salida_json completo.
        Recibe un diccionario Python y lo escribe como JSON string.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        cond_salida_str = json.dumps(condiciones_salida)
        try:
            cursor.execute('''
                UPDATE estrategias
                SET condiciones_salida_json = ?
                WHERE id = ?
            ''', (cond_salida_str, estrategia_id))
            conexion.commit()
            self.registrar_evento("ACTUALIZAR_CONDICIONES_SALIDA", f"Condiciones de salida actualizadas para ID {estrategia_id}")
            return True
        except Exception as e:
            self.registrar_evento("ERROR_ACTUALIZAR_CONDICIONES_SALIDA", f"Error en ID {estrategia_id}: {e}")
            return False
        finally:
            conexion.close()

    def actualizar_condiciones_entrada(self, estrategia_id, condiciones_entrada):
        """
        Actualiza el campo condiciones_entrada_json completo.
        Recibe un diccionario Python y lo escribe como JSON string.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        cond_entrada_str = json.dumps(condiciones_entrada)
        try:
            cursor.execute('''
                UPDATE estrategias
                SET condiciones_entrada_json = ?
                WHERE id = ?
            ''', (cond_entrada_str, estrategia_id))
            conexion.commit()
            self.registrar_evento("ACTUALIZAR_CONDICIONES_ENTRADA", f"Condiciones de entrada actualizadas para ID {estrategia_id}")
            return True
        except Exception as e:
            self.registrar_evento("ERROR_ACTUALIZAR_CONDICIONES_ENTRADA", f"Error en ID {estrategia_id}: {e}")
            return False
        finally:
            conexion.close()

    def actualizar_limites_sl_tp(self, estrategia_id, stop_loss=None, take_profit=None):
        """
        Carga las condiciones de salida previas de la estrategia,
        modifica 'stop_loss' y/o 'take_profit' manteniendo el resto de condiciones intactas,
        y las vuelve a guardar. Esencial para el Watchdog de Salidas.
        """
        estrategia = self.obtener_estrategia(estrategia_id)
        if not estrategia:
            self.registrar_evento("ERROR_LIMITES_SL_TP", f"Estrategia ID {estrategia_id} no encontrada.")
            return False
        
        condiciones = estrategia.get("condiciones_salida") or {}
        if stop_loss is not None:
            condiciones["stop_loss"] = stop_loss
        if take_profit is not None:
            condiciones["take_profit"] = take_profit
            
        return self.actualizar_condiciones_salida(estrategia_id, condiciones)

    # ==========================================
    # MÉTODOS DE COMPATIBILIDAD RETROACTIVA
    # ==========================================

    def obtener_operaciones(self):
        """
        Mapea las consultas del historial de operaciones de la UI y la API antigua
        a la nueva tabla de estrategias para evitar errores durante el pivot.
        """
        return self.obtener_estrategias_df()

    def obtener_reintentos_pendientes(self):
        """
        Retorna las estrategias que están pendientes de ejecución (estado 'PENDIENTE_ENTRADA').
        Permite al watchdog modular su polling utilizando este método unificado.
        """
        return self.obtener_estrategias_df(estado='PENDIENTE_ENTRADA')

    def actualizar_estado_orden(self, order_id, nuevo_estado):
        """
        Actualiza el estado de la estrategia que corresponda a un order_id de entrada o salida.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        try:
            cursor.execute(
                "UPDATE estrategias SET estado = ? WHERE order_id_entrada = ? OR order_id_salida = ?",
                (nuevo_estado, order_id, order_id)
            )
            conexion.commit()
            self.registrar_evento("ACTUALIZAR_ESTADO_ORDEN", f"Orden ID {order_id} actualizada a {nuevo_estado}")
            return True
        except Exception as e:
            self.registrar_evento("ERROR_ACTUALIZAR_ESTADO_ORDEN", f"Error actualizando orden {order_id}: {e}")
            return False
        finally:
            conexion.close()

    def actualizar_patas(self, estrategia_id, patas):
        """Actualiza las patas de una estrategia en formato JSON."""
        conexion = self._conectar()
        cursor = conexion.cursor()
        try:
            patas_json = json.dumps(patas)
            cursor.execute("UPDATE estrategias SET patas_json = ? WHERE id = ?", (patas_json, estrategia_id))
            conexion.commit()
            self.registrar_evento("ACTUALIZAR_PATAS_ESTRATEGIA", f"Patas de Estrategia ID {estrategia_id} actualizadas.")
            return True
        except Exception as e:
            self.registrar_evento("ERROR_ACTUALIZAR_PATAS", f"Error al actualizar patas de ID {estrategia_id}: {e}")
            return False
        finally:
            conexion.close()