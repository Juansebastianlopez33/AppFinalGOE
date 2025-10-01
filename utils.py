import random
import string
from email.mime.text import MIMEText
from email.header import Header
import smtplib
import os
from dotenv import load_dotenv

import cloudinary
import cloudinary.uploader

load_dotenv()

MAIL_USER = os.getenv('MAIL_USER')
MAIL_PASS = os.getenv('MAIL_PASS') 

def generar_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=64))

def generar_codigo_verificacion():
    return str(random.randint(100000, 999999))

def enviar_correo_verificacion(destinatario, codigo):
    cuerpo = f"Tu código de verificación es: {codigo}"
    msg = MIMEText(cuerpo, 'plain', 'utf-8')
    msg['Subject'] = Header('Código de Verificación', 'utf-8')
    msg['From'] = MAIL_USER
    msg['To'] = destinatario

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Error al enviar correo:", str(e))
        return False


# 🚀 Configuración de Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def upload_image_to_cloudinary(file, folder="general", public_id=None, overwrite=True, invalidate=True):
    """
    Sube un archivo a Cloudinary y devuelve la URL segura y la versión.
    """
    try:
        print(f"📌 [DEBUG-utils] Subiendo imagen a Cloudinary (folder={folder}, public_id={public_id})...")
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            public_id=public_id,
            overwrite=overwrite,
            invalidate=invalidate,
            resource_type="image"
        )
        secure_url = result.get("secure_url") or result.get("url")
        version = result.get("version")

        print(f"✅ [DEBUG-utils] Subida correcta: secure_url={secure_url}, version={version}")

        return {
            "secure_url": secure_url,
            "version": version
        }
    except Exception as e:
        print(f"❌ [DEBUG-utils] Error en subida Cloudinary: {e}")
        return None

# utils.py (agregar al final)

import tempfile
import json

def upload_json_to_cloudinary(data, folder="users_data", public_id=None):
    """
    Sube un dict/list como JSON a Cloudinary y devuelve la URL segura.
    """
    try:
        # Guardar temporalmente el JSON
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=4, ensure_ascii=False)
            tmp_path = tmp.name

        result = cloudinary.uploader.upload(
            tmp_path,
            folder=folder,
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            resource_type="raw"  # 👈 clave: subir como archivo crudo
        )
        os.remove(tmp_path)

        return result.get("secure_url")
    except Exception as e:
        print(f"❌ [DEBUG-utils] Error subiendo JSON a Cloudinary: {e}")
        return None


def download_json_from_cloudinary(url):
    """
    Descarga un JSON desde una URL de Cloudinary.
    """
    try:
        import requests
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"❌ [DEBUG-utils] Error descargando JSON desde Cloudinary: {e}")
        return None
