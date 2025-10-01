# extensions.py
from flask import Flask
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
import redis
import os
import sys
from flask_socketio import SocketIO

mysql = MySQL()
bcrypt = Bcrypt()
redis_client = None # Variable global para el cliente Redis

# Inicializamos SocketIO sin message_queue aquí.
# Lo configuraremos dentro de init_app para que pueda leer de app.config.
socketio = SocketIO(cors_allowed_origins="*")

def init_app(app: Flask):
    mysql.init_app(app)
    bcrypt.init_app(app)

    # ¡CAMBIO CLAVE! Configura el message_queue de SocketIO usando app.config['REDIS_URL']
    # Esto asegura que usa la URL correcta que viene de Docker Compose.
    app.config['SOCKETIO_MESSAGE_QUEUE'] = app.config['REDIS_URL']
    socketio.init_app(app)

    global redis_client
    # Obtiene detalles de conexión de Redis de variables de entorno o configuración de la app
    redis_host = app.config.get('REDIS_HOST', os.getenv('REDIS_HOST', 'localhost'))
    redis_port = int(app.config.get('REDIS_PORT', os.getenv('REDIS_PORT', 6379)))
    redis_db = int(app.config.get('REDIS_DB', os.getenv('REDIS_DB', 0)))

   try:
    redis_url = app.config.get('REDIS_URL') or os.getenv('REDIS_URL')
    if redis_url:
        # Conectar usando URL completa (ideal para Render)
        redis_client = redis.StrictRedis.from_url(redis_url, decode_responses=True)
    else:
        # Fallback: conectar usando host/port/db (ideal para Docker local)
        redis_host = app.config.get('REDIS_HOST', os.getenv('REDIS_HOST', 'localhost'))
        redis_port = int(app.config.get('REDIS_PORT', os.getenv('REDIS_PORT', 6379)))
        redis_db   = int(app.config.get('REDIS_DB', os.getenv('REDIS_DB', 0)))
        redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

    # Probar conexión
    redis_client.ping()
    print("INFO: Conectado exitosamente a Redis!")

    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: No se pudo conectar a Redis: {e}", file=sys.stderr)
        redis_client = None

