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

            clases = sorted(
                nombre for nombre in os.listdir(ruta_subproceso)
                if os.path.isdir(os.path.join(ruta_subproceso, nombre))
            )

            if clases:
                inventario.setdefault(matriz, {})[subproceso] = clases

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
