"""Shared authentication flow for CLI scripts."""

from __future__ import annotations

import getpass
import logging
import os
import sys
from pathlib import Path  # noqa: TC003 — used at runtime for default arg and file ops
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import (
    EmpowerAuthError,
    InteractiveAuthRequired,
    LoginRejectedError,
    TwoFactorRequiredError,
)
from personalcapital2.types import TwoFactorMode

log = logging.getLogger(__name__)


def _prompt(message: str) -> str:
    """Read a line from stdin, writing the prompt to stderr.

    Python's ``input(prompt)`` writes the prompt to stdout, which corrupts the
    CLI's JSON-on-stdout contract when ``run_authenticated`` triggers credential
    prompts mid-command (e.g. on stale-session recovery). Route prompts to
    stderr instead so stdout stays clean for piping/JSON parsing.
    """
    sys.stderr.write(message)
    sys.stderr.flush()
    return input()


def _end_prompt_line() -> None:
    """Finish a prompt line left open by EOF, so the next stderr write (the CLI's
    JSON error) starts on its own line."""
    sys.stderr.write("\n")
    sys.stderr.flush()


def parse_2fa_mode_env(value: str) -> TwoFactorMode:
    """Parse a pre-normalized (lowercased, stripped) EMPOWER_2FA_MODE value.

    Callers handle the empty == unset rule before reaching this function.
    Raises ``EmpowerAuthError`` (NOT ``InteractiveAuthRequired``): bad config
    is a distinct semantic from "no TTY available."
    """
    if value == "sms":
        return TwoFactorMode.SMS
    if value == "email":
        # Tombstone: Empower removed email 2FA server-side (the challengeEmail
        # endpoint now returns success but dispatches nothing). Point stale
        # config at the working method instead of a generic "invalid" error.
        raise EmpowerAuthError("Empower no longer supports email 2FA — set EMPOWER_2FA_MODE=sms")
    raise EmpowerAuthError(f"Invalid EMPOWER_2FA_MODE={value!r}: must be 'sms'")


_NO_CREDENTIALS = (
    "Login requires an interactive terminal or EMPOWER_EMAIL/EMPOWER_PASSWORD env vars."
)


def authenticate(
    session_path: Path = DEFAULT_SESSION_PATH,
    *,
    interactive: bool = True,
) -> EmpowerClient:
    """Authenticate with Empower, handling 2FA interactively.

    Credentials are read from EMPOWER_EMAIL/EMPOWER_PASSWORD env vars,
    falling back to interactive prompts.

    With ``interactive=False`` nothing is ever read from stdin: missing
    credentials raise ``InteractiveAuthRequired`` at once, and so does a login
    that needs 2FA, before the SMS is sent. Use it where no one can type a code
    (the CLI passes it for data commands run without a terminal), so a caller
    never blocks on a prompt or texts the user a code nobody can enter.

    The cache-using portion of login (initial cookies + 2FA challenge dispatch)
    is wrapped in a one-shot retry: if the cached session is stale, it's
    deleted and the flow runs again with a fresh client. ``verify_2fa_and_login``
    runs OUTSIDE the retry — a wrong code shouldn't nuke the cached session.
    A ``LoginRejectedError`` is not retried and leaves the cached session alone.

    Args:
        session_path: Path to persist session cookies.
        interactive: Allow prompts for missing credentials and the 2FA code.

    Returns:
        Authenticated EmpowerClient.

    Raises:
        InteractiveAuthRequired: if a credential or 2FA prompt would block on
            EOFError (non-TTY), or would be needed with ``interactive=False``.
        LoginRejectedError: if Empower rejects the username or password and says why.
        EmpowerAuthError: if login fails for credential or server reasons.
    """
    email = os.getenv("EMPOWER_EMAIL")
    password = os.getenv("EMPOWER_PASSWORD")
    if not interactive and not (email and password):
        raise InteractiveAuthRequired(_NO_CREDENTIALS)
    try:
        email = email or _prompt("Email: ")
        password = password or getpass.getpass("Password: ", stream=sys.stderr)
    except EOFError:
        _end_prompt_line()
        raise InteractiveAuthRequired(_NO_CREDENTIALS) from None

    # Tracks whether the cache-using login() call actually completed. Errors
    # raised AFTER login succeeds (parse_2fa_mode_env, send_2fa_challenge,
    # etc.) are not stale-cookie failures and must not trigger the retry.
    login_succeeded = False

    def _login_and_maybe_challenge() -> tuple[EmpowerClient, TwoFactorMode | None]:
        """Run the cache-using portion. Returns (client, mode); mode is None if no 2FA needed."""
        nonlocal login_succeeded
        client = EmpowerClient(session_path=session_path)
        try:
            client.login(email, password)
        except TwoFactorRequiredError:
            login_succeeded = True
        else:
            login_succeeded = True
            log.info("Logged in successfully")
            return client, None

        if not interactive:
            # Check before sending: an SMS nobody can enter is spam, and each
            # retry by an agent would send another.
            raise InteractiveAuthRequired(
                "Empower requires an SMS verification code, which needs an "
                "interactive terminal. No code was sent."
            )

        # Read EMPOWER_2FA_MODE inside this branch (not eagerly) so an
        # invalid value lying around in the environment doesn't break flows
        # where the device is already remembered and 2FA isn't triggered.
        # SMS is the only method Empower still offers, so there's no method
        # prompt — a set value is validated (a stale 'email' gets a clear
        # tombstone error), otherwise we default to SMS.
        env_mode = os.environ.get("EMPOWER_2FA_MODE", "").strip().lower()
        mode = parse_2fa_mode_env(env_mode) if env_mode else TwoFactorMode.SMS
        print("\n2FA required — sending SMS verification code.", file=sys.stderr)
        client.send_2fa_challenge(mode)
        return client, mode

    try:
        client, mode = _login_and_maybe_challenge()
    except (InteractiveAuthRequired, LoginRejectedError):
        # Both subclass EmpowerAuthError; catch them first so neither is mistaken
        # for stale cookies. "No TTY" and "Empower rejected these credentials" are
        # not session problems: re-raise as-is, keeping the cached session and
        # not calling identifyUser again.
        raise
    except EmpowerAuthError:
        # Stale cached cookies. Clear and retry once with a fresh client.
        # Only retry if we had a session file AND the failure was during the
        # cache-using login() call — config/2FA-dispatch errors after a
        # successful login don't indicate stale cookies.
        if login_succeeded or not session_path.exists():
            raise
        log.warning("Cached session appears stale, retrying with fresh client")
        session_path.unlink(missing_ok=True)  # race-safe
        client, mode = _login_and_maybe_challenge()

    # verify_2fa_and_login runs OUTSIDE the retry: a wrong code should NOT
    # nuke the session. EOFError on the code prompt → typed exception.
    if mode is not None:
        try:
            code = _prompt("Enter verification code: ")
        except EOFError:
            _end_prompt_line()
            raise InteractiveAuthRequired(
                "2FA verification cannot complete without an interactive terminal."
            ) from None
        client.verify_2fa_and_login(mode, code, password)
        log.info("Logged in with 2FA")

    client.save_session(session_path)
    return client


def _reauthenticate(session_path: Path, problem: str, *, interactive: bool) -> EmpowerClient:
    """``authenticate()``, with what was wrong with the session leading any
    ``InteractiveAuthRequired``, so the error alone says why a login was needed."""
    try:
        return authenticate(session_path, interactive=interactive)
    except InteractiveAuthRequired as e:
        raise InteractiveAuthRequired(f"{problem} {e}") from e


def run_authenticated[T](
    operation: Callable[[EmpowerClient], T],
    session_path: Path = DEFAULT_SESSION_PATH,
    *,
    client: EmpowerClient | None = None,
    interactive: bool = True,
) -> T:
    """Run ``operation(client)``; on stale-session failure, re-auth and retry once.

    Recovery path: if ``operation`` raises ``EmpowerAuthError`` (cached cookies
    no longer valid server-side), call ``authenticate()`` to refresh the session
    interactively and retry the operation once. A second failure propagates.

    The operation MUST be idempotent — it may run twice on the recovery path.

    Caveat: if ``EMPOWER_EMAIL``/``EMPOWER_PASSWORD`` are unset, the recovery
    path prompts for credentials mid-command. Set the env vars or run
    ``pc2 login`` first to avoid that. Pass ``interactive=False`` to never
    prompt (see ``authenticate()``).

    Args:
        operation: Callable taking an EmpowerClient and returning a result.
        session_path: Session file path passed through to ``authenticate()``.
        client: Optional pre-built client; constructed from ``session_path``
            if omitted.
        interactive: Passed to ``authenticate()``.

    Returns:
        Whatever ``operation`` returns.

    Raises:
        TwoFactorRequiredError: re-raised without retry (control-flow signal).
        InteractiveAuthRequired: if a login is needed but can't prompt. The
            message starts with what was wrong with the session.
        LoginRejectedError: if re-authentication is rejected by Empower (the
            operation is not run again).
        EmpowerAuthError: if re-authentication fails or the retried operation
            also fails.
    """
    if client is None:
        # Short-circuit cold starts: if there's no cached session, skip the
        # round-trip we know the API would reject and authenticate up front.
        # Avoids a misleading "Session is stale" log line for missing sessions
        # and eliminates a wasted network call on every fresh install.
        if not session_path.exists():
            log.info("No cached session at %s, authenticating", session_path)
            client = _reauthenticate(
                session_path, f"No saved session at {session_path}.", interactive=interactive
            )
        else:
            client = EmpowerClient(session_path=session_path)
    try:
        return operation(client)
    except TwoFactorRequiredError:
        # Control-flow signal, not a session problem — let the caller handle it.
        raise
    except EmpowerAuthError as e:
        # An empty/malformed session file leaves the client with no cookies,
        # so "stale" is misleading — there was nothing to go stale.
        if client.has_loaded_session:
            log.warning("Session is stale, re-authenticating: %s", e)
            problem = "The saved session has expired."
        else:
            log.warning("Cached session unusable, re-authenticating: %s", e)
            problem = f"The saved session at {session_path} is unusable."
        fresh_client = _reauthenticate(session_path, problem, interactive=interactive)
        return operation(fresh_client)
