import { NavLink, useNavigate } from "react-router-dom";
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

      <nav className="navbar-links">
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Dashboard
        </NavLink>

        <NavLink
          to="/compose"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Compose
        </NavLink>

        <NavLink
          to="/scheduled"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Scheduled
        </NavLink>

        <NavLink
          to="/sent"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Sent
        </NavLink>

        <NavLink
          to="/failed"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Failed
        </NavLink>

        <NavLink
          to="/cancelled"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Cancelled
        </NavLink>

        <NavLink
          to="/senders"
          className={({ isActive }) =>
            isActive ? "navbar-link active" : "navbar-link"
          }
        >
          Senders
        </NavLink>
      </nav>

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