from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText
from email.header import Header
import smtplib
import os
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

support_bp = Blueprint('support', __name__)

MAIL_USER = os.getenv('MAIL_USER')
MAIL_PASS = os.getenv('MAIL_PASS')

# 🚀 [CAMBIO 1] Variables de SendGrid/SMTP Externo
SMTP_SERVER = os.getenv('MAIL_HOST', 'smtp.sendgrid.net') 
SMTP_PORT = int(os.getenv('MAIL_PORT', 587)) 

def enviar_correo_soporte(nombre, email_usuario, asunto, mensaje):
    """
    Función que envía el mensaje de soporte al correo de la aplicación.
    """
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR-SUPPORT: MAIL_USER o MAIL_PASS no configurados.", file=sys.stderr)
        return False
        
    remitente = MAIL_USER # El correo de la aplicación
    destinatario = MAIL_USER # Se envía el mensaje al mismo correo de soporte
    
    asunto_app = f"Nuevo mensaje de soporte: {asunto}"
    
    cuerpo_html = f"""
    <html>
    <body>
        <h2>Mensaje de Soporte</h2>
        <p><strong>De:</strong> {nombre} ({email_usuario})</p>
        <p><strong>Asunto Original:</strong> {asunto}</p>
        <hr>
        <p><strong>Mensaje:</strong></p>
        <p>{mensaje}</p>
    </body>
    </html>
    """

    msg = MIMEText(cuerpo_html, 'html', 'utf-8')
    msg['From'] = Header(remitente, 'utf-8')
    msg['To'] = Header(destinatario, 'utf-8')
    msg['Subject'] = Header(asunto_app, 'utf-8')

    try:
        # 🚀 [CAMBIO 2] Conexión SMTP con smtplib.SMTP y STARTTLS para SendGrid
        print(f"DEBUG-SUPPORT: Conectando a {SMTP_SERVER}:{SMTP_PORT} con STARTTLS...", file=sys.stderr)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # ¡Obligatorio para el puerto 587!
            server.login(MAIL_USER, MAIL_PASS)
            print(f"DEBUG-SUPPORT: Login SMTP exitoso.", file=sys.stderr)
            server.send_message(msg)
        print("DEBUG-SUPPORT: Correo de soporte enviado exitosamente.", file=sys.stderr)
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR-SUPPORT: Fallo de autenticación SMTP. Revisa tus credenciales de SendGrid.", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR-SUPPORT: Fallo general al enviar correo de soporte: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False


@support_bp.route('/contact', methods=['POST'])
def contact_support():
    data = request.get_json()
    nombre = data.get('name')
    email = data.get('email')
    asunto = data.get('subject')
    mensaje = data.get('message')

    if not nombre or not email or not asunto or not mensaje:
        return jsonify({"error": "Faltan datos requeridos."}), 400

    if not enviar_correo_soporte(nombre, email, asunto, mensaje):
        # 503 Service Unavailable si el correo falla
        return jsonify({"error": "Fallo al enviar el mensaje de soporte. Por favor, inténtalo de nuevo más tarde."}), 503

    return jsonify({"message": "Mensaje de soporte enviado exitosamente."}), 200