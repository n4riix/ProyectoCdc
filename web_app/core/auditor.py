import os
import glob
import csv
import logging
import uuid
import shutil
import unicodedata

def _normalizar_nombre_clase(nombre):
    if not nombre:
        return ""
    s = unicodedata.normalize("NFD", str(nombre))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("/", " ").replace("_", " ").lower().strip()
from datetime import datetime
from celery_app import celery
from .ocr_engine import obtener_motor_ocr
try:
    from .routing_beto import predecir_documento_beto as predecir_documento
except Exception as _err:
    import logging
    logging.warning(f'Fallback a TF-IDF: {_err}')
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

def _obtener_lote_dir_activo():
    """Detecta la ruta del lote activo actualmente."""
    base_lotes = '/mnt/lote_nuevo'
    if os.path.isdir(base_lotes):
        # 1. Si la raíz /mnt/lote_nuevo contiene directamente un archivo de índice
        indices_raiz = [f for f in glob.glob(os.path.join(base_lotes, '*.[tT][xX][tT]')) if os.path.basename(f).lower().startswith('indice_')]
        if indices_raiz:
            return base_lotes

        # 2. Si contiene subcarpetas con lotes
        subdirs = [
            os.path.join(base_lotes, d) for d in os.listdir(base_lotes)
            if os.path.isdir(os.path.join(base_lotes, d))
        ]
        subdirs.sort(key=lambda d: os.path.getmtime(d), reverse=True)
        for d in subdirs:
            if any(f.lower().startswith('indice_') for f in os.listdir(d)):
                return d
        if subdirs:
            return subdirs[0]
        return base_lotes

    return '/volumen_compartido/lote_kofax'

def _actualizar_conteo_global(task_id_str):
    """Actualiza el total de documentos procesados en la base de datos."""
    try:
        conn = obtener_conexion()
        cursor = obtener_cursor(conn)
        execute_query(cursor, "SELECT COUNT(DISTINCT linea_indice) as total FROM auditoria_resultados WHERE auditoria_id = ?", (task_id_str,))
        row = fetchone_dict(cursor)
        total = row['total'] if row else 0
        execute_query(cursor, "UPDATE auditorias_lotes SET documentos_procesados = ? WHERE id = ?", (total, task_id_str))
        
        execute_query(cursor, "SELECT total_documentos, estado FROM auditorias_lotes WHERE id = ?", (task_id_str,))
        row_lote = fetchone_dict(cursor)
        if row_lote and row_lote['total_documentos'] > 0 and total >= row_lote['total_documentos'] and row_lote['estado'] == 'procesando':
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
        lote_dir = _obtener_lote_dir_activo()
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
        mapa_clases_norm = {_normalizar_nombre_clase(c): c for c in clases_raw}

        procesados_locales = 0

        # FIX: Auto-detectar delimitador (tab vs coma) — consistente con el orquestador
        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f_detect:
            primera_linea = f_detect.readline()
            delimitador_rango = '\t' if '\t' in primera_linea else ','
        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f, delimiter=delimitador_rango)
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
                tipo_esperado_norm = _normalizar_nombre_clase(tipo_esperado)
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

                # ── Reglas de Veredicto ──
                # REGLA DE ORO: Si lo que predijo la IA coincide con lo que dijo el Operador Cdc,
                # se convalida como CONFORME (success) sin importar el porcentaje de confianza.
                # Solo se marca como DUDA si la IA propone una clase diferente o está por debajo del 60%.
                UMBRAL_CONFIANZA = 60.0
                coincide_con_operador = (
                    prediccion == tipo_esperado 
                    or (clase_canonica and prediccion == clase_canonica) 
                    or (_normalizar_nombre_clase(prediccion) == tipo_esperado_norm)
                )

                if prediccion == "MODELO_NO_ENTRENADO":
                    estado = "warning"
                elif prediccion == "DOCUMENTO EN BLANCO / ILEGIBLE":
                    estado = "danger"
                elif coincide_con_operador:
                    # Ambas partes coinciden: Convalidación directa
                    estado = "success"
                elif confianza_pct < UMBRAL_CONFIANZA:
                    # La IA difiere del operador Y tiene baja confianza: es una DUDA para revisión humana
                    estado = "warning"
                    prediccion = f"DUDA IA ({confianza_pct}%): {prediccion}"
                else:
                    # La IA difiere del operador pero con alta confianza: es una DISCREPANCIA clara
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
def procesar_lote_kofax_task(self, task_id_str, clases_filtro=None):
    try:
        logging.info(f"🚀 [Orquestador Celery Parallel] Iniciando auditoría paralelizada para lote {task_id_str}...")

        lote_dir = _obtener_lote_dir_activo()
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

        # Contar total de líneas válidas (con soporte a filtro selectivo de clases)
        set_filtro = set(clases_filtro) if clases_filtro else None
        set_filtro_norm = {_normalizar_nombre_clase(c) for c in clases_filtro} if clases_filtro else None

        lineas_validas = []
        # FIX: Auto-detectar delimitador — el índice puede ser CSV (comas) o TSV (tabs).
        # csv.reader por defecto usa comas; si el archivo es TSV, toda la línea queda en 1 columna
        # y len(row) < 16 siempre, resultando en total_lineas=0.
        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f_detect:
            primera_linea = f_detect.readline()
            delimitador = '\t' if '\t' in primera_linea else ','
        logging.info(f"[Orquestador] Índice detectado como {'TSV' if delimitador == chr(9) else 'CSV'} (delim={repr(delimitador)})")
        with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f, delimiter=delimitador)
            num_linea = 0
            for row in reader:
                num_linea += 1
                if row and len(row) >= 16:
                    if set_filtro:
                        tipo_esp = row[14].strip() if len(row) > 14 else ''
                        tipo_norm = _normalizar_nombre_clase(tipo_esp)
                        if (tipo_esp in set_filtro) or (tipo_norm in set_filtro_norm):
                            lineas_validas.append(num_linea)
                    else:
                        lineas_validas.append(num_linea)

        # --- REINTENTO si total_lineas = 0 (puede ser falla transitoria de CIFS/SMB) ---
        if len(lineas_validas) == 0:
            logging.warning(f"[Orquestador] total_lineas=0 en primera lectura, reintentando en 5s...")
            import time as _time
            for _intento in range(2):
                _time.sleep(5)
                lineas_validas = []
                try:
                    with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f2:
                        primera2 = f2.readline()
                        delim2 = '\t' if '\t' in primera2 else ','
                    with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f2:
                        reader2 = csv.reader(f2, delimiter=delim2)
                        num2 = 0
                        for row2 in reader2:
                            num2 += 1
                            if row2 and len(row2) >= 16:
                                if set_filtro:
                                    tipo2 = row2[14].strip() if len(row2) > 14 else ''
                                    tipo2n = _normalizar_nombre_clase(tipo2)
                                    if (tipo2 in set_filtro) or (tipo2n in set_filtro_norm):
                                        lineas_validas.append(num2)
                                else:
                                    lineas_validas.append(num2)
                    logging.info(f"[Orquestador] Reintento {_intento+1}: lineas_validas={len(lineas_validas)}")
                    if lineas_validas:
                        break
                except Exception as _e:
                    logging.error(f"[Orquestador] Error en reintento {_intento+1}: {_e}")

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

        # FIX CRÍTICO: Si total_lineas = 0 después de reintentos, completar inmediatamente
        # para que la UI no quede congelada en "Iniciando..." para siempre.
        if total_lineas == 0:
            logging.error(f"[Orquestador] No se encontraron líneas válidas en el índice (clases_filtro={clases_filtro}). Marcando lote como error.")
            completar_lote_auditoria(task_id_str, 'error')
            return {"status": "Error", "error": "Índice sin líneas válidas (posible filtro de clases vacío o archivo no disponible temporalmente)."}

        # Dividir en 4 bloques (uno por worker Celery) — menos condiciones de carrera en DB
        num_bloques = 4
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
