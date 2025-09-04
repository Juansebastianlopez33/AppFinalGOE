from flask import Blueprint, request, jsonify, current_app
from extensions import mysql
from MySQLdb.cursors import DictCursor
from werkzeug.utils import secure_filename
import os
import sys
import traceback
import jwt
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

user_bp = Blueprint('user', __name__)

def get_user_from_jwt(auth_header):
    token = None
    if auth_header and "Bearer " in auth_header:
        token = auth_header.split(" ")[1]
    else:
        return None

    if not token:
        return None

    try:
        jwt_secret_key = current_app.config.get('JWT_SECRET_KEY')
        if not jwt_secret_key:
            return None

        payload = jwt.decode(token, jwt_secret_key, algorithms=['HS256'])
        return payload
    except Exception:
        return None

def get_user_details(user_id):
    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT id, username, email, DescripUsuario, verificado, foto_perfil FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if user['foto_perfil']:
            user['foto_perfil_url'] = user['foto_perfil']
        else:
            base_url = current_app.config.get('API_BASE_URL', request.url_root.rstrip('/'))
            user['foto_perfil_url'] = f"{base_url}/uploads/default-avatar.png"

        user['verificado'] = bool(user['verificado'])
        user.pop('foto_perfil', None)

        return user
    except Exception:
        return None
    finally:
        if cursor:
            cursor.close()

@user_bp.route('/logeado', methods=['GET'])
def logeado():
    auth_header = request.headers.get('Authorization')
    user_payload = get_user_from_jwt(auth_header)

    if not user_payload:
        return jsonify({"logeado": 0, "error": "Token inválido o ausente"}), 401

    current_user_id = user_payload.get('user_id')
    user_details_from_db = get_user_details(current_user_id)

    if not user_details_from_db:
        return jsonify({"logeado": 0, "error": "Usuario no encontrado"}), 404

    if not user_details_from_db.get('verificado'):
        return jsonify({"logeado": 0, "error": "Cuenta no verificada"}), 403

    return jsonify({
        "logeado": 1,
        "user_id": user_details_from_db.get('id'),
        "username": user_details_from_db.get('username'),
        "email": user_details_from_db.get('email'),
        "verificado": user_details_from_db.get('verificado'),
        "foto_perfil": user_details_from_db.get('foto_perfil_url'),
        "DescripUsuario": user_details_from_db.get('DescripUsuario')
    }), 200

@user_bp.route('/perfil', methods=['GET', 'PUT'])
@jwt_required()
def perfil():
    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado"}), 403

    user_details_from_db = get_user_details(current_user_id)
    if not user_details_from_db:
        return jsonify({"error": "Usuario no encontrado"}), 404

    conn = mysql.connection
    cursor = conn.cursor()
    try:
        if request.method == 'GET':
            dict_cursor = conn.cursor(DictCursor)
            dict_cursor.execute("SELECT dificultad_id, puntaje_actual FROM partidas WHERE user_id = %s", (current_user_id,))
            puntajes = dict_cursor.fetchall()
            dict_cursor.close()

            return jsonify({
                "username": user_details_from_db.get('username'),
                "email": user_details_from_db.get('email'),
                "descripcion": user_details_from_db.get('DescripUsuario'),
                "foto_perfil": user_details_from_db.get('foto_perfil_url'),
                "verificado": user_details_from_db.get('verificado'),
                "puntajes": [{"dificultad": p['dificultad_id'], "puntaje": p['puntaje_actual']} for p in puntajes]
            }), 200

        elif request.method == 'PUT':
            data = request.get_json()
            nueva_descripcion = data.get("descripcion")
            nuevo_username = data.get("username")

            if nueva_descripcion is None or nuevo_username is None:
                return jsonify({"error": "Faltan campos requeridos"}), 400

            cursor.execute("SELECT id FROM users WHERE username = %s AND id != %s", (nuevo_username, current_user_id))
            if cursor.fetchone():
                return jsonify({"error": "El nombre de usuario ya está en uso"}), 409

            cursor.execute("UPDATE users SET DescripUsuario = %s, username = %s WHERE id = %s", (nueva_descripcion, nuevo_username, current_user_id))
            mysql.connection.commit()

            return jsonify({"mensaje": "Perfil actualizado correctamente"}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "Error interno al actualizar perfil"}), 500
    finally:
        if cursor:
            cursor.close()

@user_bp.route('/perfil/foto', methods=['PUT'])
@jwt_required()
def upload_profile_picture():
    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado"}), 403

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT foto_perfil FROM users WHERE id = %s", (current_user_id,))
        result = cursor.fetchone()
        old_profile_picture_url = result[0] if result else None

        if 'profile_picture' not in request.files:
            return jsonify({'error': 'Falta el archivo "profile_picture".'}), 400

        file = request.files['profile_picture']
        if file.filename == '':
            return jsonify({'error': 'Archivo vacío'}), 400

        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
        if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            upload_folder = current_app.config.get('UPLOAD_FOLDER')

            base_profile_pictures_path = os.path.join(upload_folder, 'fotos_perfil')
            user_folder = os.path.join(base_profile_pictures_path, str(current_user_id))
            os.makedirs(user_folder, exist_ok=True)

            new_filename = secure_filename(f"profile_picture.{file_extension}")
            filepath = os.path.join(user_folder, new_filename)

            if old_profile_picture_url:
                old_filename_from_url = os.path.basename(old_profile_picture_url)
                old_filepath = os.path.join(user_folder, old_filename_from_url)
                if os.path.exists(old_filepath) and old_filepath != filepath and os.path.isfile(old_filepath):
                    os.remove(old_filepath)

            file.save(filepath)

            base_url = current_app.config.get('API_BASE_URL', request.url_root.rstrip('/'))
            image_url = f"{base_url}/uploads/fotos_perfil/{current_user_id}/{new_filename}"

            cursor.execute("UPDATE users SET foto_perfil = %s WHERE id = %s", (image_url, current_user_id))
            mysql.connection.commit()
            return jsonify({'message': 'Foto actualizada', 'foto_perfil_url': image_url}), 200
        else:
            return jsonify({'error': 'Formato de archivo no permitido'}), 400
    except Exception:
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error al actualizar foto de perfil"}), 500
    finally:
        if cursor:
            cursor.close()
