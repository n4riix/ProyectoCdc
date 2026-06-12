import os
import glob
import joblib
import pandas as pd
from paddleocr import PaddleOCR
import logging
import shutil
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.dummy import DummyClassifier

# Silenciar mensajes innecesarios de PaddleOCR en la consola
logging.getLogger("ppocr").setLevel(logging.WARNING)

DATASET_DIR = "/volumen_compartido/dataset_entrenamiento"
CEREBROS_DIR = "/volumen_compartido/cerebros_ia"

def archive_dataset(ruta_subproceso, matriz, subproceso):
    """
    Mueve los archivos procesados a `processed/{matriz}/{subproceso}/{clase}` para limpiar el dataset activo.
    No se preserva la marca de hora ni la estructura de timestamp.
    """
    try:
        destino_base = os.path.join(DATASET_DIR, 'processed', matriz, subproceso)
        os.makedirs(destino_base, exist_ok=True)

        # Mover cada clase completa a processed/{matriz}/{subproceso}/{clase}
        for clase in os.listdir(ruta_subproceso):
            ruta_clase = os.path.join(ruta_subproceso, clase)
            if not os.path.isdir(ruta_clase):
                continue

            destino_clase = os.path.join(destino_base, clase)
            os.makedirs(destino_clase, exist_ok=True)

            for f in glob.glob(os.path.join(ruta_clase, '*')):
                try:
                    nombre_archivo = os.path.basename(f)
                    destino_archivo = os.path.join(destino_clase, nombre_archivo)
                    if os.path.exists(destino_archivo):
                        base, ext = os.path.splitext(nombre_archivo)
                        contador = 1
                        while os.path.exists(destino_archivo):
                            destino_archivo = os.path.join(destino_clase, f"{base}_{contador}{ext}")
                            contador += 1
                    shutil.move(f, destino_archivo)
                except Exception as e:
                    print(f"⚠️ No se pudo mover {f}: {e}")

        # Intentar remover carpetas vacías de forma recursiva
        try:
            for root, dirs, files in os.walk(ruta_subproceso, topdown=False):
                if not os.listdir(root):
                    os.rmdir(root)
            if os.path.isdir(ruta_subproceso) and not os.listdir(ruta_subproceso):
                os.rmdir(ruta_subproceso)
        except Exception:
            pass

        print(f"🗄️ Datos de {matriz}-{subproceso} movidos a {destino_base}")
    except Exception as e:
        print(f"❌ Error archivando dataset para {matriz}-{subproceso}: {e}")


def obtener_texto_con_cache(ocr_instancia, ruta_archivo_imagen):
    """
    Busca si existe un archivo .txt de caché para la imagen.
    Si existe y es más nuevo que la imagen, lee el texto directamente.
    Si no existe o la imagen fue modificada, ejecuta PaddleOCR y guarda la caché.
    """
    # Definimos la ruta del archivo de texto gemelo (Ej: documento.pdf -> documento.pdf.txt)
    ruta_cache_txt = ruta_archivo_imagen + ".txt"
    
    # Verificar si la caché es válida (Existe y es más nueva que la imagen original)
    if os.path.exists(ruta_cache_txt):
        tiempo_imagen = os.path.getmtime(ruta_archivo_imagen)
        tiempo_cache = os.path.getmtime(ruta_cache_txt)
        
        if tiempo_cache > tiempo_imagen:
            # ¡Maniobra de alta velocidad! Leemos el texto plano directamente
            with open(ruta_cache_txt, 'r', encoding='utf-8') as f:
                return f.read().strip()
            
    # Si no hay caché o la imagen es más nueva, encendemos el OCR pesado
    print(f"👁️ [OCR Activo] Procesando imagen original: {os.path.basename(ruta_archivo_imagen)}")
    try:
        resultados = ocr_instancia.ocr(ruta_archivo_imagen, cls=False)
        texto_extraido = ""
        if resultados and resultados[0]:
            for linea in resultados[0]:
                texto_extraido += linea[1][0] + " "
        
        texto_limpio = texto_extraido.strip()
        
        # Guardamos el resultado en la caché para que el próximo entrenamiento tarde 0 segundos
        if texto_limpio:
            with open(ruta_cache_txt, 'w', encoding='utf-8') as f:
                f.write(texto_limpio)
                
        return texto_limpio
    except Exception as e:
        print(f"❌ Error al ejecutar OCR en {ruta_archivo_imagen}: {e}")
        return ""

def entrenar_plataforma_completa():
    print("🚀 [Maestro IA] Iniciando rutina de aprendizaje optimizada (Text Caching)...")
    
    # Inicializamos PaddleOCR (utilizará los modelos offline guardados en la bóveda)
    ocr = PaddleOCR(use_angle_cls=False, lang='es', use_gpu=False, enable_mkldnn=True, cpu_threads=4)

    matrices = ["BT", "BR"]
    for matriz in matrices:
        ruta_matriz = os.path.join(DATASET_DIR, matriz)
        if not os.path.exists(ruta_matriz):
            continue

        for subproceso in os.listdir(ruta_matriz):
            ruta_subproceso = os.path.join(ruta_matriz, subproceso)
            if not os.path.isdir(ruta_subproceso):
                continue
            
            clases_activas = sorted(
                nombre for nombre in os.listdir(ruta_subproceso)
                if os.path.isdir(os.path.join(ruta_subproceso, nombre))
            )
            ruta_subproceso_archivo = os.path.join(DATASET_DIR, 'processed', matriz, subproceso)
            clases_archivadas = []
            if os.path.isdir(ruta_subproceso_archivo):
                clases_archivadas = sorted(
                    nombre for nombre in os.listdir(ruta_subproceso_archivo)
                    if os.path.isdir(os.path.join(ruta_subproceso_archivo, nombre))
                )

            clases = sorted(set(clases_activas + clases_archivadas))
            textos, etiquetas = [], []
            hay_datos_nuevos = False
            
            for clase in clases:
                for ruta_base in [ruta_subproceso, ruta_subproceso_archivo]:
                    ruta_clase = os.path.join(ruta_base, clase)
                    if not os.path.isdir(ruta_clase):
                        continue

                    todos_los_archivos = glob.glob(os.path.join(ruta_clase, "*.*"))
                    archivos_imagenes = [f for f in todos_los_archivos if not f.endswith('.txt')]

                    for archivo in archivos_imagenes:
                        if ruta_base == ruta_subproceso:
                            hay_datos_nuevos = True
                        
                        # Llamamos a nuestra función inteligente con caché integrada
                        txt = obtener_texto_con_cache(ocr, archivo)
                        
                        if txt:
                            textos.append(txt)
                            etiquetas.append(clase)

            if hay_datos_nuevos:
                clases_unicas = sorted(set(etiquetas))
                vectorizador = TfidfVectorizer(max_features=5000, ngram_range=(1,2))
                x_vect = vectorizador.fit_transform(textos)

                if len(clases_unicas) > 1:
                    print(f"🧠 [Matemáticas] Re-calculando vectores estadísticos para {matriz} -> {subproceso}...")
                    modelo = LinearSVC(C=1.0, random_state=42)
                else:
                    print(f"⚠️ [{matriz}-{subproceso}] Solo una clase detectada ({clases_unicas[0]}). Generando un modelo de DummyClassifier de clase única.")
                    modelo = DummyClassifier(strategy='most_frequent')

                modelo.fit(x_vect, etiquetas)
                
                # Guardar el cerebro actualizado en la bóveda
                ruta_guardado = os.path.join(CEREBROS_DIR, matriz, subproceso)
                os.makedirs(ruta_guardado, exist_ok=True)
                
                try:
                    joblib.dump(modelo, os.path.join(ruta_guardado, "modelo.pkl"))
                    joblib.dump(vectorizador, os.path.join(ruta_guardado, "vectorizador.pkl"))
                    print(f"✅ [Éxito] Cerebro especializado '{matriz}-{subproceso}' actualizado en la bóveda.")
                except Exception as e:
                    print(f"❌ Error guardando modelo para {matriz}-{subproceso}: {e}")
                
                # Archivamos los ejemplos procesados para mantener el dataset limpio
                try:
                    archive_dataset(ruta_subproceso, matriz, subproceso)
                except Exception as e:
                    print(f"⚠️ Error al archivar datos de {matriz}-{subproceso}: {e}")
            else:
                print(f"⚠️ [{matriz}-{subproceso}] Sin datos nuevos para entrenar.")

    print("🎉 Rutina de aprendizaje masivo finalizada con éxito.")

if __name__ == "__main__":
    entrenar_plataforma_completa()