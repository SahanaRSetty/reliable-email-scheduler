from fastapi.testclient import TestClient
from sqlalchemy import select
from datetime import datetime, timezone

from app.main import app
from app.models.recipient import EmailRecipient
from app.models.scheduled_email import EmailStatus, ScheduledEmail


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

    assert len(senders) == 2

    sender_ids = {sender["id"] for sender in senders}

    assert sender_ids == {5, 6}

    assert all(
        "smtp_host" not in sender
        and "smtp_port" not in sender
        and "smtp_username" not in sender
        and "smtp_password" not in sender
        for sender in senders
    )

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
