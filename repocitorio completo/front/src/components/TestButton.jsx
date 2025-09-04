// src/components/TestButton.jsx

import React from 'react';

const TestButton = () => {
  return (
    // Simplemente renderizamos el botón con sus clases y spans
    <button className="hamburger active">
      <span className="hamburger-line"></span>
      <span className="hamburger-line"></span>
      <span className="hamburger-line"></span>
    </button>
  );
};

export default TestButton;