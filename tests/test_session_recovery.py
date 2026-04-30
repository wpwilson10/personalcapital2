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
from personalcapital2.types import TwoFactorMode

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


class _FakeSession:
    """Stand-in for requests.Session — only the cookies attribute matters."""

    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}


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
        self.send_2fa_modes: list[TwoFactorMode] = []
        self.verify_2fa_calls = 0
        self.verify_2fa_modes: list[TwoFactorMode] = []
        self.save_session_calls = 0
        # Mirror real EmpowerClient attributes so auth.py helpers that peek at
        # session state don't AttributeError on the test double.
        self._csrf: str = ""
        self._session = _FakeSession()
        self._loaded_from_disk = False
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
        self.send_2fa_modes.append(mode)
        err = type(self)._next(type(self).send_2fa_recipe)
        if err is not None:
            raise err

    def verify_2fa_and_login(self, mode: TwoFactorMode, code: str, password: str) -> None:
        self.verify_2fa_calls += 1
        self.verify_2fa_modes.append(mode)
        err = type(self)._next(type(self).verify_2fa_recipe)
        if err is not None:
            raise err

    def save_session(self, path: Path | None = None) -> None:
        self.save_session_calls += 1
        target = path or self.session_path
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}")

    @property
    def has_loaded_session(self) -> bool:
        return self._loaded_from_disk


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

    with pytest.raises(InteractiveAuthRequired, match="EMPOWER_2FA_MODE"):
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

    # First input() call answers the 2FA-method prompt; the next one (code prompt) EOFs.
    # _prompt() writes the message to stderr and calls input() without args, so we can't
    # dispatch on prompt content — track call ordering with a queue instead.
    answers = iter(["1"])

    def queued_or_eof(_prompt: str = "") -> str:
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None

    _patch_input(monkeypatch, queued_or_eof)

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
    # Cached session must exist so run_authenticated runs the operation first
    # (the cold-start short-circuit would otherwise authenticate up front).
    session_path.write_text("{}")
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
    # Cached session must exist so the short-circuit doesn't auth up front
    # (which would defeat the assertion that authenticate() is never called).
    session_path.write_text("{}")

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


# --- 11. Credential prompts must not leak to stdout (CLI JSON-on-stdout contract) ---


def test_authenticate_prompts_do_not_leak_to_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stale-session recovery from a data command runs ``authenticate()``
    mid-pipeline. Any prompts must go to stderr — anything on stdout would
    corrupt the CLI's structured-JSON output and break agents/scripts piping
    ``pc2 ... | jq``.
    """
    session_path = tmp_path / "session.json"
    monkeypatch.delenv("EMPOWER_EMAIL", raising=False)
    monkeypatch.delenv("EMPOWER_PASSWORD", raising=False)

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    _patch_input(monkeypatch, raise_eof)

    with pytest.raises(InteractiveAuthRequired):
        authenticate(session_path)

    captured = capsys.readouterr()
    assert captured.out == "", (
        f"authenticate() must not write prompts to stdout; got {captured.out!r}"
    )
    # The "Email: " prompt should be the thing that hit stderr.
    assert "Email:" in captured.err


# --- 12. Cold start short-circuits to authenticate() — no wasted API round-trip ---


def test_run_authenticated_cold_start_short_circuits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """When no session file exists, run_authenticated() must call authenticate()
    BEFORE running the operation, so a fresh install/logout doesn't burn a
    network round-trip the API would reject anyway. Also avoids the misleading
    'Session is stale, re-authenticating' log line for an absent session.
    """
    session_path = tmp_path / "session.json"  # does NOT exist
    assert not session_path.exists()

    _FakeClient.login_recipe = [None]  # initial authenticate succeeds

    auth_calls = {"n": 0}
    real_authenticate = authenticate

    def counting_authenticate(path: Path = session_path) -> Any:
        auth_calls["n"] += 1
        return real_authenticate(path)

    monkeypatch.setattr("personalcapital2.auth.authenticate", counting_authenticate)

    op_calls = {"n": 0}

    def operation(client: Any) -> str:
        op_calls["n"] += 1
        return "ok"

    result = run_authenticated(operation, session_path)

    assert result == "ok"
    assert auth_calls["n"] == 1, "authenticate must run once up front (cold start)"
    assert op_calls["n"] == 1, "operation must run exactly once after authenticate succeeds"


def test_run_authenticated_cached_session_skips_short_circuit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a session file already exists, run_authenticated() must run the
    operation without calling authenticate() up front — that's the whole point
    of cached sessions."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")  # cached session present

    auth_calls = {"n": 0}

    def fake_authenticate(path: Path = session_path) -> Any:
        auth_calls["n"] += 1
        raise AssertionError("authenticate must NOT be called when a session exists")

    monkeypatch.setattr("personalcapital2.auth.authenticate", fake_authenticate)

    def operation(client: Any) -> str:
        return "ok"

    assert run_authenticated(operation, session_path) == "ok"
    assert auth_calls["n"] == 0


# --- 13. Stale vs unusable session log differentiation ---


def test_has_loaded_session_false_for_blank_file(tmp_path: Path) -> None:
    """A syntactically-valid but empty session file (no csrf, no cookies)
    must report no cached state — recovery should log 'unusable', not 'stale'.
    """
    import json

    from personalcapital2.client import EmpowerClient

    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"csrf": "", "cookies": {}}))
    session_path.chmod(0o600)
    client = EmpowerClient(session_path=session_path)
    assert client.has_loaded_session is False


def test_has_loaded_session_true_when_csrf_loaded(tmp_path: Path) -> None:
    """A populated session file (csrf + cookies present) must report cached
    state — recovery should log 'stale' on auth failure."""
    import json

    from personalcapital2.client import EmpowerClient

    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"csrf": "abc-123", "cookies": {"foo": "bar"}}))
    session_path.chmod(0o600)
    client = EmpowerClient(session_path=session_path)
    assert client.has_loaded_session is True


def test_has_loaded_session_is_a_snapshot_not_live_state(tmp_path: Path) -> None:
    """has_loaded_session must reflect 'did we load state from disk', not
    'are there cookies in the jar right now'.

    Regression guard: a failed fetch() against Empower will populate the
    session jar with server-set tracking cookies even when the request was
    rejected. If has_loaded_session checks live cookies, a blank session
    that triggered a single failed call will incorrectly report True after
    that call, making run_authenticated log 'stale' instead of 'unusable'.
    """
    import json

    from personalcapital2.client import EmpowerClient

    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"csrf": "", "cookies": {}}))
    session_path.chmod(0o600)
    client = EmpowerClient(session_path=session_path)
    assert client.has_loaded_session is False

    # Simulate cookies appearing later (server set them on a failed request).
    # pyright sees cookielib's `.set()` return as partially unknown; we don't
    # care about the return value here (fixture, not production code).
    client._session.cookies.set("PC_SESSION", "tracking-cookie")  # pyright: ignore[reportUnknownMemberType]
    assert client.has_loaded_session is False, (
        "has_loaded_session must remain False after disk load failed, "
        "even if cookies later appear from a network response"
    )


def test_run_authenticated_logs_unusable_for_blank_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end: when the cached client has no loaded state, the recovery
    log line must say 'unusable', not 'stale' — there's nothing to go stale."""
    import logging

    session_path = tmp_path / "session.json"
    session_path.write_text("{}")  # FakeClient defaults: _csrf="", cookies={}

    _FakeClient.login_recipe = [None]

    def operation(client: Any) -> str:
        if not getattr(operation, "_called", False):
            operation._called = True  # type: ignore[attr-defined]
            raise EmpowerAuthError("Session not authenticated")
        return "ok"

    with caplog.at_level(logging.WARNING, logger="personalcapital2.auth"):
        assert run_authenticated(operation, session_path) == "ok"

    messages = [r.getMessage() for r in caplog.records]
    assert any("unusable" in m for m in messages), messages
    assert not any("Session is stale" in m for m in messages), messages


# --- 14. Headless 2FA via EMPOWER_2FA_MODE env var ---


def _input_must_not_be_called(_prompt: str = "") -> str:
    raise AssertionError("input() must not be called when EMPOWER_2FA_MODE is set")


def test_authenticate_2fa_mode_env_sms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """EMPOWER_2FA_MODE=sms skips the interactive method prompt and dispatches SMS."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    monkeypatch.setenv("EMPOWER_2FA_MODE", "sms")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]
    # First input() answers the verify-code prompt; method prompt must NOT be hit.
    answers = iter(["123456"])
    _patch_input(monkeypatch, lambda _prompt="": next(answers))

    authenticate(session_path)

    client = _FakeClient.instances[0]
    assert client.send_2fa_calls == 1
    assert client.send_2fa_modes == [TwoFactorMode.SMS]
    assert client.verify_2fa_calls == 1
    assert client.verify_2fa_modes == [TwoFactorMode.SMS]


def test_authenticate_2fa_mode_env_email(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """EMPOWER_2FA_MODE=email dispatches via email."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    monkeypatch.setenv("EMPOWER_2FA_MODE", "email")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]
    answers = iter(["123456"])
    _patch_input(monkeypatch, lambda _prompt="": next(answers))

    authenticate(session_path)

    client = _FakeClient.instances[0]
    assert client.send_2fa_modes == [TwoFactorMode.EMAIL]
    assert client.verify_2fa_modes == [TwoFactorMode.EMAIL]


def test_authenticate_2fa_mode_env_case_insensitive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """Mode parsing is case-insensitive — uppercase value still works."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    monkeypatch.setenv("EMPOWER_2FA_MODE", "SMS")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]
    answers = iter(["123456"])
    _patch_input(monkeypatch, lambda _prompt="": next(answers))

    authenticate(session_path)

    client = _FakeClient.instances[0]
    assert client.send_2fa_modes == [TwoFactorMode.SMS]


def test_authenticate_2fa_mode_env_invalid_raises_autherror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """Invalid mode value raises EmpowerAuthError (not InteractiveAuthRequired) —
    bad config is a distinct semantic from "no TTY available", and library
    callers must be able to distinguish without parsing strings.
    """
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    monkeypatch.setenv("EMPOWER_2FA_MODE", "carrier-pigeon")

    _FakeClient.login_recipe = [TwoFactorRequiredError()]
    _patch_input(monkeypatch, _input_must_not_be_called)

    with pytest.raises(EmpowerAuthError) as exc_info:
        authenticate(session_path)

    # type() check, not isinstance: pytest.raises(EmpowerAuthError) catches the
    # InteractiveAuthRequired subclass too. The contract is the parent class.
    assert type(exc_info.value) is EmpowerAuthError
    assert "carrier-pigeon" in str(exc_info.value)


def test_authenticate_2fa_mode_env_empty_falls_through_to_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """Empty/whitespace EMPOWER_2FA_MODE is treated as unset — orchestrator
    templating commonly produces empty env vars from missing upstream values.
    Falls through to the interactive prompt; non-TTY there raises
    InteractiveAuthRequired as usual.
    """
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    monkeypatch.setenv("EMPOWER_2FA_MODE", "   ")  # whitespace == unset

    _FakeClient.login_recipe = [TwoFactorRequiredError()]

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    _patch_input(monkeypatch, raise_eof)

    with pytest.raises(InteractiveAuthRequired, match="EMPOWER_2FA_MODE"):
        authenticate(session_path)


def test_authenticate_2fa_mode_env_ignored_when_no_2fa_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_creds: None,
) -> None:
    """Contract pin: the env var is read INSIDE the 2FA-required branch, not
    eagerly. An invalid value sitting in the environment must not break flows
    where the device is remembered and 2FA isn't triggered.
    """
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    monkeypatch.setenv("EMPOWER_2FA_MODE", "carrier-pigeon")  # invalid, but never read

    _FakeClient.login_recipe = [None]  # no 2FA needed
    _patch_input(monkeypatch, _input_must_not_be_called)

    authenticate(session_path)

    client = _FakeClient.instances[0]
    assert client.send_2fa_calls == 0
    assert client.verify_2fa_calls == 0
