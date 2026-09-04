import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { toast } from "sonner";

import api from "../services/api";
import "./Senders.css";

interface Sender {
  id: number;
  email: string;
  display_name: string | null;
}

function Senders() {
  const [senders, setSenders] = useState<Sender[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");

  useEffect(() => {
    const loadSenders = async () => {
      try {
        setError("");

        const response = await api.get<Sender[]>("/api/emails/senders");

        setSenders(response.data);
      } catch {
        setError("Failed to load email senders.");
      } finally {
        setLoading(false);
      }
    };

    void loadSenders();
  }, []);

  const handleAddSender = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setError("");
    setSuccess("");
    setSaving(true);

    try {
      const response = await api.post<Sender>("/api/emails/senders", {
        email,
        display_name: displayName || null,
        smtp_host: smtpHost,
        smtp_port: Number(smtpPort),
        smtp_username: smtpUsername,
        smtp_password: smtpPassword,
      });

      setSenders((current) => [...current, response.data]);

      setEmail("");
      setDisplayName("");
      setSmtpHost("");
      setSmtpPort("587");
      setSmtpUsername("");
      setSmtpPassword("");

      toast.success("Email sender added successfully.");
    } catch (requestError: any) {
      setError(
        requestError?.response?.data?.detail ||
          "Failed to add email sender.",
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSender = async (senderId: number) => {
    setError("");
    setSuccess("");
    setDeletingId(senderId);

    try {
      await api.delete(`/api/emails/senders/${senderId}`);

      setSenders((current) =>
        current.filter((sender) => sender.id !== senderId),
      );

      toast.success("Email sender deleted successfully.");
    } catch (requestError: any) {
      setError(
        requestError?.response?.data?.detail ||
          "Failed to delete email sender.",
      );
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <main className="senders-page">
        <p>Loading senders...</p>
      </main>
    );
  }

  return (
    <main className="senders-page">
      <div className="senders-header">
        <h1>Email Senders</h1>
        <p>
          Configure the email accounts used to send scheduled emails.
        </p>
      </div>

      {error && <p className="sender-error">{error}</p>}
      {success && <p className="sender-success">{success}</p>}

      <form
        className="sender-form"
        onSubmit={handleAddSender}
      >
        <label>
          Sender email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            required
          />
        </label>

        <label>
          Display name
          <input
            type="text"
            value={displayName}
            onChange={(event) =>
              setDisplayName(event.target.value)
            }
            placeholder="Your Name"
          />
        </label>

        <label>
          SMTP host
          <input
            type="text"
            value={smtpHost}
            onChange={(event) =>
              setSmtpHost(event.target.value)
            }
            placeholder="smtp.example.com"
            required
          />
        </label>

        <label>
          SMTP port
          <input
            type="number"
            min="1"
            max="65535"
            value={smtpPort}
            onChange={(event) =>
              setSmtpPort(event.target.value)
            }
            required
          />
        </label>

        <label>
          SMTP username
          <input
            type="text"
            value={smtpUsername}
            onChange={(event) =>
              setSmtpUsername(event.target.value)
            }
            placeholder="you@example.com"
            required
          />
        </label>

        <label>
          SMTP password
          <input
            type="password"
            value={smtpPassword}
            onChange={(event) =>
              setSmtpPassword(event.target.value)
            }
            placeholder="SMTP password"
            required
          />
        </label>

        <button type="submit" disabled={saving}>
          {saving ? "Adding..." : "Add Sender"}
        </button>
      </form>

      <section>
        <h2>Configured Senders</h2>

        {senders.length === 0 ? (
          <p>No email senders configured.</p>
        ) : (
          <div className="senders-list">
            {senders.map((sender) => (
              <div
                className="sender-card"
                key={sender.id}
              >
                <strong>
                  {sender.display_name || sender.email}
                </strong>

                {sender.display_name && (
                  <div className="sender-card-email">
                    {sender.email}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() =>
                    handleDeleteSender(sender.id)
                  }
                  disabled={deletingId === sender.id}
                >
                  {deletingId === sender.id
                    ? "Deleting..."
                    : "Delete Sender"}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default Senders;
