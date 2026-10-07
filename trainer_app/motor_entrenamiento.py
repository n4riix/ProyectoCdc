import os
import glob
import joblib
import logging
import shutil
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from paddleocr import PaddleOCR

# Silenciar mensajes innecesarios de PaddleOCR en la consola
logging.getLogger("ppocr").setLevel(logging.WARNING)

# ── Directorios del sistema ──────────────────────────────────────────────────
DATASET_DIR         = "/volumen_compartido/dataset_entrenamiento"   # legado BT/BR
DATASET_GLOBAL_DIR  = "/volumen_compartido/dataset_global"          # consolidado universal
DATASET_PEND_DIR    = "/volumen_compartido/dataset_pendientes"       # nuevas subidas
CEREBROS_DIR        = "/volumen_compartido/cerebros_ia"

# Nombre de los artefactos del modelo universal
MODELO_GLOBAL_PATH      = os.path.join(CEREBROS_DIR, "modelo_cdc_global.pkl")
VECTORIZADOR_GLOBAL_PATH = os.path.join(CEREBROS_DIR, "vectorizador_cdc_global.pkl")

# Forzar umask(0) para que todas las carpetas creadas por Root tengan permisos 777
os.umask(0)


# ── Utilidad: mover archivos de dataset_pendientes → dataset_global ──────────
def archivar_pendientes():
    """
    Consolida los archivos de dataset_pendientes/{CLASE}/ en dataset_global/{CLASE}/.
    Se llama DESPUÉS de entrenar el modelo, para marcar esos ejemplos como procesados.
    """
    if not os.path.isdir(DATASET_PEND_DIR):
        return

    for clase in os.listdir(DATASET_PEND_DIR):
        ruta_pend_clase = os.path.join(DATASET_PEND_DIR, clase)
        if not os.path.isdir(ruta_pend_clase):
            continue

        destino_clase = os.path.join(DATASET_GLOBAL_DIR, clase)
        os.makedirs(destino_clase, exist_ok=True)
        try:
            os.chmod(destino_clase, 0o777)
        except Exception:
            pass

        for f in glob.glob(os.path.join(ruta_pend_clase, "*")):
            try:
                nombre = os.path.basename(f)
                destino_f = os.path.join(destino_clase, nombre)
                # Evitar colisiones de nombre
                if os.path.exists(destino_f):
                    base, ext = os.path.splitext(nombre)
                    contador = 1
                    while os.path.exists(destino_f):
                        destino_f = os.path.join(destino_clase, f"{base}_{contador}{ext}")
                        contador += 1
                shutil.move(f, destino_f)
                try:
                    os.chmod(destino_f, 0o777)
                except Exception:
                    pass
            except Exception as e:
                print(f"⚠️ No se pudo consolidar {f}: {e}")

        # Limpiar carpeta vacía de pendientes
        try:
            if os.path.isdir(ruta_pend_clase) and not os.listdir(ruta_pend_clase):
                os.rmdir(ruta_pend_clase)
        except Exception:
            pass

    print("🗄️ Pendientes consolidados en dataset_global/")


# ── Utilidad: OCR con caché de texto ────────────────────────────────────────
def obtener_texto_con_cache(ocr_instancia, ruta_archivo_imagen):
    """
    Busca si existe un archivo .txt de caché para la imagen.
    Si existe y tiene contenido, lee el texto directamente (0 tiempo de OCR).
    Si no existe, ejecuta PaddleOCR y guarda la caché para el próximo entreno.
    """
    ruta_cache_txt = ruta_archivo_imagen + ".txt"

    if os.path.exists(ruta_cache_txt) and os.path.getsize(ruta_cache_txt) > 0:
        try:
            with open(ruta_cache_txt, 'r', encoding='utf-8', errors='ignore') as f:
                txt_c = f.read().strip()
                if txt_c:
                    return txt_c
        except Exception as e:
            print(f"Error leyendo caché {ruta_cache_txt}: {e}")

    print(f"👁️ [OCR Activo] Procesando: {os.path.basename(ruta_archivo_imagen)}")
    try:
        from PIL import Image, ImageSequence
        import numpy as np
        import cv2

        lineas_texto = []
        im = Image.open(ruta_archivo_imagen)
        if getattr(im, 'n_frames', 1) > 1:
            print(f"   📑 TIF Multipágina detectado ({im.n_frames} págs): extrayendo texto completo...")
            for page in ImageSequence.Iterator(im):
                page_rgb = page.convert('RGB')
                img_np = np.array(page_rgb)
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                res = ocr_instancia.ocr(img_bgr, cls=False)
                if res and res[0]:
                    for linea in res[0]:
                        lineas_texto.append(linea[1][0])
        else:
            resultados = ocr_instancia.ocr(ruta_archivo_imagen, cls=False)
            if resultados and resultados[0]:
                for linea in resultados[0]:
                    lineas_texto.append(linea[1][0])

        texto_limpio = " ".join(lineas_texto).strip()

        if texto_limpio:
            with open(ruta_cache_txt, 'w', encoding='utf-8') as f:
                f.write(texto_limpio)
            try:
                os.chmod(ruta_cache_txt, 0o777)
            except Exception:
                pass

        return texto_limpio
    except Exception as e:
        print(f"❌ Error al ejecutar OCR en {ruta_archivo_imagen}: {e}")
        return ""


# ── Motor principal ──────────────────────────────────────────────────────────
def entrenar_plataforma_completa(callback_progreso=None):
    """
    Entrena UN ÚNICO modelo universal (modelo_cdc_global.pkl) con TODAS las clases
    documentales del sistema, sin distinción de BT/BR ni de subproceso.

    Fuentes de datos (en orden de prioridad):
      1. /volumen_compartido/dataset_pendientes/{CLASE}/   ← nuevas subidas web
      2. /volumen_compartido/dataset_global/{CLASE}/       ← ya procesados en entrenos anteriores
      3. /volumen_compartido/dataset_entrenamiento/processed/{BT|BR}/{SUB}/{CLASE}/ ← legado histórico
    """
    print("🚀 [Cerebro Universal] Iniciando rutina de aprendizaje unificado...")
    if callback_progreso:
        callback_progreso(5)

    # Inicializar PaddleOCR (usa modelos offline, sin internet)
    ocr = PaddleOCR(use_angle_cls=False, lang='es', use_gpu=False,
                    enable_mkldnn=True, cpu_threads=1)
    if callback_progreso:
        callback_progreso(10)

    # ── 1. Recolectar todas las rutas de clases disponibles ─────────────────
    # Mapa: clase_nombre → lista_de_directorios
    mapa_clases: dict[str, list[str]] = {}

    def registrar_clases_en(directorio_raiz):
        """Agrega al mapa todas las sub-carpetas de clase que encuentre en directorio_raiz."""
        if not os.path.isdir(directorio_raiz):
            return
        for clase in os.listdir(directorio_raiz):
            ruta_clase = os.path.join(directorio_raiz, clase)
            if os.path.isdir(ruta_clase):
                mapa_clases.setdefault(clase, []).append(ruta_clase)

    # Fuentes de datos (de más reciente a más antigua)
    registrar_clases_en(DATASET_PEND_DIR)
    registrar_clases_en(DATASET_GLOBAL_DIR)

    # Legado: dataset_entrenamiento/processed/{BT|BR}/{SUBPROCESO}/{CLASE}
    ruta_procesados = os.path.join(DATASET_DIR, "processed")
    if os.path.isdir(ruta_procesados):
        for matriz in os.listdir(ruta_procesados):
            ruta_matriz = os.path.join(ruta_procesados, matriz)
            if not os.path.isdir(ruta_matriz):
                continue
            for subproceso in os.listdir(ruta_matriz):
                ruta_sub = os.path.join(ruta_matriz, subproceso)
                registrar_clases_en(ruta_sub)

    # Legado activo (sin archivar aún): dataset_entrenamiento/{BT|BR}/{SUBPROCESO}/{CLASE}
    for matriz in ["BT", "BR"]:
        ruta_matriz = os.path.join(DATASET_DIR, matriz)
        if os.path.isdir(ruta_matriz):
            for subproceso in os.listdir(ruta_matriz):
                ruta_sub = os.path.join(ruta_matriz, subproceso)
                registrar_clases_en(ruta_sub)

    clases_totales = sorted(mapa_clases.keys())
    print(f"📚 Clases detectadas en el universo: {len(clases_totales)}")
    for c in clases_totales:
        print(f"   ▸ {c}  ({len(mapa_clases[c])} directorio(s))")

    if callback_progreso:
        callback_progreso(15)

    # ── 2. Extraer texto de todos los documentos de todas las clases ─────────
    textos: list[str] = []
    etiquetas: list[str] = []
    total_clases = len(clases_totales)

    for idx, clase in enumerate(clases_totales):
        archivos_vistos: set[str] = set()  # evitar duplicados entre directorios

        for ruta_dir in mapa_clases[clase]:
            todos = glob.glob(os.path.join(ruta_dir, "*.*"))
            archivos_img = [f for f in todos if not f.endswith('.txt')]
            archivos_txt_huerfanos = [
                f for f in todos
                if f.endswith('.txt') and f[:-4] not in set(archivos_img)
            ]

            for archivo in archivos_img:
                nombre = os.path.basename(archivo)
                if nombre in archivos_vistos:
                    continue
                archivos_vistos.add(nombre)

                txt = obtener_texto_con_cache(ocr, archivo)
                if txt:
                    textos.append(txt)
                    etiquetas.append(clase)

            for txt_file in archivos_txt_huerfanos:
                nombre = os.path.basename(txt_file)
                if nombre in archivos_vistos:
                    continue
                archivos_vistos.add(nombre)
                try:
                    with open(txt_file, 'r', encoding='utf-8') as f:
                        contenido = f.read().strip()
                        if contenido:
                            textos.append(contenido)
                            etiquetas.append(clase)
                except Exception as e:
                    print(f"Error leyendo caché huérfano {txt_file}: {e}")

        # Reporte de progreso proporcional al número de clases (15% → 90%)
        if callback_progreso and total_clases > 0:
            prog = 15 + int(((idx + 1) / total_clases) * 75)
            callback_progreso(min(prog, 90))

    # ── 3. Entrenar el modelo universal ─────────────────────────────────────
    if len(textos) == 0:
        print("⚠️ No se encontraron documentos para entrenar. Abortando.")
        if callback_progreso:
            callback_progreso(100)
        return

    clases_unicas = sorted(set(etiquetas))
    print(f"\n🧠 [Matemáticas] Entrenando cerebro universal con {len(textos)} muestras y {len(clases_unicas)} clases...")

    vectorizador = TfidfVectorizer(max_features=10000, ngram_range=(1, 2))
    x_vect = vectorizador.fit_transform(textos)

    if len(clases_unicas) > 1:
        modelo = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
    else:
        print(f"⚠️ Solo una clase detectada ({clases_unicas[0]}). Usando DummyClassifier.")
        modelo = DummyClassifier(strategy='most_frequent')

    modelo.fit(x_vect, etiquetas)

    if callback_progreso:
        callback_progreso(92)

    # ── 4. Guardar el cerebro en la bóveda ───────────────────────────────────
    os.makedirs(CEREBROS_DIR, exist_ok=True)
    try:
        joblib.dump(modelo, MODELO_GLOBAL_PATH)
        joblib.dump(vectorizador, VECTORIZADOR_GLOBAL_PATH)
        print(f"✅ [Éxito] Cerebro universal guardado con {len(clases_unicas)} clases:")
        for c in clases_unicas:
            print(f"   ✔ {c}")
    except Exception as e:
        print(f"❌ Error guardando modelo universal: {e}")

    if callback_progreso:
        callback_progreso(95)

    # ── 5. Mover pendientes → global (consolidación post-entreno) ────────────
    try:
        archivar_pendientes()
    except Exception as e:
        print(f"⚠️ Error al consolidar pendientes: {e}")

    # Forzar permisos 777 en toda la bóveda y datasets
    try:
        os.system(f"chmod -R 777 {DATASET_GLOBAL_DIR} {DATASET_PEND_DIR} {CEREBROS_DIR} 2>/dev/null")
    except Exception:
        pass

    if callback_progreso:
        callback_progreso(100)

    print("🎉 Rutina de aprendizaje universal finalizada con éxito.")


if __name__ == "__main__":
    entrenar_plataforma_completa()