from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models.enums import NotificationType


class NotificationCreate(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    message: str


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int
