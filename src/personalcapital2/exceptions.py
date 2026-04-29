"""Exception types for the Empower API client."""


class EmpowerAuthError(Exception):
    """Raised when login fails (bad credentials, CSRF extraction failure, etc.)."""


class TwoFactorRequiredError(EmpowerAuthError):
    """Raised when the server requires 2FA before password auth can proceed."""

    def __init__(self, message: str = "Two-factor authentication required") -> None:
        super().__init__(message)


class InteractiveAuthRequired(EmpowerAuthError):  # noqa: N818 — name captures the recovery action, not "X happened"
    """Raised when authentication needs interactive input (TTY) and one isn't available.

    Subclass of EmpowerAuthError so existing ``except EmpowerAuthError`` handlers
    catch it without a separate branch. Library callers can catch this
    specifically to distinguish 'no TTY available' from 'bad credentials'.
    """


class EmpowerAPIError(Exception):
    """Raised when an API call returns spHeader.success = false."""


class EmpowerNetworkError(Exception):
    """Raised when an HTTP request fails for transport reasons (connection, timeout, DNS).

    Distinct from EmpowerAuthError (4xx auth failures) and EmpowerAPIError
    (server returned spHeader.success=false). Lets callers distinguish
    "site unreachable" from "wrong password."
    """
