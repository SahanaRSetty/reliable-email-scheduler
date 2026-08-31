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