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


def _fuerza_borrado_ruta(ruta):
    """
    Elimina un archivo o directorio de forma segura.
    Si la carpeta tiene permisos 777 (otorgados por el Entrenador), shutil.rmtree lo borrará sin problemas.
    """
    if not os.path.exists(ruta):
        return None
        
    import shutil
    
    try:
        if os.path.isdir(ruta):
            shutil.rmtree(ruta, ignore_errors=False)
        else:
            os.remove(ruta)
        return None
    except Exception as e:
        # Intento secundario ignorando errores de permisos menores
        try:
            if os.path.isdir(ruta):
                shutil.rmtree(ruta, ignore_errors=True)
            else:
                os.remove(ruta)
            if not os.path.exists(ruta):
                return None
        except:
            pass
        return f"{ruta}: {e}"


def borrar_todo_el_conocimiento():
    """Elimina TODOS los cerebros entrenados y TODOS los datasets (activos y procesados)."""
    errores = []
    for carpeta in [CEREBROS_DIR, DATASET_DIR]:
        if os.path.isdir(carpeta):
            for item in os.listdir(carpeta):
                ruta = os.path.join(carpeta, item)
                err = _fuerza_borrado_ruta(ruta)
                if err:
                    errores.append(err)
    return errores


def borrar_conocimiento_proceso(matriz, proceso):
    """Elimina el cerebro y los datos de entrenamiento de un proceso específico."""
    errores = []
    rutas_a_borrar = [
        os.path.join(CEREBROS_DIR, matriz, proceso),
        os.path.join(DATASET_DIR, matriz, proceso),
        os.path.join(DATASET_DIR, 'processed', matriz, proceso),
    ]
    for ruta in rutas_a_borrar:
        err = _fuerza_borrado_ruta(ruta)
        if err:
            errores.append(err)
    return errores


def borrar_conocimiento_clase(matriz, proceso, clase):
    """
    Elimina únicamente una clase específica del dataset (activo y procesado) sin borrar el cerebro completo.
    El disparador de reentrenamiento regenerará el modelo manteniendo las demás clases intactas.
    """
    errores = []
    rutas_a_borrar = [
        os.path.join(DATASET_DIR, matriz, proceso, clase),
        os.path.join(DATASET_DIR, 'processed', matriz, proceso, clase),
    ]
    for ruta in rutas_a_borrar:
        err = _fuerza_borrado_ruta(ruta)
        if err:
            errores.append(err)
    return errores

def descartar_subida_clase(matriz, proceso, clase):
    """Descarta los archivos pendientes de una clase específica sin tocar los datos procesados ni los modelos."""
    errores = []
    ruta = os.path.join(DATASET_DIR, matriz, proceso, clase)
    err = _fuerza_borrado_ruta(ruta)
    if err:
        errores.append(err)
    return errores
