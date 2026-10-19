import os
import json
import torch
import numpy as np
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer
)
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

BASE_DIR = "/home/intexus/app/ProyectoCdc/cerebro_beto"
DATA_DIR = os.path.join(BASE_DIR, "dataset_procesado")
MODEL_OUTPUT = os.path.join(BASE_DIR, "modelo_beto_final")

# Modelo base oficial en español (BETO)
MODELO_BASE = "dccuchile/bert-base-spanish-wwm-uncased"

print(f"🚀 Iniciando tubería de Fine-Tuning con BETO ({MODELO_BASE})...")
print(f"   CUDA disponible: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"   Dispositivo de cómputo: {torch.cuda.get_device_name(0)}")

# 1. Cargar metadatos
with open(os.path.join(DATA_DIR, "label2id.json"), "r", encoding="utf-8") as f:
    label2id = json.load(f)
with open(os.path.join(DATA_DIR, "id2label.json"), "r", encoding="utf-8") as f:
    id2label = {int(k): v for k, v in json.load(f).items()}

num_labels = len(label2id)
print(f"📚 Total de clases a aprender: {num_labels}")

# 2. Cargar tokenizador
print("📥 Cargando tokenizador oficial...")
tokenizer = AutoTokenizer.from_pretrained(MODELO_BASE)

# 3. Cargar datos
with open(os.path.join(DATA_DIR, "train.json"), "r", encoding="utf-8") as f:
    raw_train = json.load(f)
with open(os.path.join(DATA_DIR, "val.json"), "r", encoding="utf-8") as f:
    raw_val = json.load(f)

def tokenize_func(examples):
    # Truncar a 256 tokens para no desbordar VRAM de 4GB y enfocarse en el preámbulo legal
    return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=160)

train_ds = Dataset.from_list(raw_train).map(tokenize_func, batched=True)
val_ds = Dataset.from_list(raw_val).map(tokenize_func, batched=True)

# 4. Inicializar Modelo
print("🧠 Construyendo red neuronal clasificadora sobre BETO...")
model = AutoModelForSequenceClassification.from_pretrained(
    MODELO_BASE,
    num_labels=num_labels,
    id2label=id2label,
    label2id=label2id
)

# 5. Métricas de evaluación
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=1)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average="weighted", zero_division=0)
    acc = accuracy_score(labels, preds)
    return {
        "accuracy": acc,
        "f1": f1,
        "precision": precision,
        "recall": recall
    }

# 6. Configuración de hiperparámetros
training_args = TrainingArguments(
    output_dir=os.path.join(BASE_DIR, "checkpoints"),
    eval_strategy="epoch",
    save_strategy="epoch",
    learning_rate=3e-5,
    per_device_train_batch_size=4,
    per_device_eval_batch_size=4,
    gradient_accumulation_steps=4,
    num_train_epochs=4,
    weight_decay=0.01,
    fp16=True,  # Aceleración por precisión mixta en NVIDIA Turing GTX 1650 Ti
    logging_steps=20,
    save_total_limit=1,
    load_best_model_at_end=True,
    metric_for_best_model="accuracy",
    report_to="none"
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    processing_class=tokenizer,
    compute_metrics=compute_metrics
)

print("⚡ Comenzando ciclo de entrenamiento en GPU...")
trainer.train()

print("💾 Guardando modelo consolidado...")
trainer.save_model(MODEL_OUTPUT)
tokenizer.save_pretrained(MODEL_OUTPUT)

print(f"🎉 ¡Entrenamiento completado exitosamente! Modelo disponible en: {MODEL_OUTPUT}")
