import "./about.css";
// Si tu archivo actual está en 'src/pages/About/',
// necesitas subir dos niveles (../../) para llegar a 'src',
// y luego bajar a 'assets/'.
import juanPhoto from "../../assets/juan.jpeg";   // CORREGIDO: de .jpg a .jpeg
import ianPhoto from "../../assets/ian.jpeg";   // Esta ya estaba bien
import brayanPhoto from "../../assets/brayan.jpg"; // CORREGIDO: de .jpg a .webp


const About = () => {
  return (
    <div className="about-container">
      <ul className="about-cards">
        <li className="card-item">
          <img className="card-photo" src={brayanPhoto} alt="Foto de Brayan" />
          <h2>Brayan Penagos</h2>
          <p>¡Hola! Soy desarrollador Front-End. Me apasiona ser el puente entre el diseño creativo y la funcionalidad técnica, construyendo experiencias web que no solo se vean bien, sino que se sientan increíbles para el usuario.</p>
        </li>
        <li className="card-item">
          <img className="card-photo" src={juanPhoto} alt="Foto de Sebastián" />
          <h2>Sebastián López</h2>
          <p>Hola, soy un desarrollador que se enfoca en backend, esforzándome al máximo
            para que todos nuestros usuarios tengan una experiencia optimizada y segura.
          </p>
        </li>
        <li className="card-item">
          <img className="card-photo" src={ianPhoto} alt="Foto de Ian" />
          <h2>Ian Morales</h2>
          <p>Me encanta la programación y la resolución de problemas. Siempre busco mejorar y aprender más sobre el desarrollo web.</p>
        </li>
      </ul>
    </div>
  );
};

export default About;
