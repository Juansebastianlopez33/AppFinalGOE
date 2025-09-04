import React, { useState, useEffect } from 'react';

// Añadimos la nueva propiedad 'onComplete'
function TypingEffect({ text, speed = 150, onComplete }) {
    const [displayedText, setDisplayedText] = useState('');

    useEffect(() => {
        let i = 0;
        setDisplayedText('');

        const typingInterval = setInterval(() => {
            if (i < text.length) {
                setDisplayedText((prev) => prev + text.charAt(i));
                i++;
            } else {
                clearInterval(typingInterval);
                // Cuando termina, llamamos a la función onComplete si existe
                if (onComplete) {
                    onComplete();
                }
            }
        }, speed);

        return () => {
            clearInterval(typingInterval);
        };
    }, [text, speed, onComplete]);

    return <span>{displayedText}</span>;
}

export default TypingEffect;