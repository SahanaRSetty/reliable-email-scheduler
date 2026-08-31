import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.scheduled_email import EmailStatus, ScheduledEmail
from app.worker.tasks import send_scheduled_email

POLL_INTERVAL_SECONDS = 2
BATCH_SIZE = 100

def recover_stuck_emails() -> int:
    """
    Recover emails that have been stuck in PROCESSING
    longer than the configured processing timeout.
    """

    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        timeout = timedelta(
            seconds=settings.PROCESSING_TIMEOUT_SECONDS
        )

        cutoff = now - timeout

        stuck_emails = (
            db.execute(
                select(ScheduledEmail)
                .where(
                    ScheduledEmail.status == EmailStatus.PROCESSING,
                    ScheduledEmail.processing_started_at.is_not(None),
                    ScheduledEmail.processing_started_at <= cutoff,
                )
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        recovered = 0

        for email in stuck_emails:
            if email.attempts >= settings.MAX_EMAIL_ATTEMPTS:
                email.status = EmailStatus.FAILED
                email.last_error = (
                    f"Processing timeout after "
                    f"{email.attempts} attempt(s)"
                )
            else:
                email.status = EmailStatus.SCHEDULED
                email.scheduled_at = now
                email.processing_started_at = None
                email.last_error = (
                    "Recovered from processing timeout. "
                    "Retrying email."
                )

            recovered += 1

        db.commit()

        return recovered

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

def claim_due_emails() -> list[int]:
    """
    Atomically claim scheduled emails that are due.

    PostgreSQL row locking ensures that if multiple scheduler
    processes are running, the same email cannot be claimed
    by more than one scheduler.
    """

    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        emails = (
            db.execute(
                select(ScheduledEmail)
                .where(
                    ScheduledEmail.status == EmailStatus.SCHEDULED,
                    ScheduledEmail.scheduled_at <= now,
                )
                .order_by(ScheduledEmail.scheduled_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        email_ids = []

        for email in emails:
            email.status = EmailStatus.PROCESSING
            email.processing_started_at = now
            email.attempts += 1
            email_ids.append(email.id)

        db.commit()

        return email_ids

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def find_and_queue_due_emails() -> int:
    recovered = recover_stuck_emails()

    if recovered:
        print(
            f"Recovered {recovered} stuck email(s)."
        )

    email_ids = claim_due_emails()

    for email_id in email_ids:
        send_scheduled_email.delay(email_id)

    return len(email_ids)


def run_scheduler() -> None:
    print("Email scheduler started.")

    while True:
        try:
            queued = find_and_queue_due_emails()

            if queued:
                print(
                    f"Claimed and queued {queued} email(s) for processing."
                )

        except Exception as exc:
            print(f"Scheduler error: {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)