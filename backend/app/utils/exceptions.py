
"""Custom exception classes for the application."""
from typing import Optional


class TenantIsolationError(Exception):
    """Raised when a user tries to access data from another tenant."""

    def __init__(self, detail: str = "Access denied: tenant isolation violation"):
        self.detail = detail
        super().__init__(self.detail)


class InsufficientPermissionsError(Exception):
    """Raised when a user lacks required permissions."""

    def __init__(self, detail: str = "Insufficient permissions for this action"):
        self.detail = detail
        super().__init__(self.detail)


class ResourceNotFoundError(Exception):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = "Resource", detail: Optional[str] = None):
        self.detail = detail or f"{resource} not found"
        super().__init__(self.detail)


class AsaasIntegrationError(Exception):
    """Raised when the Asaas API returns an error."""

    def __init__(self, detail: str = "Asaas integration error"):
        self.detail = detail
        super().__init__(self.detail)


class StorageError(Exception):
    """Raised when a file upload/download operation fails."""

    def __init__(self, detail: str = "Storage operation failed"):
        self.detail = detail
        super().__init__(self.detail)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Authentication failed"):
        self.detail = detail
        super().__init__(self.detail)


class InvalidTokenError(Exception):
    """Raised when a JWT token is invalid or expired."""

    def __init__(self, detail: str = "Invalid or expired token"):
        self.detail = detail
        super().__init__(self.detail)
