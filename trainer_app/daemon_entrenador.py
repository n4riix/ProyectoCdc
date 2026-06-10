import time
import os
from motor_entrenamiento import entrenar_plataforma_completa

FLAG_FILE = "/volumen_compartido/orden_entrenar.flag"
LOCK_FILE = "/volumen_compartido/entrenando.lock"

print("💤 Guardián IA activado. Contenedor en reposo absoluto...")

while True:
    if os.path.exists(FLAG_FILE):
        print("\n🔔 ¡ALERTA! Orden recibida...")
        os.remove(FLAG_FILE) # Borramos la orden
        
        # Ponemos el letrero de "Trabajando"
        with open(LOCK_FILE, 'w') as f:
            f.write("PROCESANDO")
            
        try:
            entrenar_plataforma_completa()
            print("✅ Misión cumplida. Volviendo a hibernación... 💤\n")
        except Exception as e:
            print(f"❌ Error crítico: {e}")
        finally:
            # Quitamos el letrero al terminar (ya sea por éxito o por error)
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
            
    time.sleep(3)