from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.recipient import EmailRecipient, RecipientStatus
from app.models.scheduled_email import EmailStatus, ScheduledEmail
from app.models.sender import EmailSender
from app.services.email_sender import send_email
from app.worker.celery_app import celery_app
from app.services.encryption import decrypt_smtp_password


@celery_app.task
def test_task(message: str):
    print(f"Celery received: {message}")

    return {
        "message": message,
        "status": "processed",
    }

def calculate_retry_delay(attempts: int) -> int:
    """
    Calculate exponential backoff delay for a failed email.

    Attempt 1 -> 10 seconds
    Attempt 2 -> 20 seconds
    Attempt 3 -> 40 seconds

    The delay is capped at RETRY_MAX_DELAY_SECONDS.
    """

    delay = settings.RETRY_BASE_DELAY_SECONDS * (2 ** (attempts - 1))

    return min(
        delay,
        settings.RETRY_MAX_DELAY_SECONDS,
    )

@celery_app.task
def send_scheduled_email(email_id: int):
    db = SessionLocal()

    try:
        # ---------------------------------------------------------
        # 1. Find and lock the scheduled email
        # ---------------------------------------------------------
        scheduled_email = db.execute(
            select(ScheduledEmail)
            .where(ScheduledEmail.id == email_id)
            .with_for_update()
        ).scalar_one_or_none()

        if scheduled_email is None:
            return {
                "status": "not_found",
                "email_id": email_id,
            }

        # ---------------------------------------------------------
        # 2. Idempotency protection
        # ---------------------------------------------------------
        if scheduled_email.status in (
            EmailStatus.SENT,
            EmailStatus.CANCELLED,
        ):
            return {
                "status": "already_completed",
                "email_id": email_id,
                "current_status": scheduled_email.status,
            }

        # ---------------------------------------------------------
        # 3. Make sure the email is actually due
        # ---------------------------------------------------------
        now = datetime.now(timezone.utc)

        if scheduled_email.scheduled_at > now:
            return {
                "status": "not_due",
                "email_id": email_id,
                "scheduled_at": scheduled_email.scheduled_at.isoformat(),
            }

        # ---------------------------------------------------------
        # 4. Mark job as processing if it is still scheduled
        # ---------------------------------------------------------
        if scheduled_email.status == EmailStatus.SCHEDULED:
            scheduled_email.status = EmailStatus.PROCESSING
            scheduled_email.processing_started_at = datetime.now(timezone.utc)

            scheduled_email.last_error = None

            db.commit()

        elif scheduled_email.status == EmailStatus.PROCESSING:
            # The scheduler may have already claimed this email.
            # Do not increment attempts again.
            pass

        else:
            return {
                "status": "already_processing_or_completed",
                "email_id": email_id,
                "current_status": scheduled_email.status,
            }

        # ---------------------------------------------------------
        # 5. Load sender
        # ---------------------------------------------------------
        sender = db.execute(
            select(EmailSender)
            .where(
                EmailSender.id == scheduled_email.sender_id
            )
        ).scalar_one_or_none()

        if sender is None:
            scheduled_email.status = EmailStatus.FAILED
            scheduled_email.last_error = "Sender not found"
            db.commit()

            return {
                "status": "failed",
                "email_id": email_id,
                "error": "Sender not found",
            }

        # ---------------------------------------------------------
        # 6. Load pending recipients
        # ---------------------------------------------------------
        recipients = db.execute(
            select(EmailRecipient)
            .where(
                EmailRecipient.scheduled_email_id == email_id,
                EmailRecipient.status == RecipientStatus.PENDING,
            )
            .with_for_update(skip_locked=True)
        ).scalars().all()

        # Check whether another worker is already processing
        # recipients for this email.
        processing_recipient = db.execute(
            select(EmailRecipient)
            .where(
                EmailRecipient.scheduled_email_id == email_id,
                EmailRecipient.status == RecipientStatus.PROCESSING,
            )
        ).scalar_one_or_none()

        if not recipients and processing_recipient is not None:
            return {
                "status": "already_processing",
                "email_id": email_id,
            }

        if not recipients:
            scheduled_email.status = EmailStatus.SENT
            db.commit()

            return {
                "status": "sent",
                "email_id": email_id,
                "successful_recipients": 0,
                "failed_recipients": 0,
            }

        # ---------------------------------------------------------
        # 7. Send to each pending recipient
        # ---------------------------------------------------------
        successful = 0
        failed = 0

        for recipient in recipients:
            try:
                # Atomically claim this recipient.
                recipient.status = RecipientStatus.PROCESSING
                db.commit()

                send_email(
                    smtp_host=sender.smtp_host,
                    smtp_port=sender.smtp_port,
                    smtp_username=sender.smtp_username,
                    smtp_password=decrypt_smtp_password(sender.smtp_password),
                    sender_email=sender.email,
                    sender_name=sender.display_name,
                    recipient_email=recipient.email,
                    subject=scheduled_email.subject,
                    body=scheduled_email.body,
                )

                recipient.status = RecipientStatus.SENT
                recipient.sent_at = datetime.now(timezone.utc)
                recipient.error_message = None

                db.commit()

                successful += 1

            except Exception as exc:
                recipient.status = RecipientStatus.FAILED
                recipient.error_message = str(exc)

                db.commit()

                failed += 1

                # ---------------------------------------------------------
        # 8. Update final email status / schedule retry
        # ---------------------------------------------------------
        if failed == 0:
            scheduled_email.status = EmailStatus.SENT
            scheduled_email.last_error = None

            db.commit()

            return {
                "status": "sent",
                "email_id": email_id,
                "successful_recipients": successful,
                "failed_recipients": 0,
            }

        # ---------------------------------------------------------
        # 9. Retry failed recipients if attempts remain
        # ---------------------------------------------------------
        if scheduled_email.attempts < settings.MAX_EMAIL_ATTEMPTS:

            retry_delay = calculate_retry_delay(
                scheduled_email.attempts
            )

            retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=retry_delay
            )

            # Only failed recipients should be retried.
            failed_recipients = db.execute(
                select(EmailRecipient)
                .where(
                    EmailRecipient.scheduled_email_id == email_id,
                    EmailRecipient.status == RecipientStatus.FAILED,
                )
            ).scalars().all()

            for recipient in failed_recipients:
                recipient.status = RecipientStatus.PENDING
                recipient.error_message = None

            scheduled_email.status = EmailStatus.SCHEDULED
            scheduled_email.scheduled_at = retry_at
            scheduled_email.last_error = (
                f"{failed} recipient(s) failed. "
                f"Retrying in {retry_delay} seconds."
            )

            db.commit()

            print(
                f"RETRY SCHEDULED: email_id={email_id}, "
                f"attempt={scheduled_email.attempts}, "
                f"retry_at={retry_at.isoformat()}, "
                f"delay={retry_delay}s"
            )

            return {
                "status": "retry_scheduled",
                "email_id": email_id,
                "attempts": scheduled_email.attempts,
                "retry_delay_seconds": retry_delay,
                "successful_recipients": successful,
                "failed_recipients": failed,
            }

        # ---------------------------------------------------------
        # 10. Maximum attempts reached
        # ---------------------------------------------------------
        scheduled_email.status = EmailStatus.FAILED
        scheduled_email.last_error = (
            f"{failed} recipient(s) failed after "
            f"{scheduled_email.attempts} attempt(s)"
        )

        db.commit()

        return {
            "status": "failed",
            "email_id": email_id,
            "attempts": scheduled_email.attempts,
            "successful_recipients": successful,
            "failed_recipients": failed,
        }

    except Exception as exc:
        db.rollback()

        try:
            scheduled_email = db.get(
                ScheduledEmail,
                email_id,
            )

            if scheduled_email:
                scheduled_email.status = EmailStatus.FAILED
                scheduled_email.last_error = str(exc)
                db.commit()

        except Exception:
            db.rollback()

        raise

    finally:
        db.close()