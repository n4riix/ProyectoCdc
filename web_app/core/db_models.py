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
            nivel_confianza REAL NOT NULL,
            veredicto TEXT NOT NULL,           -- 'coincide', 'discrepancia', 'duda_ia'
            fecha_revision TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    # --- TABLA 4: LOTES DE AUDITORÍA (Celery) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auditorias_lotes (
            id TEXT PRIMARY KEY,               -- task_id de Celery
            fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_fin TIMESTAMP,
            estado TEXT NOT NULL,              -- 'procesando', 'completado', 'error'
            total_documentos INTEGER DEFAULT 0,
            documentos_procesados INTEGER DEFAULT 0,
            errores INTEGER DEFAULT 0
        )
    ''')

    # --- TABLA 5: RESULTADOS DE LOTES ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auditoria_resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auditoria_id TEXT NOT NULL,
            linea_indice INTEGER,
            archivo TEXT NOT NULL,
            matriz TEXT,
            subproceso TEXT,
            esperado TEXT,
            prediccion TEXT,
            confianza REAL DEFAULT 100.0,
            estado TEXT,                       -- 'success', 'warning', 'danger'
            FOREIGN KEY(auditoria_id) REFERENCES auditorias_lotes(id)
        )
    ''')
    
    # Intento de agregar la columna si la tabla ya existía sin ella
    try:
        cursor.execute("ALTER TABLE auditoria_resultados ADD COLUMN linea_indice INTEGER")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE auditoria_resultados ADD COLUMN confianza REAL DEFAULT 100.0")
    except:
        pass

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
            (archivo_tif, proceso_matriz, subproceso, clasificacion_humana, clasificacion_ia, veredicto, nivel_confianza) 
            VALUES (?, ?, ?, ?, ?, ?, 0.0)
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


def obtener_lineas_procesadas(auditoria_id):
    """Devuelve un set con los números de línea ya procesados para un lote."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT linea_indice FROM auditoria_resultados WHERE auditoria_id = ?", (auditoria_id,))
    lineas = {row['linea_indice'] for row in cursor.fetchall() if row['linea_indice'] is not None}
    conn.close()
    return lineas


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

# --- FUNCIONES PARA LOTES DE AUDITORÍA (CELERY) ---

def crear_lote_auditoria(task_id, total_documentos):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO auditorias_lotes (id, estado, total_documentos) VALUES (?, ?, ?)",
            (task_id, 'procesando', total_documentos)
        )
        conn.commit()
    except Exception as e:
        print(f"Error al crear lote: {e}")
    finally:
        conn.close()

def actualizar_progreso_lote(task_id, documentos_procesados, error=False):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        if error:
            cursor.execute("UPDATE auditorias_lotes SET errores = errores + 1 WHERE id = ?", (task_id,))
        else:
            cursor.execute("UPDATE auditorias_lotes SET documentos_procesados = ? WHERE id = ?", (documentos_procesados, task_id))
        conn.commit()
    except Exception as e:
        print(f"Error al actualizar lote: {e}")
    finally:
        conn.close()

def completar_lote_auditoria(task_id, estado='completado'):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE auditorias_lotes SET estado = ?, fecha_fin = CURRENT_TIMESTAMP WHERE id = ?",
            (estado, task_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error al completar lote: {e}")
    finally:
        conn.close()

def guardar_resultado_auditoria(task_id, linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado, confianza=100.0):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO auditoria_resultados 
            (auditoria_id, linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado, confianza) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado, confianza))
        conn.commit()
    except Exception as e:
        print(f"Error al guardar resultado: {e}")
    finally:
        conn.close()

def obtener_estado_lote(task_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM auditorias_lotes WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def obtener_resultados_lote(task_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM auditoria_resultados WHERE auditoria_id = ?", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def listar_lotes_auditoria():
    """Retorna los últimos 12 lotes de auditoría y limpia los más antiguos de la BD."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # 1. Limpieza automática (Mantiene solo los 12 más recientes)
    try:
        cursor.execute('''
            SELECT id FROM auditorias_lotes 
            ORDER BY fecha_inicio DESC 
            LIMIT -1 OFFSET 12
        ''')
        lotes_viejos = cursor.fetchall()
        for lote in lotes_viejos:
            cursor.execute("DELETE FROM auditoria_resultados WHERE auditoria_id = ?", (lote['id'],))
            cursor.execute("DELETE FROM auditorias_lotes WHERE id = ?", (lote['id'],))
        if lotes_viejos:
            conn.commit()
    except Exception as e:
        print(f"Error en auto-limpieza de historial: {e}")

    # 2. Retornar los restantes
    cursor.execute("SELECT * FROM auditorias_lotes ORDER BY fecha_inicio DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]