# Este archivo se importa desde celery_app.py para asegurar que las tareas
# de Celery se registren correctamente al iniciar el worker.
from core.auditor import procesar_lote_kofax_task
