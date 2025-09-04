import React, { useState } from 'react';
import Comment from './Comment';

const BlogPost = ({ post, currentUser, onUpdatePost, onDeletePost, showNotification, onEditClick }) => {
    const [liked, setLiked] = useState(false);
    const [likes, setLikes] = useState(post.likes);
    const [comments, setComments] = useState(post.comments || []); 
    const [newComment, setNewComment] = useState('');

    // **CORRECCIÓN CLAVE:** La lógica isOwner debe comparar IDs de usuario.
    // post.autor_id viene del backend y es el ID numérico del autor del post.
    // currentUser.id viene del AuthContext y es el ID numérico del usuario loggeado.
    const isOwner = currentUser && currentUser.id === post.autor_id;
    // También verifica si el usuario está verificado para realizar estas acciones
    const canPerformActions = currentUser && currentUser.verificado;


    const handleLike = () => {
        if (!currentUser) {
            showNotification("Debes iniciar sesión para dar 'like'.", 'error');
            return;
        }
        setLiked(!liked);
        setLikes(liked ? likes - 1 : likes + 1);
    };

    const handleAddComment = (e) => {
        e.preventDefault();
        if (!newComment.trim()) {
            showNotification("El comentario no puede estar vacío.", "error");
            return;
        }
        if (!currentUser) {
            showNotification("Debes iniciar sesión para comentar.", "error");
            return;
        }
        if (!currentUser.verificado) { // Verifica el estado de verificación
            showNotification("Tu cuenta no está verificada. Por favor, verifica tu correo para comentar.", "error");
            return;
        }

        // Aquí deberías enviar el comentario al backend para que se persista.
        // Por ahora, solo simula la adición.
        const comment = {
            id: Date.now(), // ID temporal, el backend debería dar uno real
            autor_id: currentUser.id, // ID del autor
            author: currentUser.username, // Nombre de usuario para mostrar
            text: newComment,
            created_at: new Date().toISOString(),
        };

        // Simulación: Actualizar el estado local y luego notificar al padre para la API
        const updatedComments = [...comments, comment];
        setComments(updatedComments);
        // Aquí deberías llamar a una prop como `onAddComment(post.id, newComment)` que interactúe con tu API
        // Ya que `onUpdatePost` se usa para actualizar el post completo, no solo añadir un comentario.
        // Por simplicidad, si `onUpdatePost` es la única opción, podrías enviar una actualización del post
        // con la lista de comentarios modificada.

        // Por ahora, solo limpiamos el input y mostramos la notificación
        setNewComment('');
        showNotification("Comentario añadido (localmente).", "success"); // Cambia esto por la respuesta del backend
    };

    const handleDeleteComment = (commentId) => {
        if (!currentUser || !currentUser.verificado) {
            showNotification("Necesitas iniciar sesión y verificar tu cuenta para borrar comentarios.", "error");
            return;
        }
        // Aquí iría la llamada a la API `DELETE /eliminar-comentario/<id>`
        console.log("Eliminando comentario:", commentId);
        const updatedComments = comments.filter(c => c.id !== commentId);
        setComments(updatedComments);
        showNotification("Comentario borrado (localmente).", "success"); // Cambia esto por la respuesta del backend
    };

    const handleEditComment = (commentId, newText) => {
        if (!currentUser || !currentUser.verificado) {
            showNotification("Necesitas iniciar sesión y verificar tu cuenta para editar comentarios.", "error");
            return;
        }
        if (!newText) return;
        // Aquí iría la llamada a la API `PUT /editar-comentario/<id>`
        console.log("Editando comentario:", commentId, newText);
        const updatedComments = comments.map(c =>
            c.id === commentId ? { ...c, text: newText } : c
        );
        setComments(updatedComments);
        showNotification("Comentario editado (localmente).", "success"); // Cambia esto por la respuesta del backend
    };


    return (
        <article className="blog-post">
            {post.imageUrl && <img src={post.imageUrl} alt={post.title} className="post-image" />}
            <h2>{post.title}</h2>
            <div className="post-meta">
                Escrito por: {post.author}
            </div>
            <p className="post-content">{post.content}</p>

            <div className="post-controls">
                <button onClick={handleLike} className={`like-button ${liked ? 'liked' : ''}`}>
                    ❤️ {likes} {likes === 1 ? 'Like' : 'Likes'}
                </button>
                {/* Muestra los botones de control solo si es el propietario Y está verificado */}
                {isOwner && canPerformActions && (
                    <div className="control-buttons">
                        <button className="control-button" onClick={() => onEditClick(post.id)}>✏️ Editar</button>
                        <button className="control-button delete" onClick={() => onDeletePost(post.id)}>🗑️ Borrar</button>
                    </div>
                )}
            </div>

            <div className="comments-section">
                <h3>Comentarios de los Bardos</h3>
                {/* Ahora comments siempre será un array, incluso si está vacío */}
                {comments.map((comment) => (
                    <Comment
                        key={comment.id}
                        comment={comment}
                        currentUser={currentUser} // 'currentUser' ahora tiene 'id' y 'verificado'
                        onDelete={handleDeleteComment}
                        onEdit={handleEditComment}
                    />
                ))}
                {currentUser && ( // Solo muestra el formulario si hay un usuario logueado
                    <form className="add-comment-form" onSubmit={handleAddComment}>
                        <textarea
                            value={newComment}
                            onChange={(e) => setNewComment(e.target.value)}
                            placeholder="Añade tu verso a esta crónica..."
                            rows="2"
                            disabled={!canPerformActions} // Deshabilita si no está verificado
                        ></textarea>
                        <button type="submit" disabled={!canPerformActions}>
                            Enviar
                        </button>
                    </form>
                )}
                {currentUser && !currentUser.verificado && (
                    <p className="verification-reminder comment-warning">
                        ⚠️ Verifica tu correo para comentar, editar y borrar comentarios.
                    </p>
                )}
            </div>
        </article>
    );
};

export default BlogPost;
