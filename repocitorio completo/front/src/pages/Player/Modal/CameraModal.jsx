import React, { useState, useEffect, useRef } from 'react';
import './CameraModal.css';

// Función de ayuda para convertir el DataURL de la imagen capturada a un objeto File
const dataURLtoFile = (dataurl, filename) => {
    let arr = dataurl.split(','),
        mime = arr[0].match(/:(.*?);/)[1],
        bstr = atob(arr[1]),
        n = bstr.length,
        u8arr = new Uint8Array(n);
    while (n--) {
        u8arr[n] = bstr.charCodeAt(n);
    }
    return new File([u8arr], filename, { type: mime });
}

// Función para aplicar filtro medieval
const applyMedievalFilter = (canvas, context) => {
    const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
    const data = imageData.data;
    
    // Aplicar efecto sepia y ajustes de color medievales
    for (let i = 0; i < data.length; i += 4) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        
        // Fórmula sepia mejorada con toque medieval
        const tr = 0.393 * r + 0.769 * g + 0.189 * b;
        const tg = 0.349 * r + 0.686 * g + 0.168 * b;
        const tb = 0.272 * r + 0.534 * g + 0.131 * b;
        
        // Ajustar para tono más cálido y dorado (medieval)
        data[i] = Math.min(255, tr * 1.1); // Más rojo/dorado
        data[i + 1] = Math.min(255, tg * 0.95); // Menos verde
        data[i + 2] = Math.min(255, tb * 0.7); // Menos azul para tono cálido
    }
    
    context.putImageData(imageData, 0, 0);
    
    // Aplicar viñeta medieval
    const gradient = context.createRadialGradient(
        canvas.width / 2, canvas.height / 2, 0,
        canvas.width / 2, canvas.height / 2, Math.max(canvas.width, canvas.height) / 2
    );
    gradient.addColorStop(0, 'rgba(0,0,0,0)');
    gradient.addColorStop(0.7, 'rgba(0,0,0,0.1)');
    gradient.addColorStop(1, 'rgba(139,69,19,0.4)'); // Viñeta marrón medieval
    
    context.globalCompositeOperation = 'multiply';
    context.fillStyle = gradient;
    context.fillRect(0, 0, canvas.width, canvas.height);
    
    // Añadir textura de pergamino
    context.globalCompositeOperation = 'overlay';
    context.fillStyle = 'rgba(160,82,45,0.1)'; // Color pergamino
    
    // Crear patrón de textura simple
    for (let x = 0; x < canvas.width; x += 4) {
        for (let y = 0; y < canvas.height; y += 4) {
            if (Math.random() > 0.7) {
                context.fillStyle = `rgba(139,69,19,${Math.random() * 0.1})`;
                context.fillRect(x, y, 2, 2);
            }
        }
    }
    
    // Resetear el modo de composición
    context.globalCompositeOperation = 'source-over';
    
    // Ajustar contraste final
    context.globalCompositeOperation = 'overlay';
    context.fillStyle = 'rgba(101,67,33,0.15)'; // Overlay dorado medieval
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.globalCompositeOperation = 'source-over';
};

const CameraModal = ({ show, onClose, onCapture }) => {
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const previewCanvasRef = useRef(null);
    const streamRef = useRef(null);
    const [error, setError] = useState(null);
    const [capturedImage, setCapturedImage] = useState(null);
    const [isCameraReady, setIsCameraReady] = useState(false);

    useEffect(() => {
        const stopStream = () => {
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(track => track.stop());
                streamRef.current = null;
            }
        };

        if (show && !capturedImage) {
            setError(null);
            setIsCameraReady(false);
            let streamIsActive = true;

            // **VERIFICACIÓN CLAVE: Asegurarse de que navigator.mediaDevices exista**
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                setError("Tu navegador no soporta la API de cámara o estás en un entorno no seguro (no HTTPS/localhost).");
                setIsCameraReady(false); // La cámara no estará lista
                return; // Salir del useEffect
            }

            const constraints = {
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: "user"
                }
            };

            navigator.mediaDevices.getUserMedia(constraints)
                .then(streamData => {
                    if (streamIsActive) {
                        streamRef.current = streamData;
                        if (videoRef.current) {
                            videoRef.current.srcObject = streamData;
                            // Añadido para asegurar que la cámara esté lista antes de capturar
                            videoRef.current.onloadedmetadata = () => {
                                setIsCameraReady(true);
                            };
                            videoRef.current.play();
                        }
                    } else {
                        streamData.getTracks().forEach(track => track.stop());
                    }
                })
                .catch(err => {
                    if (streamIsActive) {
                        console.error("Error al acceder a la cámara:", err);
                        if (err.name === "NotAllowedError") {
                            setError("Permiso de cámara denegado. Por favor, permite el acceso a la cámara.");
                        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
                            setError("No se encontró ninguna cámara. Asegúrate de que tienes una conectada.");
                        } else if (err.name === "NotReadableError" || err.name === "TrackStartError") {
                            setError("La cámara está siendo usada por otra aplicación o hay un problema.");
                        } else {
                            setError(`Error al iniciar la cámara: ${err.message}.`);
                        }
                        setIsCameraReady(false); // La cámara no está lista si hay un error
                    }
                });

            return () => {
                streamIsActive = false;
                stopStream();
            };
        } else {
            stopStream();
            setIsCameraReady(false); // Asegúrate de resetear el estado si el modal se cierra
        }
    }, [show, capturedImage]);

    const handleCapture = () => {
        if (!videoRef.current || !canvasRef.current || !isCameraReady) {
            setError("La cámara no está lista para capturar. Asegúrate de que tienes permisos y estás en un entorno seguro.");
            return;
        }

        const video = videoRef.current;
        const canvas = canvasRef.current;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const context = canvas.getContext('2d');
        
        // Transformación para efecto espejo
        context.translate(canvas.width, 0);
        context.scale(-1, 1);

        // Dibuja la imagen del video en el canvas
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // ¡AQUÍ APLICAMOS EL FILTRO MEDIEVAL!
        applyMedievalFilter(canvas, context);
        
        const dataUrl = canvas.toDataURL('image/jpeg', 0.9); // Calidad alta
        setCapturedImage(dataUrl);

        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
    };

    const handleConfirm = () => {
        if (!capturedImage) return;
        const imageFile = dataURLtoFile(capturedImage, 'medieval_capture.jpg');
        onCapture(imageFile);
        setCapturedImage(null);
        onClose();
    };

    const handleRetake = () => {
        setCapturedImage(null);
        // Cuando se retoma, reinicia el flujo de la cámara si el modal sigue abierto
        if (show) {
            // Un pequeño retraso para permitir que el useEffect se dispare
            setTimeout(() => {
                // Aquí podrías llamar directamente a startCamera si existiera como una función externa
                // o confiar en el useEffect para que se dispare con el cambio de capturedImage a null
            }, 50); 
        }
    };

    const handleClose = () => {
        setCapturedImage(null);
        onClose();
    };

    if (!show) {
        return null;
    }

    return (
        <div className="camera-modal-overlay" onClick={handleClose}>
            <div className="camera-modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                    <h3>{capturedImage ? "Retrato Medieval" : "Cámara del Cronista"}</h3>
                    <p className="medieval-subtitle">
                        {capturedImage ? "Tu retrato ha sido bendecido con la esencia medieval" : "Prepárate para tu retrato épico"}
                    </p>
                </div>
                
                {error ? (
                    <div className="error-message">{error}</div>
                ) : (
                    <div className="camera-view-wrapper">
                        <video 
                            ref={videoRef} 
                            autoPlay 
                            playsInline 
                            className={`camera-video ${capturedImage ? 'hidden' : ''}`}
                            // onCanPlay se usará para asegurar que la cámara está lista
                        ></video>
                        
                        {!isCameraReady && !capturedImage && (
                            <div className="camera-loading-message">Iniciando cámara...</div>
                        )}

                        {capturedImage && 
                            <img 
                                src={capturedImage} 
                                alt="Retrato Medieval" 
                                className="medieval-preview"
                                style={{
                                    position: 'absolute',
                                    top: 0,
                                    left: 0,
                                    width: '100%',
                                    height: '100%',
                                    objectFit: 'cover'
                                }}
                            />
                        }
                        <canvas ref={canvasRef} style={{ display: 'none' }}></canvas>
                        <canvas ref={previewCanvasRef} style={{ display: 'none' }}></canvas>
                        
                        {/* Overlay decorativo medieval cuando está capturando */}
                        {!capturedImage && (
                            <div className="medieval-overlay">
                                <div className="corner-decoration top-left"></div>
                                <div className="corner-decoration top-right"></div>
                                <div className="corner-decoration bottom-left"></div>
                                <div className="corner-decoration bottom-right"></div>
                            </div>
                        )}
                    </div>
                )}

                <div className="camera-modal-actions">
                    {capturedImage ? (
                        <>
                            <button onClick={handleConfirm} className="modal-button confirm">
                                ⚔️ Usar este Retrato
                            </button>
                            <button onClick={handleRetake} className="modal-button retake">
                                🔄 Nuevo Retrato
                            </button>
                        </>
                    ) : (
                        <>
                            <button 
                                onClick={handleCapture} 
                                className="modal-button capture" 
                                disabled={!!error || !isCameraReady}
                            >
                                📸 Crear Retrato Medieval
                            </button>
                            <button onClick={handleClose} className="modal-button cancel">
                                ❌ Cancelar
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CameraModal;
