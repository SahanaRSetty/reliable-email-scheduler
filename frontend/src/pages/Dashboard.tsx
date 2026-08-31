import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import api from "../services/api";
import "./Dashboard.css";

interface User {
  id: number;
  name: string;
  email: string;
  avatar_url: string | null;
}

interface EmailStats {
  scheduled: number;
  sent: number;
  failed: number;
}

interface Recipient {
  email: string;
  status: string;
  sent_at: string | null;
  error_message: string | null;
}

interface Email {
  id: number;
  sender_id: number;
  subject: string;
  body: string;
  scheduled_at: string;
  status: string;
  attempts: number;
  last_error: string | null;
  created_at: string;
  recipients: Recipient[];
}

function Dashboard() {
  const navigate = useNavigate();

  const [user, setUser] = useState<User | null>(null);

  const [stats, setStats] = useState<EmailStats>({
    scheduled: 0,
    sent: 0,
    failed: 0,
  });

  const [recentEmails, setRecentEmails] = useState<Email[]>([]);

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const [
          userResponse,
          statsResponse,
          emailsResponse,
        ] = await Promise.all([
          api.get<User>("/auth/me"),
          api.get<EmailStats>("/api/emails/stats"),
          api.get<Email[]>("/api/emails/scheduled"),
        ]);

        setUser(userResponse.data);
        setStats(statsResponse.data);

        const sortedEmails = [...emailsResponse.data]
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
          )
          .slice(0, 5);

        setRecentEmails(sortedEmails);
      } catch (error) {
        console.error(
          "Failed to load dashboard:",
          error
        );

        navigate("/login");
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();
  }, [navigate]);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return null;
  }

  return (
    <div>

      <main className="dashboard">
        <h1>Welcome, {user.name} 👋</h1>

        <p className="dashboard-subtitle">
          Manage your scheduled emails from one place.
        </p>

        <div className="dashboard-cards">
          <div
            className="dashboard-card dashboard-card-clickable"
            onClick={() => navigate("/scheduled")}
          >
            <span>Scheduled</span>
            <strong>{stats.scheduled}</strong>
          </div>

          <div
            className="dashboard-card dashboard-card-clickable"
            onClick={() => navigate("/sent")}
          >
            <span>Sent</span>
            <strong>{stats.sent}</strong>
          </div>

          <div className="dashboard-card">
            <span>Failed</span>
            <strong>{stats.failed}</strong>
          </div>
        </div>

        <div className="dashboard-actions">
          <button onClick={() => navigate("/compose")}>
            Compose Email
          </button>

          <button onClick={() => navigate("/scheduled")}>
            View Scheduled Emails
          </button>

          <button onClick={() => navigate("/sent")}>
            View Sent Emails
          </button>
        </div>

        <section className="recent-emails">
          <div className="recent-emails-header">
            <div>
              <h2>Recent Email Activity</h2>
              <p>
                Your latest scheduled and delivered emails.
              </p>
            </div>

            <button
              className="secondary-button"
              onClick={() => navigate("/scheduled")}
            >
              View All
            </button>
          </div>

          {recentEmails.length === 0 ? (
            <div className="recent-empty">
              <p>No email activity yet.</p>

              <button
                onClick={() => navigate("/compose")}
              >
                Schedule Your First Email
              </button>
            </div>
          ) : (
            <div className="recent-email-list">
              {recentEmails.map((email) => (
                <div
                  className="recent-email-item"
                  key={email.id}
                >
                  <div className="recent-email-main">
                    <h3>{email.subject}</h3>

                    <p>
                      Email ID: {email.id} ·{" "}
                      {email.recipients.length} recipient
                      {email.recipients.length !== 1
                        ? "s"
                        : ""}
                    </p>
                  </div>

                  <div className="recent-email-right">
                    <span
                      className={`status status-${email.status}`}
                    >
                      {email.status}
                    </span>

                    <span className="recent-email-date">
                      {new Date(
                        email.created_at
                      ).toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default Dashboard;