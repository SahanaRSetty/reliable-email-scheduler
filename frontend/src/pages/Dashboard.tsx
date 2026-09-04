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
          scheduledResponse,
          sentResponse,
        ] = await Promise.all([
          api.get<User>("/auth/me"),
          api.get<EmailStats>("/api/emails/stats"),
          api.get<Email[]>("/api/emails/scheduled"),
          api.get<Email[]>("/api/emails/sent"),
        ]);

        setUser(userResponse.data);
        setStats(statsResponse.data);

        const allEmails = [
          ...scheduledResponse.data,
          ...sentResponse.data,
        ];

        const uniqueEmails = Array.from(
          new Map(
            allEmails.map((email) => [email.id, email])
          ).values()
        );

        const sortedEmails = uniqueEmails
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime()
          )
          .slice(0, 5);

        setRecentEmails(sortedEmails);
      } catch (error) {
        console.error("Failed to load dashboard:", error);
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();

    const refreshInterval = window.setInterval(() => {
      loadDashboard();
    }, 10000);

    return () => {
      window.clearInterval(refreshInterval);
    };
  }, [navigate]);

  if (loading) {
    return (
      <main className="dashboard">
        <div className="dashboard-loading">
          <div className="dashboard-loading-spinner" />
          <p>Loading your dashboard...</p>
        </div>
      </main>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <main className="dashboard">
      <section className="dashboard-hero">
        <div className="dashboard-hero-content">
          <span className="dashboard-eyebrow">
            EMAIL MANAGEMENT
          </span>

          <h1>
            Welcome back, {user.name}
            <span className="dashboard-wave"> 👋</span>
          </h1>

          <p className="dashboard-subtitle">
            Manage your scheduled emails, senders, and delivery
            activity from one place.
          </p>

          <div className="dashboard-hero-actions">
            <button
              className="dashboard-primary-action"
              onClick={() => navigate("/compose")}
            >
              Compose Email
            </button>

            <button
              className="dashboard-secondary-action"
              onClick={() => navigate("/senders")}
            >
              Manage Senders
            </button>
          </div>
        </div>
      </section>

      <section className="dashboard-stats">
        <button
          type="button"
          className="dashboard-stat-card dashboard-stat-scheduled"
          onClick={() => navigate("/scheduled")}
        >
          <span className="dashboard-stat-label">
            Scheduled
          </span>

          <strong>{stats.scheduled}</strong>
        </button>

        <button
          type="button"
          className="dashboard-stat-card dashboard-stat-sent"
          onClick={() => navigate("/sent")}
        >
          <span className="dashboard-stat-label">
            Sent
          </span>

          <strong>{stats.sent}</strong>
        </button>

        <button
          type="button"
          className="dashboard-stat-card dashboard-stat-failed"
          onClick={() => navigate("/failed")}
        >
          <span className="dashboard-stat-label">
            Failed
          </span>

          <strong>{stats.failed}</strong>
        </button>
      </section>

      <section className="recent-emails">
        <div className="recent-emails-header">
          <div>
            <span className="section-eyebrow">
              ACTIVITY
            </span>

            <h2>Recent Email Activity</h2>

            <p>
              Your latest email activity across all statuses.
            </p>
          </div>
        </div>

        {recentEmails.length === 0 ? (
          <div className="recent-empty">
            <div className="recent-empty-icon">✉</div>

            <h3>No email activity yet</h3>

            <p>
              Schedule your first email to start tracking activity.
            </p>

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
                    Email ID: {email.id} •{" "}
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
  );
}

export default Dashboard;