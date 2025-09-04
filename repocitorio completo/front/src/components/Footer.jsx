import React, { useState } from 'react';

function Footer() {
  const API_URL = import.meta.env.VITE_API_URL;
  const currentYear = new Date().getFullYear();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    nombre: '',
    correo: '',
    motivo: ''
  });
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const footerSections = [
    {
      title: 'Enlaces Útiles',
      links: [
        { text: 'Soporte', action: 'openSupport' },
        { text: 'Guía del Juego', url: '/guia' },
      ],
    },
    {
      title: 'Legal',
      links: [
        { text: 'Términos de Servicio', url: `${API_URL}/pdfs/Terminos y Condiciones de Gods Of Eternia.pdf`, isPdf: true },
        { text: 'Política de Privacidad', url: `${API_URL}/pdfs/Política de Privacidad de Gods of Eternia.pdf`, isPdf: true },
      ],
    },
  ];

  const handleLinkClick = (link, e) => {
    if (link.url) {
        // Para los links normales, dejamos que el navegador haga su trabajo
        return;
    }
    e.preventDefault();
    if (link.action === 'openSupport') {
      setIsModalOpen(true);
      setErrorMessage('');
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage("");

    if (!formData.nombre || !formData.correo || !formData.motivo) {
      setErrorMessage('Todos los campos son obligatorios.');
      return;
    }
    if (!formData.correo.includes('@') || !formData.correo.includes('.')) {
      setErrorMessage('Por favor, ingresa un correo electrónico válido.');
      return;
    }

    try {
      const response = await fetch(`${API_URL}/api/support`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      const result = await response.json();

      if (response.ok) {
        setShowSuccessMessage(true);
        setTimeout(() => {
          setIsModalOpen(false);
          setShowSuccessMessage(false);
          setFormData({ nombre: '', correo: '', motivo: '' });
        }, 4000);
      } else {
        setErrorMessage(result.error || 'Error al enviar la solicitud.');
      }
    } catch {
      setErrorMessage('Error de conexión. Inténtalo de nuevo más tarde.');
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setShowSuccessMessage(false);
    setErrorMessage('');
    setFormData({ nombre: '', correo: '', motivo: '' });
  };

  return (
    <div>
      <footer className="footer">
        <div className="footer__container">
          {footerSections.map((section) => (
            <div className="footer__column" key={section.title}>
              <h4 className="footer__title">{section.title}</h4>
              <ul className="footer__links-list">
                {section.links.map((link) => (
                  <li key={link.text}>
                    <a
                      className="footer__link"
                      href={link.url || '#'}
                      onClick={(e) => handleLinkClick(link, e)}
                      {...(link.isPdf ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                    >
                      {link.text}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="footer__copyright">
          <p>&copy; {currentYear} Gods Of Eternia. Todos los derechos reservados.</p>
        </div>
      </footer>

      {isModalOpen && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            {showSuccessMessage ? (
              <div className="support-success">
                <span className="success-icon">&#10004;</span>
                <h3>¡Mensaje Enviado!</h3>
                <p>Gracias por contactarnos, <strong>{formData.nombre}</strong>. Te responderemos pronto.</p>
              </div>
            ) : (
              <>
                <div className="modal-header">
                  <h2 className="modal-title">Contactar Soporte</h2>
                  <button className="modal-close" onClick={closeModal}>×</button>
                </div>
                <div className="support-form">
                  {errorMessage && <p className="error-message">{errorMessage}</p>}
                  <div className="form-group">
                    <label htmlFor="nombre" className="form-label">Nombre</label>
                    <input type="text" id="nombre" name="nombre" className="form-input" value={formData.nombre} onChange={handleInputChange} required />
                  </div>
                  <div className="form-group">
                    <label htmlFor="correo" className="form-label">Correo Electrónico</label>
                    <input type="email" id="correo" name="correo" className="form-input" value={formData.correo} onChange={handleInputChange} required />
                  </div>
                  <div className="form-group">
                    <label htmlFor="motivo" className="form-label">Motivo de Contacto</label>
                    <textarea id="motivo" name="motivo" className="form-textarea" rows="4" value={formData.motivo} onChange={handleInputChange} placeholder="Describe tu consulta o problema..." required></textarea>
                  </div>
                  <div className="form-actions">
                    <button type="button" className="btn btn--secondary" onClick={closeModal}>Cancelar</button>
                    <button type="button" className="btn btn--primary" onClick={handleSubmit}>Enviar</button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Footer;