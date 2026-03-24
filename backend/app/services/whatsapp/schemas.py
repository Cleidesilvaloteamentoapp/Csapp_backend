
"""Internal dataclasses for WhatsApp provider communication."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SendResult:
    """Result of a message send operation."""

    success: bool
    message_id: Optional[str] = None
    provider: str = ""
    error: Optional[str] = None
    raw_response: Optional[dict[str, Any]] = None


@dataclass
class ConnectionStatus:
    """Provider connection status."""

    connected: bool
    status: str = "unknown"  # connected / disconnected / connecting / unknown
    profile_name: Optional[str] = None
    phone_number: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class TemplateInfo:
    """WhatsApp message template metadata."""

    name: str
    status: str  # APPROVED / PENDING / REJECTED
    category: str = ""
    language: str = "pt_BR"
    components: list[dict[str, Any]] = field(default_factory=list)
    id: Optional[str] = None
    raw: Optional[dict[str, Any]] = None
