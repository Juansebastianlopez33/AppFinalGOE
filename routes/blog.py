from flask import Blueprint, request, jsonify, current_app
from extensions import mysql, socketio
from MySQLdb.cursors import DictCursor
from werkzeug.utils import secure_filename
import os
import sys
import traceback
from datetime import datetime
import shutil
import cloudinary.uploader
import re

# ✅ Import directo desde la raíz
from utils import upload_image_to_cloudinary

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

def extract_public_id_from_url(url: str) -> str:
    """
    Extrae el public_id de una URL de Cloudinary.
    Ejemplo:
        https://res.cloudinary.com/demo/image/upload/v1234567/publicaciones/5/10/imagen.jpg
    Retorna:
        publicaciones/5/10/imagen  (sin la extensión .jpg)
    """
    if not url:
        return None

    try:
        # Quita los parámetros después del ?
        url = url.split("?")[0]
        # Quita la extensión (jpg, png, etc.)
        url_no_ext = re.sub(r"\.[a-zA-Z0-9]+$", "", url)
        # Busca la parte después de /upload/
        match = re.search(r"/upload/(?:v\d+/)?(.+)", url_no_ext)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"Error extrayendo public_id de URL {url}: {e}", file=sys.stderr)

    return None

@blog_bp.route('/crear-publicacion', methods=['POST', 'OPTIONS'])
@jwt_required()
def crear_publicacion():
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    cursor = None
    try:
        current_user_id = int(get_jwt_identity())
        claims = get_jwt()

        if not claims.get('verificado'):
            return jsonify({"error": "Usuario no verificado."}), 403

        titulo = request.form.get('titulo')
        texto = request.form.get('texto')
        categoria_id = request.form.get('categoria_id')
        image_file = request.files.get('imagen')

        if not titulo or not texto or not categoria_id:
            return jsonify({"error": "Faltan campos obligatorios."}), 400
        if not image_file or not image_file.filename.strip():
            return jsonify({"error": "La imagen es obligatoria."}), 400

        cursor = mysql.connection.cursor()
        # Primero insertamos la publicación
        cursor.execute(
            "INSERT INTO publicaciones (titulo, texto, categoria_id, autor_id) VALUES (%s, %s, %s, %s)",
            (titulo, texto, categoria_id, current_user_id)
        )
        publicacion_id = cursor.lastrowid

        # Ahora subimos la imagen en carpeta única
        upload_result = upload_image_to_cloudinary(
            image_file,
            folder=f"publicaciones/{current_user_id}/{publicacion_id}"
        )
        nueva_imagen_url = upload_result.get("secure_url") if isinstance(upload_result, dict) else upload_result

        if not nueva_imagen_url:
            mysql.connection.rollback()
            return jsonify({"error": "Error al subir la imagen."}), 500

        # Guardamos en DB
        cursor.execute(
            "INSERT INTO imagenes_publicacion (publicacion_id, url, orden) VALUES (%s, %s, 1)",
            (publicacion_id, nueva_imagen_url)
        )
        mysql.connection.commit()

        return jsonify({
            "message": "Publicación creada exitosamente.",
            "id": publicacion_id,
            "imageUrl": nueva_imagen_url
        }), 201

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/eliminar-publicacion/<int:publicacion_id>', methods=['DELETE', 'OPTIONS'])
@jwt_required()
def eliminar_publicacion(publicacion_id):
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200
    
    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    print(f"DEBUG ELIMINAR: current_user_id del JWT: {current_user_id}", file=sys.stderr)
    print(f"DEBUG ELIMINAR: claims del JWT: {claims}", file=sys.stderr)

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado."}), 403

    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)
        cursor.execute("SELECT autor_id FROM publicaciones WHERE id = %s", (publicacion_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            return jsonify({"error": "Publicación no encontrada."}), 404
        
        autor_publicacion_id = resultado['autor_id']
        if autor_publicacion_id != current_user_id:
            return jsonify({"error": "No autorizado para eliminar esta publicación."}), 403

        # 🔥 Obtener imágenes asociadas
        cursor.execute("SELECT url FROM imagenes_publicacion WHERE publicacion_id = %s", (publicacion_id,))
        image_urls_to_delete = cursor.fetchall()

        for row in image_urls_to_delete:
            img_url = row['url']
            public_id = extract_public_id_from_url(img_url)
            if public_id:
                try:
                    cloudinary.uploader.destroy(public_id)
                    print(f"DEBUG ELIMINAR: Imagen eliminada de Cloudinary: {public_id}", file=sys.stderr)
                except Exception as e:
                    print(f"ERROR ELIMINAR: Fallo eliminando {public_id} de Cloudinary: {e}", file=sys.stderr)

        # 🔥 Eliminar toda la carpeta en Cloudinary (publicaciones/<user_id>/<publicacion_id>)
        try:
            folder_prefix = f"publicaciones/{autor_publicacion_id}/{publicacion_id}"
            cloudinary.api.delete_resources_by_prefix(folder_prefix)
            cloudinary.api.delete_folder(folder_prefix)
            print(f"DEBUG ELIMINAR: Carpeta eliminada en Cloudinary: {folder_prefix}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR ELIMINAR: No se pudo eliminar la carpeta de Cloudinary: {e}", file=sys.stderr)

        # 🔥 Borrar datos relacionados en la DB
        cursor.execute("DELETE FROM comentarios WHERE publicacion_id = %s", (publicacion_id,))
        cursor.execute("DELETE FROM imagenes_publicacion WHERE publicacion_id = %s", (publicacion_id,))
        cursor.execute("DELETE FROM likes WHERE publicacion_id = %s", (publicacion_id,))
        cursor.execute("DELETE FROM publicaciones WHERE id = %s", (publicacion_id,))
        mysql.connection.commit()

        # 🔥 Emitir evento a todos los clientes
        socketio.emit('publication_deleted', {
            'id': publicacion_id,
            'message': 'Publicación eliminada.'
        }, namespace='/')

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

@blog_bp.route('/publicaciones', methods=['GET', 'OPTIONS'])
def get_publicaciones():
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    categoria_id = request.args.get('categoria_id', type=int)
    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)

        sql = """
            SELECT
                p.id, p.autor_id, p.titulo, p.texto AS content, p.created_at, p.likes_count,
                p.categoria_id, c.nombre AS categoria_nombre,
                u.username AS autor_username, u.foto_perfil AS autor_foto_perfil_url, u.verificado AS autor_verificado
            FROM publicaciones p
            JOIN users u ON p.autor_id = u.id
            LEFT JOIN categorias c ON p.categoria_id = c.id
        """
        values = []

        if categoria_id:
            sql += " WHERE p.categoria_id = %s"
            values.append(categoria_id)

        sql += " ORDER BY p.created_at DESC"

        cursor.execute(sql, tuple(values))
        publicaciones = cursor.fetchall()

        for pub in publicaciones:
            # Normalizar fechas
            if isinstance(pub['created_at'], datetime):
                pub['created_at'] = pub['created_at'].isoformat()
            pub['autor_verificado'] = bool(pub['autor_verificado'])
            pub['autor_foto_perfil_url'] = pub['autor_foto_perfil_url'] if pub['autor_foto_perfil_url'] else None

            # Obtener imágenes principales
            cursor_img = mysql.connection.cursor(DictCursor)
            cursor_img.execute("SELECT id, url FROM imagenes_publicacion WHERE publicacion_id = %s ORDER BY id", (pub['id'],))
            imagenes = cursor_img.fetchall()
            cursor_img.close()

            pub['imagenes'] = imagenes
            pub['imageUrl'] = imagenes[0]['url'] if imagenes else None
            pub['imagenes_adicionales_urls'] = [img['url'] for img in imagenes[1:]] if len(imagenes) > 1 else []

            # Renombrar campo likes_count → likes
            pub['likes'] = pub.pop('likes_count')

        return jsonify(publicaciones), 200

    except Exception as e:
        print(f"ERROR al obtener publicaciones: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": "Error interno del servidor al obtener publicaciones."}), 500
    finally:
        if cursor:
            cursor.close()



@blog_bp.route('/editar-publicacion/<int:publicacion_id>', methods=['PUT', 'OPTIONS'])
@jwt_required()
def editar_publicacion(publicacion_id):
    if request.method == 'OPTIONS':
        return jsonify({'message': 'Preflight success'}), 200

    current_user_id = int(get_jwt_identity())
    claims = get_jwt()
    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado."}), 403

    titulo = request.form.get('titulo')
    texto = request.form.get('texto')
    categoria_id = request.form.get('categoria_id')
    image_file = request.files.get('imagen')

    cursor = None
    try:
        cursor = mysql.connection.cursor(DictCursor)

        cursor.execute("SELECT autor_id FROM publicaciones WHERE id = %s", (publicacion_id,))
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Publicación no encontrada"}), 404
        if result['autor_id'] != current_user_id:
            return jsonify({"error": "No autorizado"}), 403

        update_fields, update_values = [], []
        if titulo:
            update_fields.append("titulo = %s")
            update_values.append(titulo)
        if texto:
            update_fields.append("texto = %s")
            update_values.append(texto)
        if categoria_id:
            try:
                categoria_id = int(categoria_id)
                update_fields.append("categoria_id = %s")
                update_values.append(categoria_id)
            except ValueError:
                return jsonify({"error": "El ID de categoría no es válido."}), 400

        # Si viene nueva imagen, reemplazamos
        if image_file and image_file.filename.strip():
            # Buscar la imagen actual
            cursor.execute("SELECT url FROM imagenes_publicacion WHERE publicacion_id = %s AND orden = 1", (publicacion_id,))
            old = cursor.fetchone()
            if old:
                old_public_id = extract_public_id_from_url(old['url'])
                if old_public_id:
                    try:
                        cloudinary.uploader.destroy(old_public_id)
                    except Exception as e:
                        print(f"Error eliminando {old_public_id} de Cloudinary: {e}", file=sys.stderr)

            # Subir nueva
            upload_result = upload_image_to_cloudinary(
                image_file,
                folder=f"publicaciones/{current_user_id}/{publicacion_id}"
            )
            nueva_imagen_url = upload_result.get("secure_url") if isinstance(upload_result, dict) else upload_result

            if nueva_imagen_url:
                cursor.execute(
                    "UPDATE imagenes_publicacion SET url = %s WHERE publicacion_id = %s AND orden = 1",
                    (nueva_imagen_url, publicacion_id)
                )

        if update_fields:
            update_values.append(publicacion_id)
            sql = f"UPDATE publicaciones SET {', '.join(update_fields)} WHERE id = %s"
            cursor.execute(sql, tuple(update_values))

        mysql.connection.commit()
        return jsonify({"message": "Publicación actualizada exitosamente."}), 200

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        if mysql.connection.open:
            mysql.connection.rollback()
        return jsonify({"error": "Error interno al editar la publicación."}), 500
    finally:
        if cursor:
            cursor.close()

@blog_bp.route('/comentar-publicacion', methods=['POST', 'OPTIONS'])
@jwt_required()
def comentar_publicacion():
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

    print(f"DEBUG COMENTAR: Solicitud para comentar publicacion_id: {publicacion_id}, texto: '{str(comentario_texto)[:50] if comentario_texto else 'None'}...'", file=sys.stderr)

    if publicacion_id is None or not comentario_texto:
        print("ERROR COMENTAR: Datos incompletos - publicacion_id o comentario faltante.", file=sys.stderr)
        return jsonify({"error": "ID de publicación y comentario son requeridos."}), 400

    cursor = None
    try:
        cursor = mysql.connection.cursor()
        publicacion_id = int(publicacion_id)

        cursor.execute("SELECT id FROM publicaciones WHERE id = %s", (publicacion_id,))
        if not cursor.fetchone():
            print(f"ERROR COMENTAR: Publicación {publicacion_id} no encontrada.", file=sys.stderr)
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

        # ✅ Emitir evento al "room" de la publicación
        socketio.emit(
            'comment_added',
            {'publicacion_id': publicacion_id, 'comment': new_comment_data},
            namespace='/',
            room=f'publicacion_{publicacion_id}'
        )
        print(f"DEBUG COMENTAR: Evento 'comment_added' emitido para publicacion_{publicacion_id}.", file=sys.stderr)

        return jsonify({
            "message": "Comentario publicado exitosamente.",
            "comment_id": new_comment_id,
            "comment": new_comment_data
        }), 201

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

@blog_bp.route('/publicaciones/<int:publicacion_id>/upload_imagen', methods=['POST'])
@jwt_required()
def upload_publicacion_image(publicacion_id):
    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if not claims.get('verificado'):
        return jsonify({"error": "Usuario no verificado"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Archivo vacío"}), 400

    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
    if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
        try:
            upload_result = upload_image_to_cloudinary(file, folder=f"publicaciones/{publicacion_id}")
            image_url = upload_result.get("secure_url") if isinstance(upload_result, dict) else upload_result

            if image_url:
                cursor = mysql.connection.cursor()
                cursor.execute(
                    "INSERT INTO imagenes_publicacion (publicacion_id, url, orden) VALUES (%s, %s, 1)",
                    (publicacion_id, image_url)
                )
                mysql.connection.commit()
                cursor.close()
                return jsonify({"message": "Imagen subida", "url": image_url}), 200
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return jsonify({"error": "Error al subir imagen"}), 500
    return jsonify({"error": "Formato de archivo no permitido"}), 400


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