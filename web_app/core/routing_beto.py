import os
import json
import logging
import re
import joblib
import torch

logger = logging.getLogger(__name__)

# Rutas del modelo BETO y Especialista Notarial
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CEREBRO_BETO_DIR = "/cerebro_beto" if os.path.exists("/cerebro_beto") else os.path.join(BASE_DIR, "cerebro_beto")
MODELO_BETO_PATH = os.path.join(CEREBRO_BETO_DIR, "modelo_beto_final")
CATALOGO_ID2LABEL = os.path.join(CEREBRO_BETO_DIR, "dataset_procesado", "id2label.json")
ESPECIALISTA_DIR = os.path.join(CEREBRO_BETO_DIR, "especialista_notarial")

# Familias Notariales y Cláusulas Discriminantes
CLASES_NOTARIALES = {
    "REC DocumentoConstitutivoEstatuario",
    "REC ActaAsambleaModificaciones",
    "REC ActaJuntaDirectiva",
    "REC DocumentoFirmaPersonal",
    "REC DocumentoPoder"
}

# Memoria caché en RAM (Singleton)
_MODELO_BETO = None
_TOKENIZER_BETO = None
_ID2LABEL = None
_MODELO_NOTARIAL = None
_VECT_NOTARIAL = None
_DEVICE = torch.device("cpu")


def _extraer_contenido_relevante(txt):
    if not txt:
        return ""
    txt_limpio = re.sub(r'la pub desde su emisi[oó]n tiene una vigencia[^\.\n]{0,250}', ' ', txt, flags=re.IGNORECASE)
    txt_limpio = re.sub(r'ministerio del poder popular para relaciones interiores[^\.\n]{0,100}', ' ', txt_limpio, flags=re.IGNORECASE)
    txt_limpio = re.sub(r'servicio aut[oó]nomo de registros y notar[ií]as[^\.\n]{0,100}', ' ', txt_limpio, flags=re.IGNORECASE)
    
    patrones_juridicos = [
        r'(asamblea\s+general\s+extraordinaria[^\.\n]{0,80})',
        r'(asamblea\s+general\s+ordinaria[^\.\n]{0,80})',
        r'(reuni[oó]n\s+de\s+junta\s+directiva[^\.\n]{0,80})',
        r'(sesi[oó]n\s+de\s+junta\s+directiva[^\.\n]{0,80})',
        r'(documento\s+constitutivo[^\.\n]{0,80})',
        r'(estatutos\s+sociales[^\.\n]{0,80})',
        r'(aumento\s+de\s+capital[^\.\n]{0,80})',
        r'(modificaci[oó]n\s+de\s+estatutos[^\.\n]{0,80})',
        r'(venta\s+de\s+acciones[^\.\n]{0,80})',
        r'(cesi[oó]n\s+de\s+cuotas[^\.\n]{0,80})',
        r'(cesi[oó]n\s+de\s+acciones[^\.\n]{0,80})',
        r'(designaci[oó]n\s+de\s+junta[^\.\n]{0,80})',
        r'(se\s+constituye\s+una\s+sociedad[^\.\n]{0,80})',
        r'(comparecieron\s+[^\.\n]{0,60})',
        r'(ciudadan[oa]\s+registrador[^\.\n]{0,60})'
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


def inicializar_motor_beto(force_cpu=True):
    """Carga BETO y el Especialista Notarial en memoria RAM."""
    global _MODELO_BETO, _TOKENIZER_BETO, _ID2LABEL, _MODELO_NOTARIAL, _VECT_NOTARIAL, _DEVICE
    
    if _MODELO_BETO is not None:
        return _MODELO_BETO, _TOKENIZER_BETO, _ID2LABEL, _MODELO_NOTARIAL, _VECT_NOTARIAL

    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        _DEVICE = torch.device("cpu")
        torch.set_num_threads(max(1, os.cpu_count() // 2 if os.cpu_count() else 2))

        logger.info(f"🧠 [BETO Híbrido] Inicializando Cerebro Contextual + Especialista Notarial en: {_DEVICE}...")
        
        _TOKENIZER_BETO = AutoTokenizer.from_pretrained(MODELO_BETO_PATH)
        _MODELO_BETO = AutoModelForSequenceClassification.from_pretrained(MODELO_BETO_PATH)
        _MODELO_BETO.to(_DEVICE)
        _MODELO_BETO.eval()

        if os.path.exists(CATALOGO_ID2LABEL):
            with open(CATALOGO_ID2LABEL, "r", encoding="utf-8") as f:
                _ID2LABEL = {int(k): v for k, v in json.load(f).items()}
        else:
            _ID2LABEL = _MODELO_BETO.config.id2label

        # Cargar Especialista Notarial de Documento Completo
        path_mod_notarial = os.path.join(ESPECIALISTA_DIR, "modelo_notarial.pkl")
        path_vec_notarial = os.path.join(ESPECIALISTA_DIR, "vectorizador_notarial.pkl")
        if os.path.exists(path_mod_notarial) and os.path.exists(path_vec_notarial):
            _MODELO_NOTARIAL = joblib.load(path_mod_notarial)
            _VECT_NOTARIAL = joblib.load(path_vec_notarial)
            logger.info("✔ [Especialista Notarial] Motor de documentos largos cargado exitosamente.")

        logger.info(f"✔ [BETO] Cerebro Híbrido listo ({len(_ID2LABEL)} clases).")
        return _MODELO_BETO, _TOKENIZER_BETO, _ID2LABEL, _MODELO_NOTARIAL, _VECT_NOTARIAL

    except Exception as e:
        logger.error(f"❌ Error al inicializar BETO Híbrido: {e}")
        return None, None, None, None, None


def predecir_documento_beto(texto, *args, max_tokens=160, **kwargs):
    """
    Motor de Inferencia Híbrido de 2 Niveles:
    1. Inferencia Universal con BETO (Alta semántica).
    2. Si el documento pertenece a la familia Notarial (Actas/Estatutos),
       desempata con el Especialista Notarial analizando el documento completo.
    """
    if not texto or not texto.strip():
        return "DOCUMENTO EN BLANCO", 1.0

    modelo_beto, tokenizer, id2label, mod_notarial, vec_notarial = inicializar_motor_beto()

    if not modelo_beto or not tokenizer:
        try:
            from .routing_ia import predecir_documento as predecir_tfidf
            return predecir_tfidf(texto, *args, **kwargs)
        except Exception:
            return "MODELO_NO_ENTRENADO", 0.0

    try:
        texto_procesado = _extraer_contenido_relevante(texto)
        inputs = tokenizer(
            texto_procesado,
            truncation=True,
            max_length=max_tokens,
            return_tensors="pt"
        )
        inputs = {k: v.to(_DEVICE) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = modelo_beto(**inputs)
            logits = outputs.logits
            probabilidades = torch.softmax(logits, dim=-1)[0]
            clase_id = torch.argmax(probabilidades).item()
            confianza = float(probabilidades[clase_id].item())

        clase_predicha = id2label.get(clase_id, "DESCONOCIDO")

        # ── REGLAS DETERMINISTAS DE ALTA FIDELIDAD (Eliminar dudas recurrentes) ──
        texto_u = texto.upper()
        if "FICHA DE IDENTIFICACION" in texto_u or "COMPLEMENTO DE FICHA" in texto_u:
            return "EXC FichaIdentificacionCliente", 0.99
        elif ("SOLICITAR LA MOVILIZACI" in texto_u or "SOLICITUD DE MOVILIZACI" in texto_u or 
              "INSTRUYO Y AUTORIZO A BANCO PROVINCIAL" in texto_u or "MODALIDAD ESTIPULADA PARA LA CUENTA" in texto_u or
              "INSTRUCCIONES DE APERTURA" in texto_u or "MOVILIZACION DE CUENTA" in texto_u):
            return "REC InstruccionesAperturaMovilizaciondeCuenta", 0.99

        # ── CAPA 2: Especialista Notarial para Documentos Complejos Extensos ──
        if clase_predicha in CLASES_NOTARIALES and mod_notarial and vec_notarial:
            try:
                # El especialista analiza el texto completo de todas las páginas
                X_doc = vec_notarial.transform([texto])
                clase_notarial = mod_notarial.predict(X_doc)[0]
                proba_notarial = max(mod_notarial.predict_proba(X_doc)[0])
                
                # Reglas de desempate notarial con alta certeza
                clase_predicha = clase_notarial
                confianza = max(confianza, float(proba_notarial))
            except Exception as e_not:
                logger.warning(f"Aviso en clasificador notarial: {e_not}")

        return clase_predicha, float(confianza)

    except Exception as e:
        logger.error(f"❌ Error en inferencia BETO Híbrido: {e}")
        return "ERROR_INFERENCIA", 0.0
