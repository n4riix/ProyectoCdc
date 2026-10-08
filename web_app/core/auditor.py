import os
import glob
import csv
import logging
import uuid
import shutil
from datetime import datetime
from celery_app import celery
from .ocr_engine import obtener_motor_ocr
from .routing_ia import predecir_documento
from .extractor_fechas import validar_coincidencia_fecha
from .inventory import obtener_clases_modelo_universal
from .db_models import (
    crear_lote_auditoria,
    actualizar_progreso_lote,
    completar_lote_auditoria,
    guardar_resultado_auditoria,
    obtener_lineas_procesadas,
    obtener_conexion,
    obtener_cursor,
    fetchone_dict,
    execute_query
)

def _actualizar_conteo_global(task_id_str):
    """Actualiza el total de documentos procesados en la base de datos."""
    try:
        conn = obtener_conexion()
        cursor = obtener_cursor(conn)
        execute_query(cursor, "SELECT COUNT(*) as total FROM auditoria_resultados WHERE auditoria_id = ?", (task_id_str,))
        row = fetchone_dict(cursor)
        total = row['total'] if row else 0
        execute_query(cursor, "UPDATE auditorias_lotes SET documentos_procesados = ? WHERE id = ?", (total, task_id_str))
        
        execute_query(cursor, "SELECT total_documentos, estado FROM auditorias_lotes WHERE id = ?", (task_id_str,))
        row_lote = fetchone_dict(cursor)
        if row_lote and total >= row_lote['total_documentos'] and row_lote['estado'] == 'procesando':
            execute_query(cursor, "UPDATE auditorias_lotes SET estado = 'completado', fecha_fin = CURRENT_TIMESTAMP WHERE id = ?", (task_id_str,))
            execute_query(cursor, "DELETE FROM estado_sistema WHERE clave = 'tarea_auditoria_activa'")

        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error actualizando conteo global: {e}")

@celery.task(bind=True, name="core.auditor.procesar_rango_kofax_task")
def procesar_rango_kofax_task(self, task_id_str, lineas_rango):
    """
    Procesa un rango específico de números de línea en paralelo.
    """
    try:
        # lote_dir = '/volumen_compartido/lote_kofax'
        lote_dir = '/mnt/lote_nuevo/Respaldo_ImagenesBBVA/Imagenes_30092026_Corte_131500'
        archivos_indice = [
            f for f in glob.glob(os.path.join(lote_dir, '*.[tT][xX][tT]'))
            if os.path.basename(f).lower().startswith('indice_')
        ]
        if not archivos_indice:
            return {"error": "Sin archivo de índice"}

        indice_path = archivos_indice[0]
        lineas_set = set(lineas_rango)

        # Verificar qué líneas de este rango ya se procesaron
        lineas_ya_procesadas = set(obtener_lineas_procesadas(task_id_str))
        lineas_pendientes = lineas_set - lineas_ya_procesadas

        if not lineas_pendientes:
            return {"status": "Rango ya completado", "count": 0}

        motor_ocr = obtener_motor_ocr()
        clases_raw = obtener_clases_modelo_universal()
        clases_conocidas_set = set(clases_raw)
        # Diccionario de equivalencia normalizada para soportar variaciones con '/' o espacios
        mapa_clases_norm = {c.replace('/', ' ').replace('_', ' ').lower(): c for c in clases_raw}

        procesados_locales = 0

        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            numero_linea = 0
            for partes in reader:
                numero_linea += 1
                if numero_linea not in lineas_pendientes:
                    continue

                if not partes or len(partes) < 16:
                    continue

                fecha_indice_raw = partes[0].strip().replace('"', '') if len(partes) > 0 else ""
                subproceso = partes[8].strip().upper() if len(partes) > 8 else ""
                caja_completa = partes[13].strip().upper() if len(partes) > 13 else ""
                matriz = caja_completa[:2]
                tipo_esperado = partes[14].strip() if len(partes) > 14 else ""

                archivo = partes[15].strip() if len(partes) > 15 else ""
                archivo_lower = archivo.lower()
                if archivo and not (archivo_lower.endswith('.tif') or archivo_lower.endswith('.pdf') or archivo_lower.endswith('.jpg')):
                    archivo += '.TIF'

                # Validación con el Cerebro Universal Global (con soporte de normalización)
                tipo_esperado_norm = tipo_esperado.replace('/', ' ').replace('_', ' ').lower()
                clase_canonica = tipo_esperado if tipo_esperado in clases_conocidas_set else mapa_clases_norm.get(tipo_esperado_norm)
                if clases_conocidas_set and not clase_canonica:
                    guardar_resultado_auditoria(task_id_str, numero_linea, archivo or f"Linea_{numero_linea}", matriz, subproceso, tipo_esperado, "DOCUMENTO NO ENTRENADO", "warning", 0.0, fecha_indice=fecha_indice_raw)
                    procesados_locales += 1
                    continue

                ruta_imagen = os.path.join(lote_dir, archivo)

                if not os.path.exists(ruta_imagen):
                    guardar_resultado_auditoria(task_id_str, numero_linea, archivo, matriz, subproceso, tipo_esperado, "ARCHIVO FÍSICO NO ENCONTRADO", "danger", 0.0, fecha_indice=fecha_indice_raw)
                    procesados_locales += 1
                    continue

                # Extracción con OCR (NVIDIA GPU / Intel CPU)
                texto = motor_ocr.extraer_texto(ruta_imagen)

                # Validar Comparación de Fechas (guardar en BD para histórico, pero sin bloquear el veredicto en Fase 1)
                coincide_fecha, f_ind_norm, fechas_doc_list, msg_fecha = validar_coincidencia_fecha(fecha_indice_raw, texto)
                fechas_doc_str = ", ".join(fechas_doc_list) if fechas_doc_list else "Ninguna"

                # Inferencia IA
                confianza = 1.0
                if not texto:
                    prediccion = "DOCUMENTO EN BLANCO / ILEGIBLE"
                    confianza = 0.0
                else:
                    prediccion, confianza = predecir_documento(texto, matriz, subproceso)

                confianza_pct = round(confianza * 100, 1)

                # ── Reglas de Veredicto (Umbral de Confianza 60% - Sin alerta por discrepancia de fecha) ──
                UMBRAL_CONFIANZA = 60.0

                if prediccion == "MODELO_NO_ENTRENADO":
                    estado = "warning"
                elif prediccion == "DOCUMENTO EN BLANCO / ILEGIBLE":
                    estado = "danger"
                elif confianza_pct < UMBRAL_CONFIANZA:
                    # Si no alcanza el 60% de certeza, se emite alerta por baja confianza para revisión manual
                    estado = "warning"
                    prediccion = f"DUDA IA ({confianza_pct}%): {prediccion}"
                elif prediccion == tipo_esperado or (clase_canonica and prediccion == clase_canonica):
                    estado = "success"
                else:
                    estado = "danger"

                guardar_resultado_auditoria(
                    task_id_str, numero_linea, archivo, matriz, subproceso, tipo_esperado, prediccion, estado, confianza_pct,
                    fecha_indice=f_ind_norm, fechas_documento=fechas_doc_str, coincidencia_fecha=1 if coincide_fecha else 0
                )
                procesados_locales += 1

                _actualizar_conteo_global(task_id_str)

        _actualizar_conteo_global(task_id_str)
        return {"status": "Rango Completado", "procesados": procesados_locales}
    except Exception as e:
        import traceback
        logging.error(f"❌ Error en procesar_rango_kofax_task: {traceback.format_exc()}")
        return {"status": "Error", "error": str(e)}

@celery.task(bind=True, name="core.auditor.procesar_lote_kofax_task")
def procesar_lote_kofax_task(self, task_id_str):
    try:
        logging.info(f"🚀 [Orquestador Celery Parallel] Iniciando auditoría paralelizada para lote {task_id_str}...")

        # lote_dir = '/volumen_compartido/lote_kofax'
        lote_dir = '/mnt/lote_nuevo/Respaldo_ImagenesBBVA/Imagenes_30092026_Corte_131500'
        os.makedirs(lote_dir, exist_ok=True)

        archivos_indice = [
            f for f in glob.glob(os.path.join(lote_dir, '*.[tT][xX][tT]'))
            if os.path.basename(f).lower().startswith('indice_')
        ]
        if not archivos_indice:
            completar_lote_auditoria(task_id_str, 'error')
            return {"error": "No se encontró ningún archivo de índice ('Indice_*.txt')."}

        indice_path = archivos_indice[0]

        # Respaldo
        backup_dir = '/volumen_compartido/backups_indices'
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(indice_path, os.path.join(backup_dir, f"{os.path.basename(indice_path)}.{timestamp}.bak"))

        # Contar total de líneas válidas
        lineas_validas = []
        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            num_linea = 0
            for row in reader:
                num_linea += 1
                if row and len(row) >= 16:
                    lineas_validas.append(num_linea)

        total_lineas = len(lineas_validas)
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

        crear_lote_auditoria(task_id_str, total_lineas, f"{corte}|{fecha}")

        # Dividir en 8 bloques paralelos para utilizar los 4 trabajadores Celery simultáneamente
        num_bloques = 8
        tamano_bloque = max(1, (total_lineas + num_bloques - 1) // num_bloques)

        logging.info(f"⚡ Dividiendo {total_lineas} documentos en {num_bloques} bloques paralelos (~{tamano_bloque} docs/bloque)...")

        for i in range(0, total_lineas, tamano_bloque):
            rango = lineas_validas[i:i + tamano_bloque]
            if rango:
                procesar_rango_kofax_task.delay(task_id_str, rango)

        return {"status": "Lanzado en Paralelo", "total": total_lineas, "bloques": (total_lineas + tamano_bloque - 1) // tamano_bloque}
    except Exception as e:
        import traceback
        logging.error(f"❌ Error orquestando lote {task_id_str}: {traceback.format_exc()}")
        completar_lote_auditoria(task_id_str, 'error')
        return {"status": "Error", "error": str(e)}
