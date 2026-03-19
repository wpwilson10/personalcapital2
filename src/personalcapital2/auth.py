"""Shared authentication flow for CLI scripts."""

from __future__ import annotations

import getpass
import logging
import os
from pathlib import Path  # noqa: TC003 — used at runtime for default arg and file ops

from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import EmpowerAuthError, TwoFactorRequiredError
from personalcapital2.types import TwoFactorMode

log = logging.getLogger(__name__)


def authenticate(session_path: Path = DEFAULT_SESSION_PATH) -> EmpowerClient:
    """Authenticate with Empower, handling 2FA interactively.

    Credentials are read from EMPOWER_EMAIL/EMPOWER_PASSWORD env vars,
    falling back to interactive prompts.

    Args:
        session_path: Path to persist session cookies.

    Returns:
        Authenticated EmpowerClient.

    Raises:
        SystemExit: On authentication failure.
    """
    email = os.getenv("EMPOWER_EMAIL") or input("Email: ")
    password = os.getenv("EMPOWER_PASSWORD") or getpass.getpass("Password: ")

    client = EmpowerClient(session_path=session_path)

    try:
        client.login(email, password)
        log.info("Logged in successfully")
    except TwoFactorRequiredError:
        print("\n2FA required. Choose method:")
        print("  1. SMS")
        print("  2. Email")
        choice = input("Choice [1]: ").strip() or "1"
        mode = TwoFactorMode.SMS if choice == "1" else TwoFactorMode.EMAIL

        try:
            client.send_2fa_challenge(mode)
        except EmpowerAuthError:
            # Stale session cookies can cause "session no longer valid" — clear
            # them and retry with a fresh session
            log.warning("2FA challenge failed with saved session, retrying fresh login")
            if session_path.exists():
                session_path.unlink()
            client = EmpowerClient(session_path=session_path)
            try:
                client.login(email, password)
                # If login succeeds without 2FA (unlikely but possible), we're done
                log.info("Logged in successfully on retry (no 2FA needed)")
                return client
            except TwoFactorRequiredError:
                pass
            client.send_2fa_challenge(mode)

        code = input("Enter verification code: ")
        client.verify_2fa_and_login(mode, code, password)
        log.info("Logged in with 2FA")
    except EmpowerAuthError as e:
        log.error("Login failed: %s", e)
        raise SystemExit(1) from e

    return client
