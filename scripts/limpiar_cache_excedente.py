#!/usr/bin/env python3
"""
limpiar_cache_excedente.py
==========================
Limpia los archivos de caché (.txt) en dataset_global dejando como máximo
el límite especificado (por defecto 50) por tipo documental.

Uso:
    # Simular y ver qué se borraría (sin tocar nada):
    python3 limpiar_cache_excedente.py --simular

    # Ejecutar la limpieza real:
    python3 limpiar_cache_excedente.py --ejecutar --limite 50
"""

import os
import sys
import argparse

DATASET_GLOBAL = "/home/intexus/app/ProyectoCdc/volumen_compartido/dataset_global"

def limpiar_cache(limite=50, simular=True):
    if not os.path.isdir(DATASET_GLOBAL):
        print(f"❌ No existe la ruta: {DATASET_GLOBAL}")
        sys.exit(1)

    print("=" * 70)
    print(f"🧹 {'[SIMULACIÓN] ' if simular else ''}LIMPIEZA DE CACHÉ EXCEDENTE (Límite: {limite} txt por clase)")
    print("=" * 70)

    clases = sorted([
        d for d in os.listdir(DATASET_GLOBAL)
        if os.path.isdir(os.path.join(DATASET_GLOBAL, d))
    ])

    total_eliminados = 0
    clases_afectadas = 0

    for c in clases:
        ruta_clase = os.path.join(DATASET_GLOBAL, c)
        archivos = os.listdir(ruta_clase)
        
        # Identificar imágenes y txt
        txts = sorted([f for f in archivos if f.lower().endswith('.txt')])
        
        if len(txts) > limite:
            excedente = len(txts) - limite
            clases_afectadas += 1
            print(f"📁 {c:<46} | Tiene: {len(txts):4d} txt | A podar: {excedente:4d} txt")
            
            # Los txts a eliminar (los últimos en orden para conservar los primeros 50)
            a_borrar = txts[limite:]
            
            for f_txt in a_borrar:
                ruta_txt = os.path.join(ruta_clase, f_txt)
                if not simular:
                    try:
                        os.remove(ruta_txt)
                    except Exception as e:
                        print(f"   ⚠️ Error borrando {f_txt}: {e}")
            
            total_eliminados += len(a_borrar)

    print("-" * 70)
    if simular:
        print(f"ℹ️  Total clases que superan el límite: {clases_afectadas}")
        print(f"ℹ️  Total archivos .txt que SERÍAN eliminados: {total_eliminados}")
        print("💡 Para aplicar los cambios reales ejecuta con: --ejecutar")
    else:
        print(f"✅ Limpieza finalizada.")
        print(f"✅ Clases optimizadas: {clases_afectadas}")
        print(f"✅ Total archivos .txt eliminados: {total_eliminados}")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Limpiador de caché excedente de IA")
    parser.add_argument("--limite", type=int, default=50, help="Máximo de txt a conservar por clase (default: 50)")
    parser.add_argument("--simular", action="store_true", help="Solo muestra lo que se borraría sin alterar disco")
    parser.add_argument("--ejecutar", action="store_true", help="Aplica la eliminación real en disco")

    args = parser.parse_args()

    if not args.simular and not args.ejecutar:
        parser.print_help()
        sys.exit(0)

    limpiar_cache(limite=args.limite, simular=args.simular)

if __name__ == "__main__":
    main()
