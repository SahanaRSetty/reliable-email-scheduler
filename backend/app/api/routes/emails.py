from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.rate_limiter import check_schedule_rate_limit
from app.services.encryption import encrypt_smtp_password
from app.core.config import settings
from app.core.database import get_db
from app.models.recipient import EmailRecipient, RecipientStatus
from app.models.scheduled_email import ScheduledEmail
from app.models.sender import EmailSender
from app.schemas.email import (
    EmailSenderCreate,
    EmailSenderResponse,
    ScheduledEmailCreate,
)

router = APIRouter(
    prefix="/api/emails",
    tags=["Emails"],
)


def get_authenticated_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    return user_id

@router.get("/senders")
def get_email_senders(
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Get only senders belonging to this user
    # ---------------------------------------------------------
    senders = db.execute(
        select(EmailSender)
        .where(
            EmailSender.user_id == user_id,
        )
        .order_by(
            EmailSender.created_at.asc(),
        )
    ).scalars().all()

    # ---------------------------------------------------------
    # 3. Return safe sender information only
    # ---------------------------------------------------------
    return [
        {
            "id": sender.id,
            "email": sender.email,
            "display_name": sender.display_name,
        }
        for sender in senders
    ]


@router.post(
    "/senders",
    response_model=EmailSenderResponse,
)
def create_email_sender(
    sender_request: EmailSenderCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Create sender for this user
    # ---------------------------------------------------------
    sender = EmailSender(
        user_id=user_id,
        email=str(sender_request.email),
        display_name=sender_request.display_name,
        smtp_host=sender_request.smtp_host,
        smtp_port=sender_request.smtp_port,
        smtp_username=sender_request.smtp_username,
        smtp_password=encrypt_smtp_password(sender_request.smtp_password),
    )

    db.add(sender)
    db.commit()
    db.refresh(sender)

    # ---------------------------------------------------------
    # 3. Return safe sender information only
    # ---------------------------------------------------------
    return EmailSenderResponse(
        id=sender.id,
        email=sender.email,
        display_name=sender.display_name,
    )

@router.delete("/senders/{sender_id}")
def delete_email_sender(
    sender_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = get_authenticated_user_id(request)

    sender = db.execute(
        select(EmailSender).where(
            EmailSender.id == sender_id,
            EmailSender.user_id == user_id,
        )
    ).scalar_one_or_none()

    if sender is None:
        raise HTTPException(status_code=404, detail="Sender not found")

    in_use = db.execute(
        select(ScheduledEmail.id).where(
            ScheduledEmail.sender_id == sender_id
        ).limit(1)
    ).first()

    if in_use is not None:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete sender that is used by an email",
        )

    db.delete(sender)
    db.commit()

    return {"message": "Sender deleted successfully"}

@router.post("/schedule")
def schedule_email(
    email_request: ScheduledEmailCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)
    check_schedule_rate_limit(user_id)

    # ---------------------------------------------------------
    # 2. Verify that the sender belongs to the logged-in user
    # ---------------------------------------------------------
    sender = db.execute(
        select(EmailSender).where(
            EmailSender.id == email_request.sender_id,
            EmailSender.user_id == user_id,
        )
    ).scalar_one_or_none()

    if sender is None:
        raise HTTPException(
            status_code=404,
            detail="Email sender not found",
        )

    # ---------------------------------------------------------
    # 3. Create idempotency key
    # ---------------------------------------------------------
    idempotency_key = str(uuid4())

    scheduled_email = ScheduledEmail(
        sender_id=email_request.sender_id,
        subject=email_request.subject,
        body=email_request.body,
        scheduled_at=email_request.scheduled_at,
        idempotency_key=idempotency_key,
    )

    db.add(scheduled_email)
    db.flush()

    # ---------------------------------------------------------
    # 4. Add recipients
    # ---------------------------------------------------------
    for recipient in email_request.recipients:
        email_recipient = EmailRecipient(
            scheduled_email_id=scheduled_email.id,
            email=str(recipient.email),
        )

        db.add(email_recipient)

    db.commit()
    db.refresh(scheduled_email)

    return {
        "message": "Email scheduled successfully",
        "email_id": scheduled_email.id,
        "status": scheduled_email.status,
        "scheduled_at": scheduled_email.scheduled_at,
        "recipient_count": len(email_request.recipients),
    }


@router.get("/scheduled")
def get_scheduled_emails(
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Get emails belonging only to this user
    # ---------------------------------------------------------
    scheduled_emails = db.execute(
        select(ScheduledEmail)
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            EmailSender.user_id == user_id,
        )
        .order_by(
            ScheduledEmail.scheduled_at.asc(),
        )
    ).scalars().all()

    # ---------------------------------------------------------
    # 3. Build response
    # ---------------------------------------------------------
    result = []

    for email in scheduled_emails:
        recipients = db.execute(
            select(EmailRecipient)
            .where(
                EmailRecipient.scheduled_email_id == email.id,
            )
        ).scalars().all()

        result.append(
            {
                "id": email.id,
                "sender_id": email.sender_id,
                "subject": email.subject,
                "body": email.body,
                "scheduled_at": email.scheduled_at,
                "status": email.status,
                "attempts": email.attempts,
                "last_error": email.last_error,
                "created_at": email.created_at,
                "recipients": [
                    {
                        "email": recipient.email,
                        "status": recipient.status,
                        "sent_at": recipient.sent_at,
                        "error_message": recipient.error_message,
                    }
                    for recipient in recipients
                ],
            }
        )

    return result

@router.get("/sent")
def get_sent_emails(
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Get only sent emails belonging to this user
    # ---------------------------------------------------------
    sent_emails = db.execute(
        select(ScheduledEmail)
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            EmailSender.user_id == user_id,
            ScheduledEmail.status == "sent",
        )
        .order_by(
            ScheduledEmail.created_at.desc(),
        )
    ).scalars().all()

    # ---------------------------------------------------------
    # 3. Build response
    # ---------------------------------------------------------
    result = []

    for email in sent_emails:
        recipients = db.execute(
            select(EmailRecipient)
            .where(
                EmailRecipient.scheduled_email_id == email.id,
            )
        ).scalars().all()

        result.append(
            {
                "id": email.id,
                "sender_id": email.sender_id,
                "subject": email.subject,
                "body": email.body,
                "scheduled_at": email.scheduled_at,
                "status": email.status,
                "attempts": email.attempts,
                "last_error": email.last_error,
                "created_at": email.created_at,
                "recipients": [
                    {
                        "email": recipient.email,
                        "status": recipient.status,
                        "sent_at": recipient.sent_at,
                        "error_message": recipient.error_message,
                    }
                    for recipient in recipients
                ],
            }
        )

    return result

@router.get("/cancelled")
def get_cancelled_emails(
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Get only cancelled emails belonging to this user
    # ---------------------------------------------------------
    cancelled_emails = db.execute(
        select(ScheduledEmail)
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            EmailSender.user_id == user_id,
            ScheduledEmail.status == "cancelled",
        )
        .order_by(
            ScheduledEmail.created_at.desc(),
        )
    ).scalars().all()

    # ---------------------------------------------------------
    # 3. Build response
    # ---------------------------------------------------------
    result = []

    for email in cancelled_emails:
        recipients = db.execute(
            select(EmailRecipient)
            .where(
                EmailRecipient.scheduled_email_id == email.id,
            )
        ).scalars().all()

        result.append(
            {
                "id": email.id,
                "sender_id": email.sender_id,
                "subject": email.subject,
                "body": email.body,
                "scheduled_at": email.scheduled_at,
                "status": email.status,
                "attempts": email.attempts,
                "last_error": email.last_error,
                "created_at": email.created_at,
                "recipients": [
                    {
                        "email": recipient.email,
                        "status": recipient.status,
                        "sent_at": recipient.sent_at,
                        "error_message": recipient.error_message,
                    }
                    for recipient in recipients
                ],
            }
        )

    return result

@router.get("/stats")
def get_email_stats(
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Count emails belonging only to this user
    # ---------------------------------------------------------
    scheduled_count = db.execute(
        select(func.count(ScheduledEmail.id))
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            EmailSender.user_id == user_id,
            ScheduledEmail.status == "scheduled",
        )
    ).scalar_one()

    sent_count = db.execute(
        select(func.count(ScheduledEmail.id))
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            EmailSender.user_id == user_id,
            ScheduledEmail.status == "sent",
        )
    ).scalar_one()

    failed_count = db.execute(
        select(func.count(ScheduledEmail.id))
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            EmailSender.user_id == user_id,
            ScheduledEmail.status == "failed",
        )
    ).scalar_one()

    # ---------------------------------------------------------
    # 3. Return statistics
    # ---------------------------------------------------------
    return {
        "scheduled": scheduled_count,
        "sent": sent_count,
        "failed": failed_count,
    }

@router.post("/{email_id}/cancel")
def cancel_scheduled_email(
    email_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Find and lock the email while verifying ownership
    # ---------------------------------------------------------
    email = db.execute(
        select(ScheduledEmail)
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            ScheduledEmail.id == email_id,
            EmailSender.user_id == user_id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if email is None:
        raise HTTPException(
            status_code=404,
            detail="Scheduled email not found",
        )

    # ---------------------------------------------------------
    # 3. Only scheduled emails can be cancelled
    # ---------------------------------------------------------
    if email.status != "scheduled":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Email cannot be cancelled because "
                f"its current status is '{email.status}'."
            ),
        )

    # ---------------------------------------------------------
    # 4. Mark email as cancelled
    # ---------------------------------------------------------
    email.status = "cancelled"

    db.commit()
    db.refresh(email)

    return {
        "message": "Email cancelled successfully",
        "email_id": email.id,
        "status": email.status,
    }


@router.delete("/{email_id}")
def delete_email(
    email_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Find and lock the email while verifying ownership
    # ---------------------------------------------------------
    email = db.execute(
        select(ScheduledEmail)
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            ScheduledEmail.id == email_id,
            EmailSender.user_id == user_id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if email is None:
        raise HTTPException(
            status_code=404,
            detail="Scheduled email not found",
        )

    # ---------------------------------------------------------
    # 3. Only safe-to-delete statuses can be deleted
    # ---------------------------------------------------------
    if email.status == "processing":
        raise HTTPException(
            status_code=400,
            detail=(
                "Email cannot be deleted because "
                "it is currently being processed."
            ),
        )

    if email.status == "sent":
        raise HTTPException(
            status_code=400,
            detail=(
                "Email cannot be deleted because "
                "it has already been sent."
            ),
        )

    # ---------------------------------------------------------
    # 4. Delete the email
    # ---------------------------------------------------------
    db.delete(email)
    db.commit()

    return {
        "message": "Email deleted successfully",
        "email_id": email_id,
    }


@router.post("/{email_id}/retry")
def retry_failed_email(
    email_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    # ---------------------------------------------------------
    # 1. Get logged-in user
    # ---------------------------------------------------------
    user_id = get_authenticated_user_id(request)

    # ---------------------------------------------------------
    # 2. Find and lock the email while verifying ownership
    # ---------------------------------------------------------
    email = db.execute(
        select(ScheduledEmail)
        .join(
            EmailSender,
            ScheduledEmail.sender_id == EmailSender.id,
        )
        .where(
            ScheduledEmail.id == email_id,
            EmailSender.user_id == user_id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if email is None:
        raise HTTPException(
            status_code=404,
            detail="Scheduled email not found",
        )

    # ---------------------------------------------------------
    # 3. Only failed emails can be manually retried
    # ---------------------------------------------------------
    if email.status != "failed":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Email cannot be retried because "
                f"its current status is '{email.status}'."
            ),
        )

    if email.attempts >= settings.MAX_EMAIL_ATTEMPTS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Email cannot be retried because "
                "it has reached the maximum number of attempts."
            ),
        )

    failed_recipient_exists = db.execute(
        select(EmailRecipient.id)
        .where(
            EmailRecipient.scheduled_email_id == email.id,
            EmailRecipient.status == RecipientStatus.FAILED,
        )
        .limit(1)
    ).scalar_one_or_none()

    if failed_recipient_exists is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Email cannot be retried because "
                "it has no failed recipients."
            ),
        )
# ---------------------------------------------------------
    # 4. Reset failed recipients for another attempt
    # ---------------------------------------------------------
    failed_recipients = db.execute(
        select(EmailRecipient)
        .where(
            EmailRecipient.scheduled_email_id == email.id,
            EmailRecipient.status == "failed",
        )
    ).scalars().all()

    for recipient in failed_recipients:
        recipient.status = "pending"
        recipient.error_message = None

    # ---------------------------------------------------------
    # 5. Put email back into the scheduler queue
    # ---------------------------------------------------------
    email.status = "scheduled"
    email.scheduled_at = datetime.now(timezone.utc)
    email.processing_started_at = None
    email.last_error = None

    db.commit()
    db.refresh(email)

    return {
        "message": "Email retry scheduled successfully",
        "email_id": email.id,
        "status": email.status,
        "scheduled_at": email.scheduled_at,
        "attempts": email.attempts,
    }