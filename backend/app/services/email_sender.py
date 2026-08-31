import smtplib
from email.message import EmailMessage


def send_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    sender_email: str,
    sender_name: str | None,
    recipient_email: str,
    subject: str,
    body: str,
) -> None:
    message = EmailMessage()

    if sender_name:
        message["From"] = f"{sender_name} <{sender_email}>"
    else:
        message["From"] = sender_email

    message["To"] = recipient_email
    message["Subject"] = subject

    message.set_content(body)

    with smtplib.SMTP(
        smtp_host,
        smtp_port,
        timeout=30,
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(
            smtp_username,
            smtp_password,
        )
        smtp.send_message(message)