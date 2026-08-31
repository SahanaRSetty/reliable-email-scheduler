import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import AuthLayout from "./components/AuthLayout";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import ComposeEmail from "./pages/ComposeEmail";
import ScheduledEmails from "./pages/ScheduledEmails";
import SentEmails from "./pages/SentEmails";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={<Navigate to="/login" replace />}
        />

        <Route
          path="/login"
          element={<Login />}
        />

        <Route element={<AuthLayout />}>
          <Route
            path="/dashboard"
            element={<Dashboard />}
          />

          <Route
            path="/compose"
            element={<ComposeEmail />}
          />

          <Route
            path="/scheduled"
            element={<ScheduledEmails />}
          />

          <Route
            path="/sent"
            element={<SentEmails />}
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;