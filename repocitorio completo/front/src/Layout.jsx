import { Link, Outlet } from "react-router-dom";

function Layout() {
  return (
    <div className="bg-gradient-medieval min-h-screen text-white fade-in">
      <header className="fixed w-full bg-[#2b1d0f]/90 backdrop-blur-sm z-50">
        <nav className="container mx-auto px-6 h-20 flex items-center justify-between">
          <h1 className="font-cinzel text-secondary text-3xl font-bold">Gods of Eternia</h1>
          <div className="flex gap-8">
            <Link to="/" className="font-medieval hover:text-secondary transition-colors">Inicio</Link>
            <Link to="/history" className="font-medieval hover:text-secondary transition-colors">Historia</Link>
            <Link to="/characters" className="font-medieval hover:text-secondary transition-colors">Personajes</Link>
            <Link to="/community" className="font-medieval hover:text-secondary transition-colors">Comunidad</Link>
          </div>
        </nav>
      </header>

      <main className="pt-20">
        <Outlet /> 
      </main>
    </div>
  );
}

export default Layout;
