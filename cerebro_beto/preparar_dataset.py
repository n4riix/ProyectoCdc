import os
import json
import random
from collections import Counter
from sklearn.model_selection import train_test_split

DATASET_DIR = "/home/intexus/app/ProyectoCdc/volumen_compartido/dataset_global"
OUTPUT_DIR = "/home/intexus/app/ProyectoCdc/cerebro_beto/dataset_procesado"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("🔍 Explorando clases y muestras en DEV...")

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
                contenido = arch.read().strip()
                if len(contenido) > 20: # Filtrar textos vacíos o casi nulos
                    textos.append(contenido)
                    etiquetas.append(clase)
        except Exception as e:
            pass

print(f"📊 Clases con datos: {len(clases_detectadas)}")
print(f"📄 Total documentos válidos para entrenar: {len(textos)}")

# Mapeo de clases a IDs numéricos
label2id = {c: i for i, c in enumerate(clases_detectadas)}
id2label = {i: c for i, c in enumerate(clases_detectadas)}

with open(os.path.join(OUTPUT_DIR, "label2id.json"), "w", encoding="utf-8") as f:
    json.dump(label2id, f, ensure_ascii=False, indent=2)

with open(os.path.join(OUTPUT_DIR, "id2label.json"), "w", encoding="utf-8") as f:
    json.dump(id2label, f, ensure_ascii=False, indent=2)

# División Estratificada 80% Train / 20% Val
train_texts, val_texts, train_labels, val_labels = train_test_split(
    textos, etiquetas, test_size=0.20, random_state=42, stratify=etiquetas
)

train_data = [{"text": t, "label": label2id[l]} for t, l in zip(train_texts, train_labels)]
val_data = [{"text": t, "label": label2id[l]} for t, l in zip(val_texts, val_labels)]

with open(os.path.join(OUTPUT_DIR, "train.json"), "w", encoding="utf-8") as f:
    json.dump(train_data, f, ensure_ascii=False)

with open(os.path.join(OUTPUT_DIR, "val.json"), "w", encoding="utf-8") as f:
    json.dump(val_data, f, ensure_ascii=False)

print(f"✅ Dataset estructurado exitosamente:")
print(f"   ▸ Entrenamiento: {len(train_data)} muestras")
print(f"   ▸ Validación:    {len(val_data)} muestras")
print(f"   ▸ Catálogo guardado en: {OUTPUT_DIR}")
