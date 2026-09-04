import { useEffect, useState } from "react";
import api from "../services/api";

interface Recipient {
  email: string;
  status: string;
  sent_at: string | null;
  error_message: string | null;
}

interface SentEmail {
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

function SentEmails() {
  const [emails, setEmails] = useState<SentEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchSentEmails = async () => {
      try {
        const response = await api.get<SentEmail[]>(
          "/api/emails/sent"
        );

        setEmails(response.data);
      } catch (err) {
        console.error(err);
        setError("Failed to load sent emails.");
      } finally {
        setLoading(false);
      }
    };

    fetchSentEmails();
  }, []);

  if (loading) {
    return (
      <div className="page-container">
        <h1>Sent Emails</h1>
        <p>Loading sent emails...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-container">
        <h1>Sent Emails</h1>

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
          <h1>Sent Emails</h1>
          <p>View emails that have been successfully delivered.</p>
        </div>
      </div>

      {emails.length === 0 ? (
        <div className="empty-state">
          <h2>No sent emails</h2>

          <p>
            You haven't successfully sent any emails yet.
          </p>
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

                <span
                  className={`status status-${email.status}`}
                >
                  {email.status}
                </span>
              </div>

              <div className="email-details">
                <p>
                  <strong>Scheduled for:</strong>{" "}
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
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default SentEmails;
