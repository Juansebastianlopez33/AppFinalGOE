from flask import Blueprint, request, jsonify, current_app
# ✅ Nueva importación:
from extensions import bcrypt, get_db
import random
import string
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.header import Header
import smtplib
import os
import re
import sys
import traceback
import uuid # Importa uuid para generar tokens únicos para usuarios
import pymysql.cursors # Usaremos pymysql.cursors.DictCursor
import pymysql.err # Para manejar errores de la DB

# Importar funciones de Flask-JWT-Extended
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt

from dotenv import load_dotenv

# IMPORTANTE: Importar get_user_details desde user.py
from routes.user import get_user_details

load_dotenv()

auth_bp = Blueprint('auth', __name__)

MAIL_USER = os.getenv('MAIL_USER')
MAIL_PASS = os.getenv('MAIL_PASS')

# 🚀 CONFIGURACIÓN DE SENDGRID (Puerto 587 con STARTTLS)
# Lee las variables de entorno para HOST y PORT. Si no están, usa SendGrid por defecto.
SMTP_SERVER = os.getenv('MAIL_HOST', 'smtp.sendgrid.net') 
SMTP_PORT = int(os.getenv('MAIL_PORT', 587)) 

# Regla para validar la fortaleza de la contraseña
PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"

def generar_uuid_token():
    """Genera un UUID único para el campo 'token' en la tabla users."""
    return str(uuid.uuid4())

def generar_codigo_verificacion():
    """Genera un código de verificación numérico de 6 dígitos."""
    return str(random.randint(100000, 999999))

def validar_password(password):
    """Valida la fortaleza de la contraseña con una regex."""
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[a-z]", password):
        return False, "La contraseña debe contener al menos una minúscula."
    if not re.search(r"[A-Z]", password):
        return False, "La contraseña debe contener al menos una mayúscula."
    if not re.search(r"\d", password):
        return False, "La contraseña debe contener al menos un número."
    if not re.search(r"[@$!%*?&]", password):
        return False, "La contraseña debe contener al menos un símbolo (@$!%*?&)."
    return True, ""


def enviar_correo_verificacion(destinatario, codigo):
    """
    Envía un correo electrónico con el código de verificación.
    Retorna True si el envío es exitoso, False en caso contrario.
    """
    print(f"DEBUG-VERIF: Intentando enviar correo de verificación a: {destinatario}", file=sys.stderr)
    print(f"DEBUG-VERIF: MAIL_USER configurado: {MAIL_USER}", file=sys.stderr)
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR-VERIF: MAIL_USER o MAIL_PASS no están configurados. No se puede enviar correo.", file=sys.stderr)
        return False
        
    remitente = MAIL_USER
    asunto = "Código de Verificación para tu Cuenta"
    cuerpo_html = f"""
    <html>
    <body>
        <p>Hola,</p>
        <p>Gracias por registrarte. Tu código de verificación es:</p>
        <h3 style="color: #0056b3;">{codigo}</h3>
        <p>Este código es válido por 15 minutos.</p>
        <p>Si no solicitaste este código, por favor ignora este correo.</p>
        <p>Atentamente,</p>
        <p>El equipo de tu aplicación</p>
    </body>
    </html>
    """

    msg = MIMEText(cuerpo_html, 'html', 'utf-8')
    msg['From'] = Header(remitente, 'utf-8')
    msg['To'] = Header(destinatario, 'utf-8')
    msg['Subject'] = Header(asunto, 'utf-8')

    try:
        # 🚀 [MODIFICADO] Conexión SMTP con smtplib.SMTP y STARTTLS para SendGrid
        print(f"DEBUG-VERIF: Conectando a {SMTP_SERVER}:{SMTP_PORT} con STARTTLS...", file=sys.stderr)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # ¡Obligatorio para el puerto 587!
            server.login(MAIL_USER, MAIL_PASS)
            print(f"DEBUG-VERIF: Login SMTP exitoso.", file=sys.stderr)
            server.sendmail(remitente, destinatario, msg.as_string())
        print(f"DEBUG-VERIF: Correo de verificación enviado exitosamente a: {destinatario}", file=sys.stderr)
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR-VERIF: Fallo de autenticación SMTP. Revisa tu MAIL_USER ('apikey') y MAIL_PASS (tu clave API).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except smtplib.SMTPConnectError as e:
        # Esto ahora manejará el ETIMEDOUT si el puerto 587 también falla (poco probable con SendGrid)
        print(f"ERROR-VERIF: Fallo de conexión al servidor SMTP. Host/Puerto: {SMTP_SERVER}:{SMTP_PORT}. Detalle: {e} (AÚN HAY BLOQUEO DE FIREWALL).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR-VERIF: Fallo general al enviar correo de verificación a {destinatario}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

def enviar_correo_restablecimiento(destinatario, codigo):
    """
    Envía un correo electrónico con el código para restablecer la contraseña.
    Retorna True si el envío es exitoso, False en caso contrario.
    """
    print(f"DEBUG-VERIF: Intentando enviar correo de restablecimiento a: {destinatario}", file=sys.stderr)
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR-VERIF: MAIL_USER o MAIL_PASS no están configurados.", file=sys.stderr)
        return False

    remitente = MAIL_USER
    asunto = "Restablecimiento de Contraseña"
    cuerpo_html = f"""
    <html>
    <body>
        <p>Hola,</p>
        <p>Hemos recibido una solicitud para restablecer la contraseña de tu cuenta. Tu código de restablecimiento es:</p>
        <h3 style="color: #d9534f;">{codigo}</h3>
        <p>Este código es válido por 15 minutos.</p>
        <p>Si no solicitaste este cambio, por favor ignora este correo.</p>
        <p>Atentamente,</p>
        <p>El equipo de tu aplicación</p>
    </body>
    </html>
    """
    msg = MIMEText(cuerpo_html, 'html', 'utf-8')
    msg['From'] = Header(remitente, 'utf-8')
    msg['To'] = Header(destinatario, 'utf-8')
    msg['Subject'] = Header(asunto, 'utf-8')

    try:
        # 🚀 [MODIFICADO] Conexión SMTP con smtplib.SMTP y STARTTLS para SendGrid
        print(f"DEBUG-VERIF: Conectando a {SMTP_SERVER}:{SMTP_PORT} con STARTTLS...", file=sys.stderr)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # ¡Obligatorio para el puerto 587!
            server.login(MAIL_USER, MAIL_PASS)
            print(f"DEBUG-VERIF: Login SMTP exitoso.", file=sys.stderr)
            server.sendmail(remitente, destinatario, msg.as_string())
        print(f"DEBUG-VERIF: Correo de restablecimiento enviado exitosamente a: {destinatario}", file=sys.stderr)
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR-VERIF: Fallo de autenticación SMTP. Revisa tu MAIL_USER ('apikey') y MAIL_PASS (tu clave API).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except smtplib.SMTPConnectError as e:
        print(f"ERROR-VERIF: Fallo de conexión al servidor SMTP. Host/Puerto: {SMTP_SERVER}:{SMTP_PORT}. Detalle: {e} (Bloqueo de red o configuración de host incorrecta).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR-VERIF: Fallo general al enviar correo de restablecimiento a {destinatario}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

def enviar_correo_bienvenida(destinatario, username):
    """
    Envía un correo electrónico de bienvenida.
    Retorna True si el envío es exitoso, False en caso contrario.
    """
    print(f"DEBUG-VERIF: Intentando enviar correo de bienvenida a: {destinatario}", file=sys.stderr)
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR-VERIF: MAIL_USER o MAIL_PASS no están configurados.", file=sys.stderr)
        return False

    remitente = MAIL_USER
    asunto = "¡Bienvenido a la plataforma!"
    cuerpo_html = f"""
    <html>
    <body>
        <p>Hola {username},</p>
        <p>¡Te damos la bienvenida a la plataforma! Tu registro ha sido exitoso.</p>
        <p>Ya puedes iniciar sesión y comenzar a explorar.</p>
        <p>Atentamente,</p>
        <p>El equipo de tu aplicación</p>
    </body>
    </html>
    """
    msg = MIMEText(cuerpo_html, 'html', 'utf-8')
    msg['From'] = Header(remitente, 'utf-8')
    msg['To'] = Header(destinatario, 'utf-8')
    msg['Subject'] = Header(asunto, 'utf-8')

    try:
        # 🚀 [MODIFICADO] Conexión SMTP con smtplib.SMTP y STARTTLS para SendGrid
        print(f"DEBUG-VERIF: Conectando a {SMTP_SERVER}:{SMTP_PORT} con STARTTLS...", file=sys.stderr)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # ¡Obligatorio para el puerto 587!
            server.login(MAIL_USER, MAIL_PASS)
            print(f"DEBUG-VERIF: Login SMTP exitoso.", file=sys.stderr)
            server.sendmail(remitente, destinatario, msg.as_string())
        print(f"DEBUG-VERIF: Correo de bienvenida enviado exitosamente a: {destinatario}", file=sys.stderr)
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR-VERIF: Fallo de autenticación SMTP. Revisa tu MAIL_USER ('apikey') y MAIL_PASS (tu clave API).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except smtplib.SMTPConnectError as e:
        print(f"ERROR-VERIF: Fallo de conexión al servidor SMTP. Host/Puerto: {SMTP_SERVER}:{SMTP_PORT}. Detalle: {e} (Bloqueo de red o configuración de host incorrecta).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR-VERIF: Fallo general al enviar correo de bienvenida a {destinatario}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not username or not email or not password:
        return jsonify({"error": "Faltan datos requeridos."}), 400

    # 1. Validar Contraseña
    is_valid, reason = validar_password(password)
    if not is_valid:
        return jsonify({"error": reason}), 400
    
    # 2. Validar Email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Formato de correo inválido."}), 400

    conn = None
    try:
        conn = get_db()
        # Iniciar transacción para asegurar que el usuario no se registre si falla el correo.
        conn.begin()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Verificar existencia de usuario o email
        cursor.execute("SELECT user_id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            conn.rollback()
            print(f"DEBUG-REG: Intento de registro con usuario o email ya existente: {username}/{email}", file=sys.stderr)
            return jsonify({"error": "El nombre de usuario o el correo electrónico ya están registrados."}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        verification_code = generar_codigo_verificacion()
        expiration_time = datetime.now() + timedelta(minutes=15)
        user_uuid = generar_uuid_token()
        
        # 3. Insertar usuario (status 'PENDING')
        print(f"DEBUG-REG: Insertando usuario {username} en DB (sin commit)...", file=sys.stderr)
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, is_active, is_verified, verification_code, verification_code_expira, token) 
            VALUES (%s, %s, %s, 1, 0, %s, %s, %s)
        """, (username, email, hashed_password, verification_code, expiration_time, user_uuid))

        # 4. Enviar correo de verificación
        print(f"DEBUG-REG: Llamando a enviar_correo_verificacion para {email}...", file=sys.stderr)
        if not enviar_correo_verificacion(email, verification_code):
            # 5. Si falla el correo, hacer ROLLBACK
            conn.rollback()
            print(f"ERROR-REG: Fallo al enviar correo de verificación a {email}. Se ha ejecutado ROLLBACK. Usuario NO registrado.", file=sys.stderr)
            # 503: Service Unavailable, indicando que el servicio de correo falló.
            return jsonify({"error": "Fallo al enviar el correo de verificación. Por favor, inténtalo de nuevo más tarde."}), 503

        # 6. Si el correo se envía, hacer COMMIT
        conn.commit()
        print(f"DEBUG-REG: Usuario {username} insertado y correo enviado exitosamente.", file=sys.stderr)
        
        return jsonify({
            "message": "Registro exitoso. Se ha enviado un código de verificación a tu correo.",
            "user_id": user_uuid # Devolver el UUID para futuras referencias
        }), 201

    except pymysql.err.MySQLError as e:
        if conn:
            conn.rollback()
        error_msg = f"ERROR-DB: Fallo en transacción de registro: {str(e)}"
        print(error_msg, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error de base de datos durante el registro."}), 500
    except Exception as e:
        if conn:
            conn.rollback()
        error_msg = f"ERROR: Fallo general en /register: {str(e)}"
        print(error_msg, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500
    finally:
        if conn:
            # La conexión se cierra automáticamente al final del contexto de Flask con @app.teardown_appcontext
            # Solo imprimimos un mensaje si ya estaba cerrada (manejo de error en extensions.py)
            pass

@auth_bp.route('/verificar', methods=['POST'])
def verificar_cuenta():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    if not email or not code:
        return jsonify({"error": "Faltan datos requeridos (email y código)."}), 400

    conn = get_db()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT verification_code, verification_code_expira, is_verified 
            FROM users 
            WHERE email = %s
        """, (email,))
        
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({"error": "Correo electrónico no encontrado."}), 404
        
        if user_data['is_verified']:
            return jsonify({"message": "La cuenta ya está verificada."}), 200

        stored_code = user_data['verification_code']
        expira = user_data['verification_code_expira']

        if stored_code != code:
            return jsonify({"error": "Código de verificación incorrecto."}), 400
        
        if expira is None or datetime.now() > expira:
            return jsonify({"error": "El código de verificación ha expirado."}), 400

        # Verificación exitosa
        conn.begin() # Iniciar transacción
        cursor.execute("UPDATE users SET is_verified = 1, verification_code = NULL, verification_code_expira = NULL WHERE email = %s", (email,))
        conn.commit() # Confirmar
        
        # Enviar correo de bienvenida (opcional, sin rollback)
        user_details = get_user_details(email=email)
        if user_details:
             enviar_correo_bienvenida(email, user_details['username'])

        return jsonify({"message": "Cuenta verificada exitosamente."}), 200
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo general en /verificar: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Faltan datos requeridos."}), 400

    conn = get_db()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT user_id, username, password_hash, is_verified, is_active, token 
            FROM users 
            WHERE email = %s
        """, (email,))
        user_data = cursor.fetchone()

        if user_data and bcrypt.check_password_hash(user_data['password_hash'], password):
            if not user_data['is_verified']:
                return jsonify({"error": "La cuenta no ha sido verificada. Por favor, verifica tu correo."}), 403
            
            if not user_data['is_active']:
                return jsonify({"error": "Tu cuenta ha sido desactivada."}), 403

            # Payload JWT con datos del usuario
            additional_claims = {
                "user_uuid": user_data['token'],
                "username": user_data['username'],
                "user_id": user_data['user_id']
            }
            
            access_token = create_access_token(identity=user_data['user_id'], additional_claims=additional_claims)
            refresh_token = create_refresh_token(identity=user_data['user_id'])

            return jsonify({
                "message": "Inicio de sesión exitoso.",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "username": user_data['username'],
                "user_uuid": user_data['token']
            }), 200
        else:
            return jsonify({"error": "Correo o contraseña incorrectos."}), 401
    
    except Exception as e:
        print(f"ERROR: Fallo general en /login: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user_id = get_jwt_identity()
    conn = get_db()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT username, token, user_id
            FROM users
            WHERE user_id = %s
        """, (current_user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            return jsonify({"error": "Usuario no encontrado."}), 404

        additional_claims = {
            "user_uuid": user_data['token'],
            "username": user_data['username'],
            "user_id": user_data['user_id']
        }
        
        new_access_token = create_access_token(identity=current_user_id, additional_claims=additional_claims)
        
        return jsonify({
            "access_token": new_access_token,
            "username": user_data['username'],
            "user_uuid": user_data['token']
        }), 200

    except Exception as e:
        print(f"ERROR: Fallo general en /refresh: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500

@auth_bp.route('/logeado', methods=['GET'])
@jwt_required()
def logeado():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    
    username = claims.get('username')
    user_uuid = claims.get('user_uuid')
    
    return jsonify({
        "message": "Token válido",
        "user_id": current_user_id,
        "username": username,
        "user_uuid": user_uuid
    }), 200

@auth_bp.route('/request-password-reset', methods=['POST'])
def request_password_reset():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"error": "Falta el correo electrónico."}), 400

    conn = None
    try:
        conn = get_db()
        conn.begin()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if not cursor.fetchone():
            conn.rollback()
            return jsonify({"message": "Si el correo existe, se ha enviado un código de restablecimiento."}), 200
        
        # Generar código y tiempo de expiración
        reset_code = generar_codigo_verificacion()
        expiration_time = datetime.now() + timedelta(minutes=15)
        
        # Actualizar DB
        cursor.execute("""
            UPDATE users 
            SET reset_token = %s, reset_token_expira = %s 
            WHERE email = %s
        """, (reset_code, expiration_time, email))

        # Enviar correo (usando la función ya modificada)
        if not enviar_correo_restablecimiento(email, reset_code):
            conn.rollback()
            return jsonify({"error": "Fallo al enviar el correo de restablecimiento. Inténtalo de nuevo más tarde."}), 503
        
        conn.commit()
        return jsonify({"message": "Si el correo existe, se ha enviado un código de restablecimiento."}), 200

    except pymysql.err.MySQLError as e:
        if conn:
            conn.rollback()
        error_msg = f"ERROR-DB: Fallo en transacción de restablecimiento: {str(e)}"
        print(error_msg, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error de base de datos."}), 500
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo general en /request-password-reset: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    new_password = data.get('new_password')

    if not email or not code or not new_password:
        return jsonify({"error": "Faltan datos requeridos (email, código o nueva contraseña)."}), 400
    
    # 1. Validar fortaleza de la nueva contraseña
    is_valid, reason = validar_password(new_password)
    if not is_valid:
        return jsonify({"error": reason}), 400
    
    conn = get_db()
    try:
        conn.begin()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT reset_token, reset_token_expira
            FROM users
            WHERE email = %s
        """, (email,))
        
        user_data = cursor.fetchone()
        
        if not user_data:
            conn.rollback()
            return jsonify({"error": "Correo electrónico no encontrado."}), 404
            
        stored_code = user_data['reset_token']
        expira = user_data['reset_token_expira']
        
        if stored_code is None or stored_code != code:
            conn.rollback()
            return jsonify({"error": "Código de restablecimiento incorrecto."}), 400
            
        print(f"DEBUG: Código encontrado para email: {email}, expira en: {expira}", file=sys.stderr)
        if expira is None or datetime.now() > expira:
            print(f"DEBUG: Código de restablecimiento expirado o nulo para {email}. Expiración: {expira}", file=sys.stderr)
            cursor.execute("UPDATE users SET reset_token = NULL, reset_token_expira = NULL WHERE email = %s", (email,))
            conn.commit()
            return jsonify({"error": "El código de restablecimiento ha expirado."}), 400

        hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        print(f"DEBUG: Contraseña hasheada para {email}. Actualizando DB...", file=sys.stderr)
        cursor.execute("""
            UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expira = NULL
            WHERE email = %s
        """, (hashed_new_password, email))
        conn.commit()
        print(f"DEBUG: Contraseña restablecida exitosamente para {email}.", file=sys.stderr)
        return jsonify({"message": "Contraseña restablecida exitosamente."}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo general en /reset-password: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500