from flask import Blueprint, request, jsonify, current_app
from extensions import mysql, socketio
from MySQLdb.cursors import DictCursor
from werkzeug.utils import secure_filename
import os
import sys
import traceback
from datetime import datetime
import shutil

from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required, verify_jwt_in_request

from routes.user import get_user_details

blog_bp = Blueprint('blog', __name__)

def get_publicacion_con_imagenes_y_comentarios(publicacion_id):
    """
    Obtiene los detalles completos de una publicación, incluyendo imágenes y comentarios.
    """
    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)
        publicacion_id = int(publicacion_id)

        print(f"DEBUG GET_PUB_DETAILS: Paso 1 - Obteniendo detalles básicos de la publicación {publicacion_id}", file=sys.stderr)
        cursor.execute("""
            SELECT
                p.id, p.autor_id, p.titulo, p.texto AS content, p.created_at, p.likes_count,
                p.categoria_id, c.nombre AS categoria_nombre,
                u.username AS autor_username, u.foto_perfil AS autor_foto_perfil_url, u.verificado AS autor_verificado
            FROM
                publicaciones p
            JOIN
                users u ON p.autor_id = u.id
            LEFT JOIN
                categorias c ON p.categoria_id = c.id
            WHERE p.id = %s
        """, (publicacion_id,))
        publicacion = cursor.fetchone()
        print(f"DEBUG GET_PUB_DETAILS: Paso 1 - Publicación encontrada: {publicacion is not None}", file=sys.stderr)

        if not publicacion:
            return None

        if isinstance(publicacion['created_at'], datetime):
            publicacion['created_at'] = publicacion['created_at'].isoformat()
        
        publicacion['autor_verificado'] = bool(publicacion['autor_verificado'])
        publicacion['autor_foto_perfil_url'] = publicacion['autor_foto_perfil_url'] if publicacion['autor_foto_perfil_url'] else None

        print(f"DEBUG GET_PUB_DETAILS: Paso 2 - Obteniendo imágenes para la publicación {publicacion_id}", file=sys.stderr)
        cursor.execute("SELECT id, url FROM imagenes_publicacion WHERE publicacion_id = %s ORDER BY id", (publicacion_id,))
        imagenes = cursor.fetchall()
        publicacion['imagenes'] = imagenes
        publicacion['imageUrl'] = imagenes[0]['url'] if imagenes else None
        publicacion['imagenes_adicionales_urls'] = [img['url'] for img in imagenes[1:]] if len(imagenes) > 1 else []
        print(f"DEBUG GET_PUB_DETAILS: Paso 2 - Imágenes encontradas: {len(imagenes)}", file=sys.stderr)

        print(f"DEBUG GET_PUB_DETAILS: Paso 3 - Obteniendo comentarios para la publicación {publicacion_id}", file=sys.stderr)
        cursor.execute("""
            SELECT
                c.id, c.autor_id, c.texto, c.created_at, c.edited_at,
                u.username AS autor_username, u.foto_perfil AS autor_foto_perfil_url, u.verificado AS autor_verificado
            FROM
                comentarios c
            JOIN
                users u ON c.autor_id = u.id
            WHERE c.publicacion_id = %s
            ORDER BY c.created_at ASC
        """, (publicacion_id,))
        comentarios = cursor.fetchall()
        print(f"DEBUG GET_PUB_DETAILS: Paso 3 - Comentarios encontrados: {len(comentarios)}", file=sys.stderr)

        for c in comentarios:
            if isinstance(c['created_at'], datetime):
                c['created_at'] = c['created_at'].isoformat()
            if isinstance(c['edited_at'], datetime):
                c['edited_at'] = c['edited_at'].isoformat()
            else:
                c['edited_at'] = c['created_at']
            c['autor_foto_perfil_url'] = c['autor_foto_perfil_url'] if c['autor_foto_perfil_url'] else None
            c['autor_verificado'] = bool(c['autor_verificado'])

        publicacion['comments'] = comentarios
        publicacion['likes'] = publicacion.pop('likes_count')
        return publicacion
    except Exception as e:
        print(f"ERROR: get_publicacion_con_imagenes_y_comentarios para ID {publicacion_id} - {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/publicaciones', methods=['GET', 'OPTIONS'])
def publicaciones():
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)
        categoria_id_param = request.args.get('categoria_id')
        sql_query = "SELECT p.id FROM publicaciones p"
        query_params = []

        if categoria_id_param:
            try:
                categoria_id = int(categoria_id_param)
                sql_query += " WHERE p.categoria_id = %s"
                query_params.append(categoria_id)
            except ValueError:
                print(f"ERROR PUBLICACIONES GET: ID de categoría inválido: {categoria_id_param}", file=sys.stderr)
                return jsonify({"error": "ID de categoría inválido."}), 400
        
        sql_query += " ORDER BY p.created_at DESC"
        
        cursor.execute(sql_query, tuple(query_params))
        publicacion_ids_raw = cursor.fetchall()
        
        publicaciones_con_detalles = []
        for row in publicacion_ids_raw:
            full_publicacion = get_publicacion_con_imagenes_y_comentarios(row['id'])
            if full_publicacion:
                publicaciones_con_detalles.append(full_publicacion)

        print(f"DEBUG PUBLICACIONES GET: Devolviendo {len(publicaciones_con_detalles)} publicaciones (filtradas por categoria_id: {categoria_id_param}).", file=sys.stderr)
        return jsonify(publicaciones_con_detalles), 200
    except Exception as e:
        print(f"Error en /publicaciones: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al obtener publicaciones."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/crear-publicacion', methods=['POST', 'OPTIONS'])
@jwt_required()
def crear_publicacion():
    try:
        if request.method == 'OPTIONS':
            return jsonify({'message': 'Preflight success'}), 200

        current_user_id = int(get_jwt_identity())
        claims = get_jwt()
        
        print(f"DEBUG CREAR: current_user_id del JWT: {current_user_id}", file=sys.stderr)
        print(f"DEBUG CREAR: claims del JWT: {claims}", file=sys.stderr)

        if not claims.get('verificado'):
            print(f"DEBUG CREAR: Usuario {current_user_id} no verificado, acceso denegado.", file=sys.stderr)
            return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

        user_in_db = get_user_details(current_user_id)
        if not user_in_db or not user_in_db.get('verificado'):
            print(f"ERROR CREAR: Usuario con ID {current_user_id} no encontrado o no verificado en la base de datos.", file=sys.stderr)
            return jsonify({"error": "No autorizado: El usuario asociado al token no existe o no está verificado."}), 404
        
        print(f"DEBUG CREAR: Headers de la solicitud: {request.headers}", file=sys.stderr)
        print(f"DEBUG CREAR: Content-Type: {request.headers.get('Content-Type')}", file=sys.stderr)
        print(f"DEBUG CREAR: Es JSON? {request.is_json}", file=sys.stderr)
        print(f"DEBUG CREAR: Archivos en request.files: {request.files}", file=sys.stderr)
        print(f"DEBUG CREAR: Datos de formulario en request.form: {request.form}", file=sys.stderr)
        print(f"DEBUG CREAR: Raw Request Data (primeros 200 bytes): {request.get_data()[:200]}", file=sys.stderr)

        titulo = None
        texto = None
        categoria_id = None
        image_file = None
        
        if request.is_json:
            data = request.json
            titulo = data.get('titulo')
            texto = data.get('texto')
            categoria_id = data.get('categoria_id')
            print(f"DEBUG CREAR: Contenido completo de request.json: {data}", file=sys.stderr)
        elif request.form or request.files:
            titulo = request.form.get('titulo')
            texto = request.form.get('texto')
            categoria_id = request.form.get('categoria_id')
            # 👇 Corrección: frontend envía "imagen", no "imageFile"
            image_file = request.files.get('imagen') or request.files.get('imageFile')
            print(f"DEBUG CREAR: Contenido de formulario: titulo='{titulo}', texto='{texto[:50] if texto else 'None'}...', categoria_id='{categoria_id}', image_file: {image_file.filename if image_file else 'None'}", file=sys.stderr)
        else:
            print(f"ERROR CREAR: No se detectó cuerpo JSON ni datos de formulario/archivos.", file=sys.stderr)
            return jsonify({"error": "Formato de solicitud no soportado o cuerpo vacío."}), 400

        if categoria_id is not None:
            try:
                categoria_id = int(categoria_id)
            except ValueError:
                print(f"ERROR CREAR: categoria_id '{categoria_id}' no es un entero válido.", file=sys.stderr)
                return jsonify({"error": "El ID de categoría proporcionado no es válido."}), 400

        if not titulo or not texto or categoria_id is None:
            missing_fields = []
            if not titulo: missing_fields.append("titulo")
            if not texto: missing_fields.append("texto") 
            if categoria_id is None: missing_fields.append("categoria_id")
            print(f"ERROR CREAR: Datos incompletos - Faltan campos: {', '.join(missing_fields)}.", file=sys.stderr)
            return jsonify({"error": "Título, texto y categoría de la publicación son requeridos."}), 400
        
        cursor = None
        try:
            cursor = mysql.connection.cursor()

            cursor.execute("SELECT id FROM categorias WHERE id = %s", (categoria_id,))
            if not cursor.fetchone():
                print(f"ERROR CREAR: Categoría ID {categoria_id} no existe.", file=sys.stderr)
                return jsonify({"error": "La categoría seleccionada no existe."}), 400

            cursor.execute("INSERT INTO publicaciones (autor_id, titulo, texto, categoria_id) VALUES (%s, %s, %s, %s)",
                        (current_user_id, titulo, texto, categoria_id))
            mysql.connection.commit()

            new_post_id = cursor.lastrowid
            print(f"DEBUG CREAR: Publicación {new_post_id} creada por usuario {current_user_id}.", file=sys.stderr)

            if image_file:
                print(f"DEBUG CREAR: Manejando subida de imagen para publicación {new_post_id}.", file=sys.stderr)
                allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
                
                if image_file.filename == '' or not ('.' in image_file.filename and image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
                    print(f"ERROR CREAR: Tipo de archivo de imagen no permitido o nombre de archivo inválido: {image_file.filename}", file=sys.stderr)
                else:
                    file_extension = image_file.filename.rsplit('.', 1)[1].lower()
                    upload_folder = current_app.config.get('UPLOAD_FOLDER')
                    if not upload_folder:
                        print("ERROR: UPLOAD_FOLDER no está configurado en app.config.", file=sys.stderr)
                    else:
                        base_publicaciones_path = os.path.join(upload_folder, 'publicaciones')
                        publicacion_folder_path = os.path.join(base_publicaciones_path, str(new_post_id))
                        if not os.path.exists(publicacion_folder_path):
                            os.makedirs(publicacion_folder_path)

                        new_filename = secure_filename(image_file.filename)
                        filepath = os.path.join(publicacion_folder_path, new_filename)

                        try:
                            image_file.save(filepath)
                            base_url = current_app.config.get('API_BASE_URL', request.url_root.rstrip('/'))
                            image_url_db = f"{base_url}/uploads/publicaciones/{new_post_id}/{new_filename}"
                            
                            cursor.execute("UPDATE publicaciones SET imageUrl = %s WHERE id = %s", (image_url_db, new_post_id))
                            cursor.execute("INSERT INTO imagenes_publicacion (publicacion_id, url, orden) VALUES (%s, %s, 1)", (new_post_id, image_url_db))
                            mysql.connection.commit()
                            print(f"DEBUG CREAR: Imagen principal guardada y asociada a pub {new_post_id}: {image_url_db}", file=sys.stderr)

                        except Exception as img_e:
                            print(f"ERROR CREAR: Fallo al guardar imagen para publicación {new_post_id}: {img_e}", file=sys.stderr)
                            traceback.print_exc(file=sys.stderr)
            
            nueva_publicacion_con_detalles = get_publicacion_con_imagenes_y_comentarios(new_post_id)

            if nueva_publicacion_con_detalles:
                if hasattr(current_app, 'add_to_publication_batch'):
                    current_app.add_to_publication_batch(nueva_publicacion_con_detalles)
                else:
                    socketio.emit('publication_added_instant', nueva_publicacion_con_detalles, broadcast=True, namespace='/')
                print(f"DEBUG CREAR: Evento 'publication_added' emitido para pub {new_post_id}.", file=sys.stderr)

            return jsonify({"message": "Publicación creada exitosamente.", "publicacion_id": new_post_id}), 201
        except Exception as e:
            print(f"Error al crear publicación para user {current_user_id}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if mysql.connection.open:
                mysql.connection.rollback()
            return jsonify({"error": "Error interno del servidor al crear la publicación."}), 500
    except Exception as e:
        print(f"FATAL ERROR CREAR: Excepción inesperada en crear_publicacion: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if 'mysql' in globals() and mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al procesar la solicitud de creación de publicación. Por favor, intenta de nuevo."}), 500

@blog_bp.route('/editar-publicacion/<int:publicacion_id>', methods=['PUT', 'OPTIONS'])
@jwt_required()
def editar_publicacion(publicacion_id):
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado."}), 403

    nuevo_titulo = request.form.get('titulo')
    nuevo_texto = request.form.get('texto')
    nueva_categoria = request.form.get('categoria_id')

    if not nuevo_titulo or not nuevo_texto:
        return jsonify({"error": "Título y texto son requeridos."}), 400

    cursor = None
    try:
        cursor = mysql.connection.cursor()

        # Validar autor
        cursor.execute("SELECT autor_id FROM publicaciones WHERE id = %s", (publicacion_id,))
        resultado = cursor.fetchone()
        if not resultado:
            return jsonify({"error": "Publicación no encontrada."}), 404
        if resultado[0] != current_user_id:
            return jsonify({"error": "No autorizado."}), 403

        # Armar UPDATE dinámico
        campos = ["titulo = %s", "texto = %s"]
        valores = [nuevo_titulo, nuevo_texto]

        if nueva_categoria:
            campos.append("categoria_id = %s")
            valores.append(nueva_categoria)

        valores.append(publicacion_id)
        query = f"UPDATE publicaciones SET {', '.join(campos)} WHERE id = %s"
        cursor.execute(query, tuple(valores))
        mysql.connection.commit()

        # 🔥 Manejar nueva imagen
        image_file = request.files.get("imagen") or request.files.get("imageFile")
        if image_file and image_file.filename.strip():
            allowed_extensions = current_app.config.get("ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif"})
            if '.' in image_file.filename and image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                filename = secure_filename(image_file.filename)

                # Guardar en carpeta por publicación
                pub_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "publicaciones", str(publicacion_id))
                os.makedirs(pub_folder, exist_ok=True)
                upload_path = os.path.join(pub_folder, filename)
                image_file.save(upload_path)

                # URL accesible
                base_url = current_app.config.get("API_BASE_URL", request.url_root.rstrip('/'))
                nueva_imagen_url = f"{base_url}/uploads/publicaciones/{publicacion_id}/{filename}"

                # Reemplazar imagen vieja en DB
                cursor.execute("DELETE FROM imagenes_publicacion WHERE publicacion_id = %s", (publicacion_id,))
                cursor.execute(
                    "INSERT INTO imagenes_publicacion (publicacion_id, url, orden) VALUES (%s, %s, 1)",
                    (publicacion_id, nueva_imagen_url)
                )
                cursor.execute(
                    "UPDATE publicaciones SET imageUrl = %s WHERE id = %s",
                    (nueva_imagen_url, publicacion_id)
                )
                mysql.connection.commit()

        # Obtener publicación actualizada
        updated_publicacion_con_detalles = get_publicacion_con_imagenes_y_comentarios(publicacion_id)

        if updated_publicacion_con_detalles:
            socketio.emit(
                'publication_updated_instant',
                updated_publicacion_con_detalles,
                namespace='/'
            )

        return jsonify({"message": "Publicación editada correctamente."}), 200

    except Exception as e:
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/eliminar-publicacion/<int:publicacion_id>', methods=['DELETE', 'OPTIONS'])
@jwt_required()
def eliminar_publicacion(publicacion_id):
    # Código para eliminar publicación
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200
    
    current_user_id = int(get_jwt_identity())
    publicacion_id = int(publicacion_id)
    claims = get_jwt()
    
    print(f"DEBUG ELIMINAR: current_user_id del JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG ELIMINAR: claims del JWT: {claims}", file=sys.stderr)

    if not claims.get('verificado'):
        print(f"DEBUG ELIMINAR: Usuario {current_user_id} no verificado, acceso denegado.", file=sys.stderr)
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT autor_id FROM publicaciones WHERE id = %s", (publicacion_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            print(f"ERROR ELIMINAR: Publicación {publicacion_id} no encontrada.", file=sys.stderr)
            return jsonify({"error": "Publicación no encontrada."}), 404
        
        autor_publicacion_id = resultado['autor_id']
        print(f"DEBUG ELIMINAR: Autor de la publicación {publicacion_id} es {autor_publicacion_id}, usuario actual es {current_user_id}.", file=sys.stderr)

        if autor_publicacion_id != current_user_id:
            print(f"ERROR ELIMINAR: Usuario {current_user_id} no autorizado para eliminar publicación {publicacion_id}.", file=sys.stderr)
            return jsonify({"error": "No autorizado para eliminar esta publicación."}), 403

        cursor.execute("SELECT url FROM imagenes_publicacion WHERE publicacion_id = %s", (publicacion_id,))
        image_urls_to_delete = cursor.fetchall()

        for img_url_dict in image_urls_to_delete:
            img_url = img_url_dict['url']
            if current_app.config.get('API_BASE_URL') and img_url.startswith(current_app.config.get('API_BASE_URL')):
                relative_path = img_url.replace(current_app.config.get('API_BASE_URL'), '').lstrip('/')
                filepath_to_delete = os.path.join(current_app.root_path, relative_path)
                if os.path.exists(filepath_to_delete) and os.path.isfile(filepath_to_delete):
                    os.remove(filepath_to_delete)
                    print(f"DEBUG ELIMINAR: Imagen de publicación eliminada del disco: {filepath_to_delete}", file=sys.stderr)
                else:
                    print(f"ADVERTENCIA ELIMINAR: No se encontró o no es un archivo la imagen para eliminar: {filepath_to_delete}", file=sys.stderr)

        publicacion_folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'publicaciones', str(publicacion_id))
        if os.path.exists(publicacion_folder_path):
            shutil.rmtree(publicacion_folder_path)
            print(f"DEBUG ELIMINAR: Carpeta de publicación eliminada del disco: {publicacion_folder_path}", file=sys.stderr)

        cursor.execute("DELETE FROM comentarios WHERE publicacion_id = %s", (publicacion_id,))
        cursor.execute("DELETE FROM imagenes_publicacion WHERE publicacion_id = %s", (publicacion_id,))
        cursor.execute("DELETE FROM likes WHERE publicacion_id = %s", (publicacion_id,))
        cursor.execute("DELETE FROM publicaciones WHERE id = %s", (publicacion_id,))
        mysql.connection.commit()
        print(f"DEBUG ELIMINAR: Publicación {publicacion_id} y sus datos asociados eliminados correctamente por usuario {current_user_id}.", file=sys.stderr)

        socketio.emit('publication_deleted', {'id': publicacion_id, 'message': 'Publicación eliminada.'}, namespace='/', to=None)
        print(f"DEBUG ELIMINAR: Evento 'publication_deleted' emitido para pub {publicacion_id}.", file=sys.stderr)

        return jsonify({"message": "Publicación eliminada correctamente."}), 200
    except Exception as e:
        print(f"Error al eliminar publicación {publicacion_id} para user {current_user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al eliminar publicación."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/comentar-publicacion', methods=['POST', 'OPTIONS'])
@jwt_required()
def comentar_publicacion():
    # Código para comentar publicación
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    print(f"DEBUG COMENTAR: current_user_id del JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG COMENTAR: claims del JWT: {claims}", file=sys.stderr)

    if not claims.get('verificado'):
        print(f"DEBUG COMENTAR: Usuario {current_user_id} no verificado, acceso denegado.", file=sys.stderr)
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    data = request.json
    publicacion_id = data.get('publicacion_id')
    comentario_texto = data.get('comentario')

    print(f"DEBUG COMENTAR: Solicitud para comentar publicacion_id: {publicacion_id}, texto: '{str(comentario_texto)[:50] if comentario_texto is not None else 'None'}...'", file=sys.stderr)


    if publicacion_id is None or not comentario_texto:
        print(f"ERROR COMENTAR: Datos incompletos - publicacion_id o comentario faltante.", file=sys.stderr)
        return jsonify({"error": "ID de publicación y comentario son requeridos."}), 400

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        publicacion_id = int(publicacion_id)

        cursor.execute("SELECT id FROM publicaciones WHERE id = %s", (publicacion_id,))
        if not cursor.fetchone():
            print(f"ERROR COMENTAR: Publicación {publicacion_id} no encontrada para comentar.", file=sys.stderr)
            return jsonify({"error": "La publicación no existe."}), 404

        cursor.execute(
            "INSERT INTO comentarios (publicacion_id, autor_id, texto) VALUES (%s, %s, %s)",
            (publicacion_id, current_user_id, comentario_texto)
        )
        mysql.connection.commit()
        new_comment_id = cursor.lastrowid
        print(f"DEBUG COMENTAR: Comentario {new_comment_id} creado en publicación {publicacion_id} por user {current_user_id}.", file=sys.stderr)


        comments_cursor = mysql.connection.cursor(DictCursor)
        comments_cursor.execute("""
            SELECT
                c.id, c.publicacion_id, c.autor_id, c.texto, c.created_at, c.edited_at,
                u.username AS autor_username, u.foto_perfil AS autor_foto_perfil_url, u.verificado AS autor_verificado
            FROM comentarios c
            JOIN users u ON c.autor_id = u.id
            WHERE c.id = %s
        """, (new_comment_id,))
        new_comment_data = comments_cursor.fetchone()
        comments_cursor.close()

        if new_comment_data:
            if isinstance(new_comment_data['created_at'], datetime):
                new_comment_data['created_at'] = new_comment_data['created_at'].isoformat()
            if isinstance(new_comment_data['edited_at'], datetime):
                new_comment_data['edited_at'] = new_comment_data['edited_at'].isoformat()
            else:
                new_comment_data['edited_at'] = new_comment_data['created_at']
            new_comment_data['autor_foto_perfil_url'] = new_comment_data['autor_foto_perfil_url'] if new_comment_data['autor_foto_perfil_url'] else None
            new_comment_data['autor_verificado'] = bool(new_comment_data['autor_verificado'])


        socketio.emit('comment_added', {'publicacion_id': publicacion_id, 'comment': new_comment_data}, room=f'publicacion_{publicacion_id}', namespace='/')
        print(f"DEBUG COMENTAR: Evento 'comment_added' emitido para publicacion_{publicacion_id}.", file=sys.stderr)

        return jsonify({"message": "Comentario publicado exitosamente.", "comment_id": new_comment_id, "comment": new_comment_data}), 201
    except Exception as e:
        print(f"Error al comentar publicación {publicacion_id} para user {current_user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al comentar."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/publicaciones/<int:publicacion_id>/comentarios', methods=['GET', 'OPTIONS'])
def get_comentarios_publicacion(publicacion_id):
    # Código para obtener comentarios
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    publicacion_id = int(publicacion_id)
    print(f"DEBUG GET_COMENTARIOS: Solicitud recibida para /publicaciones/{publicacion_id}/comentarios", file=sys.stderr)
    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)

        cursor.execute("SELECT id FROM publicaciones WHERE id = %s", (publicacion_id,))
        publication_exists = cursor.fetchone()
        if not publication_exists:
            print(f"DEBUG GET_COMENTARIOS: Publicación {publicacion_id} no encontrada en la DB.", file=sys.stderr)
            return jsonify({"error": "Publicación no encontrada."}), 404

        cursor.execute("""
            SELECT
                c.id,
                c.autor_id,
                u.username AS autor_username,
                u.foto_perfil AS autor_foto_perfil_url,
                u.verificado AS autor_verificado,
                c.texto AS texto,
                c.created_at AS created_at,
                c.edited_at AS edited_at
            FROM
                comentarios c
            JOIN
                users u ON c.autor_id = u.id
            WHERE
                c.publicacion_id = %s
            ORDER BY
                c.created_at ASC
        """, (publicacion_id,))
        comentarios = cursor.fetchall()

        for comentario in comentarios:
            if isinstance(comentario['created_at'], datetime):
                comentario['created_at'] = comentario['created_at'].isoformat()
            if isinstance(comentario['edited_at'], datetime):
                comentario['edited_at'] = comentario['edited_at'].isoformat()
            else:
                comentario['edited_at'] = comentario['created_at']
            comentario['autor_foto_perfil_url'] = comentario['autor_foto_perfil_url'] if comentario['autor_foto_perfil_url'] else "https://static.vecteezy.com/system/resources/previews/009/292/244/original/default-avatar-icon-of-social-media-user-vector.jpg"
            comentario['autor_verificado'] = bool(comentario['autor_verificado'])

        print(f"DEBUG GET_COMENTARIOS: Devolviendo {len(comentarios)} comentarios para publicación {publicacion_id}.", file=sys.stderr)
        return jsonify(comentarios), 200
    except Exception as e:
        print(f"Error al obtener comentarios para publicación {publicacion_id}: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al obtener comentarios."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/editar-comentario/<int:comentario_id>', methods=['PUT', 'OPTIONS'])
@jwt_required()
def editar_comentario(comentario_id):
    # Código para editar comentario
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    comentario_id = int(comentario_id)
    claims = get_jwt()

    print(f"DEBUG EDIT_COMMENT: current_user_id del JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG EDIT_COMMENT: claims del JWT: {claims}", file=sys.stderr)

    if not claims.get('verificado'):
        print(f"DEBUG EDIT_COMMENT: Usuario {current_user_id} no verificado, acceso denegado.", file=sys.stderr)
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    data = request.json
    nuevo_texto = data.get('texto')

    print(f"DEBUG EDIT_COMMENT: Solicitud para editar comentario {comentario_id} con texto: '{str(nuevo_texto)[:50] if nuevo_texto else 'None'}...'", file=sys.stderr)

    if not nuevo_texto:
        print(f"ERROR EDIT_COMMENT: Nuevo texto de comentario {comentario_id} requerido.", file=sys.stderr)
        return jsonify({"error": "Nuevo texto del comentario requerido."}), 400

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT autor_id, publicacion_id FROM comentarios WHERE id = %s", (comentario_id,))
        resultado = cursor.fetchone()
        if not resultado:
            print(f"ERROR EDIT_COMMENT: Comentario {comentario_id} no encontrado.", file=sys.stderr)
            return jsonify({"error": "Comentario no encontrado."}), 404

        comment_author_id = resultado[0]
        publicacion_id = resultado[1]
        
        print(f"DEBUG EDIT_COMMENT: Autor del comentario {comentario_id} es {comment_author_id}, usuario actual es {current_user_id}.", file=sys.stderr)

        if comment_author_id != current_user_id:
            print(f"ERROR EDIT_COMMENT: Usuario {current_user_id} no autorizado para editar comentario {comentario_id}.", file=sys.stderr)
            return jsonify({"error": "No autorizado para editar este comentario."}), 403


        cursor.execute("UPDATE comentarios SET texto = %s, edited_at = %s WHERE id = %s", (nuevo_texto, datetime.now(), comentario_id))
        mysql.connection.commit()
        print(f"DEBUG EDIT_COMMENT: Comentario {comentario_id} editado correctamente por usuario {current_user_id}.", file=sys.stderr)


        comments_cursor = mysql.connection.cursor(DictCursor)
        comments_cursor.execute("""
            SELECT
                c.id, c.publicacion_id, c.autor_id, c.texto, c.created_at, c.edited_at,
                u.username AS autor_username, u.foto_perfil AS autor_foto_perfil_url, u.verificado AS autor_verificado
            FROM comentarios c
            JOIN users u ON c.autor_id = u.id
            WHERE c.id = %s
        """, (comentario_id,))
        updated_comment_data = comments_cursor.fetchone()
        comments_cursor.close()

        if updated_comment_data:
            if isinstance(updated_comment_data['created_at'], datetime):
                updated_comment_data['created_at'] = updated_comment_data['created_at'].isoformat()
            if isinstance(updated_comment_data['edited_at'], datetime):
                updated_comment_data['edited_at'] = updated_comment_data['edited_at'].isoformat()
            else:
                updated_comment_data['edited_at'] = updated_comment_data['created_at']
            updated_comment_data['autor_foto_perfil_url'] = updated_comment_data['autor_foto_perfil_url'] if updated_comment_data['autor_foto_perfil_url'] else None
            updated_comment_data['autor_verificado'] = bool(updated_comment_data['autor_verificado'])


        socketio.emit('comment_updated', {'publicacion_id': publicacion_id, 'comment': updated_comment_data}, room=f'publicacion_{publicacion_id}', namespace='/')
        print(f"DEBUG EDIT_COMMENT: Evento 'comment_updated' emitido para publicacion_{publicacion_id}.", file=sys.stderr)

        return jsonify({"message": "Comentario editado correctamente.", "comment": updated_comment_data}), 200
    except Exception as e:
        print(f"Error al editar comentario {comentario_id} para user {current_user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al editar comentario."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/eliminar-comentario/<int:comentario_id>', methods=['DELETE', 'OPTIONS'])
def eliminar_comentario(comentario_id):
    # Código para eliminar comentario
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200
    
    verify_jwt_in_request()
    current_user_id = int(get_jwt_identity())
    comentario_id = int(comentario_id)
    claims = get_jwt()

    print(f"DEBUG DELETE_COMMENT: current_user_id del JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG DELETE_COMMENT: claims del JWT: {claims}", file=sys.stderr)

    if not claims.get('verificado'):
        print(f"DEBUG DELETE_COMMENT: Usuario {current_user_id} no verificado, acceso denegado.", file=sys.stderr)
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT autor_id, publicacion_id FROM comentarios WHERE id = %s", (comentario_id,))
        resultado = cursor.fetchone()
        if not resultado:
            print(f"ERROR DELETE_COMMENT: Comentario {comentario_id} no encontrado.", file=sys.stderr)
            return jsonify({"error": "Comentario no encontrado."}), 404

        comment_author_id = resultado[0]
        publicacion_id = resultado[1]

        cursor.execute("SELECT autor_id FROM publicaciones WHERE id = %s", (publicacion_id,))
        publicacion_autor_id = cursor.fetchone()[0]

        print(f"DEBUG DELETE_COMMENT: Autor del comentario {comentario_id} es {comment_author_id}.", file=sys.stderr)
        print(f"DEBUG DELETE_COMMENT: Autor de la publicación {publicacion_id} es {publicacion_autor_id}.", file=sys.stderr)
        print(f"DEBUG DELETE_COMMENT: Usuario actual {current_user_id}.", file=sys.stderr)

        if comment_author_id != current_user_id and publicacion_autor_id != current_user_id:
            print(f"ERROR DELETE_COMMENT: Usuario {current_user_id} no autorizado para eliminar comentario {comentario_id}.", file=sys.stderr)
            return jsonify({"error": "No autorizado para eliminar este comentario."}), 403

        cursor.execute("DELETE FROM comentarios WHERE id = %s", (comentario_id,))
        mysql.connection.commit()
        print(f"DEBUG DELETE_COMMENT: Comentario {comentario_id} eliminado correctamente por usuario {current_user_id}.", file=sys.stderr)

        socketio.emit('comment_deleted', {'id': comentario_id, 'publicacion_id': publicacion_id}, room=f'publicacion_{publicacion_id}', namespace='/')
        print(f"DEBUG DELETE_COMMENT: Evento 'comment_deleted' emitido para publicacion_{publicacion_id}.", file=sys.stderr)

        return jsonify({"message": "Comentario eliminado correctamente."}), 200
    except Exception as e:
        print(f"Error al eliminar comentario {comentario_id} para user {current_user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al eliminar comentario."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/publicaciones/<int:publicacion_id>/upload_imagen', methods=['POST', 'OPTIONS'])
@jwt_required()
def upload_publicacion_image(publicacion_id):
    # Código para subir imagen a publicación
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    publicacion_id = int(publicacion_id)
    claims = get_jwt()
    
    print(f"DEBUG UPLOAD_PUB_IMAGE: current_user_id del JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG UPLOAD_PUB_IMAGE: claims del JWT: {claims}", file=sys.stderr)

    if not claims.get('verificado'):
        print(f"DEBUG UPLOAD_PUB_IMAGE: Usuario {current_user_id} no verificado, acceso denegado.", file=sys.stderr)
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT autor_id FROM publicaciones WHERE id = %s", (publicacion_id,))
        publicacion = cursor.fetchone()
        
        if not publicacion:
            print(f"ERROR UPLOAD_PUB_IMAGE: Publicación {publicacion_id} no encontrada.", file=sys.stderr)
            return jsonify({"error": "Publicación no encontrada."}), 404
        
        autor_publicacion_id = publicacion[0]
        print(f"DEBUG UPLOAD_PUB_IMAGE: Autor de la publicación {publicacion_id} es {autor_publicacion_id}, usuario actual es {current_user_id}.", file=sys.stderr)

        if autor_publicacion_id != current_user_id:
            print(f"ERROR UPLOAD_PUB_IMAGE: Usuario {current_user_id} no tiene permiso para subir imágenes a la publicación {publicacion_id}.", file=sys.stderr)
            return jsonify({"error": "No tienes permiso para subir imágenes a esta publicación."}), 403

        if 'imagen_publicacion' not in request.files:
            print(f"ERROR UPLOAD_PUB_IMAGE: No se encontró 'imagen_publicacion' en request.files para pub {publicacion_id}.", file=sys.stderr)
            return jsonify({'error': 'No se encontró el archivo de imagen en la solicitud. El campo esperado es "imagen_publicacion".'}), 400

        file = request.files['imagen_publicacion']

        if file.filename == '':
            print(f"ERROR UPLOAD_PUB_IMAGE: Nombre de archivo vacío para pub {publicacion_id}.", file=sys.stderr)
            return jsonify({'error': 'No se seleccionó ningún archivo.'}), 400

        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})

        if file and '.' in file.filename and \
           file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:

            file_extension = file.filename.rsplit('.', 1)[1].lower()

            upload_folder = current_app.config.get('UPLOAD_FOLDER')
            if not upload_folder:
                print("ERROR: UPLOAD_FOLDER no está configurado en app.config.", file=sys.stderr)
                return jsonify({"error": "Error de configuración del servidor (UPLOAD_FOLDER no definido)."}, 500)

            base_publicaciones_path = os.path.join(upload_folder, 'publicaciones')
            publicacion_folder_path = os.path.join(base_publicaciones_path, str(publicacion_id))

            if not os.path.exists(publicacion_folder_path):
                os.makedirs(publicacion_folder_path)
                print(f"DEBUG UPLOAD_PUB_IMAGE: Carpeta de publicación creada: {publicacion_folder_path}", file=sys.stderr)

            new_filename = secure_filename(file.filename)
            filepath = os.path.join(publicacion_folder_path, new_filename)

            try:
                file.save(filepath)
                print(f"DEBUG UPLOAD_PUB_IMAGE: Imagen de publicación guardada en: {filepath}", file=sys.stderr)

                base_url = current_app.config.get('API_BASE_URL', request.url_root.rstrip('/'))
                image_url = f"{base_url}/uploads/publicaciones/{publicacion_id}/{new_filename}"

                cursor.execute("INSERT INTO imagenes_publicacion (publicacion_id, url) VALUES (%s, %s)", (publicacion_id, image_url))
                mysql.connection.commit()
                print(f"DEBUG UPLOAD_PUB_IMAGE: URL de imagen de publicación guardada en DB: {image_url}", file=sys.stderr)

                updated_publicacion_con_detalles = get_publicacion_con_imagenes_y_comentarios(publicacion_id)

                if updated_publicacion_con_detalles:
                    if hasattr(current_app, 'add_to_publication_batch'):
                        current_app.add_to_publication_batch(updated_publicacion_con_detalles)
                    else:
                        socketio.emit('publication_updated_instant', updated_publicacion_con_detalles, broadcast=True, namespace='/')
                    print(f"DEBUG UPLOAD_PUB_IMAGE: Evento 'publication_updated' emitido para pub {publicacion_id}.", file=sys.stderr)

                return jsonify({
                    'message': 'Imagen de publicación subida exitosamente.',
                    'imagen_url': image_url
                }), 201
            except Exception as save_e:
                if os.path.exists(filepath):
                    os.remove(filepath)
                print(f"Error al guardar el archivo o DB para publicación {publicacion_id}: {save_e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if mysql.connection.open:
                    mysql.connection.rollback()
                return jsonify({"error": "Error interno del servidor al guardar la imagen de la publicación."}), 500
        else:
            print(f"DEBUG BACKEND: /publicaciones/{publicacion_id}/upload_imagen -> Tipo de archivo no permitido: {file.filename}", file=sys.stderr)
            return jsonify({'error': f"Tipo de archivo no permitido o nombre de archivo inválido. Solo se permiten {', '.join(allowed_extensions)}."}), 400
    finally:
        if cursor:
            cursor.close()

from flask import Response
import json

@blog_bp.route('/categorias', methods=['GET', 'OPTIONS'])
def get_categorias():
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT id, nombre FROM categorias ORDER BY nombre ASC")
        categorias = cursor.fetchall()
        print(f"DEBUG: Devolviendo {len(categorias)} categorías.", file=sys.stderr)

        # 🚀 Devolver la respuesta en UTF-8 sin romper acentos
        return Response(
            json.dumps(categorias, ensure_ascii=False),
            mimetype="application/json; charset=utf-8"
        ), 200

    except Exception as e:
        print(f"Error al obtener categorías: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al obtener categorías."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/publicaciones/<int:publicacion_id>/like', methods=['POST', 'OPTIONS'])
@jwt_required()
def like_publicacion(publicacion_id):
    # Código para dar like
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    print(f"DEBUG LIKES: Recibida solicitud LIKE para publicacion_id: {publicacion_id}", file=sys.stderr)

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        
        cursor.execute("SELECT id FROM publicaciones WHERE id = %s", (publicacion_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Publicación no encontrada."}), 404

        cursor.execute("SELECT id FROM likes WHERE publicacion_id = %s AND user_id = %s", (publicacion_id, current_user_id))
        if cursor.fetchone():
            return jsonify({"message": "Ya le diste 'me gusta' a esta publicación."}), 200 

        cursor.execute("INSERT INTO likes (publicacion_id, user_id) VALUES (%s, %s)", (publicacion_id, current_user_id))
        
        cursor.execute("UPDATE publicaciones SET likes_count = likes_count + 1 WHERE id = %s", (publicacion_id,))
        mysql.connection.commit()

        cursor.execute("SELECT likes_count FROM publicaciones WHERE id = %s", (publicacion_id,))
        new_likes_count = cursor.fetchone()[0]

        socketio.emit('like_update', {'publicacion_id': publicacion_id, 'likes': new_likes_count, 'user_id': current_user_id, 'user_has_liked': True}, namespace='/', room=f'publicacion_{publicacion_id}')
        print(f"DEBUG LIKES: Publicación {publicacion_id} - Like añadido por user {current_user_id}. Total: {new_likes_count}", file=sys.stderr)

        return jsonify({"message": "Me gusta añadido exitosamente.", "new_likes_count": new_likes_count, "user_has_liked": True}), 200
    except Exception as e:
        print(f"ERROR LIKE: Fallo al añadir like a pub {publicacion_id} por user {current_user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al añadir 'me gusta'."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/publicaciones/<int:publicacion_id>/unlike', methods=['DELETE', 'OPTIONS'])
@jwt_required()
def unlike_publicacion(publicacion_id):
    # Código para quitar like
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado. Por favor, verifica tu correo electrónico."}), 403

    print(f"DEBUG LIKES: Recibida solicitud UNLIKE para publicacion_id: {publicacion_id}", file=sys.stderr)

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        
        cursor.execute("SELECT id FROM publicaciones WHERE id = %s", (publicacion_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Publicación no encontrada."}), 404

        cursor.execute("DELETE FROM likes WHERE publicacion_id = %s AND user_id = %s", (publicacion_id, current_user_id))
        
        if cursor.rowcount > 0:
            cursor.execute("UPDATE publicaciones SET likes_count = likes_count - 1 WHERE id = %s", (publicacion_id,))
            mysql.connection.commit()

            cursor.execute("SELECT likes_count FROM publicaciones WHERE id = %s", (publicacion_id,))
            new_likes_count = cursor.fetchone()[0]
            
            socketio.emit('like_update', {'publicacion_id': publicacion_id, 'likes': new_likes_count, 'user_id': current_user_id, 'user_has_liked': False}, namespace='/', room=f'publicacion_{publicacion_id}')
            print(f"DEBUG LIKES: Publicación {publicacion_id} - Like eliminado por user {current_user_id}. Total: {new_likes_count}", file=sys.stderr)

            return jsonify({"message": "Me gusta eliminado exitosamente.", "new_likes_count": new_likes_count, "user_has_liked": False}), 200
        else:
            return jsonify({"message": "No habías dado 'me gusta' a esta publicación."}), 200
    except Exception as e:
        print(f"ERROR UNLIKE: Fallo al eliminar like de pub {publicacion_id} por user {current_user_id}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno del servidor al eliminar 'me gusta'."}), 500
    finally:
        if cursor:
            cursor.close()