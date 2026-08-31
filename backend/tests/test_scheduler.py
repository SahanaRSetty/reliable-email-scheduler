from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.scheduled_email import EmailStatus, ScheduledEmail
from app.scheduler import service
from sqlalchemy import select
from tests.conftest import TestingSessionLocal

def test_recover_stuck_email_schedules_retry(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    stuck_at = (
        datetime.now(timezone.utc)
        - timedelta(
            seconds=service.settings.PROCESSING_TIMEOUT_SECONDS + 10
        )
    )

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Stuck Email Recovery",
        body="This email got stuck processing.",
        scheduled_at=stuck_at,
        status=EmailStatus.PROCESSING,
        attempts=1,
        processing_started_at=stuck_at,
        idempotency_key=f"pytest-recovery-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    monkeypatch.setattr(
        service,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    recovered = service.recover_stuck_emails()

    assert recovered == 1

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.SCHEDULED
    assert saved_email.processing_started_at is None

    assert saved_email.scheduled_at >= (
        datetime.now(timezone.utc) - timedelta(seconds=5)
    )

    assert saved_email.last_error == (
        "Recovered from processing timeout. "
        "Retrying email."
    )


def test_recover_stuck_email_fails_after_max_attempts(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    stuck_at = (
        datetime.now(timezone.utc)
        - timedelta(
            seconds=service.settings.PROCESSING_TIMEOUT_SECONDS + 10
        )
    )

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Permanent Failure Recovery",
        body="This email exceeded the processing limit.",
        scheduled_at=stuck_at,
        status=EmailStatus.PROCESSING,
        attempts=service.settings.MAX_EMAIL_ATTEMPTS,
        processing_started_at=stuck_at,
        idempotency_key=f"pytest-recovery-failed-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    monkeypatch.setattr(
        service,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    recovered = service.recover_stuck_emails()

    assert recovered == 1

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.FAILED

    assert saved_email.last_error == (
        f"Processing timeout after "
        f"{service.settings.MAX_EMAIL_ATTEMPTS} attempt(s)"
    )

def test_claim_due_email_marks_processing_and_increments_attempt(
    db,
    test_user_and_sender,
    monkeypatch,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Due Email Claim Test",
        body="This email should be claimed.",
        scheduled_at=(
            datetime.now(timezone.utc)
            - timedelta(seconds=10)
        ),
        status=EmailStatus.SCHEDULED,
        attempts=0,
        idempotency_key=f"pytest-claim-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    monkeypatch.setattr(
        service,
        "SessionLocal",
        lambda: TestingSessionLocal(),
    )

    claimed_ids = service.claim_due_emails()

    assert email.id in claimed_ids

    db.expire_all()

    saved_email = db.get(
        ScheduledEmail,
        email.id,
    )

    assert saved_email is not None
    assert saved_email.status == EmailStatus.PROCESSING
    assert saved_email.attempts == 1
    assert saved_email.processing_started_at is not None

def test_claim_due_email_is_not_claimed_twice(
    db,
    test_user_and_sender,
):
    user, sender = test_user_and_sender

    email = ScheduledEmail(
        sender_id=sender.id,
        subject="Concurrent Claim Test",
        body="This email must only be claimed once.",
        scheduled_at=(
            datetime.now(timezone.utc)
            - timedelta(seconds=10)
        ),
        status=EmailStatus.SCHEDULED,
        attempts=0,
        idempotency_key=f"pytest-concurrent-{uuid4().hex}",
    )

    db.add(email)
    db.commit()

    # Two completely independent PostgreSQL sessions.
    session_a = TestingSessionLocal()
    session_b = TestingSessionLocal()

    try:
        # Session A acquires the row lock.
        locked_email = (
            session_a.execute(
                select(ScheduledEmail)
                .where(
                    ScheduledEmail.id == email.id,
                    ScheduledEmail.status == EmailStatus.SCHEDULED,
                )
                .with_for_update(skip_locked=True)
            )
            .scalar_one_or_none()
        )

        assert locked_email is not None

        locked_email.status = EmailStatus.PROCESSING
        locked_email.processing_started_at = (
            datetime.now(timezone.utc)
        )
        locked_email.attempts += 1

        session_a.flush()

        # Session B tries to claim the same row.
        skipped_email = (
            session_b.execute(
                select(ScheduledEmail)
                .where(
                    ScheduledEmail.id == email.id,
                    ScheduledEmail.status == EmailStatus.SCHEDULED,
                )
                .with_for_update(skip_locked=True)
            )
            .scalar_one_or_none()
        )

        # PostgreSQL SKIP LOCKED means B does not wait for A.
        assert skipped_email is None

        session_a.commit()

        # Verify the final state using a fresh session.
        db.expire_all()

        saved_email = db.get(
            ScheduledEmail,
            email.id,
        )

        assert saved_email is not None
        assert saved_email.status == EmailStatus.PROCESSING
        assert saved_email.attempts == 1
        assert saved_email.processing_started_at is not None

    finally:
        session_a.rollback()
        session_b.rollback()
        session_a.close()
        session_b.close()