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
    descripcion = data.get('descripcion', '')
    foto_perfil = data.get('foto_perfil')

    if not username or not email or not password:
        return jsonify({"error": "Faltan datos de registro requeridos."}), 400

    es_valida, mensaje_error = validar_password(password)
    if not es_valida:
        return jsonify({"error": mensaje_error}), 400

    conn = get_db()
    conn.begin() # Iniciar transacción
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 🛑 CORRECCIÓN: Usar 'id' en lugar de 'user_id' en el SELECT
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return jsonify({"error": "El nombre de usuario o el correo electrónico ya está registrado."}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        verification_code = generar_codigo_verificacion()
        code_expiration = datetime.now() + timedelta(minutes=15)
        uuid_token = generar_uuid_token()

        cursor.execute("""
            INSERT INTO users (username, email, DescripUsuario, password_hash, verificado, verification_code, code_expiration, foto_perfil, token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (username, email, descripcion, hashed_password, False, verification_code, code_expiration, foto_perfil, uuid_token))
        
        # 🛑 CORRECCIÓN: Asegurar el commit de la transacción
        conn.commit()
        
        # Enviar correo de verificación (no bloquea el registro si falla el envío)
        if not enviar_correo_verificacion(email, verification_code):
            print(f"ADVERTENCIA: Fallo al enviar correo de verificación a {email}.", file=sys.stderr)
            # Opcional: Podrías revertir el registro aquí, pero es mejor permitirlo y dejar que el usuario reintente el código.
        
        return jsonify({
            "message": "Registro exitoso. Se ha enviado un código de verificación a tu correo.",
            "username": username,
            "user_uuid": uuid_token
        }), 201

    except pymysql.err.OperationalError as e:
        conn.rollback()
        # El error original era aquí: "Unknown column 'user_id' in 'field list'" (1054)
        print(f"ERROR-DB: Fallo en transacción de registro: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Error en la base de datos al registrar: {e.args[1]}"}), 500
    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo general en /register: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/verify-code', methods=['POST'])
def verificar_cuenta():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    if not email or not code:
        return jsonify({"error": "Faltan el correo electrónico o el código de verificación."}), 400

    conn = get_db()
    conn.begin()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute("""
            SELECT verification_code, code_expiration, verificado 
            FROM users 
            WHERE email = %s
        """, (email,))
        user_data = cursor.fetchone()

        if not user_data:
            return jsonify({"error": "Correo electrónico no encontrado."}), 404

        if user_data['verificado']:
            return jsonify({"message": "La cuenta ya está verificada."}), 200

        db_code = user_data['verification_code']
        expira = user_data['code_expiration']

        if db_code != code:
            return jsonify({"error": "Código de verificación incorrecto."}), 400

        if expira is None or datetime.now() > expira:
            return jsonify({"error": "El código de verificación ha expirado."}), 400

        # Si es correcto: actualizar la cuenta
        cursor.execute("""
            UPDATE users SET verificado = TRUE, verification_code = NULL, code_expiration = NULL 
            WHERE email = %s
        """, (email,))
        
        conn.commit()

        # Enviar correo de bienvenida (NO bloquea la verificación si falla el envío)
        user_details = get_user_details(email)
        if user_details:
             if not enviar_correo_bienvenida(email, user_details.get('username', 'usuario')):
                 print(f"ADVERTENCIA: Fallo al enviar correo de bienvenida a {email}.", file=sys.stderr)


        return jsonify({"message": "Cuenta verificada exitosamente."}), 200

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo general en /verify-code: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Faltan el correo electrónico o la contraseña."}), 400

    conn = get_db()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        # 🛑 CORRECCIÓN: Usar 'id' en lugar de 'user_id' en el SELECT
        cursor.execute("""
            SELECT id, username, password_hash, verificado, token
            FROM users 
            WHERE email = %s
        """, (email,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({"error": "Credenciales inválidas."}), 401

        # Verificar si la cuenta está verificada
        if not user_data['verificado']:
            return jsonify({"error": "Cuenta no verificada. Por favor, revisa tu correo electrónico para verificar tu cuenta."}), 403

        # Verificar la contraseña
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], password):
            
            # Payload JWT
            additional_claims = {
                "user_uuid": user_data['token'],
                "username": user_data['username'],
                # 🛑 CORRECCIÓN: Usar 'id' del diccionario para las claims
                "user_id": user_data['id'] 
            }
            
            # Crear tokens usando 'id' como identity
            # 🛑 CORRECCIÓN: Usar 'id' del diccionario para la identity
            access_token = create_access_token(identity=user_data['id'], additional_claims=additional_claims)
            refresh_token = create_refresh_token(identity=user_data['id']) # 🛑 CORRECCIÓN: Usar 'id' del diccionario para la identity

            return jsonify({
                "message": "Inicio de sesión exitoso.",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "username": user_data['username'],
                "user_uuid": user_data['token']
            }), 200
        else:
            return jsonify({"error": "Credenciales inválidas."}), 401

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
        # 🛑 CORRECCIÓN: Usar 'id' en el SELECT y en la cláusula WHERE
        cursor.execute("""
            SELECT username, token, id
            FROM users
            WHERE id = %s
        """, (current_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            # Esto puede ocurrir si el usuario fue eliminado
            return jsonify({"error": "Usuario no encontrado."}), 404
        
        additional_claims = {
            "user_uuid": user_data['token'],
            "username": user_data['username'],
            # 🛑 CORRECCIÓN: Usar 'id' del diccionario para las claims
            "user_id": user_data['id']
        }

        # Crear nuevo access token
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


@auth_bp.route('/resend-code', methods=['POST'])
def resend_verification_code():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"error": "Falta el correo electrónico."}), 400

    conn = get_db()
    conn.begin()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT verificado, code_expiration FROM users WHERE email = %s", (email,))
        user_data = cursor.fetchone()

        if not user_data:
            return jsonify({"error": "Correo electrónico no encontrado."}), 404

        if user_data['verificado']:
            return jsonify({"message": "La cuenta ya está verificada."}), 200
        
        # Generar nuevo código y tiempo de expiración
        new_code = generar_codigo_verificacion()
        new_expiration = datetime.now() + timedelta(minutes=15)

        cursor.execute("""
            UPDATE users SET verification_code = %s, code_expiration = %s 
            WHERE email = %s
        """, (new_code, new_expiration, email))
        
        conn.commit()

        if not enviar_correo_verificacion(email, new_code):
            return jsonify({"error": "Fallo al enviar el nuevo código de verificación. Inténtalo de nuevo más tarde."}), 503

        return jsonify({"message": "Nuevo código de verificación enviado a tu correo electrónico."}), 200

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo general en /resend-code: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"error": "Falta el correo electrónico."}), 400

    conn = get_db()
    conn.begin()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        # 🛑 CORRECCIÓN: Usar 'id' en el SELECT
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if not cursor.fetchone():
            return jsonify({"error": "Correo electrónico no encontrado."}), 404

        # Generar código de restablecimiento y tiempo de expiración
        reset_code = generar_codigo_verificacion()
        expiration_time = datetime.now() + timedelta(minutes=15)

        cursor.execute("""
            UPDATE users SET reset_token = %s, reset_token_expira = %s 
            WHERE email = %s
        """, (reset_code, expiration_time, email))
        
        conn.commit()

        if not enviar_correo_restablecimiento(email, reset_code):
            return jsonify({"error": "Fallo al enviar el código de restablecimiento. Inténtalo de nuevo más tarde."}), 503

        return jsonify({"message": "Código de restablecimiento de contraseña enviado a tu correo electrónico."}), 200

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Fallo general en /forgot-password: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    new_password = data.get('new_password')

    if not email or not code or not new_password:
        return jsonify({"error": "Faltan datos requeridos: correo, código o nueva contraseña."}), 400
    
    es_valida, mensaje_error = validar_password(new_password)
    if not es_valida:
        return jsonify({"error": mensaje_error}), 400

    conn = get_db()
    conn.begin()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT reset_token, reset_token_expira FROM users WHERE email = %s", (email,))
        user_data = cursor.fetchone()

        if not user_data:
            return jsonify({"error": "Correo electrónico no encontrado."}), 404

        reset_token = user_data.get('reset_token')
        expira = user_data.get('reset_token_expira')

        if reset_token != code:
            return jsonify({"error": "Código de restablecimiento incorrecto."}), 400
            
        if expira is None or datetime.now() > expira:
            cursor.execute("UPDATE users SET reset_token = NULL, reset_token_expira = NULL WHERE email = %s", (email,))
            conn.commit()
            return jsonify({"error": "El código de restablecimiento ha expirado."}), 400

        hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        cursor.execute("""
            UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expira = NULL
            WHERE email = %s
        """, (hashed_new_password, email))
        conn.commit()
        return jsonify({"message": "Contraseña restablecida exitosamente."}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo general en /reset-password: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500


@auth_bp.route('/logeado', methods=['GET'])
@jwt_required()
def logeado():
    current_user_id = get_jwt_identity()
    conn = get_db()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        # 🛑 CORRECCIÓN: Usar 'id' en el SELECT y en la cláusula WHERE
        cursor.execute("SELECT username, token FROM users WHERE id = %s", (current_user_id,))
        user_data = cursor.fetchone()

        if user_data:
            return jsonify({
                "message": "Usuario autenticado.",
                "user_id": current_user_id, # El ID primario (entero)
                "username": user_data['username'],
                "user_uuid": user_data['token'] # El token UUID
            }), 200
        else:
            return jsonify({"error": "Usuario no encontrado."}), 404

    except Exception as e:
        print(f"ERROR: Fallo general en /logeado: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500