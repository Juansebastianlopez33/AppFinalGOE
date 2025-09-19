import os
import json
import sys
import traceback
from flask import Blueprint, request, jsonify, current_app
from extensions import mysql, redis_client, socketio
from MySQLdb.cursors import DictCursor
import uuid
from flask_jwt_extended import jwt_required, get_jwt_identity
import requests
from slugify import slugify

# Blueprint para rutas del juego
auth_juego_bp = Blueprint("auth_juego", __name__)

# URL de la API de la IA
AI_API_URL = "http://100.121.255.122:8000/start-game"

# ---------------------------------------------------
# 1. Verificar acceso al juego y generar token temporal
# ---------------------------------------------------
@auth_juego_bp.route("/verify-game-access", methods=["POST"])
@jwt_required()
def verify_game_access():
    try:
        current_user_id = get_jwt_identity()
        print("DEBUG: current_user_id en verify_game_access =", current_user_id, file=sys.stderr)

        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute(
            "SELECT id, username, email, foto_perfil, verificado FROM users WHERE id = %s",
            (current_user_id,),
        )
        user_data = cursor.fetchone()
        cursor.close()

        if not user_data:
            return jsonify({"message": "Usuario no encontrado"}), 404

        game_access_token = str(uuid.uuid4())
        redis_key = f"game_token:{game_access_token}"
        redis_client.setex(redis_key, 60, current_user_id)

        socketio.emit(
            "game_access",
            {"game_access_token": game_access_token, "userData": user_data},
            namespace="/",
        )

        return jsonify({"message": "Acceso verificado", "token": game_access_token}), 200

    except Exception as e:
        print(f"ERROR en verify-game-access: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500

@auth_juego_bp.route("/check-course/<string:username>", methods=["GET"])
def check_course(username):
    """
    Verifica si un usuario ya tiene curso.json guardado.
    Devuelve {existe: 1} si lo tiene, {existe: 0} si no.
    """
    try:
        if not username:
            return jsonify({"message": "El nombre de usuario es requerido"}), 400

        # Buscar ID de usuario
        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if not user:
            return jsonify({"message": "Usuario no encontrado", "existe": 0}), 404

        user_id = str(user["id"])

        uploads_folder = current_app.config.get("UPLOAD_FOLDER_HOST_PATH", "./uploads")
        user_folder = os.path.join(uploads_folder, "users_data", user_id)
        curso_file = os.path.join(user_folder, "curso.json")

        if os.path.exists(curso_file):
            return jsonify({"existe": 1}), 200
        else:
            return jsonify({"existe": 0}), 200

    except Exception as e:
        print(f"ERROR en check_course: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500


# ---------------------------------------------------
# 2. Obtener datos completos de usuario usando token temporal
# ---------------------------------------------------
@auth_juego_bp.route("/get-game-data", methods=["POST"])
def get_game_data():
    data = request.get_json()
    game_access_token = data.get("game_access_token")

    if not game_access_token:
        return jsonify({"message": "Token de acceso requerido"}), 400

    redis_key = f"game_token:{game_access_token}"
    user_id = redis_client.get(redis_key)

    if not user_id:
        return jsonify({"message": "Token inválido o expirado"}), 401

    redis_client.delete(redis_key)

    try:
        cursor = mysql.connection.cursor(DictCursor)
        user_id_int = int(user_id.decode("utf-8"))
        cursor.execute(
            "SELECT id, username, email, foto_perfil, verificado FROM users WHERE id = %s",
            (user_id_int,),
        )
        user_data = cursor.fetchone()
        cursor.close()

        if not user_data:
            return jsonify({"message": "Usuario no encontrado"}), 404

        return jsonify(user_data), 200

    except Exception as e:
        print(f"ERROR en get-game-data: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500


@auth_juego_bp.route("/get-user-course/<string:username>", methods=["GET"])
def get_user_course(username):
    """
    Devuelve el curso.json que pertenece a un usuario,
    usando el nombre de usuario pasado en la URL.
    Ejemplo: GET /auth_juego/get-user-course/thebos135
    """
    try:
        if not username:
            return jsonify({"message": "El nombre de usuario es requerido"}), 400

        # 1. Buscar el ID del usuario en la BD
        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if not user:
            return jsonify({"message": "Usuario no encontrado"}), 404

        user_id = str(user["id"])

        # 2. Armar ruta al curso.json
        uploads_folder = current_app.config.get("UPLOAD_FOLDER_HOST_PATH", "./uploads")
        user_folder = os.path.join(uploads_folder, "users_data", user_id)
        curso_file = os.path.join(user_folder, "curso.json")

        if not os.path.exists(curso_file):
            return jsonify({"message": "El usuario no tiene curso asignado"}), 404

        # 3. Leer y devolver curso.json
        with open(curso_file, "r", encoding="utf-8") as f:
            curso_data = json.load(f)

        return jsonify({"usuario": username, "curso": curso_data}), 200

    except Exception as e:
        print(f"ERROR en get-user-course: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500


# ---------------------------------------------------
# 3. Iniciar sesión de juego con la IA
# ---------------------------------------------------
@auth_juego_bp.route("/start-game-session", methods=["POST"])
@jwt_required()
def start_game_session():
    try:
        data = request.get_json()
        print("DEBUG: Datos recibidos del frontend:", data, file=sys.stderr)

        tema = data.get("tema")
        dificultad = data.get("dificultad")
        curso = data.get("curso")

        if not all([tema, dificultad, curso]):
            return jsonify({"message": "Faltan datos de configuración"}), 400

        curso_slug = slugify(curso, lowercase=True)

        current_user_id = get_jwt_identity()
        print("DEBUG: current_user_id en start_game_session =", current_user_id, file=sys.stderr)

        if not current_user_id:
            return jsonify({"message": "Token inválido o sin identidad"}), 401

        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute(
            "SELECT username, foto_perfil FROM users WHERE id = %s",
            (current_user_id,),
        )
        user_details = cursor.fetchone()
        cursor.close()

        if not user_details:
            return jsonify({"message": "Usuario no encontrado"}), 404

        payload_ia = {
            "nombre_usuario": user_details["username"],
            "foto_perfil": user_details["foto_perfil"],
            "tema": tema,
            "dificultad": dificultad,
            "curso": curso_slug,
        }

        print("DEBUG: Payload enviado a la IA:", payload_ia, file=sys.stderr)

        response_ia = requests.post(AI_API_URL, json=payload_ia)
        print("DEBUG: Respuesta de la IA (status):", response_ia.status_code, file=sys.stderr)
        print("DEBUG: Respuesta de la IA (texto):", response_ia.text, file=sys.stderr)
        response_ia.raise_for_status()

        game_data = response_ia.json()

        curso_data = game_data.get("curso_data")
        preguntas_data = game_data.get("preguntas")

        if not curso_data or not preguntas_data:
            return jsonify({"message": "Respuesta de la IA incompleta"}), 500

        uploads_folder = current_app.config.get("UPLOAD_FOLDER_HOST_PATH", "./uploads")
        user_folder = os.path.join(uploads_folder, "users_data", str(current_user_id))
        os.makedirs(user_folder, exist_ok=True)

        with open(os.path.join(user_folder, "curso.json"), "w", encoding="utf-8") as f:
            json.dump(curso_data, f, indent=4, ensure_ascii=False)

        with open(os.path.join(user_folder, "preguntas.json"), "w", encoding="utf-8") as f:
            json.dump(preguntas_data, f, indent=4, ensure_ascii=False)

        print("DEBUG: Archivos guardados en:", user_folder, file=sys.stderr)

        return jsonify({"message": "Sesión de juego iniciada"}), 200

    except requests.exceptions.RequestException as e:
        print(f"ERROR comunicando con IA: {e}", file=sys.stderr)
        return jsonify({"message": "Error al comunicarse con IA", "error": str(e)}), 502

    except Exception as e:
        print(f"ERROR en start-game-session: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
