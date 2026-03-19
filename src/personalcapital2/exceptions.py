"""Exception types for the Empower API client."""


class EmpowerAuthError(Exception):
    """Raised when login fails (bad credentials, CSRF extraction failure, etc.)."""


class TwoFactorRequiredError(Exception):
    """Raised when the server requires 2FA before password auth can proceed."""


class EmpowerAPIError(Exception):
    """Raised when an API call returns spHeader.success = false."""
