from fastapi.testclient import TestClient
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.main import app
from app.models.recipient import EmailRecipient, RecipientStatus
from app.models.scheduled_email import EmailStatus, ScheduledEmail
from app.core.redis import redis_client
from app.services.encryption import encrypt_smtp_password

client = TestClient(app)


def test_schedule_email_requires_authentication():
    response = client.post(
        "/api/emails/schedule",
        json={
            "sender_id": 2,
            "subject": "Test Email",
            "body": "This should not be scheduled.",
            "scheduled_at": "2030-01-01T12:00:00Z",
            "recipients": [
                {
                    "email": "test@example.com",
                }
            ],
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_user_cannot_schedule_using_another_users_sender():
    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: 4

    try:
        response = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": 2,
                "subject": "Unauthorized Sender Test",
                "body": "This email should not be scheduled.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "test@example.com",
                    }
                ],
            },
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 404
    assert response.json()["detail"] == "Email sender not found"


def test_authenticated_user_can_delete_sender(client, db, test_user_and_sender):
    user, sender = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(f"/api/emails/senders/{sender.id}")
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200
    assert response.json()["message"] == "Sender deleted successfully"

    from app.models.sender import EmailSender

    deleted_sender = db.execute(
        select(EmailSender).where(EmailSender.id == sender.id)
    ).scalar_one_or_none()

    assert deleted_sender is None


def test_delete_sender_requires_authentication(client, test_user_and_sender):
    _, sender = test_user_and_sender

    response = client.delete(f"/api/emails/senders/{sender.id}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_user_cannot_delete_another_users_sender(
    client,
    db,
    test_user_and_sender,
):
    user, _ = test_user_and_sender

    from uuid import uuid4
    from app.models.sender import EmailSender
    from app.models.user import User
    from app.api.routes import emails

    other_user = User(
        google_id=f"pytest-sender-delete-user-{uuid4().hex}",
        name="Other Sender User",
        email=f"pytest-sender-delete-{uuid4().hex}@example.com",
    )

    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    other_sender = EmailSender(
        user_id=other_user.id,
        email="other-user@example.com",
        display_name="Other User",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="other-user@example.com",
        smtp_password="test-password-123",
    )

    db.add(other_sender)
    db.commit()
    db.refresh(other_sender)

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(
            f"/api/emails/senders/{other_sender.id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 404

    remaining_sender = db.execute(
        select(EmailSender).where(
            EmailSender.id == other_sender.id
        )
    ).scalar_one_or_none()

    assert remaining_sender is not None
    assert remaining_sender.user_id == other_user.id

def test_delete_sender_fails_when_sender_is_used_by_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.models.scheduled_email import ScheduledEmail
    from app.api.routes import emails
    from datetime import datetime, timezone

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Sender in use",
        body="This sender is being used.",
        scheduled_at=datetime.now(timezone.utc),
        idempotency_key="sender-delete-in-use-test",
    )

    db.add(email)
    db.commit()

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(
            f"/api/emails/senders/{sender.id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Cannot delete sender that is used by an email"
    )

def test_user_only_sees_their_own_senders():
    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: 4

    try:
        response = client.get("/api/emails/senders")
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    senders = response.json()

    sender_ids = {sender["id"] for sender in senders}

    assert {5, 6}.issubset(sender_ids)
    assert 2 not in sender_ids
    assert 4 not in sender_ids

    assert all(
        "smtp_host" not in sender
        and "smtp_port" not in sender
        and "smtp_username" not in sender
        and "smtp_password" not in sender
        for sender in senders
    )

def test_authenticated_user_can_add_sender(
    client,
    db,
    test_user_and_sender,
):
    user, _ = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            "/api/emails/senders",
            json={
                "email": "new-sender@example.com",
                "display_name": "New Sender",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_username": "new-sender@example.com",
                "smtp_password": "test-password-123",
            },
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    data = response.json()

    assert data["email"] == "new-sender@example.com"
    assert data["display_name"] == "New Sender"

    assert "smtp_host" not in data
    assert "smtp_port" not in data
    assert "smtp_username" not in data
    assert "smtp_password" not in data


def test_sender_smtp_password_is_encrypted_in_database(
    client,
    db,
    test_user_and_sender,
):
    user, _ = test_user_and_sender

    from app.api.routes import emails
    from app.models.sender import EmailSender

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    plaintext_password = "test-password-123"

    try:
        response = client.post(
            "/api/emails/senders",
            json={
                "email": "encrypted-sender@example.com",
                "display_name": "Encrypted Sender",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_username": "encrypted-sender@example.com",
                "smtp_password": plaintext_password,
            },
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    sender_id = response.json()["id"]

    sender = db.execute(
        select(EmailSender).where(
            EmailSender.id == sender_id
        )
    ).scalar_one()

    assert sender.smtp_password != plaintext_password

    from app.services.encryption import decrypt_smtp_password

    assert decrypt_smtp_password(sender.smtp_password) == plaintext_password


def test_add_sender_requires_authentication(client):
    response = client.post(
        "/api/emails/senders",
        json={
            "email": "unauthorized@example.com",
            "display_name": "Unauthorized",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "unauthorized@example.com",
            "smtp_password": "test-password-123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_added_sender_belongs_to_authenticated_user(
    client,
    db,
    test_user_and_sender,
):
    user, _ = test_user_and_sender

    from app.api.routes import emails
    from app.models.sender import EmailSender

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            "/api/emails/senders",
            json={
                "email": "ownership@example.com",
                "display_name": "Ownership Test",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_username": "ownership@example.com",
                "smtp_password": "test-password-123",
            },
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    sender_id = response.json()["id"]

    sender = db.execute(
        select(EmailSender).where(
            EmailSender.id == sender_id,
        )
    ).scalar_one()

    assert sender.user_id == user.id
    assert sender.email == "ownership@example.com"


def test_add_sender_rejects_invalid_smtp_port(
    client,
    test_user_and_sender,
):
    user, _ = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            "/api/emails/senders",
            json={
                "email": "invalid-port@example.com",
                "display_name": "Invalid Port",
                "smtp_host": "smtp.example.com",
                "smtp_port": 70000,
                "smtp_username": "invalid-port@example.com",
                "smtp_password": "test-password-123",
            },
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 422

def test_authenticated_user_can_schedule_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender.id,
                "subject": "Automated Test Email",
                "body": "This email was created by an automated test.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "recipient1@example.com",
                    },
                    {
                        "email": "recipient2@example.com",
                    },
                ],
            },
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Email scheduled successfully"
    assert data["status"] == "scheduled"
    assert data["recipient_count"] == 2

    scheduled_email = db.execute(
        select(ScheduledEmail).where(
            ScheduledEmail.id == data["email_id"]
        )
    ).scalar_one()

    assert scheduled_email.sender_id == sender.id
    assert scheduled_email.subject == "Automated Test Email"
    assert scheduled_email.body == (
        "This email was created by an automated test."
    )
    assert scheduled_email.status == "scheduled"

    recipients = db.execute(
        select(EmailRecipient).where(
            EmailRecipient.scheduled_email_id == scheduled_email.id
        )
    ).scalars().all()

    assert len(recipients) == 2

    recipient_addresses = {
        recipient.email for recipient in recipients
    }

    assert recipient_addresses == {
        "recipient1@example.com",
        "recipient2@example.com",
    }

def test_authenticated_user_can_cancel_scheduled_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user.id

    try:
        create_response = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender.id,
                "subject": "Cancellation Test",
                "body": "This email should be cancelled.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "recipient@example.com",
                    }
                ],
            },
        )

        assert create_response.status_code == 200

        email_id = create_response.json()["email_id"]

        cancel_response = client.post(
            f"/api/emails/{email_id}/cancel"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert cancel_response.status_code == 200

    data = cancel_response.json()

    assert data["message"] == "Email cancelled successfully"
    assert data["email_id"] == email_id
    assert data["status"] == "cancelled"

    db.expire_all()

    from app.models.scheduled_email import ScheduledEmail

    scheduled_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert scheduled_email is not None
    assert scheduled_email.status == "cancelled"

def test_user_cannot_cancel_another_users_email(
    client,
    db,
    test_user_and_sender,
):
    owner, sender = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    # Create an email belonging to the owner.
    emails.get_authenticated_user_id = lambda request: owner.id

    try:
        create_response = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender.id,
                "subject": "Ownership Test",
                "body": "This email belongs to another user.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "recipient@example.com",
                    }
                ],
            },
        )

        assert create_response.status_code == 200

        email_id = create_response.json()["email_id"]

        # Now pretend a different user is logged in.
        another_user_id = owner.id + 1000

        emails.get_authenticated_user_id = (
            lambda request: another_user_id
        )

        cancel_response = client.post(
            f"/api/emails/{email_id}/cancel"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert cancel_response.status_code == 404
    assert (
        cancel_response.json()["detail"]
        == "Scheduled email not found"
    )

    db.expire_all()

    from app.models.scheduled_email import ScheduledEmail

    scheduled_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert scheduled_email is not None
    assert scheduled_email.status == "scheduled"

def test_sent_email_cannot_be_cancelled(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Already Sent Email",
        body="This email has already been sent.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-sent-{user.id}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="recipient@example.com",
        status="sent",
    )

    db.add(recipient)
    db.commit()

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email.id}/cancel"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be cancelled because "
        "its current status is 'sent'."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SENT

def test_user_only_sees_their_own_scheduled_emails(
    client,
    db,
    test_user_and_sender,
):
    user_a, sender_a = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id

    # Create an email belonging to User A.
    emails.get_authenticated_user_id = lambda request: user_a.id

    try:
        response_a = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender_a.id,
                "subject": "User A Private Email",
                "body": "This belongs to User A.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "user-a@example.com",
                    }
                ],
            },
        )

        assert response_a.status_code == 200

        email_a_id = response_a.json()["email_id"]

        # Create User B and User B's sender directly in the test DB.
        from app.models.sender import EmailSender
        from app.models.user import User

        user_b = User(
            google_id=f"pytest-user-b-{user_a.id}",
            name="Pytest User B",
            email=f"pytest-user-b-{user_a.id}@example.com",
        )

        db.add(user_b)
        db.flush()

        sender_b = EmailSender(
            user_id=user_b.id,
            email=f"sender-b-{user_b.id}@example.com",
            display_name="User B Sender",
            smtp_host="smtp.test.local",
            smtp_port=587,
            smtp_username="user-b@example.com",
            smtp_password="test-password",
        )

        db.add(sender_b)
        db.commit()

        db.refresh(user_b)
        db.refresh(sender_b)

        # Create an email belonging to User B.
        emails.get_authenticated_user_id = lambda request: user_b.id

        response_b = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender_b.id,
                "subject": "User B Private Email",
                "body": "This belongs to User B.",
                "scheduled_at": "2030-01-01T13:00:00Z",
                "recipients": [
                    {
                        "email": "user-b@example.com",
                    }
                ],
            },
        )

        assert response_b.status_code == 200

        email_b_id = response_b.json()["email_id"]

        # Now authenticate as User A again.
        emails.get_authenticated_user_id = lambda request: user_a.id

        scheduled_response = client.get(
            "/api/emails/scheduled"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert scheduled_response.status_code == 200

    scheduled_emails = scheduled_response.json()

    email_ids = {
        email["id"]
        for email in scheduled_emails
    }

    assert email_a_id in email_ids
    assert email_b_id not in email_ids

    assert all(
        email["sender_id"] == sender_a.id
        for email in scheduled_emails
    )

def test_user_only_sees_their_own_sent_emails(
    client,
    db,
    test_user_and_sender,
):
    user_a, sender_a = test_user_and_sender

    from datetime import datetime, timezone
    from uuid import uuid4

    from app.api.routes import emails
    from app.models.scheduled_email import EmailStatus, ScheduledEmail
    from app.models.sender import EmailSender
    from app.models.user import User

    # Create User A's sent email.
    email_a = ScheduledEmail(
        sender_id=sender_a.id,
        subject="User A Sent Email",
        body="This belongs to User A.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-sent-a-{uuid4().hex}",
    )

    db.add(email_a)
    db.flush()

    # Create User B and User B's sender.
    user_b = User(
        google_id=f"pytest-user-b-{uuid4().hex}",
        name="Pytest User B",
        email=f"pytest-user-b-{uuid4().hex}@example.com",
    )

    db.add(user_b)
    db.flush()

    sender_b = EmailSender(
        user_id=user_b.id,
        email=f"sender-b-{uuid4().hex}@example.com",
        display_name="User B Sender",
        smtp_host="smtp.test.local",
        smtp_port=587,
        smtp_username="user-b@example.com",
        smtp_password="test-password",
    )

    db.add(sender_b)
    db.flush()

    # Create User B's sent email.
    email_b = ScheduledEmail(
        sender_id=sender_b.id,
        subject="User B Sent Email",
        body="This belongs to User B.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-sent-b-{uuid4().hex}",
    )

    db.add(email_b)
    db.commit()

    original_function = emails.get_authenticated_user_id

    # Authenticate as User A.
    emails.get_authenticated_user_id = lambda request: user_a.id

    try:
        response = client.get("/api/emails/sent")
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    sent_emails = response.json()

    email_ids = {
        email["id"]
        for email in sent_emails
    }

    assert email_a.id in email_ids
    assert email_b.id not in email_ids

    assert all(
        email["sender_id"] == sender_a.id
        for email in sent_emails
    )

    assert all(
        email["status"] == "sent"
        for email in sent_emails
    )

def test_email_stats_are_correct_and_user_specific(
    client,
    db,
    test_user_and_sender,
):
    user_a, sender_a = test_user_and_sender

    from datetime import datetime, timezone
    from uuid import uuid4

    from app.api.routes import emails
    from app.models.scheduled_email import EmailStatus, ScheduledEmail
    from app.models.sender import EmailSender
    from app.models.user import User

    scheduled_email = ScheduledEmail(
        sender_id=sender_a.id,
        subject="Scheduled",
        body="Scheduled test email.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SCHEDULED,
        idempotency_key=f"pytest-stats-scheduled-{uuid4().hex}",
    )

    sent_email = ScheduledEmail(
        sender_id=sender_a.id,
        subject="Sent",
        body="Sent test email.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-stats-sent-{uuid4().hex}",
    )

    failed_email = ScheduledEmail(
        sender_id=sender_a.id,
        subject="Failed",
        body="Failed test email.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=3,
        idempotency_key=f"pytest-stats-failed-{uuid4().hex}",
    )

    db.add_all([
        scheduled_email,
        sent_email,
        failed_email,
    ])

    # Create another user and sender.
    user_b = User(
        google_id=f"pytest-stats-user-b-{uuid4().hex}",
        name="Stats User B",
        email=f"pytest-stats-b-{uuid4().hex}@example.com",
    )

    db.add(user_b)
    db.flush()

    sender_b = EmailSender(
        user_id=user_b.id,
        email=f"stats-sender-b-{uuid4().hex}@example.com",
        display_name="Stats User B Sender",
        smtp_host="smtp.test.local",
        smtp_port=587,
        smtp_username="user-b@example.com",
        smtp_password="test-password",
    )

    db.add(sender_b)
    db.flush()

    # User B has one email of each status.
    db.add_all([
        ScheduledEmail(
            sender_id=sender_b.id,
            subject="User B Scheduled",
            body="Should not be counted.",
            scheduled_at=datetime.now(timezone.utc),
            status=EmailStatus.SCHEDULED,
            idempotency_key=f"pytest-stats-b-scheduled-{uuid4().hex}",
        ),
        ScheduledEmail(
            sender_id=sender_b.id,
            subject="User B Sent",
            body="Should not be counted.",
            scheduled_at=datetime.now(timezone.utc),
            status=EmailStatus.SENT,
            attempts=1,
            idempotency_key=f"pytest-stats-b-sent-{uuid4().hex}",
        ),
        ScheduledEmail(
            sender_id=sender_b.id,
            subject="User B Failed",
            body="Should not be counted.",
            scheduled_at=datetime.now(timezone.utc),
            status=EmailStatus.FAILED,
            attempts=3,
            idempotency_key=f"pytest-stats-b-failed-{uuid4().hex}",
        ),
    ])

    db.commit()

    original_function = emails.get_authenticated_user_id

    emails.get_authenticated_user_id = lambda request: user_a.id

    try:
        response = client.get("/api/emails/stats")
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    stats = response.json()

    assert stats["scheduled"] == 1
    assert stats["sent"] == 1
    assert stats["failed"] == 1

def test_authenticated_user_can_delete_scheduled_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        create_response = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender.id,
                "subject": "Delete Test",
                "body": "This email should be deleted.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "delete-recipient@example.com",
                    }
                ],
            },
        )

        assert create_response.status_code == 200

        email_id = create_response.json()["email_id"]

        delete_response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert delete_response.status_code == 200

    data = delete_response.json()

    assert data["message"] == "Email deleted successfully"
    assert data["email_id"] == email_id

    db.expire_all()

    from app.models.scheduled_email import ScheduledEmail

    deleted_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert deleted_email is None

def test_deleting_email_also_deletes_recipients(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.recipient import EmailRecipient
    from app.models.scheduled_email import ScheduledEmail

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        create_response = client.post(
            "/api/emails/schedule",
            json={
                "sender_id": sender.id,
                "subject": "Recipient Cascade Test",
                "body": "Testing recipient cleanup.",
                "scheduled_at": "2030-01-01T12:00:00Z",
                "recipients": [
                    {
                        "email": "recipient-one@example.com",
                    },
                    {
                        "email": "recipient-two@example.com",
                    },
                ],
            },
        )

        assert create_response.status_code == 200

        email_id = create_response.json()["email_id"]

        recipients_before = db.execute(
            select(EmailRecipient)
            .where(
                EmailRecipient.scheduled_email_id == email_id,
            )
        ).scalars().all()

        assert len(recipients_before) == 2

        delete_response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert delete_response.status_code == 200

    db.expire_all()

    deleted_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert deleted_email is None

    remaining_recipients = db.execute(
        select(EmailRecipient)
        .where(
            EmailRecipient.scheduled_email_id == email_id,
        )
    ).scalars().all()

    assert remaining_recipients == []


def test_user_cannot_delete_another_users_email(
    client,
    db,
    test_user_and_sender,
):
    user_a, sender_a = test_user_and_sender

    from app.api.routes import emails
    from app.models.user import User
    from app.models.scheduled_email import ScheduledEmail

    user_b = User(
        google_id=f"pytest-user-b-{uuid4().hex}",
        name="Second User",
        email=f"pytest-user-b-{uuid4().hex}@example.com",
    )

    db.add(user_b)
    db.flush()

    email = ScheduledEmail(
        sender_id=sender_a.id,
        subject="Ownership Delete Test",
        body="User B must not delete this.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SCHEDULED,
        attempts=0,
        idempotency_key=f"pytest-delete-owner-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user_b.id

    try:
        response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 404

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SCHEDULED


def test_authenticated_user_can_delete_cancelled_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Cancelled Delete Test",
        body="This cancelled email should be deleted.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.CANCELLED,
        attempts=0,
        idempotency_key=f"pytest-delete-cancelled-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Email deleted successfully"
    assert data["email_id"] == email_id

    db.expire_all()

    deleted_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert deleted_email is None


def test_authenticated_user_can_delete_failed_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Failed Delete Test",
        body="This failed email should be deleted.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=3,
        last_error="SMTP connection failed",
        idempotency_key=f"pytest-delete-failed-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Email deleted successfully"
    assert data["email_id"] == email_id

    db.expire_all()

    deleted_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert deleted_email is None

def test_processing_email_cannot_be_deleted(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Processing Delete Test",
        body="This email is currently being processed.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=1,
        processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-delete-processing-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be deleted because "
        "it is currently being processed."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.PROCESSING

def test_sent_email_cannot_be_deleted(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Sent Delete Test",
        body="This email has already been sent.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-delete-sent-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.delete(
            f"/api/emails/{email_id}"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be deleted because "
        "it has already been sent."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SENT

def test_authenticated_user_can_retry_failed_email(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.recipient import EmailRecipient
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Manual Retry Test",
        body="This failed email should be retried.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=2,
        last_error="SMTP connection failed",
        idempotency_key=f"pytest-manual-retry-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="retry-recipient@example.com",
        status=RecipientStatus.FAILED,
        error_message="SMTP connection failed",
    )

    db.add(recipient)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Email retry scheduled successfully"
    assert data["email_id"] == email_id
    assert data["status"] == "scheduled"
    assert data["attempts"] == 2

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SCHEDULED
    assert saved_email.processing_started_at is None
    assert saved_email.last_error is None

    saved_recipient = db.get(
        EmailRecipient,
        recipient.id,
    )

    assert saved_recipient is not None
    assert saved_recipient.status == RecipientStatus.PENDING
    assert saved_recipient.error_message is None

def test_retry_failed_email_requires_authentication(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Unauthenticated Retry Test",
        body="This email should not be retried without authentication.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=2,
        last_error="SMTP connection failed",
        idempotency_key=f"pytest-retry-auth-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    response = client.post(
        f"/api/emails/{email.id}/retry"
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.FAILED

def test_user_cannot_retry_another_users_failed_email(
    client,
    db,
    test_user_and_sender,
):
    user_a, sender_a = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail
    from app.models.user import User

    user_b = User(
        google_id=f"pytest-retry-user-b-{uuid4().hex}",
        name="Second Retry User",
        email=f"pytest-retry-user-b-{uuid4().hex}@example.com",
    )

    db.add(user_b)
    db.commit()
    db.refresh(user_b)

    email = ScheduledEmail(
        sender_id=sender_a.id,
        subject="Ownership Retry Test",
        body="User B must not retry this email.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=2,
        last_error="SMTP connection failed",
        idempotency_key=f"pytest-retry-owner-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user_b.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 404
    assert response.json()["detail"] == "Scheduled email not found"

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.FAILED
    assert saved_email.attempts == 2

def test_scheduled_email_cannot_be_manually_retried(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Scheduled Retry Test",
        body="This email is already scheduled.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SCHEDULED,
        attempts=0,
        idempotency_key=f"pytest-retry-scheduled-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be retried because "
        "its current status is 'scheduled'."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SCHEDULED
    assert saved_email.attempts == 0

def test_processing_email_cannot_be_manually_retried(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Processing Retry Test",
        body="This email is currently being processed.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=1,
        processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-retry-processing-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be retried because "
        "its current status is 'processing'."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.PROCESSING
    assert saved_email.attempts == 1

def test_sent_email_cannot_be_manually_retried(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Sent Retry Test",
        body="This email has already been sent.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-retry-sent-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be retried because "
        "its current status is 'sent'."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SENT
    assert saved_email.attempts == 1

def test_cancelled_email_cannot_be_manually_retried(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Cancelled Retry Test",
        body="This email was cancelled.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.CANCELLED,
        attempts=0,
        idempotency_key=f"pytest-retry-cancelled-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be retried because "
        "its current status is 'cancelled'."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.CANCELLED
    assert saved_email.attempts == 0

def test_failed_email_at_max_attempts_cannot_be_manually_retried(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.core.config import settings
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Max Attempts Retry Test",
        body="This email has exhausted its retry attempts.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=settings.MAX_EMAIL_ATTEMPTS,
        last_error="SMTP connection failed after maximum attempts",
        idempotency_key=f"pytest-retry-max-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be retried because "
        "it has reached the maximum number of attempts."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.FAILED
    assert saved_email.attempts == settings.MAX_EMAIL_ATTEMPTS

def test_retry_only_resets_failed_recipients(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.recipient import EmailRecipient, RecipientStatus
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Mixed Recipient Retry Test",
        body="Only failed recipients should be retried.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=1,
        last_error="Some recipients failed",
        idempotency_key=f"pytest-retry-mixed-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    sent_recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="already-sent@example.com",
        status=RecipientStatus.SENT,
    )

    failed_recipient_1 = EmailRecipient(
        scheduled_email_id=email.id,
        email="failed-one@example.com",
        status=RecipientStatus.FAILED,
        error_message="SMTP failure",
    )

    failed_recipient_2 = EmailRecipient(
        scheduled_email_id=email.id,
        email="failed-two@example.com",
        status=RecipientStatus.FAILED,
        error_message="Connection timeout",
    )

    db.add_all([
        sent_recipient,
        failed_recipient_1,
        failed_recipient_2,
    ])
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    db.expire_all()

    saved_sent = db.get(
        EmailRecipient,
        sent_recipient.id,
    )

    saved_failed_1 = db.get(
        EmailRecipient,
        failed_recipient_1.id,
    )

    saved_failed_2 = db.get(
        EmailRecipient,
        failed_recipient_2.id,
    )

    assert saved_sent.status == RecipientStatus.SENT

    assert saved_failed_1.status == RecipientStatus.PENDING
    assert saved_failed_1.error_message is None

    assert saved_failed_2.status == RecipientStatus.PENDING
    assert saved_failed_2.error_message is None

def test_failed_email_with_no_failed_recipients_cannot_be_retried(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.recipient import EmailRecipient, RecipientStatus
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="No Failed Recipients Test",
        body="There are no failed recipients.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=1,
        last_error="Previous processing failure",
        idempotency_key=f"pytest-retry-no-failed-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient_1 = EmailRecipient(
        scheduled_email_id=email.id,
        email="sent-one@example.com",
        status=RecipientStatus.SENT,
    )

    recipient_2 = EmailRecipient(
        scheduled_email_id=email.id,
        email="sent-two@example.com",
        status=RecipientStatus.SENT,
    )

    db.add_all([recipient_1, recipient_2])
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Email cannot be retried because "
        "it has no failed recipients."
    )

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.FAILED
    assert saved_email.attempts == 1

def test_retry_schedules_failed_email_immediately(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.recipient import EmailRecipient, RecipientStatus
    from app.models.scheduled_email import ScheduledEmail

    old_scheduled_at = datetime.now(timezone.utc) - timedelta(hours=2)

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Immediate Retry Test",
        body="This email should be scheduled immediately.",
        scheduled_at=old_scheduled_at,
        status=EmailStatus.FAILED,
        attempts=1,
        last_error="SMTP connection failed",
        idempotency_key=f"pytest-retry-immediate-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="retry-now@example.com",
        status=RecipientStatus.FAILED,
        error_message="SMTP connection failed",
    )

    db.add(recipient)
    db.commit()

    email_id = email.id

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        before_retry = datetime.now(timezone.utc)

        response = client.post(
            f"/api/emails/{email_id}/retry"
        )

        after_retry = datetime.now(timezone.utc)
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SCHEDULED
    assert saved_email.scheduled_at >= before_retry - timedelta(seconds=1)
    assert saved_email.scheduled_at <= after_retry + timedelta(seconds=1)
    assert saved_email.scheduled_at > old_scheduled_at

def test_retry_preserves_email_data(
    client,
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.models.recipient import EmailRecipient, RecipientStatus
    from app.models.scheduled_email import ScheduledEmail

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Original Subject",
        body="Original email body must remain unchanged.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.FAILED,
        attempts=1,
        last_error="SMTP failure",
        idempotency_key=f"pytest-retry-preserve-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="preserve@example.com",
        status=RecipientStatus.FAILED,
        error_message="SMTP failure",
    )

    db.add(recipient)
    db.commit()

    email_id = email.id
    original_idempotency_key = email.idempotency_key

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    try:
        response = client.post(
            f"/api/emails/{email_id}/retry"
        )
    finally:
        emails.get_authenticated_user_id = original_function

    assert response.status_code == 200

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email_id,
    )

    assert saved_email is not None

    assert saved_email.sender_id == sender.id
    assert saved_email.subject == "Original Subject"
    assert saved_email.body == (
        "Original email body must remain unchanged."
    )
    assert saved_email.idempotency_key == original_idempotency_key
    assert saved_email.attempts == 1

    assert saved_email.status == EmailStatus.SCHEDULED
    assert saved_email.last_error is None
    assert saved_email.processing_started_at is None

def test_schedule_rate_limit_blocks_excessive_requests(
    client,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    from app.api.routes import emails
    from app.services import rate_limiter

    original_function = emails.get_authenticated_user_id
    emails.get_authenticated_user_id = lambda request: user.id

    original_limit = rate_limiter.RATE_LIMIT_REQUESTS
    rate_limiter.RATE_LIMIT_REQUESTS = 2
    redis_client.delete(
        f"rate_limit:schedule:{user.id}"
    )

    try:
        payload = {
            "sender_id": sender.id,
            "subject": "Rate Limit Test",
            "body": "Testing schedule rate limiting.",
            "scheduled_at": "2030-01-01T12:00:00Z",
            "recipients": [
                {
                    "email": "rate-limit@example.com",
                }
            ],
        }

        first = client.post(
            "/api/emails/schedule",
            json=payload,
        )

        second = client.post(
            "/api/emails/schedule",
            json=payload,
        )

        third = client.post(
            "/api/emails/schedule",
            json=payload,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert (
            third.json()["detail"]
            == "Too many email scheduling requests. Please try again later."
        )
        assert third.headers["Retry-After"] == "60"

    finally:
        emails.get_authenticated_user_id = original_function
        rate_limiter.RATE_LIMIT_REQUESTS = original_limit


def test_schedule_rate_limit_isolated_per_user(
    client,
    db,
):
    from app.api.routes import emails
    from app.services import rate_limiter
    from app.core.redis import redis_client
    from app.models.sender import EmailSender
    from app.models.user import User

    user_1 = User(
        google_id=f"rate-limit-user-1-{uuid4().hex}",
        name="Rate Limit User 1",
        email=f"rate-limit-user-1-{uuid4().hex}@example.com",
    )

    user_2 = User(
        google_id=f"rate-limit-user-2-{uuid4().hex}",
        name="Rate Limit User 2",
        email=f"rate-limit-user-2-{uuid4().hex}@example.com",
    )

    db.add_all([user_1, user_2])
    db.flush()

    sender_1 = EmailSender(
        user_id=user_1.id,
        email=f"sender-1-{uuid4().hex}@example.com",
        display_name="Sender 1",
        smtp_host="smtp.test.local",
        smtp_port=587,
        smtp_username="test@example.com",
        smtp_password=encrypt_smtp_password("test-password"),
    )

    sender_2 = EmailSender(
        user_id=user_2.id,
        email=f"sender-2-{uuid4().hex}@example.com",
        display_name="Sender 2",
        smtp_host="smtp.test.local",
        smtp_port=587,
        smtp_username="test@example.com",
        smtp_password=encrypt_smtp_password("test-password"),
    )

    db.add_all([sender_1, sender_2])
    db.commit()

    original_function = emails.get_authenticated_user_id
    original_limit = rate_limiter.RATE_LIMIT_REQUESTS

    rate_limiter.RATE_LIMIT_REQUESTS = 1

    redis_client.delete(
        f"rate_limit:schedule:{user_1.id}"
    )
    redis_client.delete(
        f"rate_limit:schedule:{user_2.id}"
    )

    payload_1 = {
        "sender_id": sender_1.id,
        "subject": "User 1 Rate Limit Test",
        "body": "Testing user-specific rate limiting.",
        "scheduled_at": "2030-01-01T12:00:00Z",
        "recipients": [
            {
                "email": "user1@example.com",
            }
        ],
    }

    payload_2 = {
        "sender_id": sender_2.id,
        "subject": "User 2 Rate Limit Test",
        "body": "Testing user-specific rate limiting.",
        "scheduled_at": "2030-01-01T12:00:00Z",
        "recipients": [
            {
                "email": "user2@example.com",
            }
        ],
    }

    try:
        emails.get_authenticated_user_id = (
            lambda request: user_1.id
        )

        first_user_1 = client.post(
            "/api/emails/schedule",
            json=payload_1,
        )

        second_user_1 = client.post(
            "/api/emails/schedule",
            json=payload_1,
        )

        emails.get_authenticated_user_id = (
            lambda request: user_2.id
        )

        first_user_2 = client.post(
            "/api/emails/schedule",
            json=payload_2,
        )

        assert first_user_1.status_code == 200
        assert second_user_1.status_code == 429
        assert first_user_2.status_code == 200

    finally:
        emails.get_authenticated_user_id = original_function
        rate_limiter.RATE_LIMIT_REQUESTS = original_limit

        redis_client.delete(
            f"rate_limit:schedule:{user_1.id}"
        )
        redis_client.delete(
            f"rate_limit:schedule:{user_2.id}"
        )