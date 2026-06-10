from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from core.db_models import inicializar_base_datos, verificar_usuario
from werkzeug.utils import secure_filename
import os

# Importamos nuestro nuevo motor auditor
from core.auditor import procesar_lote_kofax

app = Flask(__name__)
app.secret_key = 'cdc_banco_secreto_super_seguro' 

with app.app_context():
    inicializar_base_datos()

# --- MIDDLEWARE DE SEGURIDAD ---
def login_requerido(f):
    def wrap(*args, **kwargs):
        if 'usuario' not in session:
            flash("Por favor, inicia sesión primero.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- RUTAS PRINCIPALES ---
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

# --- RUTA PARA EJECUTAR LA AUDITORÍA DE KOFAX ---
@app.route('/api/auditar_lote', methods=['POST'])
@login_requerido
def api_auditar_lote():
    # Esta es la ruta que llama al archivo auditor.py cuando presionas el botón verde
    respuesta = procesar_lote_kofax()
    return jsonify(respuesta)

# --- RUTAS DE ADMINISTRACIÓN Y ENTRENAMIENTO ---
@app.route('/admin')
@login_requerido
def admin():
    if session['rol'] != 'admin':
        flash("Acceso denegado. Módulo exclusivo para Administradores.", "danger")
        return redirect(url_for('dashboard'))
    return render_template('admin.html', usuario=session['usuario'], rol=session['rol'])

@app.route('/admin/subir_documentos', methods=['POST'])
@login_requerido
def subir_documentos():
    if session['rol'] != 'admin':
        return redirect(url_for('dashboard'))

    matriz = request.form.get('matriz')
    subproceso = request.form.get('subproceso').strip().upper()
    clase_doc = request.form.get('clase_documento').strip()
    archivos = request.files.getlist('archivos')

    if not matriz or not subproceso or not clase_doc or not archivos:
        flash("Todos los campos son obligatorios", "danger")
        return redirect(url_for('admin'))

    clase_doc_segura = secure_filename(clase_doc).replace("_", " ")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ruta_destino = os.path.join(base_dir, '..', 'volumen_compartido', 'dataset_entrenamiento', matriz, subproceso, clase_doc_segura)

    os.makedirs(ruta_destino, exist_ok=True)

    guardados = 0
    for archivo in archivos:
        if archivo.filename:
            filename = secure_filename(archivo.filename)
            archivo.save(os.path.join(ruta_destino, filename))
            guardados += 1

    flash(f"✅ Éxito: Se guardaron {guardados} archivos en la categoría '{clase_doc_segura}'.", "success")
    return redirect(url_for('admin'))

@app.route('/admin/entrenar', methods=['POST'])
@login_requerido
def entrenar_modelos():
    if session['rol'] != 'admin':
        return jsonify({"error": "No autorizado"}), 403
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ruta_flag = os.path.join(base_dir, '..', 'volumen_compartido', 'orden_entrenar.flag')
    
    with open(ruta_flag, 'w') as f:
        f.write("DESPERTAR_IA")

    return jsonify({"mensaje": "Orden enviada correctamente"})

@app.route('/admin/estado_entrenamiento')
@login_requerido
def estado_entrenamiento():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ruta_flag = os.path.join(base_dir, '..', 'volumen_compartido', 'orden_entrenar.flag')
    ruta_lock = os.path.join(base_dir, '..', 'volumen_compartido', 'entrenando.lock')
    
    if os.path.exists(ruta_flag) or os.path.exists(ruta_lock):
        return jsonify({"estado": "procesando"})
    else:
        return jsonify({"estado": "listo"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)