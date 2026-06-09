
"""Pydantic schemas for company notification settings."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID

    # Client
    notify_client_new_boleto: bool
    notify_client_due_reminder: bool
    notify_client_overdue: bool
    notify_client_service: bool

    # Admin
    notify_admin_client_created: bool
    notify_admin_client_deleted: bool
    notify_admin_boleto_generated: bool
    notify_admin_boleto_cancelled: bool
    notify_admin_cycle_request: bool

    # Admin WhatsApp numbers (comma-separated string in DB, list in API)
    admin_whatsapp_numbers: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class NotificationSettingsUpdate(BaseModel):
    # Client
    notify_client_new_boleto: Optional[bool] = None
    notify_client_due_reminder: Optional[bool] = None
    notify_client_overdue: Optional[bool] = None
    notify_client_service: Optional[bool] = None

    # Admin
    notify_admin_client_created: Optional[bool] = None
    notify_admin_client_deleted: Optional[bool] = None
    notify_admin_boleto_generated: Optional[bool] = None
    notify_admin_boleto_cancelled: Optional[bool] = None
    notify_admin_cycle_request: Optional[bool] = None

    # Comma-separated international numbers, e.g. "5511999990000,5511888880000"
    admin_whatsapp_numbers: Optional[str] = Field(None, max_length=2000)
