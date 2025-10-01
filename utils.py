import random
import string
import os
import sys
import traceback
import tempfile
import json
import requests # 👈 NECESARIO para descargar JSON de Cloudinary

# Para correo
from email.mime.text import MIMEText
from email.header import Header
import smtplib
from dotenv import load_dotenv

# Para Cloudinary
import cloudinary
import cloudinary.uploader

load_dotenv()

MAIL_USER = os.getenv('MAIL_USER')
MAIL_PASS = os.getenv('MAIL_PASS') 

# ----------------- Funciones de Token y Código -----------------

def generar_token():
    """Genera un token alfanumérico largo y único."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=64))

def generar_codigo_verificacion():
    """Genera un código de verificación numérico de 6 dígitos."""
    return str(random.randint(100000, 999999))

# ----------------- Funciones de Correo -----------------

def enviar_correo_verificacion(destinatario, codigo):
    """
    Envía un correo electrónico con el código de verificación usando smtplib.
    """
    if not MAIL_USER or not MAIL_PASS:
        print("❌ ERROR: Variables de entorno MAIL_USER o MAIL_PASS no configuradas.")
        return False
        
    cuerpo = f"Tu código de verificación es: {codigo}"
    msg = MIMEText(cuerpo, 'plain', 'utf-8')
    msg['Subject'] = Header('Código de Verificación', 'utf-8')
    msg['From'] = MAIL_USER
    msg['To'] = destinatario

    try:
        # Usar puerto 465 para SSL explícito (SMTP_SSL)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
        print(f"DEBUG: Correo de verificación enviado exitosamente a {destinatario}")
        return True
    except Exception as e:
        print("❌ Error al enviar correo de verificación:", str(e), file=sys.stderr)
        return False


# ----------------- Funciones de Cloudinary -----------------

# 🚀 Configuración de Cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def upload_image_to_cloudinary(file, folder="uploads", public_id=None):
    """
    Sube un archivo de imagen a Cloudinary y devuelve la URL segura y la versión.
    """
    try:
        if not file:
            return None
        
        # Subir a Cloudinary
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            resource_type="auto"
        )
        
        secure_url = result.get("secure_url")
        version = result.get("version")
        
        if not secure_url:
            print("❌ [DEBUG-utils] Cloudinary no devolvió una URL segura.")
            return None
            
        print(f"✅ [DEBUG-utils] Subida Cloudinary exitosa. URL: {secure_url}")
        
        return {
            "secure_url": secure_url,
            "version": version
        }
    except Exception as e:
        print(f"❌ [DEBUG-utils] Error en subida Cloudinary: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None

def upload_json_to_cloudinary(data, folder="users_data", public_id=None):
    """
    Sube un dict/list como JSON a Cloudinary y devuelve la URL segura.
    """
    tmp_path = None
    try:
        # Guardar temporalmente el JSON
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=4, ensure_ascii=False)
            tmp_path = tmp.name

        print(f"DEBUG: JSON guardado temporalmente en {tmp_path}. Subiendo a Cloudinary...")
        
        result = cloudinary.uploader.upload(
            tmp_path,
            folder=folder,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            resource_type="raw"  # 👈 clave: subir como archivo crudo
        )
        
        secure_url = result.get("secure_url")

        # Limpiar el archivo temporal
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
            
        print(f"DEBUG: JSON subido a Cloudinary. URL: {secure_url}")
        return secure_url
    except Exception as e:
        print(f"❌ [DEBUG-utils] Error subiendo JSON a Cloudinary: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # Asegurarse de limpiar si falló
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None


def download_json_from_cloudinary(url):
    """
    Descarga un JSON desde una URL de Cloudinary y lo deserializa a un objeto Python (dict/list).
    """
    if not url:
        return None

    try:
        print(f"DEBUG: Descargando JSON de Cloudinary: {url}")
        response = requests.get(url)
        response.raise_for_status() # Lanza HTTPError si el código de estado es 4xx o 5xx
        
        # Cloudinary devuelve el JSON como texto plano
        data = response.json()
        print("DEBUG: JSON descargado y deserializado exitosamente.")
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ [DEBUG-utils] Error de red/HTTP al descargar JSON de Cloudinary: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"❌ [DEBUG-utils] Error al decodificar JSON de la URL: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ [DEBUG-utils] Error general al descargar JSON de Cloudinary: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None
