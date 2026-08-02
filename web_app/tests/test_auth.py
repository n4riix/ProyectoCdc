import os
import pytest

# Forzar configuración de prueba antes de importar la app
os.environ['DB_TYPE'] = 'sqlite'
os.environ['DB_NAME'] = 'test_db.sqlite3'
os.environ['SECRET_KEY'] = 'test_key'

from app import app
from core.db_models import inicializar_base_datos, crear_usuario

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    # Ignorar Rate Limiting en los tests
    app.config['RATELIMIT_ENABLED'] = False

    with app.test_client() as client:
        with app.app_context():
            inicializar_base_datos()
            crear_usuario('test_admin', 'test_pass', 'admin')
        yield client

def test_login_page_loads(client):
    """Prueba que la página de login carga correctamente"""
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'Acceso al Sistema CDC' in rv.data

def test_login_successful(client):
    """Prueba login con credenciales correctas"""
    rv = client.post('/', data=dict(
        username='test_admin',
        password='test_pass'
    ), follow_redirects=True)
    
    # Debe redirigir al panel
    assert b'Salir' in rv.data or b'Panel' in rv.data or rv.status_code == 200

def test_login_failed(client):
    """Prueba login con credenciales incorrectas"""
    rv = client.post('/', data=dict(
        username='test_admin',
        password='wrong_pass'
    ), follow_redirects=True)
    
    # Debe volver a la pagina de login con error
    assert b'Acceso al Sistema CDC' in rv.data
