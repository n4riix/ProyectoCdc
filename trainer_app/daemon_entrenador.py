import time
import os
import sqlite3
from motor_entrenamiento import entrenar_plataforma_completa

DB_PATH = "/volumen_compartido/base_datos/cdc_database.db"

def get_estado():
    if not os.path.exists(DB_PATH):
        return "listo"
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM estado_sistema WHERE clave = 'entrenamiento'")
        resultado = cursor.fetchone()
        conn.close()
        if resultado:
            return resultado[0]
    except Exception:
        pass
    return "listo"

def set_estado(clave, valor):
    if not os.path.exists(DB_PATH):
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE estado_sistema SET valor = ? WHERE clave = ?", (valor, clave))
        conn.commit()
        conn.close()
    except Exception:
        pass

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