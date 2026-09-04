import { useEffect, useState } from "react";
import { toast } from "sonner";

import api from "../services/api";

interface Recipient {
  email: string;
  status: string;
  sent_at: string | null;
  error_message: string | null;
}

interface FailedEmail {
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

function FailedEmails() {
  const [emails, setEmails] = useState<FailedEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchFailedEmails = async () => {
    try {
      const response = await api.get<FailedEmail[]>(
        "/api/emails/scheduled"
      );

      const failedEmails = response.data.filter(
        (email) => email.status === "failed"
      );

      setEmails(failedEmails);
    } catch (err) {
      console.error(err);
      setError("Failed to load failed emails.");
    }
  };

  useEffect(() => {
    const loadEmails = async () => {
      setLoading(true);
      await fetchFailedEmails();
      setLoading(false);
    };

    loadEmails();
  }, []);

  const handleRetry = async (emailId: number) => {
    const confirmed = window.confirm(
      "Are you sure you want to retry this failed email?"
    );

    if (!confirmed) {
      return;
    }

    setRetryingId(emailId);
    setError("");
    setSuccessMessage("");

    try {
      await api.post(`/api/emails/${emailId}/retry`);

      toast.success("Email retry scheduled successfully.");

      setSuccessMessage(
        `Email ${emailId} queued for retry successfully.`
      );

      await fetchFailedEmails();
    } catch (err: any) {
      console.error(err);

      const requestError = err;

      setError(
        requestError?.response?.data?.detail ||
          "Failed to retry email."
      );

      toast.error(
        requestError?.response?.data?.detail ||
          "Failed to retry email."
      );
    } finally {
      setRetryingId(null);
    }
  };

  const handleDelete = async (emailId: number) => {
    const confirmed = window.confirm(
      "Are you sure you want to permanently delete this failed email?"
    );

    if (!confirmed) {
      return;
    }

    setDeletingId(emailId);
    setError("");
    setSuccessMessage("");

    try {
      await api.delete(`/api/emails/${emailId}`);

      toast.success("Email deleted successfully.");

      setSuccessMessage(
        `Email ${emailId} deleted successfully.`
      );

      await fetchFailedEmails();
    } catch (err: any) {
      console.error(err);

      const requestError = err;

      setError(
        requestError?.response?.data?.detail ||
          "Failed to delete email."
      );

      toast.error(
        requestError?.response?.data?.detail ||
          "Failed to delete email."
      );
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="page-container">
        <h1>Failed Emails</h1>
        <p>Loading failed emails...</p>
      </div>
    );
  }

  if (error && emails.length === 0) {
    return (
      <div className="page-container">
        <h1>Failed Emails</h1>

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
          <h1>Failed Emails</h1>
          <p>
            Review failed emails and retry eligible deliveries.
          </p>
        </div>
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
          <h2>No failed emails</h2>

          <p>
            You don't have any failed emails.
          </p>
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

                <span className="status status-failed">
                  failed
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

              {email.last_error && (
                <div className="email-error">
                  {email.last_error}
                </div>
              )}

              <div className="email-actions">
                <button
                  type="button"
                  className="primary-button"
                  onClick={() =>
                    handleRetry(email.id)
                  }
                  disabled={
                    retryingId === email.id ||
                    deletingId === email.id
                  }
                >
                  {retryingId === email.id
                    ? "Retrying..."
                    : "Retry Email"}
                </button>

                <button
                  type="button"
                  className="delete-button"
                  onClick={() =>
                    handleDelete(email.id)
                  }
                  disabled={
                    retryingId === email.id ||
                    deletingId === email.id
                  }
                >
                  {deletingId === email.id
                    ? "Deleting..."
                    : "Delete Email"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default FailedEmails;