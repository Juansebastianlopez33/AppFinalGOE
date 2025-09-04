import { useRef, useState, useEffect } from "react";
import "./Dropdown.css"; 

const MenuButton = ({ name, icon, onClick, hasSubItems, className }) => {
  return (
    <button className={`menu-button ${className || ""}`} onClick={onClick}>
      {icon && <span className="icon">{icon}</span>}
      <span className="name">{name}</span>
      {hasSubItems && <span className="chevron">{"\u276F"}</span>}{" "}
      {/* Chevron right */}
    </button>
  );
};

const MenuItem = ({
  item,
  onItemClick,
  activeSubMenu,
  onToggleSubMenu,
  parentMenuName,
}) => {
  const subMenuRef = useRef(null);
  const [subMenuHeight, setSubMenuHeight] = useState(0);

  const hasSubItems = item.subItems && item.subItems.length > 0;
  const isActive = activeSubMenu === item.id;

  useEffect(() => {
    // Calcula la altura del submenú cuando se abre o sus items cambian
    if (subMenuRef.current) {
      setSubMenuHeight(subMenuRef.current.scrollHeight);
    }
  }, [item.subItems, isActive]); // Recalcular si los subitems cambian o el menú se activa/desactiva

  const handleButtonClick = () => {
    if (hasSubItems) {
      // Pasa el ID del submenú y su altura para la animación del contenedor principal
      onToggleSubMenu(item.id, subMenuRef.current?.scrollHeight || 0);
    } else if (onItemClick) {
      onItemClick(item); // Llama al manejador de clic del ítem principal
    }
  };

  const handleBackClick = () => {
    onToggleSubMenu(null, 0); // Cierra el submenú actual, volviendo al menú principal
  };

  return (
    <>
      <MenuButton
        onClick={handleButtonClick}
        name={item.name}
        icon={item.icon}
        hasSubItems={hasSubItems}
      />
      {hasSubItems && (
        <div
          ref={subMenuRef}
          className={`sub-menu ${isActive ? "open" : ""}`}
          // La altura se anima para el efecto de slide
          style={{ height: isActive ? `${subMenuHeight}px` : "0px" }}
        >
          {/* Botón para volver al menú principal */}
          <MenuButton
            onClick={handleBackClick}
            icon={"\u2B05"} // Flecha hacia atrás
            name={parentMenuName || item.name} // Muestra el nombre del menú padre o el actual
            className="back-button"
          />
          {item.subItems.map((subItem) => (
            <MenuButton
              key={subItem.id || subItem.name} // Usar un id único si está disponible
              name={subItem.name}
              icon={subItem.icon}
              onClick={() => {
                if (onItemClick) onItemClick(subItem); // Llama al manejador de clic para sub-items
              }}
            />
          ))}
        </div>
      )}
    </>
  );
};

export const Dropdown = ({ items, onItemSelected }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeSubMenu, setActiveSubMenu] = useState(null); // ID del submenú activo
  const [currentSubMenuHeight, setCurrentSubMenuHeight] = useState(0); // Altura del submenú activo
  const dropdownRef = useRef(null); // Referencia al contenedor del dropdown para detectar clics fuera

  const handleToggleDropdown = () => {
    setIsOpen(!isOpen);
    if (isOpen) {
      // Si se está cerrando el dropdown principal, también cierra cualquier submenú abierto
      setActiveSubMenu(null);
      setCurrentSubMenuHeight(0);
    }
  };

  const handleToggleSubMenu = (itemId, height) => {
    if (activeSubMenu === itemId) {
      // Si se hace clic en el mismo submenú, se cierra
      setActiveSubMenu(null);
      setCurrentSubMenuHeight(0);
    } else {
      setActiveSubMenu(itemId);
      setCurrentSubMenuHeight(height);
    }
  };

  const handleItemClick = (item) => {
    if (onItemSelected) {
      onItemSelected(item); // Llama a la función pasada desde el componente padre (Header)
    }
    // Cierra el dropdown y cualquier submenú después de seleccionar un item
    setIsOpen(false);
    setActiveSubMenu(null);
    setCurrentSubMenuHeight(0);
  };

  // Efecto para cerrar el dropdown si se hace clic fuera de él
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
        setActiveSubMenu(null);
        setCurrentSubMenuHeight(0);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <div className="dropdown-container" ref={dropdownRef}>
      <button onClick={handleToggleDropdown} className="dropdown-toggle-button">
        Menú Perfil {/* Puedes cambiar este texto o usar un ícono, como un avatar */}
        <span className={`arrow ${isOpen ? "up" : "down"}`}></span>
      </button>
      {isOpen && (
        <div
          className="dropdown-menu"
          style={{
            height: activeSubMenu
              ? `${currentSubMenuHeight + 60}px` 
              : "auto", 
          }}
        >
          {!activeSubMenu &&
            items.map((item) => (
              <MenuItem
                key={item.id || item.name}
                item={item}
                onItemClick={handleItemClick}
                activeSubMenu={activeSubMenu}
                onToggleSubMenu={handleToggleSubMenu} 
              />
            ))}
          {/* Muestra el submenú activo si lo hay */}
          {activeSubMenu &&
            items
              .filter((item) => item.id === activeSubMenu)
              .map((item) => (
                <MenuItem
                  key={item.id}
                  item={item}
                  onItemClick={handleItemClick}
                  activeSubMenu={activeSubMenu} // Propagado para MenuItem
                  onToggleSubMenu={handleToggleSubMenu} // Propagado para MenuItem
                  parentMenuName="Principal" // Texto para el botón "back" del submenú
                />
              ))}
        </div>
      )}
    </div>
  );
};