import sqlite3
from datetime import datetime

class GestorBaseDatos:
    """
    Clase para gestionar la persistencia local del sistema mediante SQLite.
    Actúa como un log de auditoría para registrar eventos críticos del bot.
    """
    def __init__(self, db_name="tfg_trading.db"):
        self.db_name = db_name
        self._crear_tablas()

    def _conectar(self):
        """Abre una conexión a la base de datos local."""
        return sqlite3.connect(self.db_name)

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
        
        # En la Fase 4 añadiremos aquí la tabla de 'operaciones'
        
        conexion.commit()
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