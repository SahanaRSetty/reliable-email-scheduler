import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import Navbar from "./Navbar";
import api from "../services/api";

interface User {
  id: number;
  name: string;
  email: string;
  avatar_url: string | null;
}

function AuthLayout() {
  const navigate = useNavigate();

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const response = await api.get<User>("/auth/me");

        setUser(response.data);
      } catch {
        navigate("/login", { replace: true });
      } finally {
        setLoading(false);
      }
    };

    loadUser();
  }, [navigate]);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return null;
  }

  return (
    <div>
      <Navbar userName={user.name} />

      <Outlet />
    </div>
  );
}

export default AuthLayout;