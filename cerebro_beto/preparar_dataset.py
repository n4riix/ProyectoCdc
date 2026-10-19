import os
import json
import re
from sklearn.model_selection import train_test_split

DATASET_DIR = "/home/intexus/app/ProyectoCdc/volumen_compartido/dataset_global"
OUTPUT_DIR = "/home/intexus/app/ProyectoCdc/cerebro_beto/dataset_procesado"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("🔍 [Preprocesamiento Inteligente] Limpiando aranceles SAREN y extrayendo el núcleo legal...")

def extraer_contenido_relevante(txt):
    """
    Filtra planillas de pago notariales idénticas (SAREN/PUB) y busca
    el núcleo donde se declara el acto jurídico o la naturaleza del documento.
    """
    if not txt:
        return ""
    
    # 1. Remover ruido genérico de vouchers de aranceles bancarios / PUB
    txt_limpio = re.sub(r'la pub desde su emisi[oó]n tiene una vigencia[^\.\n]{0,250}', ' ', txt, flags=re.IGNORECASE)
    txt_limpio = re.sub(r'ministerio del poder popular para relaciones interiores[^\.\n]{0,100}', ' ', txt_limpio, flags=re.IGNORECASE)
    txt_limpio = re.sub(r'servicio aut[oó]nomo de registros y notar[ií]as[^\.\n]{0,100}', ' ', txt_limpio, flags=re.IGNORECASE)
    
    # 2. Si es documento extenso/notarial, anclar en la declaración jurídica real
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
            # Solo si el ancla aparece dentro de los primeros 3000 caracteres
            if m.start() < 3000:
                hallazgos.append(m.start())
                
    if hallazgos:
        inicio = min(hallazgos)
        return txt_limpio[inicio:].strip()
        
    return txt_limpio.strip()

textos = []
etiquetas = []
clases_detectadas = []

for clase in sorted(os.listdir(DATASET_DIR)):
    ruta_clase = os.path.join(DATASET_DIR, clase)
    if not os.path.isdir(ruta_clase):
        continue
    
    archivos_txt = [f for f in os.listdir(ruta_clase) if f.endswith('.txt')]
    if not archivos_txt:
        continue
        
    clases_detectadas.append(clase)
    for f in archivos_txt:
        p = os.path.join(ruta_clase, f)
        try:
            with open(p, 'r', encoding='utf-8', errors='ignore') as arch:
                contenido = arch.read()
                procesado = extraer_contenido_relevante(contenido)
                if len(procesado) > 20:
                    textos.append(procesado)
                    etiquetas.append(clase)
        except Exception:
            pass

print(f"📊 Total clases: {len(clases_detectadas)}")
print(f"📄 Total documentos procesados con filtro jurídico: {len(textos)}")

label2id = {c: i for i, c in enumerate(clases_detectadas)}
id2label = {i: c for i, c in enumerate(clases_detectadas)}

with open(os.path.join(OUTPUT_DIR, "label2id.json"), "w", encoding="utf-8") as f:
    json.dump(label2id, f, ensure_ascii=False, indent=2)

with open(os.path.join(OUTPUT_DIR, "id2label.json"), "w", encoding="utf-8") as f:
    json.dump(id2label, f, ensure_ascii=False, indent=2)

train_texts, val_texts, train_labels, val_labels = train_test_split(
    textos, etiquetas, test_size=0.20, random_state=42, stratify=etiquetas
)

train_data = [{"text": t, "label": label2id[l]} for t, l in zip(train_texts, train_labels)]
val_data = [{"text": t, "label": label2id[l]} for t, l in zip(val_texts, val_labels)]

with open(os.path.join(OUTPUT_DIR, "train.json"), "w", encoding="utf-8") as f:
    json.dump(train_data, f, ensure_ascii=False)

with open(os.path.join(OUTPUT_DIR, "val.json"), "w", encoding="utf-8") as f:
    json.dump(val_data, f, ensure_ascii=False)

print(f"✅ Dataset regenerado con éxito (Entrenamiento: {len(train_data)}, Validación: {len(val_data)})")
