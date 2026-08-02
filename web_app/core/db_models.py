import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Determinar motor de BD
DB_TYPE = os.environ.get('DB_TYPE', 'sqlite').lower()
is_postgres = (DB_TYPE == 'postgres')

# SQLite Config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB_PATH = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'base_datos', 'cdc_database.db')

def obtener_conexion():
    """Crea y retorna una conexión a la base de datos (Postgres o SQLite)."""
    if is_postgres:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'postgres'),
            user=os.environ.get('DB_USER', 'intexus'),
            password=os.environ.get('DB_PASSWORD', 'intexus01'),
            dbname=os.environ.get('DB_NAME', 'cdc_database'),
            port=os.environ.get('DB_PORT', '5432')
        )
        return conn
    else:
        import sqlite3
        os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(cursor, query, params=None):
    """Convierte parámetros de SQLite (?) a Postgres (%s) si es necesario."""
    if is_postgres:
        query = query.replace('?', '%s')
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

def fetchone_dict(cursor):
    row = cursor.fetchone()
    if not row:
        return None
    if is_postgres:
        import psycopg2.extras
        # psycopg2 cursor without DictCursor returns tuple, but wait, we can just use dict(row) if we fetch columns.
        # Actually, let's just use RealDictCursor when creating the cursor!
        return dict(row)
    else:
        return dict(row)

def obtener_cursor(conn):
    if is_postgres:
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()

def inicializar_base_datos():
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)

    if is_postgres:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK(rol IN ('superadmin', 'admin', 'analista'))
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registro_auditoria (
                id SERIAL PRIMARY KEY,
                archivo_tif TEXT NOT NULL UNIQUE,
                proceso_matriz TEXT NOT NULL,
                subproceso TEXT NOT NULL,
                clasificacion_humana TEXT NOT NULL,
                clasificacion_ia TEXT NOT NULL,
                nivel_confianza REAL NOT NULL,
                veredicto TEXT NOT NULL,
                fecha_revision TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS estado_sistema (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT INTO estado_sistema (clave, valor) VALUES ('entrenamiento', 'LISTO') ON CONFLICT (clave) DO NOTHING")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auditorias_lotes (
                id TEXT PRIMARY KEY,
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_fin TIMESTAMP,
                estado TEXT NOT NULL,
                total_documentos INTEGER DEFAULT 0,
                documentos_procesados INTEGER DEFAULT 0,
                errores INTEGER DEFAULT 0,
                archivo_indice TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auditoria_resultados (
                id SERIAL PRIMARY KEY,
                auditoria_id TEXT NOT NULL,
                linea_indice INTEGER,
                archivo TEXT NOT NULL,
                matriz TEXT,
                subproceso TEXT,
                esperado TEXT,
                prediccion TEXT,
                confianza REAL DEFAULT 100.0,
                estado TEXT,
                FOREIGN KEY(auditoria_id) REFERENCES auditorias_lotes(id)
            )
        ''')
    else:
        # Lógica original de SQLite (con su migración)
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'")
        tabla_existente = cursor.fetchone()
        if tabla_existente and 'superadmin' not in tabla_existente['sql']:
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
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    rol TEXT NOT NULL CHECK(rol IN ('superadmin', 'admin', 'analista'))
                )
            ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registro_auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archivo_tif TEXT NOT NULL UNIQUE,
                proceso_matriz TEXT NOT NULL,
                subproceso TEXT NOT NULL,
                clasificacion_humana TEXT NOT NULL,
                clasificacion_ia TEXT NOT NULL,
                nivel_confianza REAL NOT NULL,
                veredicto TEXT NOT NULL,
                fecha_revision TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS estado_sistema (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO estado_sistema (clave, valor) VALUES ('entrenamiento', 'LISTO')")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auditorias_lotes (
                id TEXT PRIMARY KEY,
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fecha_fin TIMESTAMP,
                estado TEXT NOT NULL,
                total_documentos INTEGER DEFAULT 0,
                documentos_procesados INTEGER DEFAULT 0,
                errores INTEGER DEFAULT 0,
                archivo_indice TEXT
            )
        ''')
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
                estado TEXT,
                FOREIGN KEY(auditoria_id) REFERENCES auditorias_lotes(id)
            )
        ''')
        try:
            cursor.execute("ALTER TABLE auditoria_resultados ADD COLUMN linea_indice INTEGER")
        except: pass
        try:
            cursor.execute("ALTER TABLE auditoria_resultados ADD COLUMN confianza REAL DEFAULT 100.0")
        except: pass
        try:
            cursor.execute("ALTER TABLE auditorias_lotes ADD COLUMN archivo_indice TEXT")
        except: pass

    # Inyección de usuarios maestros
    cursor.execute("SELECT COUNT(*) as count FROM usuarios")
    if cursor.fetchone()['count'] == 0:
        pass_hash = generate_password_hash('admin123') 
        execute_query(cursor, "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)", ('admin', pass_hash, 'admin'))
    
    execute_query(cursor, "SELECT COUNT(*) as count FROM usuarios WHERE username = ?", ('ecastro',))
    if cursor.fetchone()['count'] == 0:
        pass_hash_super = generate_password_hash('3346041')
        execute_query(cursor, "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)", ('ecastro', pass_hash_super, 'superadmin'))

    conn.commit()
    conn.close()

def verificar_usuario(username, password):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    execute_query(cursor, "SELECT password_hash, rol FROM usuarios WHERE username = ?", (username,))
    usuario = fetchone_dict(cursor)
    conn.close()
    if usuario and check_password_hash(usuario['password_hash'], password):
        return usuario['rol']
    return None

def registrar_auditoria_documento(archivo, matriz, subproceso, kofax, ia, veredicto):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        if is_postgres:
            q = '''INSERT INTO registro_auditoria (archivo_tif, proceso_matriz, subproceso, clasificacion_humana, clasificacion_ia, veredicto, nivel_confianza) 
                   VALUES (%s, %s, %s, %s, %s, %s, 0.0) 
                   ON CONFLICT (archivo_tif) DO UPDATE SET veredicto = EXCLUDED.veredicto'''
            cursor.execute(q, (archivo, matriz, subproceso, kofax, ia, veredicto))
        else:
            q = '''INSERT OR REPLACE INTO registro_auditoria (archivo_tif, proceso_matriz, subproceso, clasificacion_humana, clasificacion_ia, veredicto, nivel_confianza) 
                   VALUES (?, ?, ?, ?, ?, ?, 0.0)'''
            cursor.execute(q, (archivo, matriz, subproceso, kofax, ia, veredicto))
        conn.commit()
    except Exception as e:
        print(f"Error al guardar en BD: {e}")
    finally:
        conn.close()

def set_estado(clave, valor):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    if is_postgres:
        cursor.execute("INSERT INTO estado_sistema (clave, valor) VALUES (%s, %s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (clave, valor))
    else:
        cursor.execute("INSERT OR REPLACE INTO estado_sistema (clave, valor) VALUES (?, ?)", (clave, valor))
    conn.commit()
    conn.close()

def get_estado(clave, valor_por_defecto=None):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    execute_query(cursor, "SELECT valor FROM estado_sistema WHERE clave = ?", (clave,))
    resultado = fetchone_dict(cursor)
    conn.close()
    if resultado:
        return resultado['valor']
    return valor_por_defecto

def obtener_lineas_procesadas(auditoria_id):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    execute_query(cursor, "SELECT linea_indice FROM auditoria_resultados WHERE auditoria_id = ?", (auditoria_id,))
    lineas = {row['linea_indice'] for row in cursor.fetchall() if dict(row)['linea_indice'] is not None}
    conn.close()
    return lineas

def listar_usuarios():
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    cursor.execute("SELECT id, username, rol FROM usuarios ORDER BY id")
    usuarios = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return usuarios

def crear_usuario(username, password, rol):
    if rol not in ('superadmin', 'admin', 'analista'): return False, "Rol inválido."
    if not username or not password: return False, "Usuario y contraseña obligatorios."
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        pass_hash = generate_password_hash(password)
        execute_query(cursor, "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)", (username.strip(), pass_hash, rol))
        conn.commit()
        return True, f"Usuario '{username}' creado."
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        conn.close()

def eliminar_usuario(user_id, usuario_actual):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        execute_query(cursor, "SELECT username FROM usuarios WHERE id = ?", (user_id,))
        usuario = fetchone_dict(cursor)
        if not usuario: return False, "No encontrado."
        if usuario['username'] == usuario_actual: return False, "No puedes eliminar tu cuenta."
        execute_query(cursor, "DELETE FROM usuarios WHERE id = ?", (user_id,))
        conn.commit()
        return True, f"Usuario '{usuario['username']}' eliminado."
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        conn.close()

def crear_lote_auditoria(task_id, total_documentos, archivo_indice=None):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        execute_query(cursor, "INSERT INTO auditorias_lotes (id, estado, total_documentos, archivo_indice) VALUES (?, ?, ?, ?)", (task_id, 'procesando', total_documentos, archivo_indice))
        conn.commit()
    except Exception as e:
        print(f"Error lote: {e}")
    finally:
        conn.close()

def actualizar_progreso_lote(task_id, documentos_procesados, error=False):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        if error:
            execute_query(cursor, "UPDATE auditorias_lotes SET errores = errores + 1 WHERE id = ?", (task_id,))
        else:
            execute_query(cursor, "UPDATE auditorias_lotes SET documentos_procesados = ? WHERE id = ?", (documentos_procesados, task_id))
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()

def completar_lote_auditoria(task_id, estado='completado'):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        execute_query(cursor, "UPDATE auditorias_lotes SET estado = ?, fecha_fin = CURRENT_TIMESTAMP WHERE id = ?", (estado, task_id))
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()

def guardar_resultado_auditoria(task_id, linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado, confianza=100.0):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        execute_query(cursor, "INSERT INTO auditoria_resultados (auditoria_id, linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado, confianza) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (task_id, linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado, confianza))
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()

def obtener_estado_lote(task_id):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    execute_query(cursor, "SELECT * FROM auditorias_lotes WHERE id = ?", (task_id,))
    row = fetchone_dict(cursor)
    conn.close()
    return row

def obtener_resultados_lote(task_id):
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    execute_query(cursor, "SELECT * FROM auditoria_resultados WHERE auditoria_id = ?", (task_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def listar_lotes_auditoria():
    conn = obtener_conexion()
    cursor = obtener_cursor(conn)
    try:
        if is_postgres:
            cursor.execute("SELECT id FROM auditorias_lotes ORDER BY fecha_inicio DESC OFFSET 12")
        else:
            cursor.execute("SELECT id FROM auditorias_lotes ORDER BY fecha_inicio DESC LIMIT -1 OFFSET 12")
        
        lotes_viejos = cursor.fetchall()
        for lote in lotes_viejos:
            execute_query(cursor, "DELETE FROM auditoria_resultados WHERE auditoria_id = ?", (dict(lote)['id'],))
            execute_query(cursor, "DELETE FROM auditorias_lotes WHERE id = ?", (dict(lote)['id'],))
        if lotes_viejos:
            conn.commit()
    except Exception as e:
        pass

    cursor.execute("SELECT * FROM auditorias_lotes ORDER BY fecha_inicio DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows