import React, { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext"; // ¡Ruta corregida aquí!

const CreatePost = ({ onPostCreated, postToEdit, onPostUpdated, onCancelEdit, onCancelCreate }) => {
    // --- ESTADOS INTERNOS DEL FORMULARIO ---
    const [title, setTitle] = useState('');
    const [content, setContent] = useState('');
    const [imageFile, setImageFile] = useState(null); // Guarda el archivo de imagen para subirlo
    const [imagePreview, setImagePreview] = useState(''); // Guarda la URL de previsualización
    const [isSubmitting, setIsSubmitting] = useState(false); // Estado para deshabilitar el botón de envío
    const { token, user } = useAuth(); // Obtener el token y el usuario del contexto de autenticación

    const isEditing = !!postToEdit; // Determina si estamos en modo "edición"
    const API_URL = import.meta.env.VITE_API_URL;

    // Efecto para rellenar el formulario si estamos en modo edición
    useEffect(() => {
        if (isEditing) {
            setTitle(postToEdit.title);
            setContent(postToEdit.content);
            setImagePreview(postToEdit.imageUrl || ''); // Usa la imagen actual si existe
            setImageFile(null); // Reseteamos el archivo de imagen al iniciar la edición
        } else {
            // Limpiar formulario si no estamos editando (ej. para nueva creación)
            setTitle('');
            setContent('');
            setImagePreview('');
            setImageFile(null);
        }
    }, [postToEdit, isEditing]);

    // Maneja la selección de un nuevo archivo de imagen
    const handleImageChange = (e) => {
        const file = e.target.files && e.target.files[0];
        if (file) {
            setImageFile(file); // Guardamos el objeto del archivo para la subida
            setImagePreview(URL.createObjectURL(file)); // Creamos una URL local para la vista previa
        } else {
            setImageFile(null);
            if (!isEditing || !postToEdit.imageUrl) { // Si no estamos editando o no hay imagen previa, limpiar preview
                setImagePreview('');
            }
        }
    };

    // Maneja el envío del formulario
    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);

        if (!user || !user.verificado) {
            // Esta verificación ya debería estar en BlogPage, pero es buena una doble verificación
            alert("Tu cuenta no está verificada. Por favor, verifica tu correo electrónico para forjar o editar crónicas con imágenes.");
            setIsSubmitting(false);
            return;
        }

        const payload = {
            titulo: title,
            texto: content,
        };

        try {
            let response;
            let data;
            let postIdToUse = postToEdit?.id; // Usar el ID del post a editar si estamos en edición

            if (isEditing) {
                // --- Lógica de ACTUALIZACIÓN de post existente (PUT) ---
                response = await fetch(`${API_URL}/editar-publicacion/${postIdToUse}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(payload)
                });
                data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Error al actualizar la publicación.');
                }
                alert(data.message || 'Publicación actualizada correctamente.'); // Mensaje de éxito

            } else {
                // --- Lógica de CREACIÓN de nuevo post (POST) ---
                response = await fetch(`${API_URL}/crear-publicacion`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(payload)
                });
                data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Error al crear la publicación.');
                }
                postIdToUse = data.publicacion_id; // Obtener el ID del post recién creado
                alert(data.message || 'Publicación creada correctamente.'); // Mensaje de éxito
            }

            // --- Lógica de subida de IMAGEN (si hay una nueva imagen seleccionada) ---
            if (imageFile && postIdToUse) {
                const formData = new FormData();
                formData.append('imagen_publicacion', imageFile);

                const imageUploadResponse = await fetch(`${API_URL}/publicaciones/${postIdToUse}/upload_imagen`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`
                    },
                    body: formData
                });
                const imageData = await imageUploadResponse.json();

                if (!imageUploadResponse.ok) {
                    // Si falla la subida de imagen, pero el texto se guardó
                    alert(imageData.error || 'El texto se guardó, pero falló la subida de la imagen.');
                } else {
                    alert(imageData.message || 'Imagen subida exitosamente.');
                }
            }

            // Llamar a la función de callback del componente padre
            if (isEditing) {
                onPostUpdated(); // Notificar al padre que el post se actualizó
            } else {
                onPostCreated(); // Notificar al padre que un nuevo post se creó
            }

        } catch (error) {
            console.error('Error al procesar la publicación:', error);
            alert(`Error: ${error.message}`);
        } finally {
            setIsSubmitting(false);
        }
    };

    // Maneja el botón de cancelar
    const handleCancel = () => {
        if (isEditing && onCancelEdit) {
            onCancelEdit();
        } else if (onCancelCreate) {
            onCancelCreate();
        }
    };

    return (
        <div className="create-post-container">
            <h3>{isEditing ? 'Editar Crónica' : 'Forjar Nueva Crónica'}</h3>
            <form onSubmit={handleSubmit}>
                <div className="input-group">
                    <label htmlFor="postTitle">Título:</label>
                    <input
                        id="postTitle"
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="El título de tu épica crónica"
                        required
                        maxLength={100}
                    />
                </div>
                <div className="input-group">
                    <label htmlFor="postContent">Crónica:</label>
                    <textarea
                        id="postContent"
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder="Escribe aquí tu relato de aventuras, sabiduría y batallas..."
                        rows="10"
                        required
                    ></textarea>
                </div>

                <div className="input-group">
                    <label htmlFor="imageUpload" className="image-upload-label">
                        {imagePreview ? 'Cambiar Estandarte (Imagen)' : 'Seleccionar un Estandarte (Imagen)'}
                    </label>
                    <input
                        id="imageUpload"
                        type="file"
                        accept="image/*"
                        onChange={handleImageChange}
                    />
                    <p className="image-recommendation">
                        Para mejor calidad, se recomienda una imagen de al menos 800px de ancho.
                    </p>
                    {imagePreview && (
                        <img src={imagePreview} alt="Vista previa" className="image-preview" />
                    )}
                </div>

                <div className="button-group">
                    {(isEditing || onCancelCreate) && (
                        <button type="button" className="cancel-button" onClick={handleCancel} disabled={isSubmitting}>
                            Cancelar
                        </button>
                    )}
                    <button type="submit" className="save-button" disabled={isSubmitting}>
                        {isSubmitting ? (isEditing ? 'Guardando...' : 'Publicando...') : (isEditing ? 'Guardar Cambios' : 'Publicar Crónica')}
                    </button>
                </div>
            </form>
        </div>
    );
};

export default CreatePost;
