import { useState, useEffect } from "react";
import { FaEye, FaEyeSlash } from "react-icons/fa";
// eslint-disable-next-line no-unused-vars
import { motion } from "framer-motion";
import { useNavigate, useSearchParams } from "react-router-dom";
import "./resetpassword.css"; // Puedes usar el mismo CSS del login o crear uno nuevo

const ResetPassword = () => {
    const API_URL = import.meta.env.VITE_API_URL;
    const [newPassword, setNewPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [resetCode, setResetCode] = useState("");
    const [showNewPassword, setShowNewPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    
    // Obtener el token del URL si viene por enlace
    const tokenFromUrl = searchParams.get("token");
    
    useEffect(() => {
        // Si hay token en la URL, no necesitamos que ingrese código
        if (tokenFromUrl) {
            setResetCode(tokenFromUrl);
        }
    }, [tokenFromUrl]);

    const validatePasswords = () => {
        if (newPassword.length < 6) {
            setError("La contraseña debe tener al menos 6 caracteres");
            return false;
        }
        
        if (newPassword !== confirmPassword) {
            setError("Las contraseñas no coinciden");
            return false;
        }
        
        return true;
    };

    const handleResetPassword = async (e) => {
        e.preventDefault();
        setError("");
        setSuccess("");

        if (!validatePasswords()) {
            return;
        }

        if (!resetCode && !tokenFromUrl) {
            setError("Código de verificación requerido");
            return;
        }

        setIsLoading(true);

        try {
            const response = await fetch(`${API_URL}/reset-password`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    token: resetCode || tokenFromUrl,
                    newPassword: newPassword,
                }),
            });

            const data = await response.json();

            if (response.ok) {
                setSuccess("Contraseña restablecida exitosamente");
                setTimeout(() => {
                    navigate("/login");
                }, 2000);
            } else {
                setError(data.error || "Error al restablecer la contraseña");
            }
        } catch (err) {
            console.error("Error al restablecer contraseña:", err);
            setError("No se pudo conectar con el servidor. Verifica que esté activo.");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="login-container"> 
            <motion.div
                initial={{ y: -50, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.5 }}
                className="login-box"
            >
                <h2>Restablecer Contraseña</h2>
                
                {error && <p className="error-message">{error}</p>}
                {success && <p className="success-message">{success}</p>}
                
                <form onSubmit={handleResetPassword}>
                    {/* Campo de código solo si no viene token por URL */}
                    {!tokenFromUrl && (
                        <div className="password-container">
                            <input
                                type="text"
                                placeholder="Código de verificación"
                                value={resetCode}
                                onChange={(e) => setResetCode(e.target.value)}
                                required
                            />
                            <span className="eye-button" style={{ visibility: 'hidden' }}>
                                <FaEye />
                            </span>
                        </div>
                    )}

                    {/* Campo de nueva contraseña */}
                    <div className="password-container">
                        <input
                            type={showNewPassword ? "text" : "password"}
                            placeholder="Nueva contraseña"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            className="password-input"
                            required
                        />
                        <span className="eye-button" onClick={() => setShowNewPassword(!showNewPassword)}>
                            {showNewPassword ? <FaEyeSlash /> : <FaEye />}
                        </span>
                    </div>

                    {/* Campo de confirmar contraseña */}
                    <div className="password-container">
                        <input
                            type={showConfirmPassword ? "text" : "password"}
                            placeholder="Confirma contraseña"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            className="password-input"
                            required
                        />
                        <span className="eye-button" onClick={() => setShowConfirmPassword(!showConfirmPassword)}>
                            {showConfirmPassword ? <FaEyeSlash /> : <FaEye />}
                        </span>
                    </div>

                    <button type="submit" disabled={isLoading}>
                        {isLoading ? "Restableciendo..." : "Restablecer Contraseña"}
                    </button>
                </form>

                <div className="forgot-password" onClick={() => navigate("/login")}>
                    Volver al inicio de sesión
                </div>
            </motion.div>
        </div>
    );
};

export default ResetPassword;