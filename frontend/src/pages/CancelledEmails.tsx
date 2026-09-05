import { useEffect, useState } from "react";

import api from "../services/api";
import "./CancelledEmails.css";

interface Recipient {
  email: string;
  status: string;
  sent_at: string | null;
  error_message: string | null;
}

interface CancelledEmail {
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

function CancelledEmails() {
  const [emails, setEmails] = useState<CancelledEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;

    const loadCancelledEmails = async () => {
        try {
            const response = await api.get<CancelledEmail[]>(
                "/api/emails/cancelled",
            );

            if (mounted) {
                setEmails(response.data);
                setError("");
            }
        } catch (err) {
        console.error(err);

        if (mounted) {
            setError("Failed to load cancelled emails.");
        }
    } finally {
      if (mounted) {
        setLoading(false);
      }
    }
  };

  loadCancelledEmails();

  return () => {
    mounted = false;
  };
}, []);

  if (loading) {
    return (
      <main className="email-page">
        <h1>Cancelled Emails</h1>
        <p>Loading cancelled emails...</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="email-page">
        <h1>Cancelled Emails</h1>
        <div className="error-message">{error}</div>
      </main>
    );
  }

  return (
    <main className="email-page">
      <div className="email-page-header">
        <div>
          <h1>Cancelled Emails</h1>
          <p>Emails that were cancelled before delivery.</p>
        </div>
      </div>

      {emails.length === 0 ? (
        <div className="empty-state">
          <h2>No cancelled emails</h2>
          <p>Cancelled scheduled emails will appear here.</p>
        </div>
      ) : (
        <div className="email-list">
          {emails.map((email) => (
            <div className="email-card" key={email.id}>
              <div className="email-card-header">
                <div>
                  <h2>{email.subject}</h2>

                  <p className="email-id">
                    Email ID: {email.id}
                  </p>
                </div>

                <span className="status-badge cancelled">
                  CANCELLED
                </span>
              </div>

              <div className="email-details">
                <p>
                  <strong>Scheduled for:</strong>{" "}
                  {new Date(email.scheduled_at).toLocaleString()}
                </p>

                <p>
                  <strong>Attempts:</strong>{" "}
                  {email.attempts}
                </p>

                <p>
                  <strong>Recipients:</strong>
                </p>

                <ul>
                  {email.recipients.map((recipient) => (
                    <li key={recipient.email}>
                      {recipient.email}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="email-body">
                <strong>Message</strong>
                <p>{email.body}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

export default CancelledEmails;