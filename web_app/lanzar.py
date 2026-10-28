import uuid
from core.auditor import procesar_lote_kofax_task
task_id = str(uuid.uuid4())
print(f'INICIADO_TASK: {task_id}')
procesar_lote_kofax_task.apply_async(args=[task_id], task_id=task_id)
