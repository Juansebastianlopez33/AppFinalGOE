from flask import Blueprint, request, jsonify, current_app
# ❌ Reemplazado: from extensions import mysql, bcrypt
# ✅ MODIFICADO: Importa get_db para PyMySQL
from extensions import bcrypt, get_db 
import random
import string
from datetime import datetime, timedelta
# ❌ REMOVIDAS: No son necesarias si se usa utils.py
# from email.mime.text import MIMEText
# from email.header import Header
# import smtplib
import os
import re
import sys
import traceback
import uuid 

# Importar funciones de Flask-JWT-Extended
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt, set_access_cookies, set_refresh_cookies

from dotenv import load_dotenv
# ❌ Reemplazado: from MySQLdb.cursors import DictCursor
# ✅ MODIFICADO: Importa PyMySQL para cursores
import pymysql.cursors 

# IMPORTANTE: Importar get_user_details desde user.py
from routes.user import get_user_details
# ✅ AÑADIDO: Importar la función de envío de correo CORRECTA desde utils.py
from utils import enviar_correo_verificacion 

load_dotenv()

auth_bp = Blueprint('auth', __name__)

# ❌ REMOVIDAS: Las variables se acceden desde utils.py
# MAIL_USER = os.getenv('MAIL_USER')
# MAIL_PASS = os.getenv('MAIL_PASS')

def generar_uuid_token():
    """Genera un UUID único para el campo 'token' en la tabla users."""
    return str(uuid.uuid4())

def generar_codigo_verificacion():
    """Genera un código de verificación numérico de 6 dígitos."""
    return str(random.randint(100000, 999999))

# ❌ FUNCIÓN REMOVIDA: Ya se importa desde utils.py, lo que soluciona el ETIMEDOUT.
# def enviar_correo_verificacion(destinatario, codigo):
#    ...

# ---------------------------------------------------
# RUTA: Registro de usuario
# ---------------------------------------------------
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    DescripUsuario = data.get('DescripUsuario')
    
    conn = None
    cursor = None

    if not all([username, email, password]):
        return jsonify({"error": "Faltan campos requeridos."}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "Formato de correo electrónico inválido."}), 400

    if len(password) < 8:
        return jsonify({"error": "La contraseña debe tener al menos 8 caracteres."}), 400

    try:
        # ✅ FIX DB: Obtener conexión PyMySQL
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. Verificar si el usuario o email ya existen
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return jsonify({"error": "El nombre de usuario o el correo ya están registrados."}), 409

        # 2. Generar hash de contraseña, código y token
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        verification_code = generar_codigo_verificacion()
        code_expiration = datetime.now() + timedelta(minutes=15)
        uuid_token = generar_uuid_token()

        # 3. Insertar nuevo usuario
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, verification_code, code_expiration, DescripUsuario, token) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, email, hashed_password, verification_code, code_expiration, DescripUsuario, uuid_token))
        # ✅ FIX DB
        conn.commit()
        
        # 4. Enviar correo de verificación (usa la función de utils.py con SMTP_SSL:465)
        if not enviar_correo_verificacion(email, verification_code):
            print(f"ADVERTENCIA: Falló el envío del correo de verificación a {email}. (Timeout probable)", file=sys.stderr)
        
        print(f"DEBUG: Nuevo usuario registrado: {username}, ID: {cursor.lastrowid}", file=sys.stderr)

        return jsonify({
            "message": "Registro exitoso. Se ha enviado un código de verificación a su correo.",
            "user_id": cursor.lastrowid
        }), 201

    except Exception as e:
        # ✅ FIX DB
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo en /register: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor durante el registro."}), 500

    finally:
        if cursor:
            cursor.close()

# ---------------------------------------------------
# RUTA: Verificar código de registro
# ---------------------------------------------------
@auth_bp.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    conn = None
    cursor = None

    if not all([email, code]):
        return jsonify({"error": "Faltan campos requeridos."}), 400

    try:
        # ✅ FIX DB: Obtener conexión PyMySQL
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 1. Buscar usuario y código
        cursor.execute("SELECT id, verificado, verification_code, code_expiration FROM users WHERE email = %s", (email,))
        user_info = cursor.fetchone()

        if not user_info:
            return jsonify({"error": "Usuario no encontrado."}), 404

        if user_info['verificado']:
            return jsonify({"message": "Cuenta ya verificada."}), 200

        stored_code = user_info['verification_code']
        expira = user_info['code_expiration']

        # 2. Verificar código y expiración
        if stored_code is None or stored_code != code:
            print(f"DEBUG: Código incorrecto para {email}. Ingresado: {code}, Almacenado: {stored_code}", file=sys.stderr)
            return jsonify({"error": "Código de verificación incorrecto."}), 400

        if expira is None or datetime.now() > expira:
            # Limpiar el código expirado
            cursor.execute("UPDATE users SET verification_code = NULL, code_expiration = NULL WHERE email = %s", (email,))
            # ✅ FIX DB
            conn.commit()
            print(f"DEBUG: Código expirado para {email}. Expiración: {expira}", file=sys.stderr)
            return jsonify({"error": "El código de verificación ha expirado. Por favor, solicite uno nuevo."}), 400

        # 3. Marcar como verificado y limpiar campos de verificación
        cursor.execute("""
            UPDATE users SET 
                verificado = TRUE, 
                verification_code = NULL, 
                code_expiration = NULL
            WHERE email = %s
        """, (email,))
        # ✅ FIX DB
        conn.commit()
        
        # 4. Generar tokens de acceso
        access_token = create_access_token(identity=user_info['id'])
        refresh_token = create_refresh_token(identity=user_info['id'])

        response = jsonify({"message": "Cuenta verificada exitosamente.", "user_id": user_info['id']})
        
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        
        print(f"DEBUG: Cuenta de {email} verificada y tokens emitidos.", file=sys.stderr)
        return response, 200

    except Exception as e:
        # ✅ FIX DB
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo en /verify-code: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor durante la verificación."}), 500
    finally:
        if cursor:
            cursor.close()

# ---------------------------------------------------
# RUTA: Iniciar sesión
# ---------------------------------------------------
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email_or_username = data.get('email_or_username')
    password = data.get('password')
    
    conn = None
    cursor = None

    if not all([email_or_username, password]):
        return jsonify({"error": "Faltan campos requeridos."}), 400

    try:
        # ✅ FIX DB: Obtener conexión PyMySQL
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. Buscar usuario por email o username y obtener hash de contraseña
        cursor.execute("""
            SELECT id, email, password_hash, verificado 
            FROM users 
            WHERE email = %s OR username = %s
        """, (email_or_username, email_or_username))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Credenciales inválidas."}), 401

        # 2. Verificar contraseña y estado de verificación
        if not bcrypt.check_password_hash(user['password_hash'], password):
            return jsonify({"error": "Credenciales inválidas."}), 401
        
        if not user['verificado']:
             return jsonify({"error": "Cuenta no verificada. Por favor, revise su correo o solicite un nuevo código."}), 403

        # 3. Generar tokens
        user_id = user['id']
        access_token = create_access_token(identity=user_id)
        refresh_token = create_refresh_token(identity=user_id)
        
        # 4. Obtener detalles completos del usuario
        user_details = get_user_details(user_id)
        
        if not user_details:
             return jsonify({"error": "Error al obtener detalles del usuario."}), 500

        response = jsonify({
            "message": "Inicio de sesión exitoso.", 
            "user": user_details
        })
        
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        
        print(f"DEBUG: Usuario ID {user_id} ({user['email']}) ha iniciado sesión.", file=sys.stderr)
        return response, 200

    except Exception as e:
        print(f"ERROR: Fallo en /login: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500
    finally:
        if cursor:
            cursor.close()

# ---------------------------------------------------
# RUTA: Logout (Cerrar sesión)
# ---------------------------------------------------
@auth_bp.route('/logout', methods=['POST'])
def logout():
    response = jsonify({"message": "Sesión cerrada correctamente."})
    return response, 200

# ---------------------------------------------------
# RUTA: Refrescar Token de Acceso
# ---------------------------------------------------
@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user_id = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user_id)
    
    response = jsonify({})
    set_access_cookies(response, new_access_token)
    
    print(f"DEBUG: Token de acceso refrescado para user ID {current_user_id}.", file=sys.stderr)
    return response, 200

# ---------------------------------------------------
# RUTA: Solicitar código de restablecimiento de contraseña
# ---------------------------------------------------
@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    
    conn = None
    cursor = None

    if not email:
        return jsonify({"error": "Falta el correo electrónico."}), 400

    try:
        # ✅ FIX DB: Obtener conexión PyMySQL
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. Buscar usuario
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            print(f"ADVERTENCIA: Intento de restablecimiento de contraseña para email no encontrado: {email}", file=sys.stderr)
            return jsonify({"message": "Si el correo está registrado, recibirá un enlace/código de restablecimiento."}), 200

        # 2. Generar código y tiempo de expiración
        reset_code = generar_codigo_verificacion()
        reset_expiration = datetime.now() + timedelta(minutes=30) 

        # 3. Guardar en la base de datos
        cursor.execute("""
            UPDATE users SET reset_token = %s, reset_token_expira = %s 
            WHERE email = %s
        """, (reset_code, reset_expiration, email))
        # ✅ FIX DB
        conn.commit()
        
        # 4. Enviar correo electrónico (usa la función de utils.py con SMTP_SSL:465)
        if not enviar_correo_verificacion(email, reset_code):
             print(f"ADVERTENCIA: Falló el envío del correo de restablecimiento a {email}. (Timeout probable)", file=sys.stderr)
        
        print(f"DEBUG: Código de restablecimiento generado y enviado a {email}. Código: {reset_code}", file=sys.stderr)

        return jsonify({"message": "Si el correo está registrado, recibirá un código de restablecimiento."}), 200

    except Exception as e:
        # ✅ FIX DB
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo en /forgot-password: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500
    finally:
        if cursor:
            cursor.close()

# ---------------------------------------------------
# RUTA: Restablecer contraseña con código
# ---------------------------------------------------
@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    reset_code = data.get('code')
    new_password = data.get('new_password')
    
    conn = None
    cursor = None

    if not all([email, reset_code, new_password]):
        return jsonify({"error": "Faltan campos requeridos."}), 400
    
    if len(new_password) < 8:
        return jsonify({"error": "La nueva contraseña debe tener al menos 8 caracteres."}), 400

    try:
        # ✅ FIX DB: Obtener conexión PyMySQL
        conn = get_db()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. Buscar usuario y token
        cursor.execute("SELECT reset_token, reset_token_expira FROM users WHERE email = %s", (email,))
        user_info = cursor.fetchone()

        if not user_info:
            return jsonify({"error": "Usuario no encontrado."}), 404

        # 2. Verificar código
        stored_token = user_info['reset_token']
        if stored_token is None or stored_token != reset_code:
            print(f"DEBUG: Código de restablecimiento incorrecto para {email}.", file=sys.stderr)
            return jsonify({"error": "Código de restablecimiento incorrecto."}), 400

        # 3. Verificar expiración
        expira = user_info['reset_token_expira']
        
        print(f"DEBUG: Código encontrado para email: {email}, expira en: {expira}", file=sys.stderr)
        if expira is None or datetime.now() > expira:
            print(f"DEBUG: Código de restablecimiento expirado o nulo para {email}. Expiración: {expira}", file=sys.stderr)
            # Limpiar el token expirado
            cursor.execute("UPDATE users SET reset_token = NULL, reset_token_expira = NULL WHERE email = %s", (email,))
            # ✅ FIX DB
            conn.commit()
            return jsonify({"error": "El código de restablecimiento ha expirado."}), 400

        # 4. Restablecer contraseña y limpiar token
        hashed_new_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        print(f"DEBUG: Contraseña hasheada para {email}. Actualizando DB...", file=sys.stderr)
        cursor.execute("""
            UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expira = NULL
            WHERE email = %s
        """, (hashed_new_password, email))
        # ✅ FIX DB
        conn.commit()
        print(f"DEBUG: Contraseña restablecida exitosamente para {email}.", file=sys.stderr)
        return jsonify({"message": "Contraseña restablecida exitosamente."}), 200
        
    except Exception as e:
        # ✅ FIX DB
        if conn:
            conn.rollback()
        print(f"ERROR: Fallo general en /reset-password: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor."}), 500
    finally:
        if cursor:
            cursor.close()

