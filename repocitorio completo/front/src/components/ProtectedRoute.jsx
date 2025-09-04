// src/components/ProtectedRoute.jsx

import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const ProtectedRoute = () => {
  // 1. OBTENEMOS 'isAuthenticated' Y EL NUEVO ESTADO 'loading'
  const { isAuthenticated, loading } = useAuth();

  // 2. SI ESTÁ CARGANDO, NO MOSTRAMOS NADA (O UN SPINNER/SKELETON)
  // Esto evita la redirección prematura.
  if (loading) {
    return null; // O puedes retornar un componente <div>Cargando...</div>
  }

  // 3. UNA VEZ QUE LA CARGA TERMINÓ, TOMAMOS LA DECISIÓN
  // Si no está autenticado, lo redirigimos al login.
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // 4. SI TODO ESTÁ BIEN, MOSTRAMOS LA RUTA PROTEGIDA
  return <Outlet />;
};

export default ProtectedRoute;