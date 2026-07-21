import os
import shutil
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename

# --- IMPORTACIONES DE TU NÚCLEO (CORE) ---
from core.db_models import inicializar_base_datos, verificar_usuario, set_estado, get_estado
from core.inventory import obtener_inventario_tipos_documentales, obtener_modelos_conocidos, extension_permitida
from core.auditor import procesar_lote_kofax

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
    return render_template('dashboard.html', usuario=session['usuario'], rol=session['rol'])

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

@app.route('/api/auditar_lote', methods=['POST'])
@login_requerido
def api_auditar_lote():
    # Esta es la ruta que llama al archivo auditor.py cuando presionas el botón verde
    respuesta = procesar_lote_kofax()
    return jsonify(respuesta)

# ==========================================
# 5. RUTAS DE ADMINISTRACIÓN Y ENTRENAMIENTO
# ==========================================
@app.route('/admin')
@login_requerido
def admin():
    if session['rol'] != 'admin':
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
    if session['rol'] != 'admin':
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
    if session['rol'] != 'admin':
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)