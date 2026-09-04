from tests.conftest import TestingSessionLocal
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.recipient import EmailRecipient, RecipientStatus
from app.models.scheduled_email import EmailStatus, ScheduledEmail
from app.worker import tasks
from app.worker.tasks import calculate_retry_delay


def test_calculate_retry_delay_uses_exponential_backoff():
    assert calculate_retry_delay(1) == 10
    assert calculate_retry_delay(2) == 20
    assert calculate_retry_delay(3) == 40

def test_send_scheduled_email_success(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Worker Success Test",
        body="This should be sent successfully.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=1,
	processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-worker-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="worker-recipient@example.com",
        status=RecipientStatus.PENDING,
    )

    db.add(recipient)
    db.commit()

    def fake_send_email(**kwargs):
        return None

    monkeypatch.setattr(
        tasks,
        "send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
    tasks,
    "SessionLocal",
    lambda: TestingSessionLocal(),
    )

    result = tasks.send_scheduled_email(email.id)

    assert result["status"] == "sent"
    assert result["email_id"] == email.id
    assert result["successful_recipients"] == 1
    assert result["failed_recipients"] == 0

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    saved_recipient = db.get(
        EmailRecipient,
        recipient.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SENT

    assert saved_recipient is not None
    assert saved_recipient.status == RecipientStatus.SENT
    assert saved_recipient.sent_at is not None
    assert saved_recipient.error_message is None

def test_send_scheduled_email_does_not_send_already_sent_email_again(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Idempotency Test",
        body="This email must only be sent once.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.SENT,
        attempts=1,
        idempotency_key=f"pytest-worker-idempotency-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="idempotency@example.com",
        status=RecipientStatus.SENT,
        sent_at=datetime.now(timezone.utc),
    )

    db.add(recipient)
    db.commit()

    send_calls = []

    def fake_send_email(**kwargs):
        send_calls.append(kwargs)

    monkeypatch.setattr(
        tasks,
        "send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    result = tasks.send_scheduled_email(email.id)

    assert result["status"] == "already_completed"
    assert result["email_id"] == email.id
    assert send_calls == []


def test_send_scheduled_email_does_not_duplicate_processing_recipient(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Processing Idempotency Test",
        body="This must not be sent twice.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=1,
        processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-worker-processing-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="processing@example.com",
        status=RecipientStatus.PROCESSING,
    )

    db.add(recipient)
    db.commit()

    send_calls = []

    def fake_send_email(**kwargs):
        send_calls.append(kwargs)

    monkeypatch.setattr(
        tasks,
        "send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    result = tasks.send_scheduled_email(email.id)

    assert result["status"] == "already_processing"
    assert result["email_id"] == email.id
    assert send_calls == []


def test_send_scheduled_email_tracks_each_recipient_independently(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Mixed Recipient Test",
        body="One recipient succeeds and one fails.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=1,
        processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-worker-mixed-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    successful_recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="success@example.com",
        status=RecipientStatus.PENDING,
    )

    failed_recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="failure@example.com",
        status=RecipientStatus.PENDING,
    )

    db.add_all([
        successful_recipient,
        failed_recipient,
    ])
    db.commit()

    def fake_send_email(**kwargs):
        if kwargs["recipient_email"] == "failure@example.com":
            raise RuntimeError("SMTP delivery failed")

    monkeypatch.setattr(
        tasks,
        "send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    result = tasks.send_scheduled_email(email.id)

    assert result["successful_recipients"] == 1
    assert result["failed_recipients"] == 1

    db.expire_all()

    saved_successful = db.get(
        EmailRecipient,
        successful_recipient.id,
    )

    saved_failed = db.get(
        EmailRecipient,
        failed_recipient.id,
    )

    assert saved_successful is not None
    assert saved_successful.status == RecipientStatus.SENT
    assert saved_successful.sent_at is not None
    assert saved_successful.error_message is None

    assert saved_failed is not None
    assert saved_failed.status == RecipientStatus.PENDING
    assert saved_failed.error_message is None

def test_send_scheduled_email_failure_schedules_retry(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Worker Retry Test",
        body="This should fail and be retried.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=1,
        processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-worker-retry-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="worker-failure@example.com",
        status=RecipientStatus.PENDING,
    )

    db.add(recipient)
    db.commit()

    def fake_send_email(**kwargs):
        raise RuntimeError("SMTP connection failed")

    monkeypatch.setattr(
        tasks,
        "send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    before = datetime.now(timezone.utc)

    result = tasks.send_scheduled_email(email.id)

    after = datetime.now(timezone.utc)

    assert result["status"] == "retry_scheduled"
    assert result["email_id"] == email.id
    assert result["attempts"] == 1
    assert result["successful_recipients"] == 0
    assert result["failed_recipients"] == 1
    assert result["retry_delay_seconds"] == 10

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    saved_recipient = db.get(
        EmailRecipient,
        recipient.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SCHEDULED

    assert saved_email.scheduled_at >= (
        before + timedelta(seconds=10)
    )

    assert saved_email.scheduled_at <= (
        after + timedelta(seconds=10)
    )

    assert saved_email.last_error == (
        "1 recipient(s) failed. Retrying in 10 seconds."
    )

    assert saved_recipient is not None
    assert saved_recipient.status == RecipientStatus.PENDING
    assert saved_recipient.error_message is None

def test_send_scheduled_email_fails_after_max_attempts(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Maximum Attempts Test",
        body="This should permanently fail.",
        scheduled_at=datetime.now(timezone.utc),
        status=EmailStatus.PROCESSING,
        attempts=3,
        processing_started_at=datetime.now(timezone.utc),
        idempotency_key=f"pytest-worker-max-{uuid4().hex}",
    )

    db.add(email)
    db.flush()

    recipient = EmailRecipient(
        scheduled_email_id=email.id,
        email="worker-max-failure@example.com",
        status=RecipientStatus.PENDING,
    )

    db.add(recipient)
    db.commit()

    def fake_send_email(**kwargs):
        raise RuntimeError("SMTP connection failed permanently")

    monkeypatch.setattr(
        tasks,
        "send_email",
        fake_send_email,
    )

    monkeypatch.setattr(
        tasks,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    result = tasks.send_scheduled_email(email.id)

    assert result["status"] == "failed"
    assert result["email_id"] == email.id
    assert result["attempts"] == 3
    assert result["successful_recipients"] == 0
    assert result["failed_recipients"] == 1

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    saved_recipient = db.get(
        EmailRecipient,
        recipient.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.FAILED

    assert saved_email.last_error == (
        "1 recipient(s) failed after 3 attempt(s)"
    )

    assert saved_recipient is not None
    assert saved_recipient.status == RecipientStatus.FAILED

    assert (
        saved_recipient.error_message
        == "SMTP connection failed permanently"
    )
