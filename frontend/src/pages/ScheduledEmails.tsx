import { useEffect, useState } from "react";
import api from "../services/api";

interface Recipient {
  email: string;
  status: string;
  sent_at: string | null;
  error_message: string | null;
}

interface ScheduledEmail {
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

function ScheduledEmails() {
  const [emails, setEmails] = useState<ScheduledEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [successMessage, setSuccessMessage] = useState("");

  const fetchScheduledEmails = async () => {
    try {
      const response = await api.get<ScheduledEmail[]>(
        "/api/emails/scheduled"
      );

      setEmails(response.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load scheduled emails.");
    }
  };

  useEffect(() => {
    const loadEmails = async () => {
      setLoading(true);
      await fetchScheduledEmails();
      setLoading(false);
    };

    loadEmails();
  }, []);

  const handleCancel = async (emailId: number) => {
    const confirmed = window.confirm(
      "Are you sure you want to cancel this scheduled email?"
    );

    if (!confirmed) {
      return;
    }

    setCancellingId(emailId);
    setError("");
    setSuccessMessage("");

    try {
      await api.post(`/api/emails/${emailId}/cancel`);

      setSuccessMessage(
        `Email ${emailId} cancelled successfully.`
      );

      await fetchScheduledEmails();
    } catch (err: any) {
      console.error(err);

      setError(
        err.response?.data?.detail ||
          "Failed to cancel email."
      );
    } finally {
      setCancellingId(null);
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <h1>Scheduled Emails</h1>
        <p>Loading scheduled emails...</p>
      </div>
    );
  }

  if (error && emails.length === 0) {
    return (
      <div className="page-container">
        <h1>Scheduled Emails</h1>

        <div className="error-message">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Scheduled Emails</h1>
          <p>
            View and manage your scheduled emails.
          </p>
        </div>

        <a
          href="/compose"
          className="primary-button"
        >
          Compose Email
        </a>
      </div>

      {successMessage && (
        <div className="success-message">
          {successMessage}
        </div>
      )}

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {emails.length === 0 ? (
        <div className="empty-state">
          <h2>No scheduled emails</h2>

          <p>
            You don't have any scheduled emails yet.
          </p>

          <a
            href="/compose"
            className="primary-button"
          >
            Schedule Your First Email
          </a>
        </div>
      ) : (
        <div className="email-list">
          {emails.map((email) => (
            <div
              className="email-card"
              key={email.id}
            >
              <div className="email-card-header">
                <div>
                  <h2>{email.subject}</h2>

                  <p className="email-id">
                    Email ID: {email.id}
                  </p>
                </div>

                <span
                  className={`status status-${email.status}`}
                >
                  {email.status}
                </span>
              </div>

              <div className="email-details">
                <p>
                  <strong>Scheduled:</strong>{" "}
                  {new Date(
                    email.scheduled_at
                  ).toLocaleString()}
                </p>

                <p>
                  <strong>Attempts:</strong>{" "}
                  {email.attempts}
                </p>

                <p>
                  <strong>Sender ID:</strong>{" "}
                  {email.sender_id}
                </p>
              </div>

              <div className="recipients">
                <strong>Recipients:</strong>

                <ul>
                  {email.recipients.map(
                    (recipient, index) => (
                      <li key={index}>
                        {recipient.email}{" "}
                        <span>
                          ({recipient.status})
                        </span>
                      </li>
                    )
                  )}
                </ul>
              </div>

              <div className="email-body">
                <strong>Message</strong>

                <p>{email.body}</p>
              </div>

              {email.last_error && (
                <div className="email-error">
                  {email.last_error}
                </div>
              )}

              {email.status === "scheduled" && (
                <div className="email-actions">
                  <button
                    type="button"
                    className="cancel-button"
                    onClick={() =>
                      handleCancel(email.id)
                    }
                    disabled={
                      cancellingId === email.id
                    }
                  >
                    {cancellingId === email.id
                      ? "Cancelling..."
                      : "Cancel Email"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ScheduledEmails;