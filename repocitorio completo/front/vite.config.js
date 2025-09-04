// vite.config.js

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  
  // ✨ LA SOLUCIÓN ESTÁ AQUÍ ✨
  // Esta línea le dice a Vite que la base de todas las rutas de los assets es el directorio raíz ('/').
  // Esto asegura que al recargar en '/player', la petición para '/src/main.jsx' se resuelva correctamente.
  base: '/', 
});