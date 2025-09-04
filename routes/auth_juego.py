# routes/auth_juego.py
import os
import json
import sys
import traceback
from flask import Blueprint, request, jsonify, current_app
from extensions import mysql, redis_client, socketio  # Importa socketio y redis_client
from MySQLdb.cursors import DictCursor
import uuid
from flask_jwt_extended import jwt_required, get_jwt_identity, exceptions as jwt_exceptions
from jwt.exceptions import ExpiredSignatureError as JWTExpiredSignatureError

# Crea un Blueprint para las rutas de autenticación del juego
auth_juego_bp = Blueprint('auth_juego', __name__)

@auth_juego_bp.route('/verify-game-access', methods=['POST'])
@jwt_required()
def verify_game_access():
    """
    Verifica el JWT del usuario, genera un token de un solo uso, lo guarda en Redis
    y lo emite a través de Socket.IO al cliente del juego.
    """
    try:
        current_user_id = get_jwt_identity()

        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT id, username, email, foto_perfil, verificado FROM users WHERE id = %s", (current_user_id,))
        user_data = cursor.fetchone()
        cursor.close()

        if not user_data:
            return jsonify({"message": "Usuario no encontrado"}), 404

        # Genera un token de un solo uso (one-time token) para el juego
        game_access_token = str(uuid.uuid4())
        
        # Almacena el token en Redis con una expiración de 60 segundos
        redis_key = f"game_token:{game_access_token}"
        redis_client.setex(redis_key, 60, current_user_id)

        print(f"DEBUG: Token de acceso al juego generado para el usuario {current_user_id}: {game_access_token}", file=sys.stderr)

        # Emitimos el token y los datos del usuario al cliente a través de Socket.IO
        # Esto permite que GDevelop, que está escuchando en el front-end, reciba los datos
        socketio.emit('game_access', {
            'game_access_token': game_access_token,
            'userData': user_data
        }, namespace='/')

        return jsonify({
            "message": "Acceso al juego verificado. Token de acceso generado.",
        }), 200

    except Exception as e:
        print(f"ERROR: Fallo al verificar el acceso al juego: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500

@auth_juego_bp.route('/get-game-data', methods=['POST'])
def get_game_data():
    """
    Recibe el token de un solo uso del juego, lo valida en Redis
    y retorna los datos completos del usuario.
    """
    data = request.get_json()
    game_access_token = data.get('game_access_token')

    if not game_access_token:
        return jsonify({"message": "Token de acceso al juego es requerido"}), 400

    redis_key = f"game_token:{game_access_token}"
    user_id = redis_client.get(redis_key)

    if not user_id:
        return jsonify({"message": "Token inválido o expirado"}), 401

    # Elimina el token inmediatamente para asegurar que sea de un solo uso
    redis_client.delete(redis_key)
    
    try:
        cursor = mysql.connection.cursor(DictCursor)
        user_id_int = int(user_id.decode('utf-8'))
        cursor.execute("SELECT id, username, email, foto_perfil, verificado FROM users WHERE id = %s", (user_id_int,))
        user_data = cursor.fetchone()
        cursor.close()

        if not user_data:
            return jsonify({"message": "Usuario no encontrado"}), 404

        return jsonify(user_data), 200

    except Exception as e:
        print(f"ERROR: Fallo al obtener los datos del juego: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500