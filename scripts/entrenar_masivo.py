#!/usr/bin/env python3
"""
entrenar_masivo.py
==================
Herramienta de línea de comandos para Desarrolladores y Administradores.
Permite entrenar o reentrenar la IA de forma masiva sobre decenas de clases documentales
sin pasar por la interfaz gráfica web.

Uso:
    # 1. Ver qué clases existen actualmente en dataset_global:
    python3 entrenar_masivo.py --listar

    # 2. Reentrenar sobre todo lo que ya está en dataset_global (masivo):
    python3 entrenar_masivo.py --ejecutar

    # 3. Importar una carpeta externa con 30 subcarpetas de tipos documentales y reentrenar de inmediato:
    python3 entrenar_masivo.py --origen /ruta/a/carpeta_con_tipos --ejecutar
"""

import os
import sys
import shutil
import argparse
import subprocess
from datetime import datetime

DATASET_GLOBAL_HOST = "/home/intexus/app/ProyectoCdc/volumen_compartido/dataset_global"
CEREBROS_HOST = "/home/intexus/app/ProyectoCdc/volumen_compartido/cerebros_ia"
TRAINER_CONTAINER = "cdc_trainer"
WEB_CONTAINER = "cdc_web"
CELERY_CONTAINER = "cdc_celery"

FORMATOS_VALIDOS = {'.tif', '.tiff', '.pdf', '.jpg', '.jpeg', '.png'}

def listar_dataset():
    if not os.path.exists(DATASET_GLOBAL_HOST):
        print(f"❌ No existe la ruta {DATASET_GLOBAL_HOST}")
        return []
    
    clases = sorted([
        d for d in os.listdir(DATASET_GLOBAL_HOST)
        if os.path.isdir(os.path.join(DATASET_GLOBAL_HOST, d))
    ])
    
    print("\n" + "="*65)
    print(f"📊 INVENTARIO ACTUAL EN DATASET GLOBAL ({len(clases)} clases)")
    print("="*65)
    
    total_archivos = 0
    for idx, c in enumerate(clases, 1):
        ruta_c = os.path.join(DATASET_GLOBAL_HOST, c)
        archivos = [f for f in os.listdir(ruta_c) if os.path.isfile(os.path.join(ruta_c, f))]
        imgs = [f for f in archivos if os.path.splitext(f.lower())[1] in FORMATOS_VALIDOS]
        txts = [f for f in archivos if f.lower().endswith('.txt')]
        total_archivos += len(imgs)
        print(f" {idx:2d}. {c:<45} -> {len(imgs):3d} docs ({len(txts)} en caché)")
        
    print("-" * 65)
    print(f" Total de documentos físicos acumulados: {total_archivos}")
    print("="*65 + "\n")
    return clases

def importar_origen(ruta_origen):
    if not os.path.isdir(ruta_origen):
        print(f"❌ La ruta de origen no existe o no es carpeta: {ruta_origen}")
        sys.exit(1)

    print(f"\n📂 Analizando carpeta origen: {ruta_origen}...")
    subcarpetas = [
        d for d in os.listdir(ruta_origen)
        if os.path.isdir(os.path.join(ruta_origen, d))
    ]

    if not subcarpetas:
        print("⚠️ No se encontraron subcarpetas (tipos documentales) en la ruta indicada.")
        sys.exit(1)

    print(f"🔍 Detectadas {len(subcarpetas)} subcarpetas para importar.")
    copiados = 0

    for c in subcarpetas:
        src = os.path.join(ruta_origen, c)
        dst = os.path.join(DATASET_GLOBAL_HOST, c)
        os.makedirs(dst, exist_ok=True)
        
        for item in os.listdir(src):
            s_item = os.path.join(src, item)
            d_item = os.path.join(dst, item)
            if os.path.isfile(s_item):
                ext = os.path.splitext(item.lower())[1]
                if ext in FORMATOS_VALIDOS or ext == '.txt':
                    if not os.path.exists(d_item):
                        shutil.copy2(s_item, d_item)
                        copiados += 1

    # Permisos 777 para que el contenedor pueda leer/escribir caché
    try:
        subprocess.run(["chmod", "-R", "777", DATASET_GLOBAL_HOST], check=False)
    except Exception:
        pass

    print(f"✅ Importación completada: {copiados} archivos nuevos copiados a dataset_global.")

def ejecutar_entrenamiento():
    print("\n🚀 INICIANDO ENTRENAMIENTO MASIVO UNIFICADO EN CONTENEDOR...")
    print("=" * 65)
    
    # 1. Asegurar permisos 777
    subprocess.run(["chmod", "-R", "777", DATASET_GLOBAL_HOST], check=False)
    subprocess.run(["chmod", "-R", "777", CEREBROS_HOST], check=False)
    
    # 2. Ejecutar motor_entrenamiento.py dentro de cdc_trainer mostrando logs en vivo
    cmd = ["docker", "exec", "-t", TRAINER_CONTAINER, "python3", "/app/motor_entrenamiento.py"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    for line in proc.stdout:
        print(line, end="")
        sys.stdout.flush()
        
    proc.wait()
    
    if proc.returncode == 0:
        print("\n" + "=" * 65)
        print("🎉 ENTRENAMIENTO MASIVO FINALIZADO CON ÉXITO")
        print("=" * 65)
        
        # 3. Limpiar lista negra si existía
        blacklist_file = os.path.join(CEREBROS_HOST, "clases_eliminadas.json")
        try:
            with open(blacklist_file, "w", encoding="utf-8") as f:
                f.write("[]")
            print("🧹 Lista negra reseteada (todos los modelos activos).")
        except Exception as e:
            print(f"⚠️ No se pudo limpiar lista negra: {e}")

        # 4. Reiniciar cdc_web y cdc_celery para que carguen el nuevo cerebro pkl
        print("♻️ Reiniciando cdc_web y cdc_celery para recargar el nuevo cerebro IA...")
        subprocess.run(["docker", "restart", WEB_CONTAINER, CELERY_CONTAINER], check=False)
        print("✅ Servicios actualizados. La IA ya está lista con todas las clases.")
    else:
        print(f"\n❌ Error durante el entrenamiento (Código de salida: {proc.returncode})")

def main():
    parser = argparse.ArgumentParser(
        description="Script CLI de Entrenamiento Masivo de IA (CDC Auditor)"
    )
    parser.add_argument("--listar", action="store_true", help="Muestra el inventario de clases y documentos actuales en dataset_global")
    parser.add_argument("--origen", type=str, help="Ruta de una carpeta con subdirectorios de tipos documentales para importar")
    parser.add_argument("--ejecutar", action="store_true", help="Ejecuta la rutina de entrenamiento masivo unificado")

    args = parser.parse_args()

    if not any([args.listar, args.origen, args.ejecutar]):
        parser.print_help()
        sys.exit(0)

    if args.origen:
        importar_origen(args.origen)

    if args.listar and not args.ejecutar:
        listar_dataset()

    if args.ejecutar:
        listar_dataset()
        ejecutar_entrenamiento()

if __name__ == "__main__":
    main()
