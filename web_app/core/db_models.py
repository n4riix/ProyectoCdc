import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Ruta absoluta hacia la bóveda (volumen compartido)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'base_datos', 'cdc_database.db')

def obtener_conexion():
    """Crea y retorna una conexión a la base de datos SQLite."""
    # Se asegura de que la carpeta exista antes de crear el archivo
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Permite acceder a las columnas por su nombre (ej: fila['username'])
    conn.row_factory = sqlite3.Row 
    return conn

def inicializar_base_datos():
    """Crea las tablas maestras e inyecta el Administrador por defecto."""
    conn = obtener_conexion()
    cursor = conn.cursor()

    # --- TABLA 1: SEGURIDAD Y ROLES ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL CHECK(rol IN ('admin', 'analista'))
        )
    ''')

    # --- TABLA 2: TRAZABILIDAD Y AUDITORÍA ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registro_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo_tif TEXT NOT NULL UNIQUE,  -- UNIQUE evita procesar el mismo archivo dos veces
            proceso_matriz TEXT NOT NULL,      -- Ej: BR o BT
            subproceso TEXT NOT NULL,          -- Ej: CCD, ACT, CNW
            clasificacion_humana TEXT NOT NULL,
            clasificacion_ia TEXT NOT NULL,
            veredicto TEXT NOT NULL,           -- 'MATCH PERFECTO', 'ALERTA', 'CORREGIDO'
            clasificacion_final TEXT,          -- Solo se llena si un humano lo corrige
            corregido_por TEXT,                -- Firma del analista/admin
            fecha_procesamiento DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # --- INYECCIÓN DEL USUARIO MAESTRO ---
    # Verifica si la tabla de usuarios está vacía. Si es así, crea el primer Admin.
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    if cursor.fetchone()[0] == 0:
        # Encriptación fuerte de la contraseña
        pass_hash = generate_password_hash('admin123') 
        cursor.execute(
            "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)", 
            ('admin', pass_hash, 'admin')
        )
        print("✅ Base de datos inicializada. Creado usuario: 'admin' / Clave: 'admin123'")

    conn.commit()
    conn.close()

def verificar_usuario(username, password):
    """Valida el login y devuelve el rol del usuario ('admin' o 'analista'). Si falla, devuelve None."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, rol FROM usuarios WHERE username = ?", (username,))
    usuario = cursor.fetchone()
    conn.close()

    # Si el usuario existe y la contraseña encriptada coincide
    if usuario and check_password_hash(usuario['password_hash'], password):
        return usuario['rol']
    
    return None

def registrar_auditoria_documento(archivo, matriz, subproceso, kofax, ia, veredicto):
    """Guarda el resultado de la IA en tiempo real (Sustituye al antiguo Guardado en Vivo)."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO registro_auditoria 
            (archivo_tif, proceso_matriz, subproceso, clasificacion_humana, clasificacion_ia, veredicto) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (archivo, matriz, subproceso, kofax, ia, veredicto))
        conn.commit()
    except Exception as e:
        print(f"Error al guardar en BD: {e}")
    finally:
        conn.close()