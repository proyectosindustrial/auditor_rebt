import sqlite3
import json
from datetime import datetime

DB_NAME = "auditorias.db"

def init_db():
    """Inicializa la base de datos creando la tabla si no existe."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auditorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            nombre_instalacion TEXT NOT NULL,
            datos_entrada TEXT NOT NULL,
            informe_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def guardar_auditoria(nombre_instalacion: str, datos_entrada: str, informe_json_str: str) -> int:
    """Guarda una nueva auditoría en la base de datos y retorna su ID."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO auditorias (fecha, nombre_instalacion, datos_entrada, informe_json)
        VALUES (?, ?, ?, ?)
    """, (fecha_actual, nombre_instalacion, datos_entrada, informe_json_str))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id

def obtener_historial():
    """Recupera la lista abreviada de auditorías registradas."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, nombre_instalacion FROM auditorias ORDER BY id DESC")
    filas = cursor.fetchall()
    conn.close()
    return filas

def obtener_auditoria_por_id(auditoria_id: int):
    """Obtiene el registro completo de una auditoría por su ID."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha, nombre_instalacion, datos_entrada, informe_json FROM auditorias WHERE id = ?", (auditoria_id,))
    fila = cursor.fetchone()
    conn.close()
    return fila
