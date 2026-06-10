import os
import joblib

# Ruta absoluta hacia la bóveda de cerebros
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CEREBROS_DIR = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'cerebros_ia')

# Memoria Caché: Para no cargar el mismo modelo 1000 veces seguidas, lo guardamos en RAM
cache_modelos = {}

def obtener_cerebro(matriz, subproceso):
    """Busca el modelo y vectorizador correctos. Ej: matriz='BT', subproceso='CCD'"""
    clave_cache = f"{matriz}_{subproceso}"
    
    # Si ya lo cargamos hace unos segundos, lo reusamos de la memoria (¡Súper Rápido!)
    if clave_cache in cache_modelos:
        return cache_modelos[clave_cache]

    ruta_modelo = os.path.join(CEREBROS_DIR, matriz, subproceso, "modelo.pkl")
    ruta_vectorizador = os.path.join(CEREBROS_DIR, matriz, subproceso, "vectorizador.pkl")

    if not os.path.exists(ruta_modelo) or not os.path.exists(ruta_vectorizador):
        return None, None # Significa que el Admin aún no ha entrenado este proceso

    # Cargar desde el disco duro
    print(f"🧠 Cargando Cerebro Especialista a la RAM: {matriz} -> {subproceso}")
    modelo = joblib.load(ruta_modelo)
    vectorizador = joblib.load(ruta_vectorizador)
    
    # Guardar en la caché
    cache_modelos[clave_cache] = (modelo, vectorizador)
    return modelo, vectorizador

def predecir_documento(texto, matriz, subproceso):
    """Recibe el texto extraído del OCR y devuelve la clasificación matemática."""
    if not texto:
        return "DOCUMENTO EN BLANCO"

    modelo, vectorizador = obtener_cerebro(matriz, subproceso)
    
    if not modelo:
        return "MODELO_NO_ENTRENADO" # Alerta para avisarle al Admin

    # Transformar texto a números y predecir
    texto_vectorizado = vectorizador.transform([texto])
    prediccion = modelo.predict(texto_vectorizado)[0]
    
    return prediccion