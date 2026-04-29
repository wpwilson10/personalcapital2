"""Tests for stale-session recovery, non-TTY handling, and run_authenticated.

Mocks at the EmpowerClient boundary via monkeypatch so we exercise the real
authenticate() / run_authenticated() control flow without HTTP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from personalcapital2.auth import authenticate, run_authenticated
from personalcapital2.exceptions import (
    EmpowerAuthError,
    InteractiveAuthRequired,
    TwoFactorRequiredError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from personalcapital2.types import TwoFactorMode

# --- Public API smoke (Task 6) ---


def test_public_api_imports() -> None:
    """Documented exports are importable from the package root."""
    from personalcapital2 import (
        EmpowerNetworkError,
        InteractiveAuthRequired,
        run_authenticated,
    )

    assert run_authenticated is not None
    assert EmpowerNetworkError is not None
    assert InteractiveAuthRequired is not None


# --- Test fixtures: configurable FakeClient ---


class _FakeClient:
    """Stand-in for EmpowerClient. Behavior driven by class-level recipe lists.

    Recipes are mutable iterators on the class. Each test sets them at start
    and reads instance counts via _FakeClient.instances at the end.
    """

    instances: ClassVar[list[_FakeClient]] = []
    login_recipe: ClassVar[list[BaseException | None]] = []
    send_2fa_recipe: ClassVar[list[BaseException | None]] = []
    verify_2fa_recipe: ClassVar[list[BaseException | None]] = []

    def __init__(self, session_path: Path | None = None) -> None:
        self.session_path = session_path
        self.login_calls = 0
        self.send_2fa_calls = 0
        self.verify_2fa_calls = 0
        self.save_session_calls = 0
        type(self).instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.login_recipe = []
        cls.send_2fa_recipe = []
        cls.verify_2fa_recipe = []

    @classmethod
    def _next(cls, recipe: list[BaseException | None]) -> BaseException | None:
        return recipe.pop(0) if recipe else None

    def login(self, email: str, password: str) -> None:
        self.login_calls += 1
        err = type(self)._next(type(self).login_recipe)
        if err is not None:
            raise err

    def send_2fa_challenge(self, mode: TwoFactorMode) -> None:
        self.send_2fa_calls += 1
        err = type(self)._next(type(self).send_2fa_recipe)
        if err is not None:
            raise err

    def verify_2fa_and_login(self, mode: TwoFactorMode, code: str, password: str) -> None:
        self.verify_2fa_calls += 1
        err = type(self)._next(type(self).verify_2fa_recipe)
        if err is not None:
            raise err

    def save_session(self, path: Path | None = None) -> None:
        self.save_session_calls += 1
        target = path or self.session_path
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}")


@pytest.fixture(autouse=True)
def patch_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.reset()
    monkeypatch.setattr("personalcapital2.auth.EmpowerClient", _FakeClient)


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass interactive email/password prompts via env vars."""
    monkeypatch.setenv("EMPOWER_EMAIL", "user@example.com")
    monkeypatch.setenv("EMPOWER_PASSWORD", "secret")


def _patch_input(monkeypatch: pytest.MonkeyPatch, fn: Callable[[str], str]) -> None:
    monkeypatch.setattr("builtins.input", fn)


# --- 1. Stale session on initial login → recovers (the #4 regression test) ---


def test_authenticate_recovers_from_stale_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """Issue #4: cached cookies stale → first login() raises EmpowerAuthError →
    session file unlinked → fresh client retries and succeeds."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")

    _FakeClient.login_recipe = [EmpowerAuthError("Session is no longer valid"), None]

    client = authenticate(session_path)

    # Two clients constructed (original + retry); the retry succeeded.
    assert len(_FakeClient.instances) == 2
    assert client is _FakeClient.instances[1]
    # save_session was called on the successful client at the tail of authenticate().
    assert _FakeClient.instances[1].save_session_calls == 1


# --- 2. No cached session + auth error → raises, no retry ---


def test_authenticate_no_cached_session_no_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    session_path = tmp_path / "session.json"  # does NOT exist

    _FakeClient.login_recipe = [EmpowerAuthError("Bad credentials")]

    with pytest.raises(EmpowerAuthError, match="Bad credentials"):
        authenticate(session_path)

    assert len(_FakeClient.instances) == 1


# --- 3. Wrong 2FA code → raises, session NOT cleared ---


def test_authenticate_wrong_2fa_code_preserves_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """A wrong verification code should propagate cleanly without unlinking
    the cached session — verify_2fa_and_login runs OUTSIDE the retry block."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]
    _FakeClient.verify_2fa_recipe = [EmpowerAuthError("2FA verification failed: invalid code")]

    inputs = iter(["1", "wrongcode"])
    _patch_input(monkeypatch, lambda _prompt="": next(inputs))

    with pytest.raises(EmpowerAuthError, match="2FA verification failed"):
        authenticate(session_path)

    assert session_path.exists(), "wrong 2FA code must NOT delete the cached session"
    # Only one client constructed (verify is outside the retry block, so no second attempt).
    assert len(_FakeClient.instances) == 1


# --- 4. Non-TTY at email prompt → InteractiveAuthRequired ---


def test_authenticate_non_tty_email_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_path = tmp_path / "session.json"
    monkeypatch.delenv("EMPOWER_EMAIL", raising=False)
    monkeypatch.delenv("EMPOWER_PASSWORD", raising=False)

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    _patch_input(monkeypatch, raise_eof)

    with pytest.raises(InteractiveAuthRequired, match="interactive terminal"):
        authenticate(session_path)


# --- 5. Non-TTY at 2FA-method prompt → InteractiveAuthRequired; session preserved ---


def test_authenticate_non_tty_2fa_method_preserves_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """Regression guard for the InteractiveAuthRequired carve-out in the inner
    retry: non-TTY at the 2FA-method prompt must NOT trigger session unlink."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    _patch_input(monkeypatch, raise_eof)

    with pytest.raises(InteractiveAuthRequired, match="issues/5"):
        authenticate(session_path)

    assert session_path.exists(), (
        "non-TTY 2FA-method prompt must preserve the cached session "
        "(the InteractiveAuthRequired carve-out)"
    )
    # Only one client — no retry occurred.
    assert len(_FakeClient.instances) == 1


# --- 6. Non-TTY at verification-code prompt → InteractiveAuthRequired ---


def test_authenticate_non_tty_verify_code_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]

    inputs: list[str] = ["1"]  # 2FA-method prompt answered, code prompt EOFs

    def maybe_eof(prompt: str = "") -> str:
        if "verification code" in prompt:
            raise EOFError
        return inputs.pop(0)

    _patch_input(monkeypatch, maybe_eof)

    with pytest.raises(InteractiveAuthRequired, match="2FA verification cannot complete"):
        authenticate(session_path)

    assert session_path.exists(), "non-TTY at code prompt must NOT unlink the session"


# --- 7. run_authenticated stale session during fetch → re-auths and retries ---


def test_run_authenticated_recovers_from_stale_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """A stale session detected during a fetch should trigger re-auth and a
    single retry of the operation."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")

    # The retry path inside authenticate() goes through _login_and_maybe_challenge
    # using a fresh FakeClient. login_recipe has one entry (None=success) for
    # that fresh client.
    _FakeClient.login_recipe = [None]

    auth_calls = {"n": 0}
    real_authenticate = authenticate

    def counting_authenticate(path: Path = session_path) -> Any:
        auth_calls["n"] += 1
        return real_authenticate(path)

    monkeypatch.setattr("personalcapital2.auth.authenticate", counting_authenticate)

    op_calls = {"n": 0}

    def operation(client: Any) -> str:
        op_calls["n"] += 1
        if op_calls["n"] == 1:
            raise EmpowerAuthError("Session not authenticated")
        return "ok"

    result = run_authenticated(operation, session_path)

    assert result == "ok"
    assert op_calls["n"] == 2
    assert auth_calls["n"] == 1


# --- 8. run_authenticated propagates InteractiveAuthRequired from authenticate ---


def test_run_authenticated_propagates_interactive_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If re-auth itself fails with InteractiveAuthRequired (no TTY), the
    outer caller sees that error — operation is not retried."""
    session_path = tmp_path / "session.json"
    monkeypatch.delenv("EMPOWER_EMAIL", raising=False)
    monkeypatch.delenv("EMPOWER_PASSWORD", raising=False)

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    _patch_input(monkeypatch, raise_eof)

    op_calls = {"n": 0}

    def operation(client: Any) -> str:
        op_calls["n"] += 1
        raise EmpowerAuthError("Session not authenticated")

    with pytest.raises(InteractiveAuthRequired, match="interactive terminal"):
        run_authenticated(operation, session_path)

    assert op_calls["n"] == 1, "operation must not retry after re-auth fails"


# --- 9. run_authenticated re-raises TwoFactorRequiredError without invoking authenticate ---


def test_run_authenticated_does_not_recover_from_2fa_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TwoFactorRequiredError is a control-flow signal, not a stale-session
    error — run_authenticated must propagate it without calling authenticate()."""
    session_path = tmp_path / "session.json"

    auth_calls = {"n": 0}

    def fake_authenticate(path: Path = session_path) -> Any:
        auth_calls["n"] += 1
        raise AssertionError("authenticate must NOT be called for TwoFactorRequiredError")

    monkeypatch.setattr("personalcapital2.auth.authenticate", fake_authenticate)

    def operation(client: Any) -> str:
        raise TwoFactorRequiredError()

    with pytest.raises(TwoFactorRequiredError):
        run_authenticated(operation, session_path)

    assert auth_calls["n"] == 0


# --- 10. run_authenticated second failure → propagates, no second retry ---


def test_run_authenticated_does_not_retry_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """If the operation still fails after re-auth, the second failure
    propagates — no third attempt."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")

    _FakeClient.login_recipe = [None]  # re-auth succeeds

    auth_calls = {"n": 0}
    real_authenticate = authenticate

    def counting_authenticate(path: Path = session_path) -> Any:
        auth_calls["n"] += 1
        return real_authenticate(path)

    monkeypatch.setattr("personalcapital2.auth.authenticate", counting_authenticate)

    op_calls = {"n": 0}

    def operation(client: Any) -> str:
        op_calls["n"] += 1
        raise EmpowerAuthError("still stale")

    with pytest.raises(EmpowerAuthError, match="still stale"):
        run_authenticated(operation, session_path)

    assert op_calls["n"] == 2, "operation must run exactly twice (initial + one retry)"
    assert auth_calls["n"] == 1, "authenticate must run exactly once"
