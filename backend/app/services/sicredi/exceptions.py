
"""Sicredi-specific exception hierarchy."""


class SicrediError(Exception):
    """Base exception for all Sicredi integration errors."""

    def __init__(self, detail: str = "Sicredi integration error", status_code: int | None = None, raw_response: dict | None = None):
        self.detail = detail
        self.status_code = status_code
        self.raw_response = raw_response or {}
        super().__init__(self.detail)


class SicrediAuthError(SicrediError):
    """Raised when authentication or token refresh fails."""

    def __init__(self, detail: str = "Sicredi authentication failed", **kwargs):
        super().__init__(detail=detail, **kwargs)


class SicrediValidationError(SicrediError):
    """Raised when the API rejects input data (4xx)."""

    def __init__(self, detail: str = "Sicredi validation error", **kwargs):
        super().__init__(detail=detail, **kwargs)


class SicrediNotFoundError(SicrediError):
    """Raised when the requested resource is not found (404/422)."""

    def __init__(self, detail: str = "Sicredi resource not found", **kwargs):
        super().__init__(detail=detail, **kwargs)


class SicrediRateLimitError(SicrediError):
    """Raised when rate limited by the Sicredi API (429)."""

    def __init__(self, detail: str = "Sicredi rate limit exceeded", **kwargs):
        super().__init__(detail=detail, **kwargs)


class SicrediTimeoutError(SicrediError):
    """Raised when a request to the Sicredi API times out."""

    def __init__(self, detail: str = "Sicredi request timeout", **kwargs):
        super().__init__(detail=detail, **kwargs)
