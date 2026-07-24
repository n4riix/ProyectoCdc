import os
import shutil
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.utils import secure_filename
import csv
import io

# --- IMPORTACIONES DE TU NÚCLEO (CORE) ---
from core.db_models import inicializar_base_datos, verificar_usuario, set_estado, get_estado, listar_usuarios, crear_usuario, eliminar_usuario
from core.inventory import obtener_inventario_tipos_documentales, obtener_modelos_conocidos, extension_permitida, borrar_todo_el_conocimiento, borrar_conocimiento_proceso, borrar_conocimiento_clase

# ==========================================
# 1. CONFIGURACIÓN DE CARPETAS Y LOGS
# ==========================================
base_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(base_dir, '..', 'volumen_compartido', 'logs')
os.makedirs(log_dir, exist_ok=True) # Crea la carpeta si no existe

log_file = os.path.join(log_dir, 'intexus_auditor.log')

# Definimos cómo se verá cada línea (Fecha, Hora, Nivel de Alerta, Mensaje)
formato_log = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Manejador 1: Escribe en el archivo de texto (Máximo 5MB por archivo, guarda 3 históricos)
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setFormatter(formato_log)

# Manejador 2: Imprime en la consola de Docker (para que sigamos viéndolo en vivo)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formato_log)

# Configuramos el registrador principal
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Silenciamos un poco el ruido de Flask para que no ensucie nuestra bitácora
logging.getLogger('werkzeug').setLevel(logging.WARNING)
# --- FIN CONFIGURACIÓN DE LOGS ---

app = Flask(__name__)

# ==========================================
# 2. INICIALIZACIÓN DE FLASK Y SEGURIDAD
# ==========================================
# Obtenemos la llave inyectada por Docker (.env)
app.secret_key = os.environ.get('SECRET_KEY')

# Blindaje: Si no hay llave, detenemos el sistema por seguridad
if not app.secret_key:
    raise ValueError("🚨 ¡ALERTA DE SEGURIDAD! Falta la variable SECRET_KEY en el entorno.")

with app.app_context():
    inicializar_base_datos()

# ==========================================
# 3. MIDDLEWARE DE SEGURIDAD (Rutas Protegidas)
# ==========================================
def login_requerido(f):
    def wrap(*args, **kwargs):
        if 'usuario' not in session:
            flash("Por favor, inicia sesión primero.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# ==========================================
# 4. RUTAS PRINCIPALES Y DE AUDITORÍA
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        rol = verificar_usuario(username, password)
        if rol:
            session['usuario'] = username
            session['rol'] = rol
            return redirect(url_for('dashboard'))
        else:
            flash("Usuario o contraseña incorrectos.", "danger")
            
    return render_template('login.html')

@app.route('/dashboard')
@login_requerido
def dashboard():
    modelos_conocidos = obtener_modelos_conocidos()
    return render_template('dashboard.html', usuario=session['usuario'], rol=session['rol'], modelos_conocidos=modelos_conocidos)

@app.route('/conocimiento')
@login_requerido
def conocimiento():
    modelos_conocidos = obtener_modelos_conocidos()
    return render_template(
        'conocimiento.html',
        usuario=session['usuario'],
        rol=session['rol'],
        modelos_conocidos=modelos_conocidos
    )

from core.auditor import procesar_lote_kofax_task
from core.db_models import obtener_estado_lote, obtener_resultados_lote, listar_lotes_auditoria
import uuid

@app.route('/api/estado_auditoria/<task_id>', methods=['GET'])
@login_requerido
def api_estado_auditoria(task_id):
    estado = obtener_estado_lote(task_id)
    if not estado:
        return jsonify({"archivo": "No encontrado", "procesados": 0, "meta": 0, "estado": "error"})
    
    # Intentar obtener el progreso actual desde Celery si la tarea sigue activa
    from celery_app import celery
    task = celery.AsyncResult(task_id)
    archivo_actual = "Iniciando..."
    if task.state == 'PROGRESS':
        archivo_actual = task.info.get('archivo', 'Procesando...')
    elif estado['estado'] == 'completado':
        archivo_actual = "Completado"
    
    return jsonify({
        "archivo": archivo_actual,
        "procesados": estado['documentos_procesados'],
        "meta": estado['total_documentos'],
        "estado": estado['estado']
    })

@app.route('/api/auditar_lote', methods=['POST'])
@login_requerido
def api_auditar_lote():
    task_id = str(uuid.uuid4())
    procesar_lote_kofax_task.apply_async(args=[task_id], task_id=task_id)
    return jsonify({"status": "Lote enviado a procesamiento en segundo plano", "task_id": task_id})

@app.route('/api/auditoria_resultados/<task_id>', methods=['GET'])
@login_requerido
def api_auditoria_resultados(task_id):
    resultados = obtener_resultados_lote(task_id)
    estado = obtener_estado_lote(task_id)
    return jsonify({"resultados": resultados, "lote": estado})

@app.route('/api/historial_lotes', methods=['GET'])
@login_requerido
def api_historial_lotes():
    lotes = listar_lotes_auditoria()
    return jsonify(lotes)

@app.route('/api/descargar_reporte/<task_id>', methods=['GET'])
@login_requerido
def api_descargar_reporte(task_id):
    """Genera y descarga un CSV con todos los resultados de la auditoría."""
    resultados = obtener_resultados_lote(task_id)
    estado = obtener_estado_lote(task_id)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Línea', 'Archivo', 'Matriz', 'Subproceso', 'Tipo Esperado (Cdc)', 'Predicción IA', 'Confianza %', 'Veredicto'])
    
    for r in resultados:
        veredicto_texto = 'COINCIDE' if r['estado'] == 'success' else ('NO ENTRENADO' if r['estado'] == 'warning' else 'DISCREPANCIA')
        confianza_val = r.get('confianza', '')
        writer.writerow([r.get('linea_indice', ''), r['archivo'], r.get('matriz', ''), r.get('subproceso', ''), r.get('esperado', ''), r.get('prediccion', ''), confianza_val, veredicto_texto])
    
    output.seek(0)
    bytes_output = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    
    fecha = estado['fecha_inicio'][:10] if estado and estado.get('fecha_inicio') else 'sin_fecha'
    nombre_archivo = f'Reporte_Auditoria_{fecha}_{task_id[:8]}.csv'
    
    return send_file(bytes_output, mimetype='text/csv', as_attachment=True, download_name=nombre_archivo)

@app.route('/api/imagen/<path:nombre_archivo>', methods=['GET'])
@login_requerido
def api_previsualizar_imagen(nombre_archivo):
    """Sirve una imagen del lote para previsualización en el navegador (convirtiendo TIF a JPEG si es necesario)."""
    lote_dir = '/volumen_compartido/lote_kofax'
    ruta = os.path.join(lote_dir, nombre_archivo)
    if not os.path.exists(ruta):
        return jsonify({"error": "Archivo no encontrado"}), 404
        
    try:
        from PIL import Image
        img = Image.open(ruta)
        # Convert to RGB (to handle CMYK, palettes, or TIFF specifics)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=85)
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    except Exception as e:
        logging.error(f"Error convirtiendo imagen {ruta}: {e}")
        return jsonify({"error": "No se pudo procesar la imagen"}), 500

@app.route('/api/discrepancias/<task_id>', methods=['GET'])
@login_requerido
def api_discrepancias(task_id):
    """Devuelve solo las filas con discrepancias para revisión manual."""
    resultados = obtener_resultados_lote(task_id)
    discrepancias = [r for r in resultados if r['estado'] == 'danger']
    return jsonify({"discrepancias": discrepancias})

@app.route('/api/aplicar_correcciones/<task_id>', methods=['POST'])
@login_requerido
def api_aplicar_correcciones(task_id):
    """Aplica solo las correcciones aprobadas por el usuario al archivo Indice_*.txt."""
    import glob
    data = request.get_json()
    correcciones_aprobadas = data.get('correcciones', [])  # Lista de {linea_indice, nuevo_valor}
    
    if not correcciones_aprobadas:
        return jsonify({"error": "No se recibieron correcciones para aplicar."}), 400
    
    lote_dir = '/volumen_compartido/lote_kofax'
    archivos_indice = glob.glob(os.path.join(lote_dir, 'Indice_*.txt'))
    if not archivos_indice:
        return jsonify({"error": "No se encontró el archivo Indice_*.txt."}), 404
    
    indice_path = archivos_indice[0]
    
    # Leer todas las líneas del archivo original
    with open(indice_path, 'r', encoding='utf-8', errors='ignore') as f:
        lineas = f.readlines()
    
    # Crear un diccionario de correcciones aprobadas {linea: nuevo_valor}
    mapa_correcciones = {int(c['linea_indice']): c['nuevo_valor'] for c in correcciones_aprobadas}
    
    # Aplicar los cambios
    cambios_aplicados = 0
    for num_linea, nuevo_valor in mapa_correcciones.items():
        if 1 <= num_linea <= len(lineas):
            linea_original = lineas[num_linea - 1]
            # Parseamos la línea como CSV para modificar solo el campo 14 (Tipo Documental)
            reader = csv.reader(io.StringIO(linea_original))
            for partes in reader:
                if len(partes) >= 16:
                    partes[14] = nuevo_valor
                    # Reconstruimos la línea
                    output_line = io.StringIO()
                    writer = csv.writer(output_line)
                    writer.writerow(partes)
                    lineas[num_linea - 1] = output_line.getvalue()
                    cambios_aplicados += 1
    
    # Escribir de vuelta
    with open(indice_path, 'w', encoding='utf-8', newline='') as f:
        f.writelines(lineas)
    
    logging.info(f"[AUDITOR] {session['usuario']} aplicó {cambios_aplicados} correcciones al índice.")
    return jsonify({"mensaje": f"Se aplicaron {cambios_aplicados} correcciones al archivo índice.", "cambios": cambios_aplicados})

# ==========================================
# 5. RUTAS DE ADMINISTRACIÓN Y ENTRENAMIENTO
# ==========================================
@app.route('/admin')
@login_requerido
def admin():
    if session['rol'] not in ('admin', 'superadmin'):
        flash("Acceso denegado. Módulo exclusivo para Administradores.", "danger")
        return redirect(url_for('dashboard'))

    inventario = obtener_inventario_tipos_documentales()
    modelos_conocidos = obtener_modelos_conocidos()

    return render_template(
        'admin.html',
        usuario=session['usuario'],
        rol=session['rol'],
        inventario=inventario,
        modelos_conocidos=modelos_conocidos
    )

@app.route('/admin/subir_documentos', methods=['POST'])
@login_requerido
def subir_documentos():
    if session['rol'] not in ('admin', 'superadmin'):
        return redirect(url_for('dashboard'))

    matriz = secure_filename(request.form.get('matriz', '').strip())
    subproceso_raw = request.form.get('subproceso', '').strip().upper()
    clase_doc = request.form.get('clase_documento', '').strip()
    archivos = request.files.getlist('archivos')

    # Separar subprocesos por coma y limpiarlos
    lista_subprocesos = [secure_filename(sp.strip()) for sp in subproceso_raw.split(',') if sp.strip()]

    if not matriz or not lista_subprocesos or not clase_doc or not archivos:
        flash("Todos los campos son obligatorios", "danger")
        return redirect(url_for('admin'))

    clase_doc_segura = secure_filename(clase_doc).replace("_", " ")
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Pre-leer archivos válidos en memoria (para poder guardarlos múltiples veces)
    archivos_validos = []
    invalidos = 0
    for archivo in archivos:
        if archivo.filename:
            filename = secure_filename(archivo.filename)
            if extension_permitida(filename):
                archivos_validos.append((filename, archivo.read()))
            else:
                invalidos += 1

    guardados = 0
    for sp in lista_subprocesos:
        ruta_destino = os.path.join(base_dir, '..', 'volumen_compartido', 'dataset_entrenamiento', matriz, sp, clase_doc_segura)
        os.makedirs(ruta_destino, exist_ok=True)
        
        for filename, datos in archivos_validos:
            ruta_archivo = os.path.join(ruta_destino, filename)
            with open(ruta_archivo, 'wb') as f:
                f.write(datos)
            guardados += 1

    subprocesos_str = ", ".join(lista_subprocesos)
    mensaje = f"✅ Éxito: Se guardaron {guardados} archivos en total para los subprocesos [{subprocesos_str}] en la categoría '{clase_doc_segura}'."
    if invalidos:
        mensaje += f" ({invalidos} archivo(s) inválido(s) omitido(s). Use TIF, PDF, JPG o PNG)."

    flash(mensaje, "success")
    return redirect(url_for('admin'))

@app.route('/admin/entrenar', methods=['POST'])
@login_requerido
def entrenar_modelos():
    if session['rol'] not in ('admin', 'superadmin'):
        return jsonify({"error": "No autorizado"}), 403
    
    set_estado('progreso_entrenamiento', '0')
    set_estado('entrenamiento', 'PROCESANDO')

    return jsonify({"mensaje": "Orden enviada correctamente"})

@app.route('/admin/estado_entrenamiento')
@login_requerido
def estado_entrenamiento():
    estado = get_estado('entrenamiento', 'listo').lower()
    progreso = get_estado('progreso_entrenamiento', '0')
    try:
        progreso = int(progreso)
    except:
        progreso = 0
    return jsonify({"estado": estado, "progreso": progreso})

@app.route('/admin/refresh_inventario')
@login_requerido
def refresh_inventario():
    """Retorna el inventario y los modelos conocidos en JSON para actualización parcial del UI."""
    inventario = obtener_inventario_tipos_documentales()
    modelos = obtener_modelos_conocidos()
    return jsonify({
        'inventario': inventario,
        'modelos': modelos
    })

# ==========================================
# 6. RUTAS DE SUPERADMINISTRADOR
# ==========================================
@app.route('/superadmin')
@login_requerido
def superadmin():
    if session['rol'] != 'superadmin':
        flash("Acceso denegado. Módulo exclusivo para Superadministradores.", "danger")
        return redirect(url_for('dashboard'))
    modelos_conocidos = obtener_modelos_conocidos()
    usuarios = listar_usuarios()
    return render_template(
        'superadmin.html',
        usuario=session['usuario'],
        rol=session['rol'],
        modelos_conocidos=modelos_conocidos,
        usuarios=usuarios
    )

@app.route('/superadmin/borrar_todo', methods=['POST'])
@login_requerido
def borrar_todo():
    if session['rol'] != 'superadmin':
        flash("Acceso denegado.", "danger")
        return redirect(url_for('dashboard'))
    errores = borrar_todo_el_conocimiento()
    if errores:
        flash(f"⚠️ Borrado completado con advertencias: {'; '.join(errores)}", "warning")
    else:
        flash("✅ Todos los conocimientos de la IA han sido eliminados exitosamente.", "success")
    logging.info(f"[SUPERADMIN] {session['usuario']} ejecutó BORRADO TOTAL de conocimientos.")
    return redirect(url_for('superadmin'))

@app.route('/superadmin/borrar_proceso', methods=['POST'])
@login_requerido
def borrar_proceso():
    if session['rol'] != 'superadmin':
        flash("Acceso denegado.", "danger")
        return redirect(url_for('dashboard'))
    matriz = secure_filename(request.form.get('matriz', '').strip())
    proceso = secure_filename(request.form.get('proceso', '').strip())
    if not matriz or not proceso:
        flash("Parámetros inválidos.", "danger")
        return redirect(url_for('superadmin'))
    errores = borrar_conocimiento_proceso(matriz, proceso)
    nombre_matriz = 'Natural' if matriz == 'BT' else ('Jurídico' if matriz == 'BR' else matriz)
    if errores:
        flash(f"⚠️ Proceso {proceso} ({nombre_matriz}) borrado con advertencias: {'; '.join(errores)}", "warning")
    else:
        flash(f"✅ Proceso {proceso} ({nombre_matriz}) eliminado exitosamente.", "success")
    logging.info(f"[SUPERADMIN] {session['usuario']} borró proceso {matriz}/{proceso}.")
    return redirect(url_for('superadmin'))

@app.route('/superadmin/borrar_clase', methods=['POST'])
@login_requerido
def borrar_clase():
    if session['rol'] != 'superadmin':
        flash("Acceso denegado.", "danger")
        return redirect(url_for('dashboard'))
    matriz = secure_filename(request.form.get('matriz', '').strip())
    proceso = secure_filename(request.form.get('proceso', '').strip())
    clase = secure_filename(request.form.get('clase', '').strip())
    if not matriz or not proceso or not clase:
        flash("Parámetros inválidos.", "danger")
        return redirect(url_for('superadmin'))
    errores = borrar_conocimiento_clase(matriz, proceso, clase)
    nombre_matriz = 'Natural' if matriz == 'BT' else ('Jurídico' if matriz == 'BR' else matriz)
    if errores:
        flash(f"⚠️ Clase '{clase}' del proceso {proceso} ({nombre_matriz}) borrada con advertencias: {'; '.join(errores)}", "warning")
    else:
        flash(f"✅ Clase '{clase}' del proceso {proceso} ({nombre_matriz}) eliminada. Recuerda re-entrenar la IA.", "success")
    logging.info(f"[SUPERADMIN] {session['usuario']} borró clase {clase} de {matriz}/{proceso}.")
    return redirect(url_for('superadmin'))

@app.route('/superadmin/crear_usuario', methods=['POST'])
@login_requerido
def crear_usuario_route():
    if session['rol'] != 'superadmin':
        flash("Acceso denegado.", "danger")
        return redirect(url_for('dashboard'))
    username = request.form.get('nuevo_username', '').strip()
    password = request.form.get('nuevo_password', '').strip()
    rol = request.form.get('nuevo_rol', '').strip()
    exito, mensaje = crear_usuario(username, password, rol)
    if exito:
        flash(f"✅ {mensaje}", "success")
        logging.info(f"[SUPERADMIN] {session['usuario']} creó usuario '{username}' con rol '{rol}'.")
    else:
        flash(f"❌ {mensaje}", "danger")
    return redirect(url_for('superadmin'))

@app.route('/superadmin/eliminar_usuario', methods=['POST'])
@login_requerido
def eliminar_usuario_route():
    if session['rol'] != 'superadmin':
        flash("Acceso denegado.", "danger")
        return redirect(url_for('dashboard'))
    user_id = request.form.get('user_id', '').strip()
    if not user_id:
        flash("ID de usuario inválido.", "danger")
        return redirect(url_for('superadmin'))
    exito, mensaje = eliminar_usuario(int(user_id), session['usuario'])
    if exito:
        flash(f"✅ {mensaje}", "success")
        logging.info(f"[SUPERADMIN] {session['usuario']} eliminó usuario ID {user_id}.")
    else:
        flash(f"❌ {mensaje}", "danger")
    return redirect(url_for('superadmin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)