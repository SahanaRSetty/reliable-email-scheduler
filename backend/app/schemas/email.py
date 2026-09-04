from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RecipientCreate(BaseModel):
    email: EmailStr


class ScheduledEmailCreate(BaseModel):
    sender_id: int
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    scheduled_at: datetime
    recipients: list[RecipientCreate] = Field(min_length=1)

class EmailSenderCreate(BaseModel):
    email: EmailStr
    display_name: str | None = Field(
        default=None,
        max_length=255,
    )
    smtp_host: str = Field(
        min_length=1,
        max_length=255,
    )
    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
    )
    smtp_username: str = Field(
        min_length=1,
        max_length=320,
    )
    smtp_password: str = Field(
        min_length=1,
        max_length=500,
    )


class EmailSenderResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None = None