from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.recipient import EmailRecipient
from app.models.scheduled_email import ScheduledEmail
from app.models.sender import EmailSender
from app.schemas.email import ScheduledEmailCreate


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
