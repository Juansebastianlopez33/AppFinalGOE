import React from 'react';

const Comment = ({ comment, currentUser, onDelete, onEdit }) => {
    // CORRECCIÓN 1: La lógica isOwner debe comparar IDs de usuario para mayor precisión.
    // 'comment.autor_id' es el ID del autor del comentario (lo obtenemos del backend).
    // 'currentUser.id' es el ID del usuario loggeado (del AuthContext).
    const isOwner = currentUser && currentUser.id === comment.autor_id;

    return (
        <div className="comment">
            <div className="comment-meta">
                {/* CORRECCIÓN 2: Renderizado defensivo de comment.author.
                    Si 'comment.author' inesperadamente llega como un objeto (lo que causa el error actual),
                    intentamos mostrar su propiedad 'username'. De lo contrario, lo mostramos directamente
                    (esperando que sea la cadena de texto del nombre de usuario).
                */}
                <span className="comment-author">
                    {typeof comment.author === 'object' && comment.author !== null
                        ? comment.author.username
                        : comment.author
                    }
                </span>
                {isOwner && (
                    <div className="comment-controls">
                        <button onClick={() => onDelete(comment.id)}>
                            🗑️ Borrar
                        </button>
                        <button onClick={() => onEdit(comment.id, prompt('Editar comentario:', comment.text))}>
                            ✏️ Editar
                        </button>
                    </div>
                )}
            </div>
            <p className="comment-content">{comment.text}</p>
        </div>
    );
};

export default Comment;
