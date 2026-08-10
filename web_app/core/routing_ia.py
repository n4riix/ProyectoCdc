import os
import joblib

# Ruta absoluta hacia la bóveda de cerebros
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CEREBROS_DIR = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'cerebros_ia')

# Memoria Caché: Para no cargar el mismo modelo 1000 veces seguidas, lo guardamos en RAM
cache_modelos = {}

# ============================================================
# REGLAS DE NEGOCIO BANCARIAS
# Cuando el modelo duda entre dos clases (margen < umbral),
# estas reglas desempatan según la política del banco.
# Formato: { frozenset({clase_A, clase_B}): clase_ganadora }
# ============================================================
MARGEN_DUDA = 0.15  # Si la diferencia es menor al 15%, el modelo "duda"

REGLAS_NEGOCIO = {
    # Política: Cédula+RIF juntos → siempre es DocumentoIdentidad
    frozenset(["REC DocumentoIdentidad", "REC RIF"]): "REC DocumentoIdentidad",
}

def aplicar_regla_negocio(clases, probabilidades):
    """
    Si el modelo duda entre dos clases (margen < MARGEN_DUDA),
    verifica si existe una regla de negocio que desempate.
    Devuelve (clase_ganadora, confianza_ajustada, regla_aplicada).
    """
    if len(clases) < 2:
        return None, None, False

    # Ordenar por probabilidad descendente
    ranking = sorted(zip(clases, probabilidades), key=lambda x: x[1], reverse=True)
    top_clase, top_prob = ranking[0]
    seg_clase, seg_prob = ranking[1]

    margen = top_prob - seg_prob

    if margen < MARGEN_DUDA:
        par = frozenset([top_clase, seg_clase])
        if par in REGLAS_NEGOCIO:
            ganador = REGLAS_NEGOCIO[par]
            # La confianza asignada es la suma de ambas (el banco está seguro aunque el modelo dude)
            confianza_ajustada = top_prob + seg_prob
            return ganador, min(confianza_ajustada, 0.99), True

    return None, None, False

def limpiar_cache(matriz=None, subproceso=None):
    """Limpia la caché de modelos (solo afecta al proceso actual)."""
    global cache_modelos
    if matriz and subproceso:
        clave = f"{matriz}_{subproceso}"
        cache_modelos.pop(clave, None)
    else:
        cache_modelos.clear()

def obtener_cerebro(matriz, subproceso):
    """Busca el modelo y vectorizador correctos. Ej: matriz='BT', subproceso='CCD'"""
    clave_cache = f"{matriz}_{subproceso}"
    ruta_modelo = os.path.join(CEREBROS_DIR, matriz, subproceso, "modelo.pkl")
    ruta_vectorizador = os.path.join(CEREBROS_DIR, matriz, subproceso, "vectorizador.pkl")

    if not os.path.exists(ruta_modelo) or not os.path.exists(ruta_vectorizador):
        return None, None # Significa que el Admin aún no ha entrenado este proceso

    tiempo_disco = os.path.getmtime(ruta_modelo)

    # Si ya lo cargamos, verificamos si el archivo en disco cambió (reentrenamiento)
    if clave_cache in cache_modelos:
        modelo_cache, vectorizador_cache, tiempo_cache = cache_modelos[clave_cache]
        if tiempo_disco <= tiempo_cache:
            return modelo_cache, vectorizador_cache
        else:
            print(f"🔄 Cerebro {matriz}-{subproceso} fue actualizado. Recargando caché...")

    # Cargar desde el disco duro
    print(f"🧠 Cargando Cerebro Especialista a la RAM: {matriz} -> {subproceso}")
    modelo = joblib.load(ruta_modelo)
    vectorizador = joblib.load(ruta_vectorizador)
    
    # Guardar en la caché junto con el timestamp de modificación
    cache_modelos[clave_cache] = (modelo, vectorizador, tiempo_disco)
    return modelo, vectorizador

def predecir_documento(texto, matriz, subproceso):
    """Recibe el texto extraído del OCR y devuelve la clasificación matemática y la confianza."""
    if not texto:
        return "DOCUMENTO EN BLANCO", 1.0

    modelo, vectorizador = obtener_cerebro(matriz, subproceso)
    
    if not modelo:
        return "MODELO_NO_ENTRENADO", 0.0 # Alerta para avisarle al Admin

    # Transformar texto a números y predecir
    texto_vectorizado = vectorizador.transform([texto])
    prediccion = modelo.predict(texto_vectorizado)[0]
    
    try:
        proba = modelo.predict_proba(texto_vectorizado)[0]
        confianza = max(proba)

        # ── Aplicar Reglas de Negocio del Banco ──
        clase_regla, confianza_regla, regla_aplicada = aplicar_regla_negocio(
            list(modelo.classes_), list(proba)
        )
        if regla_aplicada:
            print(f"📋 [Regla de Negocio] '{prediccion}' → '{clase_regla}' (margen insuficiente, política bancaria aplicada)")
            prediccion = clase_regla
            confianza = confianza_regla

    except AttributeError:
        # El modelo antiguo (LinearSVC) no soporta predict_proba
        confianza = 1.0
    
    return prediccion, confianza