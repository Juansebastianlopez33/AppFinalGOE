# extensions.py (MODIFICADO)
from flask import Flask, g, current_app # ✅ AÑADIDO 'g', 'current_app'
# ❌ REMOVER: from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
import redis
import os
import sys
from flask_socketio import SocketIO
import pymysql # ✅ NUEVA IMPORTACIÓN
import pymysql.cursors # ✅ NUEVA IMPORTACIÓN

# ❌ REMOVER: mysql = MySQL()
bcrypt = Bcrypt()
redis_client = None  # Variable global para el cliente Redis
socketio = SocketIO(cors_allowed_origins="*")

# ===============================================
# ✅ NUEVAS FUNCIONES PARA LA GESTIÓN DE CONEXIÓN PyMySQL
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
            
            # Lógica para SSL/TiDB Cloud
            basedir = os.path.abspath(os.path.dirname(__file__))
            tidb_ca = os.path.join(basedir, "certs", "isrgrootx1.pem")

            # La lógica de SSL para PyMySQL usa 'ssl' con el path al certificado
            if 'tidbcloud.com' in current_app.config['MYSQL_HOST'] and os.path.exists(tidb_ca):
                config["ssl"] = {"ca": tidb_ca}
                print("INFO: Conexión PyMySQL configurada con SSL/CA para TiDB Cloud.", file=sys.stderr)

            g.db = pymysql.connect(**config)
            print("INFO: ✅ Conexión a DB PyMySQL creada y almacenada en g.db.", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Fallo al conectar a la base de datos con PyMySQL: {e}", file=sys.stderr)
            raise e

    return g.db

def close_db(e=None):
    """Cierra la conexión a la base de datos si existe en g."""
    db = g.pop('db', None)

    if db is not None:
        db.close()

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
    try:
        # ... (Lógica de Redis: SIN CAMBIOS) ...
        redis_url = app.config.get('REDIS_URL') or os.getenv('REDIS_URL')
        if redis_url:
            redis_client = redis.StrictRedis.from_url(redis_url, decode_responses=True)
            print(f"INFO: Conectando a Redis mediante URL: {redis_url}")
        else:
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

    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: ❌ No se pudo conectar a Redis: {e}.", file=sys.stderr)
        redis_client = None
    except Exception as e:
        print(f"ERROR: ❌ Error inesperado al conectar a Redis: {e}", file=sys.stderr)
        redis_client = None