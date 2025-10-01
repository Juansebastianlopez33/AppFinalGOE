import mysql.connector
import os

# Base dir para localizar el certificado SSL
basedir = os.path.abspath(os.path.dirname(__file__))

def get_db_connection():
    """
    Devuelve una conexión segura a MySQL/TiDB usando mysql-connector-python.
    - Si es TiDB Cloud, usa SSL con el certificado CA.
    - Si es un MySQL local, se conecta sin SSL.
    """
    host = os.getenv("MYSQL_HOST")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DB")

    # Configuración base
    config = {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
        "charset": "utf8mb4"
    }

    # ✅ Forzar SSL si es TiDB Cloud
    if host and "tidbcloud.com" in host:
        config["ssl_ca"] = os.path.join(basedir, "certs", "isrgrootx1.pem")

    # Crear conexión
    return mysql.connector.connect(**config)
