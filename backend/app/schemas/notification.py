
"""Notification schemas (Pydantic v2)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """Notification read response."""

    id: UUID
    company_id: UUID
    user_id: UUID
    title: str
    message: str
    type: str
    is_read: bool
    data: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    """Unread notification count."""

    unread_count: int
