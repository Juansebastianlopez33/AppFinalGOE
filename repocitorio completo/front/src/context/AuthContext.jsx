/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { jwtDecode } from 'jwt-decode';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    // Inicializar los tokens desde localStorage
    const [accessToken, setAccessToken] = useState(() => localStorage.getItem("access_token"));
    const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem("refresh_token"));
    
    const [user, setUser] = useState(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [loading, setLoading] = useState(true);

    // Asegúrate de que esta variable de entorno esté configurada en tu archivo .env
    const API_URL = import.meta.env.VITE_API_URL;

    // Función para refrescar el token de acceso
    const refreshAccessToken = useCallback(async () => {
        if (!refreshToken) {
            console.warn("No hay refresh token disponible para refrescar.");
            logout(); // Si no hay refresh token, cerrar sesión
            return false;
        }

        try {
            const response = await fetch(`${API_URL}/refresh`, { // CAMBIO: Endpoint /refresh
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${refreshToken}` // Usar el refresh token aquí
                },
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem("access_token", data.access_token);
                setAccessToken(data.access_token);
                console.log("Access token refrescado exitosamente.");
                return true;
            } else {
                console.error("Fallo al refrescar token:", await response.json());
                logout(); // Si el refresh token falla, cerrar sesión
                return false;
            }
        } catch (error) {
            console.error("Error de red al refrescar token:", error);
            logout(); // Si hay error de red, cerrar sesión
            return false;
        }
    }, [refreshToken, API_URL]);

    // Efecto principal para verificar la autenticación
    useEffect(() => {
        setLoading(true);
        const checkAuth = async () => {
            if (accessToken) {
                try {
                    const decodedUser = jwtDecode(accessToken);
                    const isAccessTokenExpired = decodedUser.exp * 1000 < Date.now();

                    if (isAccessTokenExpired) {
                        console.log("Access token expirado. Intentando refrescar...");
                        const refreshed = await refreshAccessToken();
                        if (refreshed) {
                            // Si se refrescó, el useEffect se re-ejecutará con el nuevo accessToken
                            // así que simplemente salimos de esta ejecución.
                            return; 
                        } else {
                            // Si no se pudo refrescar, logout ya fue llamado.
                            setLoading(false);
                            return;
                        }
                    } else {
                        // Access token válido
                        setUser({
                            id: decodedUser.user_id, // Asegúrate de que el claim sea 'user_id'
                            username: decodedUser.username,
                            email: decodedUser.email,
                            // ¡CORRECCIÓN CLAVE! Guardar el estado de verificación
                            verificado: decodedUser.verificado 
                        });
                        setIsAuthenticated(true);
                        console.log("Usuario autenticado con access token válido.");
                    }
                } catch (error) {
                    console.error("Error al decodificar access token:", error);
                    logout(); // Limpiar tokens inválidos.
                }
            } else {
                // Si no hay access token, no estamos autenticados.
                setIsAuthenticated(false);
                setUser(null);
                console.log("No access token. Usuario no autenticado.");
            }
            setLoading(false);
        };

        checkAuth();
    }, [accessToken, refreshAccessToken]); // Dependencias: accessToken para re-evaluar al cambiar, refreshAccessToken para asegurar su disponibilidad

    // Función de login: ahora acepta ambos tokens
    const login = (newAccessToken, newRefreshToken, userData) => {
        localStorage.setItem("access_token", newAccessToken);
        localStorage.setItem("refresh_token", newRefreshToken);
        setAccessToken(newAccessToken);
        setRefreshToken(newRefreshToken);
        // Al hacer login, también puedes decodificar el token para obtener el estado verificado
        try {
            const decodedUser = jwtDecode(newAccessToken);
            setUser({
                id: decodedUser.user_id,
                username: decodedUser.username,
                email: decodedUser.email,
                verificado: decodedUser.verificado // Guardar el estado de verificación en el login
            });
        } catch (error) {
            console.error("Error al decodificar token durante el login:", error);
            setUser(null);
            setIsAuthenticated(false);
        }
        setIsAuthenticated(true);
        console.log("Login exitoso. Tokens y usuario guardados.");
    };

    // Función de logout
    const logout = () => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        setAccessToken(null);
        setRefreshToken(null);
        setUser(null);
        setIsAuthenticated(false);
        console.log("Cierre de sesión.");
    };

    // El valor que se comparte con toda la aplicación.
    const value = {
        token: accessToken, // Renombrado a `token` para compatibilidad con `Player.jsx`
        user,
        isAuthenticated,
        loading,
        login,
        logout,
        refreshAccessToken // Exponer la función de refresco si es necesario llamarla manualmente
    };

    return (
        <AuthContext.Provider value={value}>
            {/* Solo renderiza los hijos cuando la carga inicial ha terminado */}
            {!loading && children} 
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    return useContext(AuthContext);
};
