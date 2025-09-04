import React, { useState, useEffect, useCallback } from 'react';
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from "framer-motion";
import BlogPost from '../../components/BlogPost';
import CreatePost from '../../components/CreatePost';
import { useAuth } from '../../context/AuthContext';
import './Blog.css'; // Asegúrate de que este archivo CSS contenga los estilos que hemos discutido

const BlogPage = () => {
    // --- ESTADOS ---
    const [posts, setPosts] = useState([]); // Inicia vacío, se cargará desde la API
    const [loading, setLoading] = useState(true);
    const { user, token } = useAuth(); // 'user' ahora incluye 'verificado'
    const [notification, setNotification] = useState({ message: '', type: '' });
    const [editingPostId, setEditingPostId] = useState(null);
    const [isCreating, setIsCreating] = useState(false);
    const API_URL = import.meta.env.VITE_API_URL;

    // --- EFECTOS ---
    useEffect(() => {
        document.title = 'Crónicas de Eternia | Blog';
    }, []);

    // Efecto para manejar las notificaciones
    useEffect(() => {
        if (!notification.message) return;
        const timerId = setTimeout(() => {
            setNotification({ message: '', type: '' });
        }, 3000);
        return () => clearTimeout(timerId);
    }, [notification]);

    // --- LÓGICA DE DATOS (API) ---

    const showNotification = (message, type) => {
        setNotification({ message, type });
    };

    // Función para obtener todos los posts
    const fetchPosts = useCallback(async () => {
        setLoading(true);
        try {
            const response = await fetch(`${API_URL}/publicaciones`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || "No se pudieron cargar las crónicas.");
            }
            const data = await response.json();
            setPosts(data);
        } catch (error) {
            showNotification(error.message, 'error');
        } finally {
            setLoading(false);
        }
    }, [API_URL]);

    // Carga los posts iniciales al montar el componente
    useEffect(() => {
        fetchPosts();
    }, [fetchPosts]);

    // --- MANEJADORES DE EVENTOS ---

    // Manejador para la creación de posts (proceso de 2 pasos)
    const handlePostCreated = async () => {
        // Esta función se llama DESDE CreatePost cuando la operación es exitosa
        // Solo necesitamos recargar y cerrar el modal.
        setIsCreating(false);
        await fetchPosts();
    };
    
    // Lógica para actualizar posts: ahora simplemente recarga posts y cierra el modo edición
    const handlePostUpdated = async () => {
        await fetchPosts(); // Recargar los posts después de una actualización
        setEditingPostId(null); // Salir del modo edición
    };

    // Lógica para eliminar un post
    const handleDeletePost = async (postId) => {
        if (!token) {
            showNotification("Debes iniciar sesión para esta acción.", "error");
            return;
        }
        // **NUEVA VERIFICACIÓN DE VERIFICACIÓN DE CUENTA**
        if (user && !user.verificado) {
            showNotification("Tu cuenta no está verificada. Por favor, verifica tu correo electrónico para borrar crónicas.", "error");
            return;
        }

        if (window.confirm('¿Estás seguro de que quieres que esta crónica se pierda en el tiempo?')) {
            try {
                const response = await fetch(`${API_URL}/eliminar-publicacion/${postId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                const data = await response.json();
                if (!response.ok) {
                    // Mensaje específico si la cuenta no está verificada
                    if (response.status === 403 && data.error === "Usuario no verificado.") {
                        showNotification("Tu cuenta no está verificada. Por favor, verifica tu correo electrónico para borrar crónicas.", "error");
                    } else {
                        throw new Error(data.error);
                    }
                } else {
                    showNotification('La crónica ha sido borrada.', 'success');
                }
                fetchPosts(); // Recargar la lista de posts
            } catch (error) {
                showNotification(error.message, 'error');
            }
        }
    };
    
    const handleEditClick = (postId) => {
        setIsCreating(false);
        setEditingPostId(postId);
    };

    const handleCancelEdit = () => {
        setEditingPostId(null);
    };

    // --- RENDERIZADO DEL COMPONENTE ---
    if (loading) {
        return <div className="loading-screen">Cargando crónicas de Eternia...</div>;
    }

    // Determina si el usuario actual puede realizar acciones que requieren verificación
    const canPerformVerifiedActions = user && user.verificado;


    return (
        <>
            <div className={`notification ${notification.type} ${notification.message ? 'show' : ''}`}>
                {notification.message}
            </div>

            <div className="blog-container">
                <div className="blog-header">
                    <h1>Crónicas de Eternia</h1>
                    {/* Habilitar el botón de crear solo si el usuario está logueado y verificado */}
                    {user && !isCreating && !editingPostId && (
                        <button 
                            className="create-new-post-button" 
                            onClick={() => {
                                if (canPerformVerifiedActions) {
                                    setIsCreating(true);
                                } else {
                                    showNotification("Necesitas verificar tu cuenta para forjar nuevas crónicas.", "error");
                                }
                            }}
                            disabled={!user || !user.verificado} // Deshabilita si no está logueado o no verificado
                        >
                            + Forjar Nueva Crónica
                        </button>
                    )}
                     {user && !user.verificado && (
                        <p className="verification-reminder">
                            ⚠️ Por favor, verifica tu correo electrónico para poder publicar crónicas con imágenes y eliminarlas.
                        </p>
                    )}
                </div>

                {posts.length > 0 ? (
                    posts.map((post) => (
                        editingPostId === post.id ? (
                            <CreatePost 
                                key={`editing-${post.id}`}
                                postToEdit={post}
                                onPostUpdated={handlePostUpdated} // Pasa la función para manejar la actualización exitosa
                                onCancelEdit={handleCancelEdit}
                            />
                        ) : (
                            <BlogPost
                                key={post.id}
                                post={post}
                                currentUser={user} // 'user' ahora incluye 'verificado' y 'id'
                                onDeletePost={handleDeletePost}
                                onEditClick={handleEditClick}
                                onUpdatePost={handlePostUpdated} // Se sigue pasando, aunque ahora CreatePost maneja la API
                                showNotification={showNotification}
                            />
                        )
                    ))
                ) : (
                    <p>Aún no se han escrito crónicas. ¡Sé el primero en forjar una leyenda!</p>
                )}
            </div>

            <AnimatePresence>
                {isCreating && (
                    <motion.div
                        className="create-post-modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => setIsCreating(false)}
                    >
                        <motion.div
                            className="create-post-modal-content"
                            initial={{ y: -50, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            exit={{ y: -50, opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <CreatePost
                                onPostCreated={handlePostCreated}
                                onCancelCreate={() => setIsCreating(false)}
                            />
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
};

export default BlogPage;
