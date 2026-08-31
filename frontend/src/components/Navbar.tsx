import { useNavigate } from "react-router-dom";
import api from "../services/api";
import "./Navbar.css";

interface NavbarProps {
  userName: string;
}

function Navbar({ userName }: NavbarProps) {
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout");
      navigate("/login");
    } catch (error) {
      console.error("Logout failed:", error);
    }
  };

  return (
    <header className="navbar">
      <div className="navbar-brand">
        Reliable Email Scheduler
      </div>

      <div className="navbar-right">
        <span className="navbar-user">
          {userName}
        </span>

        <button
          className="logout-button"
          onClick={handleLogout}
        >
          Logout
        </button>
      </div>
    </header>
  );
}

export default Navbar;