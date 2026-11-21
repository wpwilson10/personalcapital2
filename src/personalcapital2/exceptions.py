"""Exception types for the Empower API client."""


class EmpowerAuthError(Exception):
    """Raised when login fails (bad credentials, CSRF extraction failure, etc.)."""


class TwoFactorRequiredError(EmpowerAuthError):
    """Raised when the server requires 2FA before password auth can proceed."""

    def __init__(self, message: str = "Two-factor authentication required") -> None:
        super().__init__(message)


class LoginRejectedError(EmpowerAuthError):
    """Raised when Empower rejects the sign-in at identification and says why.

    The message leads with Empower's own error codes and messages. The fields
    carry what the server sent, unchanged:

    - ``errors``: the ``spHeader.errors`` entries (e.g. ``{"code": 113,
      "message": "Please use a valid email address."}``)
    - ``login_url`` / ``destination_url``: ``spHeader.loginURL`` /
      ``spHeader.destinationURL``, set when Empower points the account elsewhere

    The cached session is left alone and the login is not retried: the server
    rejected the identity, not the session.
    """

    def __init__(
        self,
        message: str = "Empower rejected the sign-in",
        errors: tuple[dict[str, object], ...] = (),
        login_url: str | None = None,
        destination_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.errors = errors
        self.login_url = login_url
        self.destination_url = destination_url

    @property
    def codes(self) -> tuple[str, ...]:
        """Error codes as strings, in server order (entries without a code are skipped)."""
        return tuple(str(e["code"]) for e in self.errors if e.get("code") is not None)


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
