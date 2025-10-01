import os
import json
import random
import sys
import traceback
from flask import Blueprint, render_template_string, jsonify, current_app, request, redirect
# ❌ Reemplazar: from extensions import mysql, redis_client, socketio
# ✅ Nueva importación:
from extensions import get_db, redis_client, socketio
# ❌ Reemplazar: from MySQLdb.cursors import DictCursor
# ✅ Nueva importación:
import pymysql.cursors
import uuid
from flask_jwt_extended import jwt_required, get_jwt_identity
import requests
from slugify import slugify
from utils import upload_json_to_cloudinary, download_json_from_cloudinary

# Blueprint para rutas del juego
auth_juego_bp = Blueprint("auth_juego", __name__)

# URL de la API de la IA
AI_API_URL = "http://100.121.255.122:8000/start-game"

# Función para cargar y guardar las preguntas
def load_and_save_questions(username, action="load", data=None):
    """Carga o guarda las preguntas del usuario en Cloudinary (URL guardada en BD)."""
    conn = None
    cursor = None
    try:
        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id, preguntas_url FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user:
            return None

        user_id = str(user["id"])

        if action == "load":
            preguntas_url = user.get("preguntas_url")
            if not preguntas_url:
                return []
            return download_json_from_cloudinary(preguntas_url)

        elif action == "save" and data is not None:
            url = upload_json_to_cloudinary(
                data,
                folder=f"cursosUsuarios/{user_id}",
                public_id="preguntas"  # 👈 siempre se llama "preguntas.json"
            )
            if url:
                # Se necesita un nuevo cursor para la transacción UPDATE si el anterior ya se usó para SELECT
                # O reutilizar el cursor si la lógica de PyMySQL lo permite, pero es más seguro re-abrir/reutilizar
                # En este caso, reutilizaré 'cursor' si no está cerrado.
                # Como ya se llamó fetchone, lo mejor es reabrir la conexión para la transacción si PyMySQL no maneja bien la reutilización del cursor.
                # Dado que PyMySQL permite múltiples cursores en una conexión, mantendré la estructura simple:
                
                # Se podría reabrir/reutilizar la conexión y el cursor, pero por simplicidad de PyMySQL
                # la conexión actual está abierta. Solo necesito un cursor simple para la actualización.
                
                # Para evitar problemas con el cursor de DictCursor anterior, aseguramos el cierre de ese cursor
                cursor.close()
                cursor = conn.cursor() # Cursor simple para UPDATE

                cursor.execute("UPDATE users SET preguntas_url = %s WHERE id = %s", (url, user_id))
                # ✅ CAMBIO 3: Usar conn.commit()
                conn.commit()
                # cursor.close() se hará en finally
                return True
            return False

    except Exception as e:
        print(f"ERROR en load_and_save_questions: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None
    finally:
        # ✅ CAMBIO 4: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ---------------------------------------------------
# 1. Verificar acceso al juego y generar token temporal
# ---------------------------------------------------
@auth_juego_bp.route("/verify-game-access", methods=["POST"])
@jwt_required()
def verify_game_access():
    conn = None
    cursor = None
    try:
        current_user_id = get_jwt_identity()
        print("DEBUG: current_user_id en verify_game_access =", current_user_id, file=sys.stderr)

        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT id, username, email, foto_perfil, verificado FROM users WHERE id = %s",
            (current_user_id,),
        )
        user_data = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user_data:
            return jsonify({"message": "Usuario no encontrado"}), 404

        game_access_token = str(uuid.uuid4())
        redis_key = f"game_token:{game_access_token}"
        # El tiempo de expiración es corto (60 segundos)
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
    finally:
        # ✅ CAMBIO 3: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@auth_juego_bp.route("/check-course/<string:username>", methods=["GET"])
def check_course(username):
    """
    Verifica si un usuario ya tiene curso.json guardado.
    Devuelve {existe: 1} si lo tiene, {existe: 0} si no.
    """
    conn = None
    cursor = None
    try:
        if not username:
            return jsonify({"message": "El nombre de usuario es requerido"}), 400

        # Buscar ID de usuario
        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user:
            return jsonify({"message": "Usuario no encontrado", "existe": 0}), 404

        user_id = str(user["id"])

        # NOTE: Si la URL del curso se guarda en la DB (como en start-game-session), esta lógica de archivo local es incorrecta.
        # Asumiendo que la lógica *debe* verificar el archivo local si existe (por historial de código)
        # o que en realidad se quería verificar 'curso_url' en la DB (como en get_user_course).
        # MANTENDRÉ la lógica de archivo local, pero lo ideal sería usar 'curso_url'.
        # Como no tengo la estructura de carpetas, mantendré el código original, pero es una potencial falla.
        
        # **Usando la lógica de archivo local del código original:**
        uploads_folder = current_app.config.get("UPLOAD_FOLDER_HOST_PATH", "./uploads")
        user_folder = os.path.join(uploads_folder, "users_data", user_id)
        curso_file = os.path.join(user_folder, "curso.json")

        if os.path.exists(curso_file):
            return jsonify({"existe": 1}), 200
        else:
            return jsonify({"existe": 0}), 200
        # **Alternativa más robusta (si curso_url se usa):**
        # cursor.execute("SELECT curso_url FROM users WHERE id = %s", (user_id,))
        # user_url = cursor.fetchone()
        # return jsonify({"existe": 1}) if user_url and user_url['curso_url'] else jsonify({"existe": 0}), 200


    except Exception as e:
        print(f"ERROR en check_course: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 3: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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
    user_id_bytes = redis_client.get(redis_key)

    if not user_id_bytes:
        return jsonify({"message": "Token inválido o expirado"}), 401

    redis_client.delete(redis_key)
    user_id = user_id_bytes.decode("utf-8")

    conn = None
    cursor = None
    try:
        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        user_id_int = int(user_id)
        cursor.execute(
            "SELECT id, username, email, foto_perfil, verificado FROM users WHERE id = %s",
            (user_id_int,),
        )
        user_data = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user_data:
            return jsonify({"message": "Usuario no encontrado"}), 404

        return jsonify(user_data), 200

    except Exception as e:
        print(f"ERROR en get-game-data: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 3: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@auth_juego_bp.route("/get-user-course/<string:username>", methods=["GET"])
def get_user_course(username):
    """Devuelve el curso.json del usuario desde Cloudinary."""
    conn = None
    cursor = None
    try:
        if not username:
            return jsonify({"message": "El nombre de usuario es requerido"}), 400

        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id, curso_url FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user:
            return jsonify({"message": "Usuario no encontrado"}), 404

        if not user["curso_url"]:
            return jsonify({"message": "El usuario no tiene curso asignado"}), 404

        curso_data = download_json_from_cloudinary(user["curso_url"])

        return jsonify({"usuario": username, "curso": curso_data}), 200

    except Exception as e:
        print(f"ERROR en get-user-course: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 3: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ---------------------------------------------------
# 3. Iniciar sesión de juego con la IA
# ---------------------------------------------------
@auth_juego_bp.route("/start-game-session", methods=["POST"])
@jwt_required()
def start_game_session():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        tema = data.get("tema")
        dificultad = data.get("dificultad")
        curso = data.get("curso")

        if not all([tema, dificultad, curso]):
            return jsonify({"message": "Faltan datos de configuración"}), 400

        curso_slug = slugify(curso, lowercase=True)
        current_user_id = get_jwt_identity()

        if not current_user_id:
            return jsonify({"message": "Token inválido o sin identidad"}), 401

        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT username, foto_perfil FROM users WHERE id = %s", (current_user_id,))
        user_details = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user_details:
            return jsonify({"message": "Usuario no encontrado"}), 404

        payload_ia = {
            "nombre_usuario": user_details["username"],
            "foto_perfil": user_details["foto_perfil"],
            "tema": tema,
            "dificultad": dificultad,
            "curso": curso_slug,
        }
        response_ia = requests.post(AI_API_URL, json=payload_ia)
        response_ia.raise_for_status()
        game_data = response_ia.json()

        curso_data = game_data.get("curso_data")
        preguntas_data = game_data.get("preguntas")

        if not curso_data or not preguntas_data:
            return jsonify({"message": "Respuesta de la IA incompleta"}), 500

        # 🚀 Guardar en Cloudinary con la carpeta cursosUsuarios/<id>
        curso_url = upload_json_to_cloudinary(
            curso_data,
            folder=f"cursosUsuarios/{current_user_id}",
            public_id="curso"
        )
        preguntas_url = upload_json_to_cloudinary(
            preguntas_data,
            folder=f"cursosUsuarios/{current_user_id}",
            public_id="preguntas"
        )

        # Guardar URLs en la base de datos
        # Se puede reutilizar 'conn', pero es mejor asegurar un cursor simple para el UPDATE.
        # Ya se cerró el DictCursor arriba para el SELECT. Reabrimos un cursor simple.
        cursor.close()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE users SET curso_url = %s, preguntas_url = %s WHERE id = %s",
            (curso_url, preguntas_url, current_user_id)
        )
        # ✅ CAMBIO 3: Usar conn.commit()
        conn.commit()
        # cursor.close() y conn.close() ahora en finally

        return jsonify({"message": "Sesión de juego iniciada"}), 200

    except requests.exceptions.RequestException as e:
        # Si hay un error de Request, no hay que hacer rollback a menos que se haya hecho un commit anterior
        print(f"ERROR comunicando con IA: {e}", file=sys.stderr)
        return jsonify({"message": "Error al comunicarse con IA", "error": str(e)}), 502
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR en start-game-session: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 4: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@auth_juego_bp.route("/game-questions-ui/<string:username>", methods=["GET"])
def game_questions_ui(username):
    # La ruta UI solo retorna HTML, no tiene interacciones con la DB de Flask-MySQL.
    # El código HTML/JS hace peticiones a otras rutas que sí han sido modificadas.
    # Por lo tanto, no se requiere cambiar el contenido de esta función.
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aventura de Preguntas</title>
        <link href="https://fonts.googleapis.com/css2?family=MedievalSharp&display=swap" rel="stylesheet">
        <style>
            /* ======================
               Variables de la forja
               ====================== */
            :root {{
                --forge-border-glow: #e07b0f;
                --forge-core: #2b1e16;
                --flame-yellow: #ffd36b;
                --flame-orange: #ff6b15;
                --flame-red: #d93800;
                --ember: rgba(255,180,60,0.9);
                --modal-bg: radial-gradient(circle at 50% 120%, #2b1e16 0%, #1a0f0a 80%, #0c0805 100%);
            }}

            /* ======================
               Estilo de la página
               ====================== */
            body {{
                font-family: 'MedievalSharp', cursive;
                background: radial-gradient(circle at 50% 50%, #1a0f0a 0%, #0c0805 100%);
                color: var(--flame-yellow);
                margin: 0;
                padding: 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                min-height: 100vh;
                box-sizing: border-box;
                position: relative;
                overflow: hidden;
            }}

            h1 {{
                color: #ffda88;
                text-shadow: 0 0 10px rgba(255, 180, 0, 0.7);
                font-size: 2.5rem;
                margin-bottom: 2rem;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}

            /* ======================
               Contenedor principal de pregunta (estilo forja)
               ====================== */
            #modal-pregunta {{
                position: relative;
                border-radius: 12px;
                background: var(--modal-bg);
                border: 2px solid #803300;
                box-shadow: 0 0 20px rgba(255,100,0,0.4), inset 0 0 10px rgba(255,180,100,0.2);
                color: var(--flame-yellow);
                font-weight: bold;
                letter-spacing: 1px;
                overflow: hidden;
                padding: 2rem;
                max-width: 600px;
                width: 90%;
                margin-top: 20px;
            }}
            
            /* Efectos de brillo, brasas y cenizas para el contenedor principal */
            #modal-pregunta::before,
            #modal-pregunta::after {{
                content: "";
                position: absolute;
                inset: -10px;
                border-radius: inherit;
                z-index: 0;
                pointer-events: none;
            }}
            
            #modal-pregunta::before {{
                background:
                    radial-gradient(50% 35% at 50% 10%, rgba(255,210,120,0.15), transparent 20%),
                    radial-gradient(40% 30% at 20% 90%, rgba(255,140,50,0.08), transparent 25%),
                    radial-gradient(40% 30% at 80% 90%, rgba(255,70,0,0.06), transparent 25%);
                filter: blur(20px) saturate(120%);
                animation: forge-glow 3.5s linear infinite;
                mix-blend-mode: screen;
            }}

            #modal-pregunta::after {{
                background: linear-gradient(90deg, transparent, rgba(255,200,100,0.06) 25%, rgba(255,120,40,0.09) 50%, rgba(255,20,0,0.06) 75%, transparent);
                filter: blur(6px);
                animation: flame-flow 1.6s ease-in-out infinite;
                mix-blend-mode: screen;
                opacity: 0.95;
            }}

            #modal-pregunta .embers,
            #modal-pregunta .ashes {{
                position: absolute;
                inset: 0;
                z-index: 0;
                pointer-events: none;
            }}

            #modal-pregunta .embers {{
                background-image:
                    radial-gradient(circle at 20% 10%, rgba(255,180,90,0.7) 0px, transparent 6px),
                    radial-gradient(circle at 70% 30%, rgba(255,100,50,0.5) 0px, transparent 5px),
                    radial-gradient(circle at 40% 80%, rgba(255,200,120,0.4) 0px, transparent 6px);
                background-size: 100% 100%;
                filter: blur(4px) contrast(110%);
                animation: embers-move 6s linear infinite;
            }}

            #modal-pregunta .ashes {{
                background-image: 
                    radial-gradient(circle, rgba(255,30,0,0.55) 0px, transparent 45px),
                    radial-gradient(circle, rgba(255,100,20,0.45) 0px, transparent 60px),
                    radial-gradient(circle, rgba(255,180,60,0.35) 0px, transparent 50px);
                background-size: 180% 180%;
                background-repeat: repeat;
                animation: ashes-chaos 8s ease-in-out infinite;
                opacity: 0.7;
                filter: blur(2px) contrast(140%);
                mix-blend-mode: screen;
            }}

            /* Contenedores internos */
            #pregunta-container {{
                position: relative;
                z-index: 1; /* Asegura que el contenido quede encima de los efectos */
                background: rgba(0,0,0,0.3);
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                border: 1px solid #4a4540;
            }}
            
            #pregunta-texto {{
                font-size: 1.5rem;
                margin-bottom: 15px;
                color: #fff;
                text-shadow: 0 0 5px rgba(255,255,255,0.7);
            }}

            #opciones {{
                position: relative;
                z-index: 1;
                display: flex;
                flex-direction: column;
                gap: 15px;
                margin-bottom: 20px;
            }}
            
            /* ======================
               Botones estilo forja
               ====================== */
            .option-button, .modal-button {{
                font-family: 'MedievalSharp', cursive;
                font-size: clamp(1rem, 2.5vw, 1.2rem);
                padding: 12px 25px;
                cursor: pointer;
                border: 2px solid #803300;
                border-radius: 8px;
                background-color: #000;
                color: var(--flame-yellow);
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
                position: relative;
                transition: all 0.3s ease;
                z-index: 1;
                overflow: hidden;
                width: 100%;
            }}

            .option-button:not(:disabled)::after, 
            .modal-button:not(:disabled)::after {{
                content: "";
                position: absolute;
                left: 50%;
                transform: translateX(-50%) translateY(10px) scale(0.6);
                bottom: 0;
                width: 80%;
                height: 40px;
                border-radius: 40% 40% 20% 20%;
                background: radial-gradient(circle at 50% 25%, var(--flame-yellow), transparent 25%),
                            radial-gradient(circle at 30% 60%, var(--flame-orange), transparent 25%),
                            radial-gradient(circle at 70% 60%, var(--flame-red), transparent 25%);
                filter: blur(6px) saturate(140%);
                opacity: 0;
                pointer-events: none;
                transform-origin: center bottom;
                transition: all 260ms ease;
                mix-blend-mode: screen;
            }}

            .option-button:hover:not(:disabled)::after, 
            .modal-button:hover:not(:disabled)::after {{
                opacity: 1;
                transform: translateX(-50%) translateY(-6px) scale(1);
                animation: flame-flicker 400ms infinite;
            }}

            .option-button:hover:not(:disabled), .modal-button:hover:not(:disabled) {{
                background: linear-gradient(180deg, #000 20%, #1a0a05 80%);
                box-shadow: 0 0 20px rgba(255,90,0,0.9), inset 0 0 10px rgba(255,200,120,0.6);
                color: #fff6d0;
            }}

            .modal-button.confirm {{
                border-color: #ff4500;
                box-shadow: 0 0 10px rgba(255,70,0,0.6), inset 0 0 6px rgba(255,140,60,0.4);
            }}
            
            .modal-button.cancel {{
                border-color: #b87333;
                box-shadow: 0 0 8px rgba(255,200,100,0.3), inset 0 0 5px rgba(120,60,20,0.4);
            }}

            /* Loader estilo forja */
            .loader {{
                border: 6px solid #e0d0b0;
                border-top: 6px solid var(--flame-orange);
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite, forge-pulse 1.5s ease-in-out infinite;
                filter: drop-shadow(0 0 5px rgba(255, 100, 0, 0.7));
                margin: 2rem auto;
            }}
            
            /* ======================
               Modal de respuesta (estilo forja)
               ====================== */
            #modal-respuesta {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.85);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 1000;
            }}
            
            #modal-content {{
                position: relative;
                background: var(--modal-bg);
                border: 2px solid #803300;
                box-shadow: 0 0 20px rgba(255,100,0,0.4), inset 0 0 10px rgba(255,180,100,0.2);
                color: var(--flame-yellow);
                font-weight: bold;
                letter-spacing: 1px;
                overflow: hidden;
                padding: 2rem;
                border-radius: 12px;
                max-width: 500px;
                width: 90%;
                text-align: center;
            }}

            #modal-content::before,
            #modal-content::after {{
                content: "";
                position: absolute;
                inset: -10px;
                border-radius: inherit;
                z-index: 0;
                pointer-events: none;
            }}

            #modal-content::before {{
                background: radial-gradient(50% 35% at 50% 10%, rgba(255,210,120,0.15), transparent 20%);
                filter: blur(20px) saturate(120%);
                animation: forge-glow 3.5s linear infinite;
                mix-blend-mode: screen;
            }}

            #modal-content::after {{
                background: linear-gradient(90deg, transparent, rgba(255,200,100,0.06) 25%, rgba(255,120,40,0.09) 50%, rgba(255,20,0,0.06) 75%, transparent);
                filter: blur(6px);
                animation: flame-flow 1.6s ease-in-out infinite;
                mix-blend-mode: screen;
                opacity: 0.95;
            }}

            #modal-titulo {{
                font-size: 2rem;
                margin-bottom: 10px;
                text-transform: uppercase;
                position: relative;
                z-index: 1;
            }}
            
            #modal-titulo.correcto {{
                color: #b8ffb8;
                text-shadow: 0 0 8px rgba(108, 255, 108, 0.7);
            }}
            
            #modal-titulo.incorrecto {{
                color: #ffb8b8;
                text-shadow: 0 0 8px rgba(255, 108, 108, 0.7);
            }}

            #modal-mensaje {{
                font-size: 1.2rem;
                margin-bottom: 20px;
                position: relative;
                z-index: 1;
            }}

            /* ======================
               Animaciones
               ====================== */
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}

            @keyframes forge-glow {{
                0% {{ transform: scale(0.995); opacity: 0.9; }}
                50% {{ transform: scale(1.01); opacity: 1; }}
                100% {{ transform: scale(0.995); opacity: 0.9; }}
            }}

            @keyframes flame-flow {{
                0% {{ background-position: 0% 0%; }}
                50% {{ background-position: 50% 20%; }}
                100% {{ background-position: 100% 0%; }}
            }}

            @keyframes embers-move {{
                0% {{ transform: translateY(0) scale(1); opacity: 1; }}
                50% {{ transform: translateY(-10px) scale(0.95); opacity: 0.6; }}
                100% {{ transform: translateY(0) scale(1); opacity: 1; }}
            }}

            @keyframes ashes-chaos {{
                0% {{ background-position: 0% 100%; transform: scale(1); }}
                50% {{ background-position: 50% 0%; transform: scale(1.05); }}
                100% {{ background-position: 100% 100%; transform: scale(1); }}
            }}

            @keyframes flame-flicker {{
                0% {{ transform: translateX(-50%) translateY(-6px) scale(0.95) rotate(-1deg); opacity: 0.95; }}
                30% {{ transform: translateX(-50%) translateY(-2px) scale(1.02) rotate(1deg); opacity: 1; }}
                60% {{ transform: translateX(-50%) translateY(-8px) scale(0.98) rotate(-0.5deg); opacity: 0.92; }}
                100% {{ transform: translateX(-50%) translateY(-6px) scale(1) rotate(0deg); opacity: 0.96; }}
            }}
            
            @keyframes forge-pulse {{
                0% {{ border-top-color: var(--flame-orange); }}
                50% {{ border-top-color: var(--flame-yellow); }}
                100% {{ border-top-color: var(--flame-orange); }}
            }}

            /* Media queries */
            @media (max-width: 480px) {{
                #modal-pregunta {{ padding: 1.5rem; }}
                #pregunta-texto {{ font-size: 1.2rem; }}
                #modal-content {{ padding: 1.5rem; }}
                #modal-titulo {{ font-size: 1.5rem; }}
            }}
        </style>
    </head>
    <body>

        <h1>Aventura de Preguntas</h1>

        <div id="modal-pregunta">
            <div class="embers"></div>
            <div class="ashes"></div>
            <div id="pregunta-container">
                <p id="pregunta-texto">Cargando pregunta...</p>
            </div>
            <div id="opciones">
            </div>
        </div>

        <div id="modal-respuesta" style="display: none;">
            <div id="modal-content">
                <h2 id="modal-titulo"></h2>
                <p id="modal-mensaje"></p>
                <p id="continueText">presiona T para continuar</p>
        </div>

      <script>
        const API_BASE_URL = window.location.origin + "/auth_juego";
        const username = "{username}";

        async function cargarNuevaPregunta() {{
            try {{
                document.getElementById('pregunta-texto').textContent = "Cargando...";
                document.getElementById('opciones').innerHTML = '';
                const response = await fetch(`${{API_BASE_URL}}/get-next-question/${{username}}`);
                const data = await response.json();
                
                if (data.pregunta) {{
                    mostrarPregunta(data.pregunta);
                }} else if (data.message) {{
                    document.getElementById('pregunta-texto').textContent = data.message;
                    document.getElementById('opciones').innerHTML = '';
                }} else {{
                    document.getElementById('pregunta-texto').textContent = "Respuesta inválida del servidor.";
                    document.getElementById('opciones').innerHTML = '';
                }}
            }} catch (error) {{
                console.error("Error al cargar la pregunta:", error);
                document.getElementById('pregunta-texto').textContent = "Error al cargar la pregunta.";
                document.getElementById('opciones').innerHTML = '';
            }}
        }}

        function mostrarPregunta(preguntaData) {{
            document.getElementById('pregunta-texto').textContent = preguntaData.pregunta;
            const opcionesContainer = document.getElementById('opciones');
            opcionesContainer.innerHTML = '';
            
            const opcionesArray = Object.entries(preguntaData.opciones);
            opcionesArray.forEach(([key, value]) => {{
                const button = document.createElement('button');
                button.textContent = `${{key}}: ${{value}}`;
                button.classList.add('option-button');
                button.onclick = () => enviarRespuesta(key);
                opcionesContainer.appendChild(button);
            }});
        }}

        async function enviarRespuesta(respuesta) {{
            try {{
                const response = await fetch(`${{API_BASE_URL}}/submit-answer/${{username}}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ respuesta }})
                }});
                const data = await response.json();
                
                mostrarResultadoInline(data.resultado, data.message);
                actualizarEstadoPregunta(data.resultado);
            }} catch (error) {{
                console.error("Error al enviar la respuesta:", error);
                mostrarResultadoInline('error', 'Error al enviar la respuesta.');
            }}
        }}

        function mostrarResultadoInline(resultado, mensaje) {{
            const container = document.getElementById('pregunta-container');
            container.innerHTML = `
                <h2 style="color:${{resultado === 'correcto' ? '#b8ffb8' : '#ffb8b8'}}">
                    ${{resultado === 'correcto' ? '¡Respuesta Correcta!' : 'Respuesta Incorrecta'}}
                </h2>
                <p>${{mensaje}}</p>
                <p style="font-size:0.9rem; opacity:0.7;">Presiona T para continuar</p>
            `;
            document.getElementById('opciones').innerHTML = '';
        }}

        async function actualizarEstadoPregunta(estado) {{
            try {{
                await fetch(`${{API_BASE_URL}}/update-last-answer-status/${{username}}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ estado }})
                }});
            }} catch (error) {{
                console.error("Error al actualizar estado:", error);
            }}
        }}

        document.addEventListener('keydown', function(event) {{
            if (event.key === 't' || event.key === 'T') {{
                cargarNuevaPregunta();
            }}
        }});

        window.onload = cargarNuevaPregunta;
      </script>

    </body>
    </html>
    """
    return render_template_string(html_content)
    
# ---------------------------------------------------
# 4. Ruta para obtener la siguiente pregunta
# ---------------------------------------------------
@auth_juego_bp.route("/get-next-question/<string:username>", methods=["GET"])
def get_next_question(username):
    """
    Entrega la siguiente pregunta al usuario de forma aleatoria desde su archivo JSON.
    Si una pregunta activa ya existe en Redis, la retorna. De lo contrario,
    selecciona una nueva y la guarda.
    """
    conn = None
    cursor = None
    try:
        # 1. Verificar si el usuario tiene una pregunta activa en Redis
        pregunta_activa_str = redis_client.get(f"pregunta_actual_{username}")
        
        # SI la pregunta existe, la devolvemos INMEDIATAMENTE.
        if pregunta_activa_str:
            pregunta_activa = json.loads(pregunta_activa_str)
            return jsonify({"pregunta": pregunta_activa}), 200

        # Si no hay pregunta activa, la siguiente parte del código se ejecutará.
        
        # 2. Actualizar el estado en la base de datos a 'no_respondio'
        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "UPDATE users SET estado_pregunta = %s WHERE username = %s",
            ("no_respondio", username)
        )
        # ✅ CAMBIO 3: Usar conn.commit()
        conn.commit()
        # cursor.close() y conn.close() ahora en finally

        # 3. Cargar todas las preguntas del archivo JSON
        # load_and_save_questions ya usa la nueva conexión internamente
        preguntas_del_usuario = load_and_save_questions(username, "load")
        if not preguntas_del_usuario:
            return jsonify({"message": "No hay más preguntas disponibles"}), 404

        # 4. Seleccionar una pregunta al azar y guardarla en Redis
        pregunta_elegida = random.choice(preguntas_del_usuario)
        redis_client.setex(
            f"pregunta_actual_{username}",
            300,
            json.dumps(pregunta_elegida, ensure_ascii=False)
        )

        # 5. Devolver la pregunta al usuario
        return jsonify({"pregunta": pregunta_elegida}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR en get-next-question: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 4: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ---------------------------------------------------
# 5. Ruta para enviar la respuesta del usuario
# ---------------------------------------------------
@auth_juego_bp.route("/submit-answer/<string:username>", methods=["POST"])
def submit_answer(username):
    """
    Recibe la respuesta del usuario, la valida y retorna el resultado.
    Si la respuesta es correcta, elimina la pregunta de Redis y del archivo JSON.
    """
    conn = None
    cursor = None
    try:
        data = request.get_json()
        respuesta_usuario = data.get("respuesta")
        
        if not respuesta_usuario:
            return jsonify({"message": "Respuesta no proporcionada"}), 400
        
        pregunta_actual_str = redis_client.get(f"pregunta_actual_{username}")
        if not pregunta_actual_str:
            return jsonify({"message": "No hay una pregunta activa para este usuario"}), 404
        
        pregunta_actual = json.loads(pregunta_actual_str)
        respuesta_correcta = pregunta_actual["respuesta"]
        explicacion = pregunta_actual["explicacion"]
        
        if respuesta_usuario.strip().lower() == respuesta_correcta.strip().lower():
            resultado = "correcto"
            message = f"¡Correcto! {explicacion}"
            
            # 1. Eliminar la pregunta de Redis
            redis_client.delete(f"pregunta_actual_{username}")
            
            # 2. Cargar todas las preguntas del archivo JSON
            # load_and_save_questions ya usa la nueva conexión internamente
            preguntas_del_usuario = load_and_save_questions(username, "load")
            
            # 3. Eliminar la pregunta respondida de la lista
            preguntas_restantes = [
                p for p in preguntas_del_usuario
                if p.get("pregunta") != pregunta_actual.get("pregunta")
            ]
            
            # 4. Guardar la lista actualizada en el archivo JSON
            load_and_save_questions(username, "save", preguntas_restantes)
            
        else:
            resultado = "incorrecto"
            message = f"Incorrecto. La respuesta correcta es '{respuesta_correcta}'. {explicacion}"
            # No eliminar la pregunta de Redis para que se mantenga la misma

        # Actualizar el estado en la base de datos
        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "UPDATE users SET estado_pregunta = %s WHERE username = %s",
            (resultado, username),
        )
        # ✅ CAMBIO 3: Usar conn.commit()
        conn.commit()
        # cursor.close() y conn.close() ahora en finally

        return jsonify({
            "resultado": resultado,
            "message": message,
            "success": resultado == "correcto"
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR en submit_answer: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 4: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
# ---------------------------------------------------
# NUEVA RUTA: Obtener el estado de la última pregunta
# ---------------------------------------------------
@auth_juego_bp.route("/get-last-answer-status/<string:username>", methods=["GET"])
def get_last_answer_status(username):
    """
    Retorna el valor del campo 'estado_pregunta' del usuario.
    """
    conn = None
    cursor = None
    try:
        if not username:
            return jsonify({"message": "El nombre de usuario es requerido"}), 400

        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT estado_pregunta FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        # cursor.close() y conn.close() ahora en finally

        if not user:
            return jsonify({"message": "Usuario no encontrado"}), 404

        return jsonify({"estado_pregunta": user["estado_pregunta"]}), 200

    except Exception as e:
        print(f"ERROR en get-last-answer-status: {e}", file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 3: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ---------------------------------------------------
# NUEVA RUTA: Actualizar el estado de la última pregunta
# ---------------------------------------------------
@auth_juego_bp.route("/update-last-answer-status/<string:username>", methods=["POST"])
def update_last_answer_status(username):
    """
    Actualiza el campo 'estado_pregunta' en la tabla users
    con el estado de la última respuesta (correcto o incorrecto).
    """
    conn = None
    cursor = None
    try:
        data = request.get_json()
        estado = data.get("estado")

        if estado not in ["correcto", "incorrecto"]:
            return jsonify({"message": "Estado inválido"}), 400

        # ✅ CAMBIO 1: Usar get_db()
        conn = get_db()
        # ✅ CAMBIO 2: Usar pymysql.cursors.DictCursor
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "UPDATE users SET estado_pregunta = %s WHERE username = %s",
            (estado, username),
        )
        # ✅ CAMBIO 3: Usar conn.commit()
        conn.commit()
        # cursor.close() y conn.close() ahora en finally

        return jsonify({"message": "Estado actualizado", "estado": estado}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR en update-last-answer-status: {e}", file=sys.stderr)
        return jsonify({"message": "Error interno del servidor", "error": str(e)}), 500
    finally:
        # ✅ CAMBIO 4: Asegurar cierre
        if cursor:
            cursor.close()
        if conn:
            conn.close()