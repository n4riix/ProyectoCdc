import os
import json
import time
import torch
import psutil
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = "/home/intexus/app/ProyectoCdc/cerebro_beto/modelo_beto_final"
DATA_DIR = "/home/intexus/app/ProyectoCdc/cerebro_beto/dataset_procesado"

print("⚙️ [BENCHMARK CPU] Iniciando prueba de simulación de Producción en CPU...")

# 1. Forzar ejecución ESTRICTAMENTE en CPU
device = torch.device("cpu")
print(f"   Dispositivo asignado: {device}")
print(f"   Hilos CPU disponibles: {torch.get_num_threads()}")

# 2. Cargar tokenizador y modelo
t0_carga = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.to(device)
model.eval()
t_carga = round((time.time() - t0_carga), 2)
print(f"✔ Modelo cargado en RAM de CPU en {t_carga} segundos.")

# 3. Cargar lote de validación
with open(f"{DATA_DIR}/val.json", "r", encoding="utf-8") as f:
    val_data = json.load(f)

# Tomar 100 documentos reales para promediar latencia
muestras = val_data[:100]
textos = [m["text"] for m in muestras]

# Warm-up (calentamiento de memoria caché de CPU)
inputs_warmup = tokenizer(textos[0], truncation=True, max_length=160, return_tensors="pt")
with torch.no_grad():
    _ = model(**inputs_warmup)

# Medición de consumo de RAM del proceso
proceso = psutil.Process(os.getpid())
ram_inicio_mb = proceso.memory_info().rss / (1024 * 1024)

# 4. Prueba secuencial (1 worker individual en CPU)
tiempos_ms = []
cpu_porcentajes = []

print(f"\n🏃 Procesando {len(textos)} inferencias individuales en CPU (simulación Celery Worker)...")

for i, t in enumerate(textos):
    t_inicio = time.perf_counter()
    
    # Tokenización + Inferencia
    inputs = tokenizer(t, truncation=True, max_length=160, return_tensors="pt")
    with torch.no_grad():
        salida = model(**inputs)
        logits = salida.logits
        probabilidades = torch.softmax(logits, dim=-1)
        clase_id = torch.argmax(probabilidades, dim=-1).item()
        confianza = probabilidades[0, clase_id].item()
        
    t_fin = time.perf_counter()
    duracion_ms = (t_fin - t_inicio) * 1000.0
    tiempos_ms.append(duracion_ms)

ram_final_mb = proceso.memory_info().rss / (1024 * 1024)

# 5. Cálculo estadístico
latencia_promedio = sum(tiempos_ms) / len(tiempos_ms)
latencia_min = min(tiempos_ms)
latencia_max = max(tiempos_ms)
latencia_p95 = sorted(tiempos_ms)[int(len(tiempos_ms) * 0.95)]
tifs_por_segundo_por_core = 1000.0 / latencia_promedio

print("\n" + "="*60)
print("             RESULTADOS DEL BENCHMARK EN CPU")
print("="*60)
print(f" Latencia Promedio por documento:   {latencia_promedio:.2f} ms")
print(f" Latencia Mínima:                   {latencia_min:.2f} ms")
print(f" Latencia Máxima:                   {latencia_max:.2f} ms")
print(f" Latencia Percentil 95 (P95):       {latencia_p95:.2f} ms")
print(f" Consumo de RAM del modelo:         {ram_final_mb - ram_inicio_mb:.2f} MB (Total proceso: {ram_final_mb:.2f} MB)")
print(f" Throughput por core CPU individual: {tifs_por_segundo_por_core:.1f} docs/segundo")
print("="*60)

# Proyección a 11,000 expedientes
print("\n📊 PROYECCIÓN PARA LOTE DE 11,000 EXPEDIENTES EN CPU:")
print(f"   ▸ Con 1 solo worker CPU:   {((11000 * latencia_promedio) / 1000) / 60:.1f} minutos (solo inferencia)")
print(f"   ▸ Con 4 workers Celery:    {(((11000 * latencia_promedio) / 1000) / 60) / 4:.1f} minutos")
print(f"   ▸ Con 8 workers (DL380):   {(((11000 * latencia_promedio) / 1000) / 60) / 8:.1f} minutos")
print("="*60)
