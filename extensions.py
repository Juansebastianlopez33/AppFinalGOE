# extensions.py (CORREGIDO - AHORA MANEJA EL ERROR "ALREADY CLOSED")
from flask import Flask, g, current_app 
from flask_bcrypt import Bcrypt
import redis
import os
import sys
from flask_socketio import SocketIO
import pymysql # ✅ NUEVA IMPORTACIÓN
import pymysql.cursors # ✅ NUEVA IMPORTACIÓN
import pymysql.err # 👈 Importación necesaria para manejar la excepción

# ❌ REMOVER: mysql = MySQL()
bcrypt = Bcrypt()
redis_client = None 
socketio = SocketIO(cors_allowed_origins="*")

# ===============================================
# ✅ FUNCIONES PARA LA GESTIÓN DE CONEXIÓN PyMySQL
# ===============================================

def get_db():
    """Obtiene una conexión a la base de datos (PyMySQL), creando una si no existe."""
    if 'db' not in g:
        try:
            # Reutiliza la configuración de Flask
            config = {
                "host": current_app.config['MYSQL_HOST'],
                "user": current_app.config['MYSQL_USER'],
                "password": current_app.config['MYSQL_PASSWORD'],
                "database": current_app.config['MYSQL_DB'],
                "charset": current_app.config['MYSQL_CHARSET'],
                # Usar DictCursor por defecto para que las consultas devuelvan diccionarios
                "cursorclass": pymysql.cursors.DictCursor 
            }
            
            # Lógica para SSL con TiDB Cloud
            basedir = os.path.abspath(os.path.dirname(__file__))
            tidb_ca = os.path.join(basedir, "certs", "isrgrootx1.pem")

            if 'tidbcloud.com' in current_app.config['MYSQL_HOST'] and os.path.exists(tidb_ca):
                config["ssl"] = {"ca": tidb_ca}

            g.db = pymysql.connect(**config)
        except Exception as e:
            print(f"ERROR: Fallo al conectar a la base de datos con PyMySQL: {e}", file=sys.stderr)
            # Asegúrate de propagar el error si la conexión falla completamente
            raise e
    return g.db

def close_db(e=None):
    """
    Cierra la conexión a la base de datos si existe. 
    Maneja el error 'Already closed' que ocurre si PyMySQL cerró la conexión
    automáticamente después de un error de SQL.
    """
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except pymysql.err.Error as error:
            # Captura y maneja el error 'Already closed'
            if "Already closed" not in str(error):
                # Si es otro error, lo relanza (para no ocultar problemas reales)
                raise
            # Si es 'Already closed', simplemente ignoramos la excepción.
            print("INFO: Conexión PyMySQL ya estaba cerrada. Ignorando 'Already closed' en teardown.", file=sys.stderr)


# ===============================================

def init_app(app: Flask):
    # ❌ REMOVER: mysql.init_app(app)
    bcrypt.init_app(app)
    
    # ✅ REGISTRAR la función para que se ejecute después de cada solicitud
    app.teardown_appcontext(close_db) 

    # Configuración de SocketIO y Redis (sin cambios)
    app.config['SOCKETIO_MESSAGE_QUEUE'] = app.config.get('REDIS_URL')
    socketio.init_app(app)

    global redis_client
    # ... (Lógica de conexión a Redis, sin cambios) ...
    try:
        redis_url = app.config.get('REDIS_URL') or os.getenv('REDIS_URL')
        if redis_url:
            # 🚀 Render u otra instancia con URL completa
            redis_client = redis.StrictRedis.from_url(redis_url, decode_responses=True)
            print(f"INFO: Conectando a Redis mediante URL: {redis_url}")
        else:
            # 🚀 Local con Docker Compose
            redis_host = app.config.get('REDIS_HOST', os.getenv('REDIS_HOST', 'localhost'))
            redis_port = int(app.config.get('REDIS_PORT', os.getenv('REDIS_PORT', 6379)))
            redis_db = int(app.config.get('REDIS_DB', os.getenv('REDIS_DB', 0)))
            redis_client = redis.StrictRedis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True
            )
            print(f"INFO: Conectando a Redis en {redis_host}:{redis_port}/{redis_db}")
            
        redis_client.ping()
        print("INFO: ✅ Conectado exitosamente a Redis!")
    except Exception as e:
        redis_client = None
        print(f"ERROR: Fallo al conectar a Redis: {e}", file=sys.stderr)
        # Esto no es fatal si la app no depende fuertemente de Redis.
        # En tu caso, es necesario para SocketIO y rate limiting.
        if app.config.get('REDIS_URL'):
             print("ADVERTENCIA: Si usas SocketIO con REDIS_URL, la cola de mensajes podría fallar.", file=sys.stderr)
