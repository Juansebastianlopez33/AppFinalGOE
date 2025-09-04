import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute'; 

import Header from './components/Header';
import Home from './pages/Home';
import Login from './pages/Login/loginpage';
import Register from './pages/Register/Register';
import Verification from './pages/Verification/Verification'; // Página de verificación
import Player from './pages/Player/Player'; 
import BlogPage from './pages/Blog/BlogPage'; // Página del blog
import About from './pages/About/about'; // Página de "Sobre Nosotros"

const App = () => {
  return (
      <AuthProvider>
        <Header /> {/* El Header necesita estar dentro del Provider para saber si el usuario está logueado */}
        <Routes>
          {/* --- Rutas Públicas --- */}
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/verificar" element={<Verification />} />
          <Route path="/blog" element={<BlogPage />} />
          <Route path="/about" element={<About />} />

          {/* --- Rutas Protegidas --- */}
          <Route element={<ProtectedRoute />}>
            <Route path="/player" element={<Player />} />
            {/* Aquí irían otras rutas protegidas como /dashboard, /jugar, etc. */}
          </Route>
        </Routes>
      </AuthProvider>
  );
};

export default App;