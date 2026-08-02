import time
import os
import sqlite3
from motor_entrenamiento import entrenar_plataforma_completa

DB_TYPE = os.environ.get('DB_TYPE', 'sqlite').lower()
is_postgres = (DB_TYPE == 'postgres')
DB_PATH = "/volumen_compartido/base_datos/cdc_database.db"

def obtener_conexion():
    if is_postgres:
        import psycopg2
        return psycopg2.connect(
            host=os.environ.get('DB_HOST', 'postgres'),
            user=os.environ.get('DB_USER', 'intexus'),
            password=os.environ.get('DB_PASSWORD', 'intexus01'),
            dbname=os.environ.get('DB_NAME', 'cdc_database'),
            port=os.environ.get('DB_PORT', '5432')
        )
    else:
        return sqlite3.connect(DB_PATH)

def get_estado():
    if not is_postgres and not os.path.exists(DB_PATH):
        return "listo"
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM estado_sistema WHERE clave = 'entrenamiento'")
        resultado = cursor.fetchone()
        conn.close()
        if resultado:
            return resultado[0]
    except Exception as e:
        print(f"Error DB (get_estado): {e}")
    return "listo"

def set_estado(clave, valor):
    if not is_postgres and not os.path.exists(DB_PATH):
        return
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        if is_postgres:
            cursor.execute("UPDATE estado_sistema SET valor = %s WHERE clave = %s", (valor, clave))
        else:
            cursor.execute("UPDATE estado_sistema SET valor = ? WHERE clave = ?", (valor, clave))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error DB (set_estado): {e}")

print("💤 Guardián IA activado. Contenedor en reposo absoluto...")

while True:
    estado = get_estado()
    if estado == "PROCESANDO":
        print("\n🔔 ¡ALERTA! Orden recibida...")
        
        try:
            entrenar_plataforma_completa(callback_progreso=lambda p: set_estado('progreso_entrenamiento', str(p)))
            print("✅ Misión cumplida. Volviendo a hibernación... 💤\n")
        except Exception as e:
            print(f"❌ Error crítico: {e}")
        finally:
            set_estado('entrenamiento', 'LISTO')
            set_estado('progreso_entrenamiento', '100')
            
    time.sleep(3)