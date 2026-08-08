import os
import joblib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'dataset_entrenamiento')
CEREBROS_DIR = os.path.join(BASE_DIR, '..', 'volumen_compartido', 'cerebros_ia')

ALLOWED_EXTENSIONS = {'.tif', '.tiff', '.pdf', '.jpg', '.jpeg', '.png'}


def extension_permitida(nombre_archivo):
    _, ext = os.path.splitext(nombre_archivo)
    return ext.lower() in ALLOWED_EXTENSIONS


def obtener_inventario_tipos_documentales():
    inventario = {}
    for matriz in ['BT', 'BR']:
        ruta_matriz = os.path.join(DATASET_DIR, matriz)
        if not os.path.isdir(ruta_matriz):
            continue

        for subproceso in sorted(os.listdir(ruta_matriz)):
            ruta_subproceso = os.path.join(ruta_matriz, subproceso)
            if not os.path.isdir(ruta_subproceso):
                continue
            
            # Solo incluir clases que tengan al menos un archivo dentro
            clases = []
            for nombre in os.listdir(ruta_subproceso):
                ruta_clase = os.path.join(ruta_subproceso, nombre)
                if os.path.isdir(ruta_clase) and len(os.listdir(ruta_clase)) > 0:
                    clases.append(nombre)
            
            if clases:
                inventario.setdefault(matriz, {})[subproceso] = sorted(clases)

    return inventario


def obtener_modelos_conocidos():
    modelos = {}

    for matriz in ['BT', 'BR']:
        ruta_matriz = os.path.join(CEREBROS_DIR, matriz)
        if not os.path.isdir(ruta_matriz):
            continue

        for subproceso in sorted(os.listdir(ruta_matriz)):
            ruta_subproceso = os.path.join(ruta_matriz, subproceso)
            if not os.path.isdir(ruta_subproceso):
                continue

            ruta_modelo = os.path.join(ruta_subproceso, 'modelo.pkl')
            clases = []
            entrenado = False

            if os.path.exists(ruta_modelo):
                try:
                    modelo = joblib.load(ruta_modelo)
                    clases = list(getattr(modelo, 'classes_', []))
                    entrenado = True
                except Exception:
                    clases = []

            if not clases:
                ruta_dataset = os.path.join(DATASET_DIR, matriz, subproceso)
                if os.path.isdir(ruta_dataset):
                    clases = sorted(
                        nombre for nombre in os.listdir(ruta_dataset)
                        if os.path.isdir(os.path.join(ruta_dataset, nombre))
                    )

            if clases:
                modelos.setdefault(matriz, {})[subproceso] = {
                    'entrenado': entrenado,
                    'clases': clases,
                }

    return modelos


def borrar_todo_el_conocimiento():
    """Elimina TODOS los cerebros entrenados y TODOS los datasets (activos y procesados)."""
    import shutil
    errores = []
    for carpeta in [CEREBROS_DIR, DATASET_DIR]:
        if os.path.isdir(carpeta):
            for item in os.listdir(carpeta):
                ruta = os.path.join(carpeta, item)
                try:
                    if os.path.isdir(ruta):
                        shutil.rmtree(ruta)
                    else:
                        os.remove(ruta)
                except Exception as e:
                    errores.append(f"{ruta}: {e}")
    return errores


def borrar_conocimiento_proceso(matriz, proceso):
    """Elimina el cerebro y los datos de entrenamiento de un proceso específico."""
    import shutil
    errores = []
    rutas_a_borrar = [
        os.path.join(CEREBROS_DIR, matriz, proceso),
        os.path.join(DATASET_DIR, matriz, proceso),
        os.path.join(DATASET_DIR, 'processed', matriz, proceso),
    ]
    for ruta in rutas_a_borrar:
        if os.path.isdir(ruta):
            try:
                shutil.rmtree(ruta)
            except Exception as e:
                errores.append(f"{ruta}: {e}")
    return errores


def borrar_conocimiento_clase(matriz, proceso, clase):
    """Elimina una clase específica del dataset y marca el cerebro para re-entrenamiento."""
    import shutil
    errores = []
    rutas_a_borrar = [
        os.path.join(DATASET_DIR, matriz, proceso, clase),
        os.path.join(DATASET_DIR, 'processed', matriz, proceso, clase),
    ]
    for ruta in rutas_a_borrar:
        if os.path.isdir(ruta):
            try:
                shutil.rmtree(ruta)
            except Exception as e:
                errores.append(f"{ruta}: {e}")

    # Eliminar el cerebro del proceso para forzar re-entrenamiento sin esa clase
    ruta_cerebro = os.path.join(CEREBROS_DIR, matriz, proceso)
    if os.path.isdir(ruta_cerebro):
        try:
            shutil.rmtree(ruta_cerebro)
        except Exception as e:
            errores.append(f"{ruta_cerebro}: {e}")
    return errores

def descartar_subida_clase(matriz, proceso, clase):
    """Descarta los archivos pendientes de una clase específica sin tocar los datos procesados ni los modelos."""
    import shutil
    errores = []
    ruta = os.path.join(DATASET_DIR, matriz, proceso, clase)
    if os.path.isdir(ruta):
        try:
            shutil.rmtree(ruta)
        except Exception as e:
            errores.append(f"{ruta}: {e}")
    return errores
