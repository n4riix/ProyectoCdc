import os
import joblib

# Ruta absoluta hacia la bóveda de cerebros
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CEREBROS_DIR = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'cerebros_ia')

# Memoria Caché: Para no cargar el mismo modelo en cada llamada
cache_modelos = {}

# ============================================================
# REGLAS DE NEGOCIO BANCARIAS
# Desempatan según política bancaria cuando el modelo duda
# ============================================================
MARGEN_DUDA = 0.15

REGLAS_NEGOCIO = {
    frozenset(["REC DocumentoIdentidad", "REC RIF"]): "REC DocumentoIdentidad",
}

def aplicar_regla_negocio(clases, probabilidades, texto=""):
    """
    Desempata según REGLAS_NEGOCIO únicamente cuando el modelo está en duda (margen < MARGEN_DUDA).
    """
    if len(clases) < 2:
        return None, None, False

    ranking = sorted(zip(clases, probabilidades), key=lambda x: x[1], reverse=True)
    top_clase, top_prob = ranking[0]
    seg_clase, seg_prob = ranking[1]

    margen = top_prob - seg_prob
    if margen < MARGEN_DUDA:
        par = frozenset([top_clase, seg_clase])
        if par in REGLAS_NEGOCIO:
            ganador = REGLAS_NEGOCIO[par]
            confianza_ajustada = top_prob + seg_prob
            return ganador, min(confianza_ajustada, 0.99), True

    return None, None, False

def limpiar_cache():
    """Limpia la caché de modelos en RAM."""
    global cache_modelos
    cache_modelos.clear()

def obtener_cerebro_universal():
    """Carga el Modelo Maestro Unificado global en RAM."""
    clave_cache = "GLOBAL"
    ruta_modelo = os.path.join(CEREBROS_DIR, "modelo_cdc_global.pkl")
    ruta_vectorizador = os.path.join(CEREBROS_DIR, "vectorizador_cdc_global.pkl")

    if not os.path.exists(ruta_modelo) or not os.path.exists(ruta_vectorizador):
        return None, None

    tiempo_disco = os.path.getmtime(ruta_modelo)

    if clave_cache in cache_modelos:
        modelo_cache, vectorizador_cache, tiempo_cache = cache_modelos[clave_cache]
        if tiempo_disco <= tiempo_cache:
            return modelo_cache, vectorizador_cache

    print("🧠 [Cerebro Universal] Cargando Modelo Maestro Global a la RAM: modelo_cdc_global.pkl")
    modelo = joblib.load(ruta_modelo)
    vectorizador = joblib.load(ruta_vectorizador)
    
    cache_modelos[clave_cache] = (modelo, vectorizador, tiempo_disco)
    return modelo, vectorizador

def predecir_documento(texto, *args, **kwargs):
    """Clasifica el texto extraído usando únicamente el Cerebro Universal."""
    if not texto:
        return "DOCUMENTO EN BLANCO", 1.0

    modelo, vectorizador = obtener_cerebro_universal()
    
    if not modelo:
        return "MODELO_NO_ENTRENADO", 0.0

    texto_vectorizado = vectorizador.transform([texto])
    prediccion = modelo.predict(texto_vectorizado)[0]
    
    try:
        proba = modelo.predict_proba(texto_vectorizado)[0]
        confianza = max(proba)

        clase_regla, confianza_regla, regla_aplicada = aplicar_regla_negocio(
            list(modelo.classes_), list(proba), texto=texto
        )
        if regla_aplicada:
            print(f"📋 [Regla de Negocio] '{prediccion}' → '{clase_regla}' (política bancaria aplicada)")
            prediccion = clase_regla
            confianza = confianza_regla

    except AttributeError:
        confianza = 1.0
    
    return prediccion, confianza