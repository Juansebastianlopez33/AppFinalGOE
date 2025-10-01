from flask import Blueprint, request, jsonify, current_app
# ❌ Reemplazar: from extensions import mysql, bcrypt
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

# Importar funciones de Flask-JWT-Extended
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt

from dotenv import load_dotenv
# ❌ Reemplazar: from MySQLdb.cursors import DictCursor # Importar DictCursor aquí
# ✅ Nueva importación:
import pymysql.cursors # Usaremos pymysql.cursors.DictCursor

# IMPORTANTE: Importar get_user_details desde user.py
from routes.user import get_user_details

load_dotenv()

auth_bp = Blueprint('auth', __name__)

MAIL_USER = os.getenv('MAIL_USER')
MAIL_PASS = os.getenv('MAIL_PASS')

def generar_uuid_token():
    """Genera un UUID único para el campo 'token' en la tabla users."""
    return str(uuid.uuid4())

def generar_codigo_verificacion():
    """Genera un código de verificación numérico de 6 dígitos."""
    return str(random.randint(100000, 999999))

def enviar_correo_verificacion(destinatario, codigo):
    """
    Envía un correo electrónico con el código de verificación.
    Retorna True si el envío es exitoso, False en caso contrario.
    """
    print(f"DEBUG: Intentando enviar correo de verificación a: {destinatario}", file=sys.stderr)
    print(f"DEBUG: MAIL_USER (verificación): {MAIL_USER}", file=sys.stderr)
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR: MAIL_USER o MAIL_PASS no están configurados para verificación. No se puede enviar correo.", file=sys.stderr)
        return False
    try:
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

        # ✅ CORRECCIÓN: Usar smtplib.SMTP_SSL y el puerto 465
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            # server.starttls() # No es necesario con SMTP_SSL
            server.login(MAIL_USER, MAIL_PASS)
            server.sendmail(remitente, destinatario, msg.as_string())
        print(f"DEBUG: Correo de verificación enviado exitosamente a: {destinatario}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"ERROR: Fallo al enviar correo de verificación a {destinatario}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

def enviar_correo_restablecimiento(destinatario, reset_code):
    """
    Envía un correo electrónico con el CÓDIGO para restablecer la contraseña.
    Retorna True si el envío es exitoso, False en caso contrario.
    """
    print(f"DEBUG: Intentando enviar correo de restablecimiento a: {destinatario}", file=sys.stderr)
    print(f"DEBUG: MAIL_USER (restablecimiento): {MAIL_USER}", file=sys.stderr) # Muestra el usuario, pero no la contraseña
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR: MAIL_USER o MAIL_PASS no están configurados para restablecimiento. No se puede enviar correo.", file=sys.stderr)
        return False

    reset_email_body = f"""
    <html>
    <body>
        <p>Estimado usuario,</p>
        <p>Hemos recibido una solicitud para restablecer la contraseña de su cuenta en God of Eternia.</p>
        <p>Por favor, use el siguiente <strong>CÓDIGO DE RESTABLECIMIENTO</strong>:</p>
        <h3 style="color: #0056b3;">{reset_code}</h3>
        <p>Ingrese este código en la aplicación para proceder con el cambio de contraseña.</p>
        <p>Este código es válido por 1 hora. Si usted no solicitó este restablecimiento, por favor, ignore este correo.</p>
        <p>Atentamente,</p>
        <p>El equipo de God of Eternia.</p>
    </body>
    </html>
    """
    
    msg = MIMEText(reset_email_body, 'html', 'utf-8')
    msg['Subject'] = Header('Restablecimiento de Contraseña - God of Eternia', 'utf-8')
    msg['From'] = MAIL_USER
    msg['To'] = destinatario

    try:
        # ✅ CORRECCIÓN: Usar smtplib.SMTP_SSL y el puerto 465
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            # server.starttls() # No es necesario con SMTP_SSL
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
        print(f"DEBUG: Correo de restablecimiento enviado exitosamente a: {destinatario}", file=sys.stderr)
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR: Fallo de autenticación SMTP. Revisa tu MAIL_USER y MAIL_PASS (contraseña de aplicación si usas 2FA).", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except smtplib.SMTPServerDisconnected:
        print("ERROR: El servidor SMTP se desconectó inesperadamente. Revisa la conexión o configuración.", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except smtplib.SMTPConnectError:
        print("ERROR: No se pudo conectar al servidor SMTP. Revisa la dirección y el puerto.", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: Fallo general al enviar correo de restablecimiento a {destinatario}: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

def enviar_correo_bienvenida(nombre_usuario, destinatario):
    """
    Envía un correo electrónico de bienvenida después de la verificación exitosa.
    Retorna True si el envío es exitoso, False en caso contrario.
    """
    print(f"DEBUG: Intentando enviar correo de bienvenida a: {destinatario}", file=sys.stderr)
    print(f"DEBUG: MAIL_USER (bienvenida): {MAIL_USER}", file=sys.stderr)
    if not MAIL_USER or not MAIL_PASS:
        print("ERROR: MAIL_USER o MAIL_PASS no están configurados para bienvenida. No se puede enviar correo.", file=sys.stderr)
        return False
    try:
        cuerpo = f"¡Hola {nombre_usuario}!\n\n" \
                 f"Tu cuenta en God of Eternia ha sido verificada exitosamente. ¡Bienvenido a la aventura!\n\n" \
                 f"¡Que disfrutes tu experiencia!\n" \
                 f"El equipo de God of Eternia."
        msg = MIMEText(cuerpo, 'plain', 'utf-8')
        msg['Subject'] = Header('¡Bienvenido a God of Eternia!', 'utf-8')
        msg['From'] = MAIL_USER
        msg['To'] = destinatario

        # ✅ CORRECCIÓN: Usar smtplib.SMTP_SSL y el puerto 465
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            # server.starttls() # No es necesario con SMTP_SSL
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(msg)
        print(f"DEBUG: Correo de bienvenida enviado exitosamente a: {destinatario}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"ERROR: Fallo al enviar correo de bienvenida a {destinatario}: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

def validar_password(password):
    """
    Valida que la contraseña cumpla con los requisitos de seguridad.
    Retorna None si es válida, o un mensaje de error si no lo es.
    """
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe contener al menos una letra mayúscula."
    if not re.search(r"[a-z]", password):
        return "La contraseña debe contener al menos una letra minúscula."
    if not re.search(r"[0-9]", password):
        return "La contraseña debe contener al menos un número."
    if not re.search(r"[!@#$%^&*()_+=\-{}[\]|:;<>,.?/~`]", password):
        # Esta regex incluye la mayoría de los caracteres especiales comunes. Puedes ajustarla.
        return "La contraseña debe contener al menos un carácter especial."
    return None # Retorna None si la contraseña es válida

@auth_bp.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        # Manejar la solicitud OPTIONS (preflight CORS)
        response = jsonify({'message': 'Preflight success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        return response

    conn = None
    cursor = None
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        # Asegúrate de que 'DescripUsuario' se pase, o usa un valor por defecto si no está presente.
        descrip_usuario = data.get('DescripUsuario', '') 

        if not all([username, email, password]):
            return jsonify({"error": "Faltan datos requeridos (username, email, password)."}), 400

        # Validaciones adicionales (ej. formato de correo, longitud de contraseña)
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"error": "Formato de correo electrónico inválido."}), 400
        
        password_error = validar_password(password)
        if password_error:
            return jsonify({"error": password_error}), 400

        # ✅ CAMBIO 1: Obtener la conexión usando get_db()
        conn = get_db()
        cursor = conn.cursor()

        # Normalizar el correo electrónico para la verificación de existencia
        normalized_email = email.strip().lower()

        # Verificar si el usuario o el correo ya existen
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, normalized_email))
        if cursor.fetchone():
            return jsonify({"error": "El nombre de usuario o correo electrónico ya está registrado."}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Generar código de verificación y tiempo de expiración
        verification_code = generar_codigo_verificacion()
        code_expiration = datetime.now() + timedelta(minutes=15) # Expira en 15 minutos

        # Generar un token UUID único para el usuario.
        # Esta columna 'token' puede ser usada para identificar públicamente al usuario
        # sin exponer el ID de la base de datos, o para fines de seguimiento.
        new_user_uuid_token = generar_uuid_token()

        # Insertar el nuevo usuario con el token UUID generado
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, token, verificado, verification_code, code_expiration, DescripUsuario)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (username, normalized_email, hashed_password, new_user_uuid_token, 0, verification_code, code_expiration, descrip_usuario)
        )
        # ✅ CAMBIO 2: Usar conn.commit()
        conn.commit()

        # Enviar correo de verificación
        if not enviar_correo_verificacion(email, verification_code):
            print(f"Advertencia: No se pudo enviar el correo de verificación a {email}", file=sys.stderr)
        
        # El cursor.close() se hace en el finally
        
        return jsonify({
            "message": "Registro exitoso. Se ha enviado un código de verificación a su correo.",
            "user_id": cursor.lastrowid # lastrowid obtiene el ID del usuario recién insertado
        }), 201

    except Exception as e:
        # Asegúrate de hacer un rollback si ocurre un error inesperado antes del commit
        if conn: # Verifica si la conexión está abierta
            conn.rollback()
        print(f"Error en /register: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al registrar usuario."}), 500
    finally:
        # ✅ CAMBIO 3: Asegurar el cierre de la conexión (y cursor)
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@auth_bp.route('/verificar', methods=['POST'])
def verify_email():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        email = data.get('email')
        verification_code = data.get('verification_code')

        if not all([email, verification_code]):
            return jsonify({"error": "Faltan datos requeridos (email, verification_code)."}), 400

        # ✅ CAMBIO 1: Obtener la conexión
        conn = get_db()
        cursor = conn.cursor()

        # Normalizar el correo electrónico para la búsqueda
        normalized_email = email.strip().lower()

        # Buscar usuario por email y código de verificación
        cursor.execute("SELECT id, username, verification_code, code_expiration, verificado FROM users WHERE email = %s", (normalized_email,))
        user_info = cursor.fetchone()

        if not user_info:
            return jsonify({"error": "Email no encontrado."}), 404
        
        user_id, username, stored_code, code_expiration, is_verified = user_info

        if is_verified:
            return jsonify({"message": "La cuenta ya está verificada."}), 200

        if stored_code != verification_code:
            return jsonify({"error": "Código de verificación inválido."}), 401

        if code_expiration is None or datetime.now() > code_expiration:
            # Limpiar el código expirado de la base de datos
            cursor.execute("UPDATE users SET verification_code = NULL, code_expiration = NULL WHERE id = %s", (user_id,))
            # ✅ CAMBIO 2: Usar conn.commit()
            conn.commit() # Aplicar el cambio para limpiar el token expirado
            return jsonify({"error": "El código de verificación ha expirado. Por favor, solicita uno nuevo."}), 401

        # Si el código es válido y no ha expirado, actualizar el estado 'verificado'
        cursor.execute("UPDATE users SET verificado = 1, verification_code = NULL, code_expiration = NULL WHERE id = %s", (user_id,))
        # ✅ CAMBIO 3: Usar conn.commit()
        conn.commit()

        # Enviar correo de bienvenida
        if not enviar_correo_bienvenida(username, email):
            print(f"Advertencia: No se pudo enviar el correo de bienvenida a {email}", file=sys.stderr)

        return jsonify({"message": "Correo electrónico verificado exitosamente."}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error en /verify-email: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al verificar correo."}), 500
    finally:
        # ✅ CAMBIO 4: Asegurar el cierre de la conexión (y cursor)
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@auth_bp.route('/login', methods=['POST'])
def login():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not all([email, password]):
            return jsonify({"error": "Faltan datos requeridos (email, password)."}), 400

        # ✅ CAMBIO 1: Obtener la conexión
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor) # Usar DictCursor aquí
        
        # Normalizar el correo electrónico para la búsqueda
        normalized_email = email.strip().lower()

        # Obtener id, username, password_hash Y verificado
        cursor.execute("SELECT id, username, email, password_hash, verificado FROM users WHERE email = %s", (normalized_email,))
        user = cursor.fetchone()
        
        if user and bcrypt.check_password_hash(user['password_hash'], password): # Usar 'password_hash' como clave
            user_id = user['id']
            username = user['username']
            user_email = user['email']
            is_verified = user['verificado']
            
            if is_verified == 0: # is_verified es 0 (False) o 1 (True)
                return jsonify({"error": "Cuenta no verificada. Por favor, verifica tu correo electrónico."}), 403
            
            # Generar el token JWT de acceso
            access_token_payload = {
                'user_id': user_id,
                'username': username,
                'email': user_email,
                'verificado': bool(is_verified)
            }
            # Convertir user_id a string para la identidad del JWT
            access_token = create_access_token(identity=str(user_id), additional_claims=access_token_payload)

            # Generar el token JWT de refresco
            # Convertir user_id a string para la identidad del JWT
            refresh_token = create_refresh_token(identity=str(user_id))

            return jsonify({
                "message": "Inicio de sesión exitoso.",
                "access_token": access_token,
                "refresh_token": refresh_token
            }), 200
        else:
            return jsonify({"error": "Credenciales inválidas."}), 401
    except Exception as e:
        print(f"Error en /login: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al iniciar sesión."}), 500
    finally:
        # ✅ CAMBIO 3: Asegurar el cierre de la conexión (y cursor)
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True) # Este endpoint requiere un refresh token válido
def refresh():
    """
    Endpoint para obtener un nuevo access token usando un refresh token.
    Ahora obtiene los últimos detalles del usuario de la DB para actualizar los claims.
    """
    current_user_id = get_jwt_identity() # Obtiene la identidad (user_id) del refresh token
    
    # Obtener los detalles actualizados del usuario desde la base de datos
    # NOTA: Se asume que get_user_details() internamente utiliza get_db()
    user_details = get_user_details(current_user_id) # Usamos la función importada

    if not user_details:
        print(f"ERROR: No se encontraron detalles para el usuario ID: {current_user_id} al refrescar token.", file=sys.stderr)
        return jsonify({"error": "Usuario no encontrado o detalles no disponibles para refrescar token."}), 404
    
    # Construir los claims del nuevo access token con la información más reciente
    access_token_payload = {
        'user_id': user_details['id'],
        'username': user_details['username'], # Usar el username actualizado
        'email': user_details['email'],
        'verificado': bool(user_details['verificado'])
    }
    
    # Re-crear el access token con la identidad y los claims actualizados
    new_access_token = create_access_token(identity=str(user_details['id']), additional_claims=access_token_payload)
    print(f"DEBUG: Nuevo access token generado para usuario ID: {current_user_id} con claims actualizados.", file=sys.stderr)
    return jsonify({"access_token": new_access_token}), 200

@auth_bp.route('/logeado', methods=['GET'])
@jwt_required() # Este endpoint ahora requiere un access token válido
def logeado():
    """
    Endpoint para verificar si un usuario está logeado (si el access token es válido).
    No consulta la base de datos para el campo 'token' del usuario.
    """
    current_user_id = get_jwt_identity() # Obtiene la identidad (user_id) del token
    claims = get_jwt() # Obtiene todos los claims del token

    print(f"DEBUG: /logeado - User ID from JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG: /logeado - Claims from JWT: {claims}", file=sys.stderr)

    if claims.get('verificado', False): # Verifica el claim 'verificado' del token
        return jsonify({
            "logeado": 1,
            "user_id": current_user_id,
            "username": claims.get('username'),
            "email": claims.get('email')
        }), 200
    else:
        # Esto debería ser manejado por el login si la cuenta no está verificada
        # Pero como fallback, si el token es válido pero el claim 'verificado' es falso
        return jsonify({"logeado": 0, "error": "Cuenta no verificada."}), 403

# REVERTIDO: Nombre de la ruta a /request-password-reset
@auth_bp.route('/request-password-reset', methods=['POST', 'OPTIONS'])
def request_password_reset(): # REVERTIDO: Nombre de la función
    """
    Endpoint para solicitar un restablecimiento de contraseña.
    Genera un CÓDIGO de 6 dígitos y lo envía al correo del usuario.
    """
    if request.method == 'OPTIONS': # Manejador para la solicitud OPTIONS (preflight)
        response = jsonify({'message': 'Preflight success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        return response

    data = request.get_json()
    email = data.get('email')

    print(f"DEBUG: Solicitud de restablecimiento de contraseña para el correo: {email}", file=sys.stderr)

    if not email:
        print("DEBUG: Correo electrónico no proporcionado en la solicitud.", file=sys.stderr)
        return jsonify({"error": "El correo electrónico es obligatorio."}), 400

    conn = None
    cursor = None # Inicializar cursor a None
    try:
        # Normalizar el correo electrónico antes de la consulta
        normalized_email = email.strip().lower()
        print(f"DEBUG: Correo normalizado para búsqueda: {normalized_email}", file=sys.stderr)

        # ✅ CAMBIO 1: Obtener la conexión
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor) 
        cursor.execute("SELECT id, email FROM users WHERE email = %s", (normalized_email,))
        user = cursor.fetchone()
        
        print(f"DEBUG: Resultado de la búsqueda de usuario en DB: {user}", file=sys.stderr)

        if user: # Solo procede si el usuario existe para evitar enumeración
            print(f"DEBUG: Usuario encontrado en la DB: {user['email']}", file=sys.stderr)
            # Generar CÓDIGO de restablecimiento y fecha de expiración
            reset_code = generar_codigo_verificacion() # Usamos la función para generar código de 6 dígitos
            expira = datetime.now() + timedelta(hours=1) # El código expira en 1 hora
            expira_str = expira.strftime('%Y-%m-%d %H:%M:%S')

            # Guardar el CÓDIGO de restablecimiento y su expiración en la base de datos
            # Se sigue usando la columna 'reset_token' para almacenar este código de 6 dígitos.
            print(f"DEBUG: Generado código de restablecimiento: {reset_code} para {email}", file=sys.stderr)
            cursor.execute("""
                UPDATE users SET reset_token = %s, reset_token_expira = %s WHERE email = %s
            """, (reset_code, expira_str, normalized_email)) # Usar normalized_email aquí
            # ✅ CAMBIO 3: Usar conn.commit()
            conn.commit()
            
            # Restaurado el control de errores al enviar correo de restablecimiento
            print(f"DEBUG: Llamando a enviar_correo_restablecimiento para {email} con código {reset_code}", file=sys.stderr)
            if not enviar_correo_restablecimiento(email, reset_code):
                print(f"Advertencia: enviar_correo_restablecimiento devolvió False para {email}", file=sys.stderr)
                # No se devuelve error al cliente por seguridad (evitar enumeración de usuarios)
            return jsonify({"message": "Se ha enviado un código para restablecer la contraseña a su correo."}), 200
        else:
            print(f"DEBUG: Usuario con correo {email} NO encontrado en la DB. (Después de fetchone)", file=sys.stderr)
            # Si el usuario no se encuentra, devolver 404 para evitar enumeración de usuarios
            return jsonify({"error": "Correo electrónico no registrado."}), 404
    except Exception as e:
        print(f"ERROR: Fallo general en /request-password-reset para {email}: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500
    finally:
        # ✅ CAMBIO 4: Asegurar el cierre de la conexión (y cursor)
        if cursor: # Asegura que el cursor se cierre incluso si hay un error
            cursor.close()
        if conn:
            conn.close()

# REVERTIDO: Nombre de la ruta a /reset-password
@auth_bp.route('/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    """
    Endpoint para restablecer la contraseña de un usuario usando un CÓDIGO de 6 dígitos.
    """
    if request.method == 'OPTIONS': # Manejador para la solicitud OPTIONS (preflight)
        response = jsonify({'message': 'Preflight success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        return response

    data = request.get_json()
    # REVERTIDO: El frontend enviará el código en el campo 'token', así que lo recibimos como 'token'
    reset_code = data.get('token') 
    new_password = data.get('new_password')

    print(f"DEBUG: Solicitud de restablecimiento de contraseña (POST) con código: {reset_code}", file=sys.stderr)

    if not all([reset_code, new_password]):
        print("DEBUG: Faltan datos requeridos (código o nueva contraseña).", file=sys.stderr)
        return jsonify({"error": "Código de restablecimiento y nueva contraseña son obligatorios."}), 400
    
    password_error = validar_password(new_password)
    if password_error:
        print(f"DEBUG: Error de validación de contraseña: {password_error}", file=sys.stderr)
        return jsonify({"error": password_error}), 400

    conn = None
    cursor = None # Inicializar cursor a None
    try:
        # ✅ CAMBIO 1: Obtener la conexión
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        # Buscar usuario por el CÓDIGO de restablecimiento (almacenado en 'reset_token')
        cursor.execute("SELECT email, reset_token_expira FROM users WHERE reset_token = %s", (reset_code,))
        user_info = cursor.fetchone()
        
        print(f"DEBUG: Resultado de la búsqueda de código de restablecimiento en DB: {user_info}", file=sys.stderr)

        if not user_info:
            print(f"DEBUG: Código de restablecimiento inválido: {reset_code}", file=sys.stderr)
            return jsonify({"error": "Código de restablecimiento inválido."}), 400

        email = user_info['email'] # Acceder por clave
        expira = user_info['reset_token_expira'] # Acceder por clave

        print(f"DEBUG: Código encontrado para email: {email}, expira en: {expira}", file=sys.stderr)
        if expira is None or datetime.now() > expira:
            print(f"DEBUG: Código de restablecimiento expirado o nulo para {email}. Expiración: {expira}", file=sys.stderr)
            cursor.execute("UPDATE users SET reset_token = NULL, reset_token_expira = NULL WHERE email = %s", (email,))
            # ✅ CAMBIO 3: Usar conn.commit()
            conn.commit()
            return jsonify({"error": "El código de restablecimiento ha expirado."}), 400

        hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        print(f"DEBUG: Contraseña hasheada para {email}. Actualizando DB...", file=sys.stderr)
        cursor.execute("""
            UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expira = NULL
            WHERE email = %s
        """, (hashed_new_password, email))
        # ✅ CAMBIO 4: Usar conn.commit()
        conn.commit()
        print(f"DEBUG: Contraseña restablecida exitosamente para {email}.", file=sys.stderr)
        return jsonify({"message": "Contraseña restablecida exitosamente."}), 200
    except Exception as e:
        print(f"ERROR: Fallo general en /reset-password: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500
    finally:
        # ✅ CAMBIO 5: Asegurar el cierre de la conexión (y cursor)
        if cursor:
            cursor.close()
        if conn:
            conn.close()