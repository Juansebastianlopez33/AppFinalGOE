import React, { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import infoIcon from '../assets/Info.png'; // Asegúrate de que la ruta sea correcta

// Componente Dropdown ultra simplificado, ya que no hay submenús
const SimpleDropdown = ({ items, onItemSelected }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const handleToggle = () => setIsOpen(!isOpen);

  const handleItemClick = (item) => {
    onItemSelected(item);
    setIsOpen(false);
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <div className="dropdown-wrapper" ref={dropdownRef}>
      <button onClick={handleToggle} className="dropdown-button">
        <span className="user-icon">👤</span>
        <span className="dropdown-text">Mi Cuenta</span>
        <span className={`dropdown-arrow ${isOpen ? 'open' : ''}`}>▼</span>
      </button>
      {isOpen && (
        <ul className="dropdown-menu">
          {items.map((item) => (
            <li key={item.id}>
              <button onClick={() => handleItemClick(item)} className="dropdown-item">
                <span className="dropdown-icon">{item.icon}</span>
                <span>{item.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

// Componente Principal del Header
function Header() {
  const navigate = useNavigate();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const headerRef = useRef(null);
  const { isAuthenticated: isLoggedIn, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };
  
  // Array de items simplificado sin "Ajustes"
  const dropdownItems = [
    { id: "perfil", name: "Mi perfil", icon: "👤", url: "/player" },
    { id: "cerrar", name: "Cerrar sesión", icon: "🚪" },
  ];

  const handleDropdownSelect = (item) => {
    setIsMobileMenuOpen(false); // Cierra el menú móvil al seleccionar algo
    if (item.url) {
      navigate(item.url);
    }
    if (item.id === "cerrar") {
      handleLogout();
    }
  };

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (headerRef.current && !headerRef.current.contains(event.target)) {
        setIsMobileMenuOpen(false);
      }
    };
    if (isMobileMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMobileMenuOpen]);

  return (
    <header className="header" ref={headerRef}>
      <div className="header-container">
        <div className="logo-container">
          <Link to="/" className="logo-link-wrapper" onClick={() => setIsMobileMenuOpen(false)}>
            <img 
              src="/Logo_1.jpg" 
              alt="Gods of Eternia Logo" 
              className="game-logo"
              onError={(e) => { e.target.onerror = null; e.target.src = 'https://placehold.co/40x40/8b5a2b/FFFFFF?text=GOE&font=roboto'; }}
            />
            <h1 className="game-title">Gods of Eternia</h1>
          </Link>
        </div>

        <nav className={`nav ${isMobileMenuOpen ? "nav-active" : ""}`}>
          
          {/* Menú para Escritorio */}
          <ul className="desktop-nav">
            {isLoggedIn ? (
              <>
                <li><Link to="/" className="nav-link">🏰 Inicio</Link></li>
                <li>
                  <Link to="/about" className="nav-link">
                    <img src={infoIcon} alt="Acerca de" className="nav-icon" /> Acerca de
                  </Link>
                </li>
                <li> 
                  <SimpleDropdown items={dropdownItems} onItemSelected={handleDropdownSelect} />
                </li>
              </>
            ) : (
              <>
                <li><Link to="/login" className="nav-link">🔑 Iniciar Sesión</Link></li>
                <li><Link to="/register" className="nav-link">📜 Registrarse</Link></li>
              </>
            )}
          </ul>

          {/* Menú para Móvil */}
          <ul className="mobile-nav">
             {isLoggedIn ? (
              <>
                <li><Link to="/" className="nav-link" onClick={toggleMobileMenu}>🏰 Inicio</Link></li>
                <li>
                  <Link to="/about" className="nav-link" onClick={toggleMobileMenu}>
                    <img src={infoIcon} alt="Acerca de" className="nav-icon" /> Acerca de
                  </Link>
                </li>
                {/* Mapeo simplificado, ya no necesita verificar subItems */}
                {dropdownItems.map(item => (
                  <li key={item.id}>
                    <Link 
                      to={item.url || '#'} 
                      className="nav-link" 
                      onClick={() => handleDropdownSelect(item)}
                    >
                      <span className="dropdown-icon">{item.icon}</span> {item.name}
                    </Link>
                  </li>
                ))}
              </>
            ) : (
              <>
                <li><Link to="/login" className="nav-link" onClick={toggleMobileMenu}>🔑 Iniciar Sesión</Link></li>
                <li><Link to="/register" className="nav-link" onClick={toggleMobileMenu}>📜 Registrarse</Link></li>
              </>
            )}
          </ul>
        </nav>

        <button
          className={`hamburger ${isMobileMenuOpen ? "active" : ""}`}
          onClick={toggleMobileMenu}
        >
          <span className="hamburger-line"></span>
          <span className="hamburger-line"></span>
          <span className="hamburger-line"></span>
        </button>
      </div>
    </header>
  );
}

export default Header;