import eventlet  # ¡NUEVA IMPORTACIÓN!
eventlet.monkey_patch()  # ¡NUEVA LÍNEA! Esto debe ir al principio

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
from extensions import mysql, bcrypt, socketio, init_app as inicializar_extensiones
import os
from datetime import timedelta
from flask_jwt_extended import JWTManager
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError as JWTExpiredSignatureError, DecodeError
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, exceptions as jwt_exceptions 
import sys
import traceback
from dotenv import load_dotenv
from threading import Timer, Lock
from flask_socketio import join_room, leave_room, emit

load_dotenv()

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

# ================== MYSQL ==================
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'flask_api')
app.config['MYSQL_CHARSET'] = 'utf8mb4'

basedir = os.path.abspath(os.path.dirname(__file__))

# 🔑 Forzar SSL si se conecta a TiDB Cloud
if "tidbcloud.com" in app.config['MYSQL_HOST']:
    app.config['MYSQL_CLIENT_FLAGS'] = [2048]  # 2048 = CLIENT_SSL
    app.config['MYSQL_SSL'] = {
        "ca": os.path.join(basedir, "certs", "isrgrootx1.pem")
    }

# ================== EMAIL ==================
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USER')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASS')
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

# ================== JWT ==================
app.config["JWT_SECRET_KEY"] = os.getenv('JWT_SECRET_KEY', 'super-secreto-jwt')
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

jwt = JWTManager(app)

# ====================================================================================================
# Manejadores de Errores JWT
# ====================================================================================================

@app.errorhandler(jwt_exceptions.NoAuthorizationError)
def handle_auth_error(e):
    print(f"ERROR: Fallo de autorización - {e}", file=sys.stderr)
    return jsonify({
        "verificado": False,
        "message": "Falta el encabezado de autorización o el token es inválido."
    }), 401

@app.errorhandler(JWTExpiredSignatureError)
def handle_expired_error(e):
    print(f"ERROR: Fallo de token expirado - {e}", file=sys.stderr)
    return jsonify({
        "verificado": False,
        "message": "El token ha expirado."
    }), 401

@app.errorhandler(500)
def handle_500_error(e):
    print(f"ERROR: Un error interno del servidor ocurrió: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr) # Imprime el stack trace completo
    return jsonify({
        "verificado": False,
        "message": "Un error interno del servidor ha ocurrido. Por favor, inténtelo de nuevo más tarde."
    }), 500

# ====================================================================================================

# ¡NUEVO! Manejador para solicitudes OPTIONS para CORS Preflight
@app.before_request
def handle_options_requests():
    if request.method == 'OPTIONS':
        return '', 200

# ================== RUTAS PARA UPLOADS ==================
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, UPLOAD_FOLDER)

os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'fotos_perfil'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'publicaciones'), exist_ok=True)

PDF_FOLDER = 'pdfs'
app.config['PDF_FOLDER'] = os.path.join(basedir, PDF_FOLDER)

os.makedirs(app.config['PDF_FOLDER'], exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

app.config['API_BASE_URL'] = os.getenv('API_BASE_URL', 'http://localhost:5000')
app.config['REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# ================== INICIALIZAR EXTENSIONES ==================
inicializar_extensiones(app)

# ================== RUTAS PARA ARCHIVOS ==================
@app.route('/uploads/fotos_perfil/<username>/<filename>')
def uploaded_profile_picture(username, filename):
    profile_picture_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos_perfil', username)
    return send_from_directory(profile_picture_folder, filename)

@app.route('/uploads/publicaciones/<int:publicacion_id>/<filename>')
def uploaded_publication_image(publicacion_id, filename):
    publication_images_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'publicaciones', str(publicacion_id))
    try:
        return send_from_directory(publication_images_folder, filename)
    except Exception as e:
        print(f"ERROR: No se pudo servir la imagen '{filename}' de la publicación '{publicacion_id}': {e}", file=sys.stderr)
        return jsonify({"error": "Imagen no encontrada."}), 404

@app.route('/uploads/<username>/<filename>')
def uploaded_file_legacy(username, filename):
    user_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
    return send_from_directory(user_upload_folder, filename)

@app.route('/uploads/<filename>')
def uploaded_general_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ================== BLUEPRINTS ==================
from routes.auth import auth_bp
from routes.user import user_bp
from support import support_bp
from pdf_routes import pdf_bp
from routes.blog import blog_bp
from routes.auth_juego import auth_juego_bp

app.register_blueprint(auth_bp)
app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(support_bp)
app.register_blueprint(pdf_bp)
app.register_blueprint(blog_bp, url_prefix='/blog')
app.register_blueprint(auth_juego_bp, url_prefix='/auth_juego')

# ================== BATCH DE PUBLICACIONES ==================
batched_publication_updates = {}
batched_publication_updates_lock = Lock()
BATCH_INTERVAL = 15

def emit_batched_updates():
    with batched_publication_updates_lock:
        if batched_publication_updates:
            updates_to_send = list(batched_publication_updates.values())
            print(f"DEBUG APP: Emitiendo {len(updates_to_send)} actualizaciones de publicaciones por batch.", file=sys.stderr)
            socketio.emit('batched_publication_updates', updates_to_send, namespace='/', room='/')
            batched_publication_updates.clear()

    global batch_timer
    batch_timer = Timer(BATCH_INTERVAL, emit_batched_updates)
    batch_timer.daemon = True
    batch_timer.start()

def add_to_publication_batch(publication_data):
    with batched_publication_updates_lock:
        batched_publication_updates[publication_data['id']] = publication_data

app.add_to_publication_batch = add_to_publication_batch

global batch_timer
batch_timer = Timer(BATCH_INTERVAL, emit_batched_updates)
batch_timer.daemon = True
batch_timer.start()

# ================== SOCKET.IO EVENTS ==================
@socketio.on('connect')
def test_connect():
    print('Cliente conectado a Socket.IO')

@socketio.on('disconnect')
def test_disconnect():
    print('Cliente desconectado de Socket.IO')

@socketio.on('join_room')
def on_join(data):
    room = data['room']
    join_room(room)
    print(f"Cliente unido a la sala: {room}")

@socketio.on('leave_room')
def on_leave(data):
    room = data['room']
    leave_room(room)
    print(f"Cliente salió de la sala: {room}")

# ================== RUN ==================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render asigna $PORT
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
