import os
from celery import Celery

def make_celery(app_name=__name__):
    # Usar Redis por defecto, o la variable de entorno
    broker = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    celery = Celery(app_name, broker=broker, backend=backend, include=['core.auditor'])
    
    # Configuraciones de Celery
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,

        # ─── RESILIENCIA ANTE OOM KILLER ──────────────────────────────────────
        # acks_late=True: el broker (Redis) NO confirma la tarea como "recibida"
        # hasta que el worker la completa exitosamente. Si el kernel mata el
        # proceso con SIGKILL (OOM), Redis detecta que la tarea nunca fue
        # confirmada y la vuelve a encolar automáticamente en el siguiente
        # worker disponible. Sin esto, las tareas se pierden silenciosamente.
        task_acks_late=True,

        # task_reject_on_worker_lost=True: complementa acks_late. Cuando el
        # proceso worker muere inesperadamente (signal 9), la tarea se rechaza
        # (NACK) en lugar de perderse, forzando su re-encole inmediato.
        task_reject_on_worker_lost=True,

        # worker_max_tasks_per_child: el proceso Celery muere y renace tras
        # cada tarea para devolver la RAM al OS. Crítico para OCR pesado.
        worker_max_tasks_per_child=1,
        # ─────────────────────────────────────────────────────────────────────
    )
    
    return celery

celery = make_celery('cdc_auditor')
