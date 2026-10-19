import os
import json
import logging
import torch

logger = logging.getLogger(__name__)

import re

def _extraer_contenido_relevante(txt):
    if not txt:
        return ''
    txt_limpio = re.sub(r'la pub desde su emisi[oó]n tiene una vigencia[^\.
]{0,250}', ' ', txt, flags=re.IGNORECASE)
    txt_limpio = re.sub(r'ministerio del poder popular para relaciones interiores[^\.
]{0,100}', ' ', txt_limpio, flags=re.IGNORECASE)
    txt_limpio = re.sub(r'servicio aut[oó]nomo de registros y notar[ií]as[^\.
]{0,100}', ' ', txt_limpio, flags=re.IGNORECASE)
    
    patrones_juridicos = [
        r'(asamblea\s+general\s+extraordinaria[^\.
]{0,80})',
        r'(asamblea\s+general\s+ordinaria[^\.
]{0,80})',
        r'(reuni[oó]n\s+de\s+junta\s+directiva[^\.
]{0,80})',
        r'(sesi[oó]n\s+de\s+junta\s+directiva[^\.
]{0,80})',
        r'(documento\s+constitutivo[^\.
]{0,80})',
        r'(estatutos\s+sociales[^\.
]{0,80})',
        r'(aumento\s+de\s+capital[^\.
]{0,80})',
        r'(modificaci[oó]n\s+de\s+estatutos[^\.
]{0,80})',
        r'(venta\s+de\s+acciones[^\.
]{0,80})',
        r'(cesi[oó]n\s+de\s+cuotas[^\.
]{0,80})',
        r'(cesi[oó]n\s+de\s+acciones[^\.
]{0,80})',
        r'(designaci[oó]n\s+de\s+junta[^\.
]{0,80})',
        r'(se\s+constituye\s+una\s+sociedad[^\.
]{0,80})',
        r'(comparecieron\s+[^\.
]{0,60})',
        r'(ciudadan[oa]\s+registrador[^\.
]{0,60})'
    ]
    txt_lower = txt_limpio.lower()
    hallazgos = []
    for pat in patrones_juridicos:
        for m in re.finditer(pat, txt_lower):
            if m.start() < 3000:
                hallazgos.append(m.start())
    if hallazgos:
        return txt_limpio[min(hallazgos):].strip()
    return txt_limpio.strip()

# Rutas del modelo BETO
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CEREBRO_BETO_DIR = os.path.join(BASE_DIR, "cerebro_beto")
MODELO_BETO_PATH = os.path.join(CEREBRO_BETO_DIR, "modelo_beto_final")
CATALOGO_ID2LABEL = os.path.join(CEREBRO_BETO_DIR, "dataset_procesado", "id2label.json")

# Memoria caché en RAM para instanciar el modelo una sola vez
_MODELO_BETO = None
_TOKENIZER_BETO = None
_ID2LABEL = None
_DEVICE = torch.device("cpu")  # Por defecto en CPU (simulación de Producción y compatible con Celery)


def inicializar_motor_beto(force_cpu=True):
    """
    Carga en memoria RAM el modelo y tokenizador de BETO una única vez (Singleton).
    Diseñado para correr de manera ultra-rápida y concurrente en Celery Workers.
    """
    global _MODELO_BETO, _TOKENIZER_BETO, _ID2LABEL, _DEVICE
    
    if _MODELO_BETO is not None and _TOKENIZER_BETO is not None:
        return _MODELO_BETO, _TOKENIZER_BETO, _ID2LABEL

    if not os.path.exists(MODELO_BETO_PATH):
        logger.warning(f"⚠️ El modelo BETO aún no existe en: {MODELO_BETO_PATH}")
        return None, None, None

    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        if not force_cpu and torch.cuda.is_available():
            _DEVICE = torch.device("cuda")
        else:
            _DEVICE = torch.device("cpu")
            # Optimizar hilos para no saturar Celery si hay múltiples workers
            torch.set_num_threads(max(1, os.cpu_count() // 2 if os.cpu_count() else 2))

        logger.info(f"🧠 [BETO] Inicializando Cerebro Contextual en dispositivo: {_DEVICE}...")
        
        _TOKENIZER_BETO = AutoTokenizer.from_pretrained(MODELO_BETO_PATH)
        _MODELO_BETO = AutoModelForSequenceClassification.from_pretrained(MODELO_BETO_PATH)
        _MODELO_BETO.to(_DEVICE)
        _MODELO_BETO.eval()

        if os.path.exists(CATALOGO_ID2LABEL):
            with open(CATALOGO_ID2LABEL, "r", encoding="utf-8") as f:
                _ID2LABEL = {int(k): v for k, v in json.load(f).items()}
        else:
            _ID2LABEL = _MODELO_BETO.config.id2label

        logger.info(f"✔ [BETO] Cerebro cargado exitosamente ({len(_ID2LABEL)} clases disponibles).")
        return _MODELO_BETO, _TOKENIZER_BETO, _ID2LABEL

    except Exception as e:
        logger.error(f"❌ Error al inicializar BETO: {e}")
        return None, None, None


def predecir_documento_beto(texto, *args, max_tokens=160, **kwargs):
    """
    Función puente compatible 1 a 1 con predecir_documento():
    Recibe texto extraído -> Retorna (clase_predicha, confianza_float)
    """
    if not texto or not texto.strip():
        return "DOCUMENTO EN BLANCO", 1.0

    modelo, tokenizer, id2label = inicializar_motor_beto()

    if not modelo or not tokenizer:
        # Fallback de seguridad en caso de que BETO no esté compilado
        logger.warning("⚠️ BETO no disponible, intentando fallback a TF-IDF clásico...")
        try:
            from .routing_ia import predecir_documento as predecir_tfidf
            return predecir_tfidf(texto, *args, **kwargs)
        except Exception:
            return "MODELO_NO_ENTRENADO", 0.0

    try:
        # Tokenización truncada enfocada en la carátula y cláusulas iniciales
        texto_procesado = _extraer_contenido_relevante(texto)
        inputs = tokenizer(
            texto_procesado,
            truncation=True,
            max_length=max_tokens,
            return_tensors="pt"
        )
        inputs = {k: v.to(_DEVICE) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = modelo(**inputs)
            logits = outputs.logits
            probabilidades = torch.softmax(logits, dim=-1)[0]
            clase_id = torch.argmax(probabilidades).item()
            confianza = probabilidades[clase_id].item()

        clase_predicha = id2label.get(clase_id, "DESCONOCIDO")
        return clase_predicha, float(confianza)

    except Exception as e:
        logger.error(f"❌ Error en inferencia BETO: {e}")
        return "ERROR_INFERENCIA", 0.0
