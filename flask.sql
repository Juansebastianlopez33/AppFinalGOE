-- Crear la base de datos
CREATE DATABASE IF NOT EXISTS flask_api
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Usar la base de datos recién creada o existente
USE flask_api;

-- Tabla de usuarios
-- Incluye la columna 'foto_perfil' para almacenar la URL de la imagen de perfil
-- y las columnas para restablecimiento de contraseña.
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    DescripUsuario VARCHAR(150),
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verificado BOOLEAN DEFAULT FALSE,
    verification_code VARCHAR(6),        -- Renamed for consistency with Python
    code_expiration DATETIME DEFAULT NULL, -- Renamed for consistency with Python
    foto_perfil VARCHAR(255) DEFAULT NULL, -- Columna para la URL de la foto de perfil
    reset_token VARCHAR(255) NULL,         -- Columna para el token/código de restablecimiento de contraseña
    reset_token_expira DATETIME NULL,      -- Columna para la expiración del token/código de restablecimiento
    token VARCHAR(255) NULL,               -- Added token column
    estado_pregunta VARCHAR(20) DEFAULT NULL -- 🔹 NUEVA COLUMNA
);

-- Tabla de dificultades para las partidas (ej. Fácil, Intermedio, Difícil, Experto)
CREATE TABLE IF NOT EXISTS dificultades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(15) NOT NULL UNIQUE
);

-- Insertar datos iniciales en la tabla de dificultades
-- IGNORE asegura que no se inserten si ya existen (útil para ejecuciones repetidas del script)
INSERT IGNORE INTO dificultades (id, nombre) VALUES
(1, 'Fácil'),
(2, 'Intermedio'),
(3, 'Difícil'),
(4, 'Experto');

-- Tabla de partidas
-- Almacena el progreso y las estadísticas de un usuario en diferentes dificultades.
CREATE TABLE IF NOT EXISTS partidas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    dificultad_id INT NOT NULL,
    puntaje_actual INT DEFAULT 0,
    pergaminos_comunes INT DEFAULT 0,
    pergaminos_raros INT DEFAULT 0,
    pergaminos_epicos INT DEFAULT 0,
    pergaminos_legendarios INT DEFAULT 0,
    mobs_derrotados INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Asegura que un usuario solo tenga una partida por dificultad
    UNIQUE (user_id, dificultad_id),
    -- Claves foráneas para mantener la integridad referencial
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (dificultad_id) REFERENCES dificultades(id) ON DELETE CASCADE
);

-- NUEVO: Tabla de categorías para las publicaciones
CREATE TABLE IF NOT EXISTS categorias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

-- Tabla de publicaciones
-- Donde los usuarios pueden crear posts de texto.
CREATE TABLE IF NOT EXISTS publicaciones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    autor_id INT NOT NULL,
    titulo VARCHAR(255) NOT NULL, -- Added titulo column
    texto TEXT NOT NULL,
    imageUrl VARCHAR(255) DEFAULT NULL, -- Added imageUrl column for primary image
    -- NUEVO: Columna 'categoria_id' para enlazar con la tabla 'categorias'
    categoria_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    likes_count INT DEFAULT 0, -- ¡NUEVA COLUMNA AÑADIDA!
    -- Clave foránea al usuario que creó la publicación
    FOREIGN KEY (autor_id) REFERENCES users(id) ON DELETE CASCADE,
    -- NUEVO: Clave foránea para la categoría
    FOREIGN KEY (categoria_id) REFERENCES categorias(id) ON DELETE SET NULL
);

-- Tabla de imágenes por publicación
-- Permite asociar múltiples imágenes a una sola publicación.
CREATE TABLE IF NOT EXISTS imagenes_publicacion (
    id INT AUTO_INCREMENT PRIMARY KEY,
    publicacion_id INT NOT NULL,
    url VARCHAR(255) NOT NULL, -- URL de la imagen (ej. 'http://localhost:5000/uploads/imagen.jpg')
    orden INT DEFAULT 1, -- Para controlar el orden de las imágenes en una publicación
    -- Clave foránea a la publicación a la que pertenece la imagen
    FOREIGN KEY (publicacion_id) REFERENCES publicaciones(id) ON DELETE CASCADE
);

-- Tabla de comentarios por publicación
-- Almacena los comentarios que los usuarios hacen en las publicaciones.
CREATE TABLE IF NOT EXISTS comentarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    publicacion_id INT NOT NULL,
    autor_id INT NOT NULL,
    texto TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- NUEVO: Columna para registrar la fecha de última edición del comentario
    edited_at TIMESTAMP NULL DEFAULT NULL, 
    -- Claves foráneas a la publicación y al autor del comentario
    FOREIGN KEY (publicacion_id) REFERENCES publicaciones(id) ON DELETE CASCADE,
    FOREIGN KEY (autor_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Tabla de likes para publicaciones
-- Registra los 'me gusta' que un usuario da a una publicación.
CREATE TABLE likes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    publicacion_id INT NOT NULL,
    user_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (publicacion_id, user_id), -- Un usuario solo puede dar 'me gusta' una vez por publicación
    FOREIGN KEY (publicacion_id) REFERENCES publicaciones(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);


-- Tabla de leaderboard
-- Almacena los puntajes más altos de los usuarios por dificultad para una clasificación.
CREATE TABLE IF NOT EXISTS leaderboard (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    dificultad_id INT NOT NULL,
    puntaje INT NOT NULL DEFAULT 0,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Un usuario solo puede tener un registro por dificultad en el leaderboard
    UNIQUE (user_id, dificultad_id),
    -- Claves foráneas a la tabla de usuarios y dificultades
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (dificultad_id) REFERENCES dificultades(id) ON DELETE CASCADE
);

-- Cambiador de delimitador para permitir la creación del TRIGGER
DELIMITER $$

-- TRIGGER para verificar que la publicación a la que se intenta comentar exista
-- Antes de insertar un comentario, se verifica si el publicacion_id existe en la tabla 'publicaciones'.
-- Si no existe, se genera una señal de error (SQLSTATE '45000') y el INSERT es abortado.
CREATE TRIGGER verificar_publicacion_existente
BEFORE INSERT ON comentarios
FOR EACH ROW
BEGIN
    DECLARE existe INT;

    -- Cuenta cuántas publicaciones existen con el ID proporcionado para el nuevo comentario
    SELECT COUNT(*) INTO existe
    FROM publicaciones
    WHERE id = NEW.publicacion_id;

    -- Si no se encuentra ninguna publicación, se lanza un error
    IF existe = 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'No se puede crear el comentario: la publicación no existe.';
    END IF;
END$$

-- Restaura el delimitador por defecto a punto y coma
DELIMITER ;

-- NUEVO: Inserts iniciales para categorías
INSERT IGNORE INTO categorias (id, nombre) VALUES (1, 'Noticias');
INSERT IGNORE INTO categorias (id, nombre) VALUES (2, 'Tutoriales');
INSERT IGNORE INTO categorias (id, nombre) VALUES (3, 'Eventos');
INSERT IGNORE INTO categorias (id, nombre) VALUES (4, 'Opinión');
INSERT IGNORE INTO categorias (id, nombre) VALUES (5, 'Desarrollo');
INSERT IGNORE INTO categorias (id, nombre) VALUES (6, 'General');
