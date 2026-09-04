import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { toast } from "sonner";

import api from "../services/api";
import "./ComposeEmail.css";

interface Sender {
  id: number;
  email: string;
  display_name: string | null;
}

function ComposeEmail() {

  const [senders, setSenders] = useState<Sender[]>([]);
  const [senderId, setSenderId] = useState("");

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [recipients, setRecipients] = useState("");
  const [csvFileName, setCsvFileName] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");

  const [loadingSenders, setLoadingSenders] = useState(true);
  const [loading, setLoading] = useState(false);

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const loadSenders = async () => {
      try {
        const response = await api.get<Sender[]>(
          "/api/emails/senders",
        );

        setSenders(response.data);

        if (response.data.length > 0) {
          setSenderId(String(response.data[0].id));
        }
      } catch (err) {
        console.error(err);
        setError("Failed to load email senders.");
      } finally {
        setLoadingSenders(false);
      }
    };

    loadSenders();
  }, []);


  function handleCsvUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Please upload a CSV file.");
      toast.error("Please upload a CSV file.");
      event.target.value = "";
      return;
    }

    const reader = new FileReader();

    reader.onload = () => {
      const text = String(reader.result ?? "");

    const emails = text
      .split(/\r?\n/)
      .flatMap((line) => line.split(","))
      .map((value) => value.trim())
      .filter(Boolean);

    if (emails.length === 0) {
      setError("The CSV file does not contain any email addresses.");
      toast.error("The CSV file does not contain any email addresses.");
      return;
    }

    const uniqueEmails = [...new Set(emails)];

    setRecipients(uniqueEmails.join(", "));
    setCsvFileName(file.name);
    setError("");

    toast.success(
      `${uniqueEmails.length} recipient${
        uniqueEmails.length === 1 ? "" : "s"
      } imported from CSV.`,
    );
  };

  reader.onerror = () => {
    setError("Failed to read the CSV file.");
    toast.error("Failed to read the CSV file.");
  };

  reader.readAsText(file);
}


  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    setLoading(true);
    setMessage("");
    setError("");

    try {
      const recipientList = recipients
        .split(",")
        .map((email) => email.trim())
        .filter(Boolean);

      const response = await api.post("/api/emails/schedule", {
        sender_id: Number(senderId),
        subject,
        body,
        scheduled_at: new Date(
          scheduledAt,
        ).toISOString(),
        recipients: recipientList.map((email) => ({
          email,
        })),
      });

      setMessage(
        `Email scheduled successfully. Email ID: ${response.data.email_id}`,
      );

      toast.success("Email scheduled successfully.");

      setSubject("");
      setBody("");
      setRecipients("");
      setScheduledAt("");
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail ||
        "Failed to schedule email. Please try again.";

      setError(errorMessage);

      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="compose-page">
      <div className="compose-container">

        <div className="compose-header">
          <h1>Compose Email</h1>

          <p>
            Create and schedule an email for delivery.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="compose-form"
        >

          {/* Sender */}
          <div className="form-group">
            <label htmlFor="sender">
              From
            </label>

            {loadingSenders ? (
              <p className="form-help">
                Loading senders...
              </p>
            ) : senders.length === 0 ? (
              <div className="error-message">
                No email senders are configured for your account.
              </div>
            ) : (
              <>
                <select
                  id="sender"
                  value={senderId}
                  onChange={(event) =>
                    setSenderId(event.target.value)
                  }
                  required
                  className="form-input"
                >
                  {senders.map((sender) => (
                    <option
                      key={sender.id}
                      value={sender.id}
                    >
                      {sender.display_name
                        ? `${sender.display_name} <${sender.email}>`
                        : sender.email}
                    </option>
                  ))}
                </select>

                <small className="form-help">
                  Select the email address you want to send from.
                </small>
              </>
            )}
          </div>

          {/* Recipients */}
          <div className="form-group">
            <label htmlFor="recipients">
              To
            </label>

            <input
              id="recipients"
              type="text"
              value={recipients}
              onChange={(event) =>
                setRecipients(event.target.value)
              }
              placeholder="person1@example.com, person2@example.com"
              required
              className="form-input"
            />

            <small className="form-help">
              Separate multiple email addresses with commas.
            </small>

            <div className="csv-upload">
              <label htmlFor="csvFile" className="csv-upload-label">
                Or upload recipients from CSV
              </label>

              <input
                id="csvFile"
                type="file"
                accept=".csv,text/csv"
                onChange={handleCsvUpload}
                className="form-input"
              />

              {csvFileName && (
                <small className="form-help">
                  Imported from: {csvFileName}
                </small>
              )}
            </div>
          </div>

          {/* Subject */}
          <div className="form-group">
            <label htmlFor="subject">
              Subject
            </label>

            <input
              id="subject"
              type="text"
              value={subject}
              onChange={(event) =>
                setSubject(event.target.value)
              }
              placeholder="Email subject"
              required
              className="form-input"
            />
          </div>

          {/* Message */}
          <div className="form-group">
            <label htmlFor="body">
              Message
            </label>

            <textarea
              id="body"
              value={body}
              onChange={(event) =>
                setBody(event.target.value)
              }
              placeholder="Write your email..."
              rows={10}
              required
              className="form-input message-input"
            />
          </div>

          {/* Schedule */}
          <div className="form-group">
            <label htmlFor="scheduledAt">
              Schedule Date & Time
            </label>

            <input
              id="scheduledAt"
              type="datetime-local"
              value={scheduledAt}
              onChange={(event) =>
                setScheduledAt(event.target.value)
              }
              required
              className="form-input"
            />
          </div>

          {/* Success */}
          {message && (
            <div className="success-message">
              {message}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={
              loading ||
              loadingSenders ||
              senders.length === 0
            }
            className="schedule-button"
          >
            {loading
              ? "Scheduling..."
              : "Schedule Email"}
          </button>

        </form>
      </div>
    </main>
  );
}

export default ComposeEmail;
