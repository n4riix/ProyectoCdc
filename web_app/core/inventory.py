import os
import joblib

import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOLUMEN_COMPARTIDO = os.path.join(BASE_DIR, '..', 'volumen_compartido')
DATASET_GLOBAL_DIR = os.path.join(VOLUMEN_COMPARTIDO, 'dataset_global')
DATASET_PENDIENTES_DIR = os.path.join(VOLUMEN_COMPARTIDO, 'dataset_pendientes')
DATASET_LEGACY_DIR = os.path.join(VOLUMEN_COMPARTIDO, 'dataset_entrenamiento')
CEREBROS_DIR = os.path.join(VOLUMEN_COMPARTIDO, 'cerebros_ia')
MAPA_PROCESOS_FILE = os.path.join(VOLUMEN_COMPARTIDO, 'procesos_map.json')

ALLOWED_EXTENSIONS = {'.tif', '.tiff', '.pdf', '.jpg', '.jpeg', '.png'}


# Caché en memoria para evitar I/O redundante en disco
_CACHE_MAPA_PROCESOS = None
_CACHE_MTIME_MAPA = -1.0


def _cargar_mapa_procesos():
    """Carga el mapa dinámico de procesos con caché en RAM invalidada por mtime."""
    global _CACHE_MAPA_PROCESOS, _CACHE_MTIME_MAPA

    if not os.path.exists(MAPA_PROCESOS_FILE):
        _CACHE_MAPA_PROCESOS = {}
        _CACHE_MTIME_MAPA = -1.0
        return {}

    try:
        mtime = os.path.getmtime(MAPA_PROCESOS_FILE)
        if _CACHE_MAPA_PROCESOS is not None and mtime <= _CACHE_MTIME_MAPA:
            return _CACHE_MAPA_PROCESOS

        with open(MAPA_PROCESOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _CACHE_MAPA_PROCESOS = data if isinstance(data, dict) else {}
            _CACHE_MTIME_MAPA = mtime
            return _CACHE_MAPA_PROCESOS
    except Exception as e:
        print(f"Advertencia al leer {MAPA_PROCESOS_FILE}: {e}")
        return _CACHE_MAPA_PROCESOS if _CACHE_MAPA_PROCESOS is not None else {}


def _guardar_mapa_procesos_file(mapa):
    """Guarda el mapa de procesos de forma atómica (tmp + os.replace) para prevenir corrupción."""
    global _CACHE_MAPA_PROCESOS, _CACHE_MTIME_MAPA
    try:
        os.makedirs(VOLUMEN_COMPARTIDO, exist_ok=True)
        tmp_file = f"{MAPA_PROCESOS_FILE}.tmp.{os.getpid()}"
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(mapa, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        try:
            os.chmod(tmp_file, 0o777)
        except Exception:
            pass

        # Reemplazo atómico en el sistema de archivos
        os.replace(tmp_file, MAPA_PROCESOS_FILE)

        _CACHE_MAPA_PROCESOS = mapa
        try:
            _CACHE_MTIME_MAPA = os.path.getmtime(MAPA_PROCESOS_FILE)
        except Exception:
            _CACHE_MTIME_MAPA = -1.0
    except Exception as e:
        print(f"Error guardando mapa de procesos JSON de forma atómica: {e}")


def extension_permitida(nombre_archivo):
    _, ext = os.path.splitext(nombre_archivo)
    return ext.lower() in ALLOWED_EXTENSIONS


def guardar_mapa_procesos_clase(clase, lista_procesos):
    """Guarda o actualiza la lista de procesos en mayúsculas para un tipo documental."""
    if not clase or not lista_procesos:
        return
    mapa = _cargar_mapa_procesos()
    procesos_clean = [p.strip().upper() for p in lista_procesos if p.strip()]
    existentes = mapa.get(clase, [])
    nuevos = list(dict.fromkeys(existentes + procesos_clean))
    mapa[clase] = nuevos
    _guardar_mapa_procesos_file(mapa)


def obtener_procesos_de_clase(clase):
    """Retorna la lista actual de procesos para una clase, usando mapa dinámico o base estático."""
    mapa_dinamico = _cargar_mapa_procesos()
    procesos = mapa_dinamico.get(clase, [])
    if not procesos:
        procesos = PROCESOS_BASE.get(clase, [])
    if not procesos:
        if clase.startswith("EXC"):
            procesos = ["CCD", "CNE", "CNW"]
        elif clase.startswith("REC"):
            procesos = ["ACT", "AMC", "CCD", "CNE", "CNW", "TDC"]
        else:
            procesos = ["GLOBAL"]
    return procesos


def obtener_inventario_pendientes():
    """
    Retorna el Pre-Inventario: únicamente los documentos pendientes por ser aprendidos por la IA.
    Retorna un diccionario: { nombre_clase: int_pendientes }
    """
    inventario_pendientes = {}

    if os.path.isdir(DATASET_PENDIENTES_DIR):
        for nombre in sorted(os.listdir(DATASET_PENDIENTES_DIR)):
            ruta_clase = os.path.join(DATASET_PENDIENTES_DIR, nombre)
            if os.path.isdir(ruta_clase):
                archivos = [f for f in os.listdir(ruta_clase) if extension_permitida(f)]
                if archivos:
                    inventario_pendientes[nombre] = len(archivos)

    if os.path.isdir(DATASET_LEGACY_DIR):
        for matriz in ['BT', 'BR']:
            ruta_matriz = os.path.join(DATASET_LEGACY_DIR, matriz)
            if os.path.isdir(ruta_matriz):
                for subproceso in os.listdir(ruta_matriz):
                    if subproceso == 'processed':
                        continue
                    ruta_sub = os.path.join(ruta_matriz, subproceso)
                    if os.path.isdir(ruta_sub):
                        for nombre in os.listdir(ruta_sub):
                            ruta_clase = os.path.join(ruta_sub, nombre)
                            if os.path.isdir(ruta_clase):
                                archivos = [f for f in os.listdir(ruta_clase) if extension_permitida(f)]
                                if archivos:
                                    inventario_pendientes[nombre] = inventario_pendientes.get(nombre, 0) + len(archivos)

    return inventario_pendientes


def obtener_clases_modelo_universal():
    """Carga y retorna las clases entrenadas en el modelo global universal."""
    ruta_modelo = os.path.join(CEREBROS_DIR, 'modelo_cdc_global.pkl')
    if os.path.exists(ruta_modelo):
        try:
            modelo = joblib.load(ruta_modelo)
            return sorted(list(getattr(modelo, 'classes_', [])))
        except Exception:
            pass

    clases_disco = set()
    if os.path.isdir(DATASET_GLOBAL_DIR):
        clases_disco.update(os.listdir(DATASET_GLOBAL_DIR))

    ruta_proc = os.path.join(DATASET_LEGACY_DIR, 'processed')
    if os.path.isdir(ruta_proc):
        for m in os.listdir(ruta_proc):
            r_m = os.path.join(ruta_proc, m)
            if os.path.isdir(r_m):
                for s in os.listdir(r_m):
                    r_s = os.path.join(r_m, s)
                    if os.path.isdir(r_s):
                        clases_disco.update(os.listdir(r_s))

    return sorted(list(clases_disco))


# Mapa base de procesos estándar según las reglas del negocio bancario
PROCESOS_BASE = {
    'REC DocumentoIdentidad': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW', 'RCL', 'TDC'],
    'REC RIF': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW', 'RCL', 'TDC'],
    'REC ConstanciadeResidencia': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW'],
    'REC ConstanciadeTrabajoy oCertificaciondeIngresos': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW', 'TDC'],
    'REC DeclaracionISLR': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW', 'TDC'],
    'REC ReferenciaBancaria': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW', 'TDC'],
    'REC ReferenciasPersonales': ['ACT', 'AMC', 'CCD', 'CNE', 'CNW', 'TDC'],
    'EXC ContratoDeCuenta': ['CCD', 'CNE', 'CNW'],
    'EXC CartaPreContractual': ['CCD', 'CNE', 'CNW'],
    'EXC ContratoTarjetaDebito': ['CCD', 'CNE', 'CNW'],
    'EXC RegistrodeFirmasCuentas': ['CCD', 'CNE', 'CNW'],
    'EXC PlanillaConocimientoPrevioDelCliente': ['CCD', 'CNE', 'CNW'],
    'EXC FichaIdentificacionCliente': ['CCD', 'CNE', 'CNW'],
    'REC SolicitudAfiliacionPOS': ['PPC'],
    'EXC SolicitudAfiliacionPOS': ['PPC'],
}


def obtener_conocimiento_agrupado_por_tipo():
    """
    Retorna el conocimiento de la IA estructurado por Tipo Documental -> Lista de Procesos en los que aplica.
    Fisiona el mapa base por defecto con los procesos ingresados dinámicamente.
    """
    clases_entrenadas = obtener_clases_modelo_universal()
    mapa_dinamico = _cargar_mapa_procesos()
    resultado = []

    for clase in clases_entrenadas:
        procesos = mapa_dinamico.get(clase, [])
        if not procesos:
            procesos = PROCESOS_BASE.get(clase, [])
            if not procesos:
                if clase.startswith("EXC"):
                    procesos = ["CCD", "CNE", "CNW"]
                elif clase.startswith("REC"):
                    procesos = ["ACT", "AMC", "CCD", "CNE", "CNW", "TDC"]
                else:
                    procesos = ["GLOBAL"]

        resultado.append({
            'clase': clase,
            'procesos': procesos
        })

    return resultado


def obtener_inventario_tipos_documentales():
    return obtener_inventario_pendientes()


def obtener_modelos_conocidos():
    return obtener_conocimiento_agrupado_por_tipo()


def _fuerza_borrado_ruta(ruta):
    if not os.path.exists(ruta):
        return None
        
    import shutil
    
    def _onerror(func, path, exc_info):
        try:
            os.chmod(path, 0o777)
            func(path)
        except Exception:
            pass

    try:
        if os.path.isdir(ruta):
            shutil.rmtree(ruta, onerror=_onerror)
        else:
            try:
                os.chmod(ruta, 0o777)
            except Exception:
                pass
            os.remove(ruta)
    except Exception:
        os.system(f"rm -rf '{ruta}' 2>/dev/null")

    if os.path.exists(ruta):
        os.system(f"rm -rf '{ruta}' 2>/dev/null")

    if os.path.exists(ruta):
        return f"{ruta}: No se pudo eliminar la carpeta por permisos del sistema."

    return None


def borrar_todo_el_conocimiento():
    errores = []
    for carpeta in [CEREBROS_DIR, DATASET_GLOBAL_DIR, DATASET_PENDIENTES_DIR, DATASET_LEGACY_DIR]:
        if os.path.isdir(carpeta):
            for item in os.listdir(carpeta):
                ruta = os.path.join(carpeta, item)
                err = _fuerza_borrado_ruta(ruta)
                if err:
                    errores.append(err)
    if os.path.exists(MAPA_PROCESOS_FILE):
        _fuerza_borrado_ruta(MAPA_PROCESOS_FILE)
    return errores


def borrar_conocimiento_clase_global(clase):
    errores = []
    rutas_a_borrar = [
        os.path.join(DATASET_GLOBAL_DIR, clase),
        os.path.join(DATASET_PENDIENTES_DIR, clase),
    ]
    for matriz in ['BT', 'BR']:
        for base in [DATASET_LEGACY_DIR, os.path.join(DATASET_LEGACY_DIR, 'processed')]:
            mat_path = os.path.join(base, matriz)
            if os.path.isdir(mat_path):
                for sub in os.listdir(mat_path):
                    rutas_a_borrar.append(os.path.join(mat_path, sub, clase))

    for ruta in rutas_a_borrar:
        err = _fuerza_borrado_ruta(ruta)
        if err:
            errores.append(err)

    # Eliminar la clase del archivo JSON de procesos
    mapa = _cargar_mapa_procesos()
    if clase in mapa:
        del mapa[clase]
        _guardar_mapa_procesos_file(mapa)

    return errores


def descartar_subida_clase_global(clase):
    errores = []
    r = os.path.join(DATASET_PENDIENTES_DIR, clase)
    err = _fuerza_borrado_ruta(r)
    if err:
        errores.append(err)
    return errores


def borrar_conocimiento_proceso(matriz, proceso):
    return []


def borrar_conocimiento_clase(matriz, proceso, clase):
    return borrar_conocimiento_clase_global(clase)


def descartar_subida_clase(matriz, proceso, clase):
    return descartar_subida_clase_global(clase)
