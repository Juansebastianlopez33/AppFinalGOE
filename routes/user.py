from flask import Blueprint, request, jsonify, current_app
from extensions import mysql
from MySQLdb.cursors import DictCursor
from werkzeug.utils import secure_filename
import os
import sys
import traceback
import jwt
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

# ✅ Import directo desde la raíz
from utils import upload_image_to_cloudinary


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

@user_bp.route("/perfil/foto", methods=["PUT"])
@jwt_required()
def actualizar_foto_perfil():
    user_id = get_jwt_identity()
    print("📌 [DEBUG] Usuario autenticado:", user_id)

    if "profile_picture" not in request.files:
        print("❌ [DEBUG] No se recibió el archivo 'profile_picture'")
        return jsonify({"error": "No se envió ninguna imagen"}), 400

    file = request.files["profile_picture"]
    print("📌 [DEBUG] Archivo recibido:", file.filename, "Content-Type:", file.content_type)

    try:
        public_id = f"fotos_perfil/{user_id}/profile_picture"
        print("📌 [DEBUG] Subiendo a Cloudinary con public_id:", public_id)

        upload_result = upload_image_to_cloudinary(
            file=file,
            folder=f"fotos_perfil/{user_id}",
            public_id="profile_picture"
        )

        print("✅ [DEBUG] Respuesta Cloudinary:", upload_result)

        foto_url = upload_result.get("secure_url")
        version = upload_result.get("version")
        print("📌 [DEBUG] URL final:", foto_url, "Versión:", version)

        if not foto_url:
            print("❌ [DEBUG] Cloudinary no devolvió secure_url")
            return jsonify({"error": "Error al obtener URL de Cloudinary"}), 500

        # Guardar en DB (tabla users ✅)
        cursor = mysql.connection.cursor()
        cursor.execute(
            "UPDATE users SET foto_perfil = %s WHERE id = %s",
            (foto_url, user_id)
        )
        mysql.connection.commit()
        cursor.close()

        print("✅ [DEBUG] Foto actualizada en la DB")

        return jsonify({
            "message": "Foto de perfil actualizada correctamente",
            "foto_perfil_url": foto_url,
            "version": version
        }), 200

    except Exception as e:
        print("❌ [DEBUG] Excepción en actualizar_foto_perfil:", str(e))
        traceback.print_exc()
        return jsonify({"error": "Error interno del servidor", "detalle": str(e)}), 500
