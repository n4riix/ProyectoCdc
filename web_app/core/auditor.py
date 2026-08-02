import os
import glob
import csv
import logging
import uuid
from celery_app import celery
from .ocr_engine import obtener_motor_ocr
from .routing_ia import predecir_documento
from .db_models import crear_lote_auditoria, actualizar_progreso_lote, completar_lote_auditoria, guardar_resultado_auditoria

@celery.task(bind=True, name="core.auditor.procesar_lote_kofax_task")
def procesar_lote_kofax_task(self, task_id_str):
    try:
        logging.info(f"🔍 [Auditor Celery] Iniciando revisión del lote Kofax {task_id_str}...")
        
        lote_dir = '/volumen_compartido/lote_kofax'
        os.makedirs(lote_dir, exist_ok=True)
        
        archivos_indice = glob.glob(os.path.join(lote_dir, 'Indice_*.txt'))
        if not archivos_indice:
            completar_lote_auditoria(task_id_str, 'error')
            return {"error": "No se encontró ningún archivo 'Indice_*.txt'."}

        indice_path = archivos_indice[0]
        
        # 0. Crear un respaldo (backup) del índice original
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        indice_backup_path = f"{indice_path}.{timestamp}.bak"
        # Copiar solo si no existe el backup para esta tarea, aunque al ser por timestamp siempre creará uno nuevo
        shutil.copy2(indice_path, indice_backup_path)
        logging.info(f"Respaldo creado en: {indice_backup_path}")

        # Contar total de líneas para saber cuánto vamos a procesar
        total_lineas = 0
        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            total_lineas = sum(1 for row in reader if row and len(row) >= 16)

        indice_nombre = os.path.basename(indice_path)
        import re
        match = re.search(r'_(\d{8})_(\d+)', indice_nombre)
        if match:
            f_str = match.group(1)
            corte = str(int(match.group(2)))
            fecha = f"{f_str[6:8]}/{f_str[4:6]}/{f_str[0:4]}"
        else:
            fecha = datetime.fromtimestamp(os.path.getmtime(indice_path)).strftime('%d/%m/%Y')
            corte = indice_nombre.replace('Indice_', '').replace('.txt', '')
            
        info_corte = f"{corte}|{fecha}"
        crear_lote_auditoria(task_id_str, total_lineas, info_corte)
        
        # Obtener las líneas ya procesadas por si es una reanudación
        from .db_models import obtener_lineas_procesadas
        lineas_procesadas = obtener_lineas_procesadas(task_id_str)
        procesados = len(lineas_procesadas)
        logging.info(f"Reanudando: {procesados} documentos ya estaban procesados.")

        # Encendemos el OCR en la memoria RAM
        motor_ocr = obtener_motor_ocr() 
        
        from .inventory import obtener_modelos_conocidos
        modelos_conocidos = obtener_modelos_conocidos()

        numero_linea = 0
        llamadas_ocr_chunk = 0

        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)

            for partes in reader:
                numero_linea += 1
                if not partes or len(partes) < 16:
                    continue

                if numero_linea in lineas_procesadas:
                    # Ya se procesó en una ejecución anterior (reanudación)
                    continue

                subproceso = partes[8].strip().upper()
                caja_completa = partes[13].strip().upper()
                matriz = caja_completa[:2]

                if matriz != 'BT':
                    procesados += 1
                    if procesados % 10 == 0: actualizar_progreso_lote(task_id_str, procesados)
                    continue
                
                if matriz not in modelos_conocidos or subproceso not in modelos_conocidos[matriz]:
                    procesados += 1
                    if procesados % 10 == 0: actualizar_progreso_lote(task_id_str, procesados)
                    continue
                
                tipo_esperado = partes[14].strip()
                clases_conocidas = modelos_conocidos[matriz][subproceso].get('clases', [])
                if tipo_esperado not in clases_conocidas:
                    procesados += 1
                    if procesados % 10 == 0: actualizar_progreso_lote(task_id_str, procesados)
                    continue

                archivo = partes[15].strip()
                archivo_lower = archivo.lower()
                if not (archivo_lower.endswith('.tif') or archivo_lower.endswith('.pdf') or archivo_lower.endswith('.jpg')):
                    archivo += '.TIF'

                ruta_imagen = os.path.join(lote_dir, archivo)

                # --- ESTADO EN VIVO PARA EL POLLING LIGERO ---
                self.update_state(state='PROGRESS', meta={'archivo': archivo, 'procesados': procesados, 'total': total_lineas})

                if not os.path.exists(ruta_imagen):
                    guardar_resultado_auditoria(task_id_str, numero_linea, archivo, matriz, subproceso, tipo_esperado, "ARCHIVO FÍSICO NO ENCONTRADO", "danger")
                    procesados += 1
                    actualizar_progreso_lote(task_id_str, procesados)
                    continue

                # 1. Visión Artificial
                texto = motor_ocr.extraer_texto(ruta_imagen)

                # 2. Inferencia IA
                confianza = 1.0
                if not texto:
                    prediccion = "DOCUMENTO EN BLANCO / ILEGIBLE"
                    confianza = 0.0
                else:
                    prediccion, confianza = predecir_documento(texto, matriz, subproceso)

                # 3. Auditoría con umbral de confianza (90%)
                confianza_pct = round(confianza * 100, 1)
                if prediccion == "MODELO_NO_ENTRENADO":
                    estado = "warning"
                elif confianza < 0.90:
                    estado = "danger"
                elif prediccion == tipo_esperado:
                    estado = "success"
                else:
                    estado = "danger"

                guardar_resultado_auditoria(task_id_str, numero_linea, archivo, matriz, subproceso, tipo_esperado, prediccion, estado, confianza_pct)
                
                procesados += 1
                actualizar_progreso_lote(task_id_str, procesados)
                
                llamadas_ocr_chunk += 1
                if llamadas_ocr_chunk >= 100:
                    logging.warning(f"🔄 [Chunk Limit] 100 imágenes procesadas. Terminando tarea para forzar al OS a liberar RAM...")
                    # Volvemos a lanzar la misma tarea. Como usamos el mismo ID y la DB guarda el progreso,
                    # la nueva tarea saltará automáticamente los procesados y continuará.
                    procesar_lote_kofax_task.apply_async(args=[task_id_str], task_id=task_id_str, countdown=2)
                    return {"status": "Chunk Completado. Re-encolando...", "total": procesados}

        completar_lote_auditoria(task_id_str, 'completado')
        return {"status": "Completado", "total": procesados}
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        logging.error(f"❌ Error crítico procesando lote {task_id_str}: {error_msg}")
        completar_lote_auditoria(task_id_str, 'error')
        return {"status": "Error", "error": str(e)}