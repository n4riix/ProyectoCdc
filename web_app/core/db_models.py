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
    # Migración: verificar si la tabla existente tiene el constraint antiguo sin 'superadmin'
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'")
    tabla_existente = cursor.fetchone()
    if tabla_existente and 'superadmin' not in tabla_existente[0]:
        # Migrar: recrear tabla con el nuevo constraint
        cursor.execute('ALTER TABLE usuarios RENAME TO usuarios_old')
        cursor.execute('''
            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK(rol IN ('superadmin', 'admin', 'analista'))
            )
        ''')
        cursor.execute('INSERT INTO usuarios SELECT * FROM usuarios_old')
        cursor.execute('DROP TABLE usuarios_old')
        print("\u2705 Migración completada: rol 'superadmin' habilitado.")
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK(rol IN ('superadmin', 'admin', 'analista'))
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

    # --- TABLA 3: ESTADO DEL SISTEMA ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estado_sistema (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO estado_sistema (clave, valor) VALUES ('entrenamiento', 'LISTO')")

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
        print("\u2705 Base de datos inicializada. Creado usuario: 'admin' / Clave: 'admin123'")

    # --- INYECCIÓN DEL SUPERADMINISTRADOR ---
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'ecastro'")
    if cursor.fetchone()[0] == 0:
        pass_hash_super = generate_password_hash('3346041')
        cursor.execute(
            "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)",
            ('ecastro', pass_hash_super, 'superadmin')
        )
        print("\u2705 Superadministrador creado: 'ecastro'")

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

def set_estado(clave, valor):
    """Establece un estado global en el sistema."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO estado_sistema (clave, valor) VALUES (?, ?)", (clave, valor))
    conn.commit()
    conn.close()

def get_estado(clave, valor_por_defecto=None):
    """Obtiene un estado global del sistema."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM estado_sistema WHERE clave = ?", (clave,))
    resultado = cursor.fetchone()
    conn.close()
    if resultado:
        return resultado['valor']
    return valor_por_defecto


def listar_usuarios():
    """Retorna la lista de todos los usuarios registrados (sin contraseñas)."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, rol FROM usuarios ORDER BY id")
    usuarios = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return usuarios


def crear_usuario(username, password, rol):
    """Crea un nuevo usuario. Retorna (True, mensaje) o (False, error)."""
    if rol not in ('superadmin', 'admin', 'analista'):
        return False, "Rol inválido."
    if not username or not password:
        return False, "Usuario y contraseña son obligatorios."
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        pass_hash = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)",
            (username.strip(), pass_hash, rol)
        )
        conn.commit()
        return True, f"Usuario '{username}' creado con rol '{rol}'."
    except sqlite3.IntegrityError:
        return False, f"El usuario '{username}' ya existe."
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        conn.close()


def eliminar_usuario(user_id, usuario_actual):
    """Elimina un usuario por ID. No permite auto-eliminación."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM usuarios WHERE id = ?", (user_id,))
        usuario = cursor.fetchone()
        if not usuario:
            return False, "Usuario no encontrado."
        if usuario['username'] == usuario_actual:
            return False, "No puedes eliminar tu propia cuenta."
        cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
        conn.commit()
        return True, f"Usuario '{usuario['username']}' eliminado."
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        conn.close()