import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { Toaster } from "sonner";

import AuthLayout from "./components/AuthLayout";

import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import ComposeEmail from "./pages/ComposeEmail";
import ScheduledEmails from "./pages/ScheduledEmails";
import SentEmails from "./pages/SentEmails";
import FailedEmails from "./pages/FailedEmails";
import CancelledEmails from "./pages/CancelledEmails";
import Senders from "./pages/Senders";

function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" richColors />

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

          <Route
            path="/failed"
            element={<FailedEmails />}
          />

          <Route
            path="/cancelled"
            element={<CancelledEmails />}
          />

          <Route
            path="/senders"
            element={<Senders />}
          />

        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;