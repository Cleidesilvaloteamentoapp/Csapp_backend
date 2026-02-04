from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    CLIENT = "client"


class ClientStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEFAULTER = "defaulter"


class LotStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"


class ClientLotStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InvoiceStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class ServiceOrderStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReferralStatus(str, Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    LOST = "lost"


class NotificationType(str, Enum):
    PAYMENT_OVERDUE = "payment_overdue"
    SERVICE_UPDATE = "service_update"
    GENERAL = "general"
