import os
import glob
from .ocr_engine import MotorOCR
from .routing_ia import predecir_documento

def procesar_lote_kofax():
    print("🔍 [Auditor] Iniciando revisión del lote Kofax (Estructura Intexus 16 campos)...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Ruta donde el banco (Kofax) deja los expedientes
    lote_dir = os.path.join(base_dir, '..', 'volumen_compartido', 'lote_kofax')
    os.makedirs(lote_dir, exist_ok=True)
    
    # Busca cualquier archivo que empiece con "Indice_" y termine en ".txt"
    archivos_indice = glob.glob(os.path.join(lote_dir, 'Indice_*.txt'))
    
    if not archivos_indice:
        return {"error": "No se encontró ningún archivo 'Indice_*.txt' en la carpeta 'lote_kofax'."}

    # Si hay varios índices, procesamos el primero que encuentre
    indice_path = archivos_indice[0]
    resultados = []

    # Encendemos el OCR en la memoria RAM
    motor_ocr = MotorOCR() 

    with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
        lineas = f.readlines()

    for linea in lineas:
        if not linea.strip(): continue
        
        separador = '|' if '|' in linea else (';' if ';' in linea else ',')
        partes = linea.strip().split(separador)
        
        # Validar que sea una línea válida con al menos 16 campos
        if len(partes) < 16: 
            continue
        
        # --- MAPEO EXACTO DE LA ESTRUCTURA INTEXUS (16 CAMPOS) ---
        subproceso = partes[8].strip().upper()
        
        # Extraemos la caja (ej: 'BT00123') y tomamos solo los 2 primeros caracteres ('BT')
        caja_completa = partes[13].strip().upper()
        matriz = caja_completa[:2] 
        
        tipo_esperado = partes[14].strip()
        archivo = partes[15].strip()
        
        # Blindaje de extensión
        if not (archivo.lower().endswith('.TIF') or archivo.lower().endswith('.pdf') or archivo.lower().endswith('.jpg')):
            archivo += '.TIF'

        ruta_imagen = os.path.join(lote_dir, archivo)

        if not os.path.exists(ruta_imagen):
            resultados.append({
                "archivo": archivo, "esperado": tipo_esperado, 
                "prediccion": "ARCHIVO FÍSICO NO ENCONTRADO", "estado": "danger"
            })
            continue

        # 1. Visión Artificial: Leemos el documento
        texto = motor_ocr.extraer_texto(ruta_imagen)

        # 2. Inferencia IA: Clasificamos
        if not texto:
            prediccion = "DOCUMENTO EN BLANCO / ILEGIBLE"
        else:
            prediccion = predecir_documento(texto, matriz, subproceso)

        # 3. Auditoría: ¿Coincide?
        if prediccion == "MODELO_NO_ENTRENADO":
            estado = "warning"
        elif prediccion == tipo_esperado:
            estado = "success"
        else:
            estado = "danger"

        resultados.append({
            "archivo": archivo,
            "matriz": matriz,
            "subproceso": subproceso,
            "esperado": tipo_esperado,
            "prediccion": prediccion,
            "estado": estado
        })

    return {"resultados": resultados}