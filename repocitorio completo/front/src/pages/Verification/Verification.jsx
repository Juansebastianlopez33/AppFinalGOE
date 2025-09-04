import { useState, useEffect } from "react";
// eslint-disable-next-line no-unused-vars
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import "./Verification.css";

const Verification = ({ prefilledEmail = "" }) => {
    // CAMBIO: Leemos la variable de entorno
    const API_URL = import.meta.env.VITE_API_URL;

    const [loading, setLoading] = useState(true);
    const [code, setCode] = useState("");
    const [email, setEmail] = useState(prefilledEmail);
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false); // MEJORA: Estado de carga para el botón
    const navigate = useNavigate();

    useEffect(() => {
        // MEJORA: Unificamos los efectos que se ejecutan solo al montar el componente
        document.title = 'Verificación | Gods Of Eternia';
        setTimeout(() => setLoading(false), 1000);
    }, []); // MEJORA: Añadido el array de dependencias vacío

    const handleSubmit = async (e) => {
        e.preventDefault();
        setMessage("");
        setError("");
        setIsSubmitting(true); // MEJORA: Activar loading

        try {
            // CAMBIO: Usamos la variable API_URL
            const response = await fetch(`${API_URL}/verificar`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                // AJUSTE CLAVE AQUÍ: Ahora enviamos 'email' y 'verification_code'
                body: JSON.stringify({
                    email: email, // ¡Añadido el email!
                    verification_code: code // Cambiado de 'codigo' a 'verification_code' para coincidir con el backend
                }),
            });

            const data = await response.json();

            if (response.ok) {
                setMessage(data.message);
                setTimeout(() => {
                    navigate("/login");
                }, 1500);
            } else {
                setError(data.error || "Error de verificación");
            }
        } catch (err) {
            console.error("Error al conectar con el servidor de verificación:", err);
            setError("Error al conectar con el servidor. Verifica que esté activo.");
        } finally {
            setIsSubmitting(false); // MEJORA: Desactivar loading en cualquier caso
        }
    };

    return (
        <div className="verification-container">
            {loading ? (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="loading-screen"
                >
                    Cargando...
                </motion.div>
            ) : (
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.5 }}
                    className="verification-box"
                >
                    <h2>Verificación - Gods of Eternia</h2>
                    <p>Ingresa tu correo y el código que te enviamos.</p>
                    <form onSubmit={handleSubmit}>
                        <input
                            type="email"
                            placeholder="Correo electrónico"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                        />
                        <input
                            type="text"
                            maxLength="6"
                            placeholder="Código de verificación"
                            required
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                        />
                        {/* MEJORA: Deshabilitamos el botón y cambiamos el texto mientras carga */}
                        <button type="submit" disabled={isSubmitting}>
                            {isSubmitting ? "Verificando..." : "Verificar"}
                        </button>
                    </form>

                    {message && <p className="success">{message}</p>}
                    {error && <p className="error">{error}</p>}
                </motion.div>
            )}
        </div>
    );
};

export default Verification;
