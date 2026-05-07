import sqlite3
import os
from datetime import datetime

class GestorBaseDatos:
    """
    Clase para gestionar la persistencia local del sistema mediante SQLite.
    Actúa como un log de auditoría para registrar eventos críticos del bot.
    """
    def __init__(self, db_name="tfg_trading.db"):
        # REGLA ARCHITECTURE.md: Ruta absoluta anclada al directorio del script.
        # Evita el desplazamiento de Working Directory de Streamlit.
        _dir_actual = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(_dir_actual, db_name)
        self._crear_tablas()

    def _conectar(self):
        """Abre una conexión a la base de datos local usando ruta absoluta."""
        return sqlite3.connect(self.db_path)

    def _crear_tablas(self):
        """Crea las tablas necesarias si no existen (Patrón Singleton de BD)."""
        conexion = self._conectar()
        cursor = conexion.cursor()
        
        # Tabla de Auditoría: Registra accesos y validaciones del motor
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TIMESTAMP,
                evento TEXT,
                detalles TEXT
            )
        ''')

        # Tabla de Operaciones: Historial financiero de órdenes ejecutadas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operaciones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha       TIMESTAMP,
                order_id    INTEGER,
                ticker      TEXT,
                vencimiento TEXT,
                put_long    REAL,
                put_short   REAL,
                call_short  REAL,
                call_long   REAL,
                credito     REAL,
                max_beneficio REAL,
                max_riesgo  REAL,
                status      TEXT
            )
        ''')
        
        conexion.commit()
        conexion.close()

    def registrar_operacion(self, order_id, ticker, vencimiento, strikes, credito, metricas, status):
        """
        Inserta un registro en la tabla de operaciones con el perfil financiero
        completo de la orden BAG ejecutada.

        Difiere del log de auditoría en que almacena datos cuantitativos
        (strikes, crédito, riesgo) pensados para análisis post-operativo.
        """
        conexion = self._conectar()
        cursor = conexion.cursor()
        p_long, p_short, c_short, c_long = strikes
        try:
            cursor.execute(
                '''
                INSERT INTO operaciones
                    (fecha, order_id, ticker, vencimiento,
                     put_long, put_short, call_short, call_long,
                     credito, max_beneficio, max_riesgo, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    datetime.now(), order_id, ticker, str(vencimiento),
                    p_long, p_short, c_short, c_long,
                    credito, metricas['max_beneficio'], metricas['max_riesgo'], status
                )
            )
            conexion.commit()
        except Exception as e:
            print(f"Error al registrar operación en BD: {e}")
        finally:
            conexion.close()

    def obtener_operaciones(self):
        """
        Recupera el historial completo de órdenes ejecutadas.
        Retorna un DataFrame de Pandas ordenado por fecha descendente.
        """
        import pandas as pd
        conexion = self._conectar()
        try:
            query = '''
                SELECT fecha, order_id, ticker, vencimiento,
                       put_long, put_short, call_short, call_long,
                       credito, max_beneficio, max_riesgo, status
                FROM operaciones
                ORDER BY fecha DESC
            '''
            df = pd.read_sql_query(query, conexion)
            return df
        except Exception as e:
            print(f"Error al obtener operaciones: {e}")
            return None
        finally:
            conexion.close()

    def registrar_evento(self, evento, detalles=""):
        """Inserta un nuevo registro en el log de auditoría."""
        conexion = self._conectar()
        cursor = conexion.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO auditoria (fecha, evento, detalles) VALUES (?, ?, ?)",
                (datetime.now(), evento, detalles)
            )
            conexion.commit()
        except Exception as e:
            print(f"Error al registrar evento en BD: {e}")
        finally:
            conexion.close()

    
    def obtener_logs(self):
        """
        Recupera todos los registros de auditoría ordenados por fecha descendente.
        Retorna un DataFrame de Pandas para facilitar la visualización.
        """
        import pandas as pd # Import local para eficiencia
        conexion = self._conectar()
        try:
            # Query para obtener los datos ordenados del más reciente al más antiguo
            query = "SELECT fecha, evento, detalles FROM auditoria ORDER BY fecha DESC"
            df = pd.read_sql_query(query, conexion)
            return df
        except Exception as e:
            print(f"Error al obtener logs: {e}")
            return None
        finally:
            conexion.close()