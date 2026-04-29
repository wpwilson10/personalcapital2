"""Shared authentication flow for CLI scripts."""

from __future__ import annotations

import getpass
import logging
import os
from pathlib import Path  # noqa: TC003 — used at runtime for default arg and file ops
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import (
    EmpowerAuthError,
    InteractiveAuthRequired,
    TwoFactorRequiredError,
)
from personalcapital2.types import TwoFactorMode

log = logging.getLogger(__name__)


def authenticate(session_path: Path = DEFAULT_SESSION_PATH) -> EmpowerClient:
    """Authenticate with Empower, handling 2FA interactively.

    Credentials are read from EMPOWER_EMAIL/EMPOWER_PASSWORD env vars,
    falling back to interactive prompts.

    The cache-using portion of login (initial cookies + 2FA challenge dispatch)
    is wrapped in a one-shot retry: if the cached session is stale, it's
    deleted and the flow runs again with a fresh client. ``verify_2fa_and_login``
    runs OUTSIDE the retry — a wrong code shouldn't nuke the cached session.

    Args:
        session_path: Path to persist session cookies.

    Returns:
        Authenticated EmpowerClient.

    Raises:
        InteractiveAuthRequired: if a credential or 2FA prompt would block on
            EOFError (non-TTY).
        EmpowerAuthError: if login fails for credential or server reasons.
    """
    try:
        email = os.getenv("EMPOWER_EMAIL") or input("Email: ")
        password = os.getenv("EMPOWER_PASSWORD") or getpass.getpass("Password: ")
    except EOFError:
        raise InteractiveAuthRequired(
            "Login requires an interactive terminal or EMPOWER_EMAIL/EMPOWER_PASSWORD env vars."
        ) from None

    def _login_and_maybe_challenge() -> tuple[EmpowerClient, TwoFactorMode | None]:
        """Run the cache-using portion. Returns (client, mode); mode is None if no 2FA needed."""
        client = EmpowerClient(session_path=session_path)
        try:
            client.login(email, password)
            log.info("Logged in successfully")
            return client, None
        except TwoFactorRequiredError:
            pass

        try:
            print("\n2FA required. Choose method:")
            print("  1. SMS")
            print("  2. Email")
            choice = input("Choice [1]: ").strip() or "1"
        except EOFError:
            raise InteractiveAuthRequired(
                "2FA cannot complete without an interactive terminal. "
                "See https://github.com/wpwilson10/personalcapital2/issues/5 "
                "for headless support."
            ) from None
        mode = TwoFactorMode.SMS if choice == "1" else TwoFactorMode.EMAIL
        client.send_2fa_challenge(mode)
        return client, mode

    try:
        client, mode = _login_and_maybe_challenge()
    except InteractiveAuthRequired:
        # Non-TTY at the 2FA-method prompt is NOT a stale-session problem.
        # Re-raise without unlinking — preserve the user's cached session.
        raise
    except EmpowerAuthError:
        # Stale cached cookies. Clear and retry once with a fresh client.
        # Only retry if we had a session file — otherwise it's a real auth failure.
        if not session_path.exists():
            raise
        log.warning("Cached session appears stale, retrying with fresh client")
        session_path.unlink(missing_ok=True)  # race-safe
        client, mode = _login_and_maybe_challenge()

    # verify_2fa_and_login runs OUTSIDE the retry: a wrong code should NOT
    # nuke the session. EOFError on the code prompt → typed exception.
    if mode is not None:
        try:
            code = input("Enter verification code: ")
        except EOFError:
            raise InteractiveAuthRequired(
                "2FA verification cannot complete without an interactive terminal."
            ) from None
        client.verify_2fa_and_login(mode, code, password)
        log.info("Logged in with 2FA")

    client.save_session(session_path)
    return client


def run_authenticated[T](
    operation: Callable[[EmpowerClient], T],
    session_path: Path = DEFAULT_SESSION_PATH,
    *,
    client: EmpowerClient | None = None,
) -> T:
    """Run ``operation(client)``; on stale-session failure, re-auth and retry once.

    Recovery path: if ``operation`` raises ``EmpowerAuthError`` (cached cookies
    no longer valid server-side), call ``authenticate()`` to refresh the session
    interactively and retry the operation once. A second failure propagates.

    The operation MUST be idempotent — it may run twice on the recovery path.

    Caveat: if ``EMPOWER_EMAIL``/``EMPOWER_PASSWORD`` are unset, the recovery
    path prompts for credentials mid-command. Set the env vars or run
    ``pc2 login`` first to avoid that.

    Args:
        operation: Callable taking an EmpowerClient and returning a result.
        session_path: Session file path passed through to ``authenticate()``.
        client: Optional pre-built client; constructed from ``session_path``
            if omitted.

    Returns:
        Whatever ``operation`` returns.

    Raises:
        TwoFactorRequiredError: re-raised without retry (control-flow signal).
        EmpowerAuthError: if re-authentication fails or the retried operation
            also fails.
    """
    if client is None:
        client = EmpowerClient(session_path=session_path)
    try:
        return operation(client)
    except TwoFactorRequiredError:
        # Control-flow signal, not a session problem — let the caller handle it.
        raise
    except EmpowerAuthError as e:
        log.warning("Session is stale, re-authenticating: %s", e)
        fresh_client = authenticate(session_path)
        return operation(fresh_client)
