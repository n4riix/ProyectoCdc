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
        accept_content=['json'],  # Ignore other content
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        worker_max_tasks_per_child=1,  # FORZA QUE EL PROCESO CELERY MUERA Y REVIVA TRAS CADA TAREA PARA DEVOLVER RAM AL OS
    )
    
    return celery

celery = make_celery('cdc_auditor')
