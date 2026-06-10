import os
import glob
import joblib
import pandas as pd
from paddleocr import PaddleOCR
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

# Silenciar mensajes innecesarios de PaddleOCR en la consola
logging.getLogger("ppocr").setLevel(logging.WARNING)

DATASET_DIR = "/volumen_compartido/dataset_entrenamiento"
CEREBROS_DIR = "/volumen_compartido/cerebros_ia"

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
            
            clases = os.listdir(ruta_subproceso)
            textos, etiquetas = [], []
            hay_datos_nuevos = False
            
            for clase in clases:
                ruta_clase = os.path.join(ruta_subproceso, clase)
                if not os.path.isdir(ruta_clase): 
                    continue

                # Buscamos archivos originales (filtramos para no intentar leer los propios .txt de caché)
                todos_los_archivos = glob.glob(os.path.join(ruta_clase, "*.*"))
                archivos_imagenes = [f for f in todos_los_archivos if not f.endswith('.txt')]

                for archivo in archivos_imagenes:
                    hay_datos_nuevos = True
                    
                    # Llamamos a nuestra función inteligente con caché integrada
                    txt = obtener_texto_con_cache(ocr, archivo)
                    
                    if txt:
                        textos.append(txt)
                        etiquetas.append(clase)
            
            # Entrenamiento del modelo matemático LinearSVC (Hiper rápido)
            if hay_datos_nuevos and len(set(etiquetas)) > 1:
                print(f"🧠 [Matemáticas] Re-calculando vectores estadísticos para {matriz} -> {subproceso}...")
                
                vectorizador = TfidfVectorizer(max_features=5000, ngram_range=(1,2))
                x_vect = vectorizador.fit_transform(textos)
                
                modelo = LinearSVC(C=1.0, random_state=42)
                modelo.fit(x_vect, etiquetas)
                
                # Guardar el cerebro actualizado en la bóveda
                ruta_guardado = os.path.join(CEREBROS_DIR, matriz, subproceso)
                os.makedirs(ruta_guardado, exist_ok=True)
                
                joblib.dump(modelo, os.path.join(ruta_guardado, "modelo.pkl"))
                joblib.dump(vectorizador, os.path.join(ruta_guardado, "vectorizador.pkl"))
                print(f"✅ [Éxito] Cerebro especializado '{matriz}-{subproceso}' actualizado en la bóveda.")
            elif hay_datos_nuevos:
                print(f"⚠️ [{matriz}-{subproceso}] Ignorado: Requiere al menos 2 categorías distintas para aprender.")

    print("🎉 Rutina de aprendizaje masivo finalizada con éxito.")

if __name__ == "__main__":
    entrenar_plataforma_completa()