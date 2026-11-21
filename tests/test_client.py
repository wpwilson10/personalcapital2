"""Tests for the Empower API client."""

from __future__ import annotations

import json
import pickle
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest
import requests

from personalcapital2.client import DEFAULT_USER_AGENT, EmpowerClient
from personalcapital2.exceptions import (
    EmpowerAPIError,
    EmpowerAuthError,
    EmpowerNetworkError,
    LoginRejectedError,
    TwoFactorRequiredError,
)
from personalcapital2.types import TwoFactorMode


def _mock_response(
    json_data: dict[str, Any] | None = None,
    text: str = "",
    status_code: int = 200,
) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = json.JSONDecodeError("", "", 0)
    resp.raise_for_status.return_value = None
    return resp


# --- CSRF extraction ---


def test_extract_csrf_from_login_page() -> None:
    client = EmpowerClient()
    html = "<html><script>window.csrf='abc-123-def'</script></html>"
    with patch.object(client._session, "request", return_value=_mock_response(text=html)):
        csrf = client._extract_csrf()
    assert csrf == "abc-123-def"


def test_extract_csrf_returns_none_on_missing_pattern() -> None:
    client = EmpowerClient()
    html = "<html><body>No CSRF here</body></html>"
    with patch.object(client._session, "request", return_value=_mock_response(text=html)):
        csrf = client._extract_csrf()
    assert csrf is None


# --- Login flow ---


def test_login_success_with_remembered_session() -> None:
    client = EmpowerClient()
    csrf_page = _mock_response(text="window.csrf='aaa-111-bbb'")
    identify_resp = _mock_response(
        json_data={"spHeader": {"csrf": "token-2", "authLevel": "USER_REMEMBERED", "success": True}}
    )
    auth_resp = _mock_response(
        json_data={
            "spHeader": {"csrf": "token-3", "authLevel": "SESSION_AUTHENTICATED", "success": True}
        }
    )

    with patch.object(
        client._session, "request", side_effect=[csrf_page, identify_resp, auth_resp]
    ):
        client.login("user@example.com", "password123")

    assert client._csrf == "token-3"


def test_login_raises_2fa_when_not_remembered() -> None:
    client = EmpowerClient()
    csrf_page = _mock_response(text="window.csrf='aaa-111-bbb'")
    identify_resp = _mock_response(
        json_data={"spHeader": {"csrf": "token-2", "authLevel": "USER_IDENTIFIED", "success": True}}
    )

    with (
        patch.object(client._session, "request", side_effect=[csrf_page, identify_resp]),
        pytest.raises(TwoFactorRequiredError),
    ):
        client.login("user@example.com", "password123")


def test_login_raises_auth_error_on_none_auth_level() -> None:
    client = EmpowerClient()
    csrf_page = _mock_response(text="window.csrf='aaa-111-bbb'")
    identify_resp = _mock_response(
        json_data={"spHeader": {"csrf": "token-2", "authLevel": "NONE", "success": True}}
    )

    with (
        patch.object(client._session, "request", side_effect=[csrf_page, identify_resp]),
        pytest.raises(EmpowerAuthError, match="rate-limited") as exc_info,
    ):
        client.login("user@example.com", "password123")
    # No reason given → plain EmpowerAuthError, so the stale-session retry still applies.
    assert type(exc_info.value) is EmpowerAuthError


# identifyUser rejections. Codes and messages for 113/207 are the ones quoted in
# issue #9; the surrounding payloads are reconstructed, not captured responses.


def _identify_error(header: dict[str, object]) -> EmpowerAuthError:
    """Run login() against an identifyUser spHeader and return the raised error."""
    client = EmpowerClient()
    csrf_page = _mock_response(text="window.csrf='aaa-111-bbb'")
    identify_resp = _mock_response(json_data={"spHeader": header})
    with (
        patch.object(client._session, "request", side_effect=[csrf_page, identify_resp]),
        pytest.raises(EmpowerAuthError) as exc_info,
    ):
        client.login("someone", "password123")
    return exc_info.value


def _rejected(header: dict[str, object]) -> LoginRejectedError:
    err = _identify_error(header)
    assert isinstance(err, LoginRejectedError)
    return err


@pytest.mark.parametrize(
    ("code", "message", "hint"),
    [
        (113, "Please use a valid email address.", "Accounts that sign in with a username"),
        (207, "Please enter a valid username.", "If this account signs in with a username"),
    ],
)
def test_login_rejection_username_codes(code: int, message: str, hint: str) -> None:
    error = {"code": code, "message": message}
    err = _rejected({"csrf": "token-2", "authLevel": "NONE", "success": False, "errors": [error]})
    assert err.errors == (error,)  # passed through as sent
    assert err.codes == (str(code),)
    assert str(err).startswith(f"Empower rejected the sign-in ({code}: {message}).")
    assert hint in str(err)
    assert "issues/9" in str(err)
    assert "rate-limited" not in str(err)


def test_login_rejection_other_code_has_no_username_hint() -> None:
    err = _rejected(
        {
            "csrf": "token-2",
            "authLevel": "NONE",
            "errors": [{"code": 910, "message": "Username not found."}],
        }
    )
    assert "910: Username not found." in str(err)
    assert "username instead of an email" not in str(err)


def test_login_rejection_carries_redirect_urls() -> None:
    err = _rejected(
        {
            "csrf": "token-2",
            "authLevel": "NONE",
            "errors": [{"code": 920, "message": "Your experience has moved."}],
            "loginURL": "https://login.example.test/",
            "destinationURL": "https://dest.example.test/",
        }
    )
    assert err.login_url == "https://login.example.test/"
    assert err.destination_url == "https://dest.example.test/"
    assert "https://login.example.test/" in str(err)
    assert "https://dest.example.test/" in str(err)


def test_login_urls_without_errors_are_not_a_rejection() -> None:
    """A URL alone isn't a reason; it stays a plain error but keeps the URL in the text."""
    err = _identify_error({"csrf": "token-2", "authLevel": "NONE", "loginURL": "https://x.test/"})
    assert type(err) is EmpowerAuthError
    assert "rate-limited" in str(err)
    assert "https://x.test/" in str(err)


def test_login_rejection_with_missing_csrf() -> None:
    err = _rejected(
        {"authLevel": "NONE", "errors": [{"code": 113, "message": "Please use a valid email."}]}
    )
    assert err.codes == ("113",)
    assert "no CSRF" not in str(err)


@pytest.mark.parametrize(
    "error",
    [
        {"code": 201, "message": "Session not authenticated."},
        {"code": 999, "message": "Session expired"},
        # Verbatim wording from issue #4.
        {"message": "Session is no longer valid. Please return to the login screen."},
    ],
)
def test_login_session_error_is_not_a_rejection(error: dict[str, object]) -> None:
    """Stale-cookie errors stay plain EmpowerAuthError so the stale-session retry applies,
    and the message still carries what Empower said."""
    err = _identify_error({"csrf": "token-2", "authLevel": "NONE", "errors": [error]})
    assert type(err) is EmpowerAuthError
    assert f"Empower said: {_describe(error)}" in str(err)


def _describe(error: dict[str, object]) -> str:
    code, message = error.get("code"), error.get("message")
    return f"{code}: {message}" if code is not None else str(message)


def test_is_auth_error_matches_issue_4_wording() -> None:
    from personalcapital2.client import _is_auth_error

    assert _is_auth_error({}, "Session is no longer valid. Please return to the login screen.")


@pytest.mark.parametrize(
    ("errors", "expected"),
    [
        ([{"message": "No code given."}], "(No code given.)"),
        ([{"code": 5}], "(code 5)"),
        ([None, {}, {"code": 7, "message": "x"}], "(7: x)"),
    ],
)
def test_login_rejection_tolerates_odd_error_entries(errors: object, expected: str) -> None:
    err = _rejected({"csrf": "token-2", "authLevel": "NONE", "errors": errors})
    assert expected in str(err)
    assert "None" not in str(err)


@pytest.mark.parametrize("errors", ["oops", [{}], [{"code": None, "message": ""}]])
def test_login_errors_without_content_fall_back_to_generic_message(errors: object) -> None:
    err = _identify_error({"csrf": "token-2", "authLevel": "NONE", "errors": errors})
    assert type(err) is EmpowerAuthError
    assert "rate-limited" in str(err)
    assert "Empower said" not in str(err)


def test_login_rejected_error_pickles() -> None:
    err = LoginRejectedError(
        "Empower rejected the sign-in (113: x).",
        errors=({"code": 113},),
        login_url="https://x.test/",
    )
    restored = pickle.loads(pickle.dumps(err))  # noqa: S301 — round-trips our own object
    assert isinstance(restored, LoginRejectedError)
    assert str(restored) == str(err)
    assert restored.errors == err.errors
    assert restored.login_url == "https://x.test/"


def test_authenticate_rejection_keeps_session_and_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: a rejection at identifyUser with a cached session present must not
    delete the session file or call identifyUser a second time."""
    from personalcapital2.auth import authenticate

    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "version": 2,
                "csrf": "cached-csrf",
                "cookies": [{"name": "JSESSIONID", "value": "x", "domain": "pc-api.test"}],
            }
        )
    )
    session_path.chmod(0o600)
    monkeypatch.setenv("EMPOWER_EMAIL", "someone")
    monkeypatch.setenv("EMPOWER_PASSWORD", "password123")

    csrf_page = _mock_response(text="window.csrf='aaa-111-bbb'")
    identify_resp = _mock_response(
        json_data={
            "spHeader": {
                "csrf": "token-2",
                "authLevel": "NONE",
                "errors": [{"code": 113, "message": "Please use a valid email address."}],
            }
        }
    )
    with (
        patch("requests.Session.request", side_effect=[csrf_page, identify_resp]) as request,
        pytest.raises(LoginRejectedError),
    ):
        authenticate(session_path)

    assert session_path.exists()
    identify_calls = [c for c in request.call_args_list if "identifyUser" in str(c)]
    assert len(identify_calls) == 1


def test_authenticate_session_error_at_identify_still_clears_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: a session error (201) at identifyUser with a cached session present is
    a stale session, so the file is deleted and the login retried once."""
    from personalcapital2.auth import authenticate

    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "version": 2,
                "csrf": "cached-csrf",
                "cookies": [{"name": "JSESSIONID", "value": "x", "domain": "pc-api.test"}],
            }
        )
    )
    session_path.chmod(0o600)
    monkeypatch.setenv("EMPOWER_EMAIL", "someone")
    monkeypatch.setenv("EMPOWER_PASSWORD", "password123")

    def identify(header: dict[str, object]) -> MagicMock:
        return _mock_response(json_data={"spHeader": header})

    stale: dict[str, object] = {
        "csrf": "token-2",
        "authLevel": "NONE",
        "errors": [{"code": 201, "message": "Session not authenticated."}],
    }
    # The retry gets a rejection, which ends the test with a distinct error type.
    rejected: dict[str, object] = {
        "csrf": "token-3",
        "authLevel": "NONE",
        "errors": [{"code": 910}],
    }
    page = "window.csrf='aaa-111-bbb'"
    responses = [
        _mock_response(text=page),
        identify(stale),
        _mock_response(text=page),
        identify(rejected),
    ]
    with (
        patch("requests.Session.request", side_effect=responses) as request,
        pytest.raises(LoginRejectedError),
    ):
        authenticate(session_path)

    assert not session_path.exists()
    identify_calls = [c for c in request.call_args_list if "identifyUser" in str(c)]
    assert len(identify_calls) == 2


def _password_error(errors: list[dict[str, object]]) -> EmpowerAuthError:
    """Run login() to a rejected authenticatePassword and return the raised error."""
    client = EmpowerClient()
    responses = [
        _mock_response(text="window.csrf='aaa-111-bbb'"),
        _mock_response(json_data={"spHeader": {"csrf": "t2", "authLevel": "USER_REMEMBERED"}}),
        _mock_response(json_data={"spHeader": {"success": False, "errors": errors}}),
    ]
    with (
        patch.object(client._session, "request", side_effect=responses),
        pytest.raises(EmpowerAuthError) as exc_info,
    ):
        client.login("user@example.com", "wrong")
    return exc_info.value


def test_login_wrong_password_is_a_rejection() -> None:
    # Message as Empower sent it in a live wrong-password login.
    err = _password_error([{"message": "Incorrect password entered."}])
    assert isinstance(err, LoginRejectedError)
    assert str(err) == "Empower rejected the sign-in (Incorrect password entered.)."


def test_login_session_error_at_password_step_stays_retryable() -> None:
    """Issue #4: stale cookies surface at authenticatePassword; that must stay retryable."""
    err = _password_error(
        [{"message": "Session is no longer valid. Please return to the login screen."}]
    )
    assert type(err) is EmpowerAuthError


def test_authenticate_wrong_password_keeps_session_and_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end, as seen live: remembered device + wrong password must not delete the
    session file (losing the remembered device) or retry (a second failed attempt + SMS)."""
    from personalcapital2.auth import authenticate

    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "version": 2,
                "csrf": "cached-csrf",
                "cookies": [{"name": "JSESSIONID", "value": "x", "domain": "pc-api.test"}],
            }
        )
    )
    session_path.chmod(0o600)
    monkeypatch.setenv("EMPOWER_EMAIL", "user@example.com")
    monkeypatch.setenv("EMPOWER_PASSWORD", "wrong")

    responses = [
        _mock_response(text="window.csrf='aaa-111-bbb'"),
        _mock_response(json_data={"spHeader": {"csrf": "t2", "authLevel": "USER_REMEMBERED"}}),
        _mock_response(
            json_data={
                "spHeader": {
                    "success": False,
                    "errors": [{"message": "Incorrect password entered."}],
                }
            }
        ),
    ]
    with (
        patch("requests.Session.request", side_effect=responses) as request,
        pytest.raises(LoginRejectedError),
    ):
        authenticate(session_path)

    assert session_path.exists()
    password_calls = [c for c in request.call_args_list if "authenticatePassword" in str(c)]
    assert len(password_calls) == 1


def test_login_raises_on_missing_csrf() -> None:
    client = EmpowerClient()
    csrf_page = _mock_response(text="<html>no csrf</html>")

    with (
        patch.object(client._session, "request", return_value=csrf_page),
        pytest.raises(EmpowerAuthError, match="CSRF"),
    ):
        client.login("user@example.com", "password123")


# --- Password auth (authLevel validation) ---


def test_authenticate_password_raises_on_non_authenticated_level() -> None:
    """Stale session returning USER_REMEMBERED should trigger 2FA flow."""
    client = EmpowerClient()
    client._csrf = "test-csrf"

    auth_resp = _mock_response(
        json_data={"spHeader": {"success": True, "authLevel": "USER_REMEMBERED", "csrf": "new"}}
    )

    with (
        patch.object(client._session, "request", return_value=auth_resp),
        pytest.raises(TwoFactorRequiredError),
    ):
        client._authenticate_password("password123")


def test_authenticate_password_raises_on_mfa_required() -> None:
    """MFA_REQUIRED after password auth should still raise TwoFactorRequiredError."""
    client = EmpowerClient()
    client._csrf = "test-csrf"

    auth_resp = _mock_response(
        json_data={"spHeader": {"success": True, "authLevel": "MFA_REQUIRED", "csrf": "new"}}
    )

    with (
        patch.object(client._session, "request", return_value=auth_resp),
        pytest.raises(TwoFactorRequiredError),
    ):
        client._authenticate_password("password123")


def test_authenticate_password_success() -> None:
    """SESSION_AUTHENTICATED should succeed and update CSRF."""
    client = EmpowerClient()
    client._csrf = "old-csrf"

    auth_resp = _mock_response(
        json_data={
            "spHeader": {"success": True, "authLevel": "SESSION_AUTHENTICATED", "csrf": "new-csrf"}
        }
    )

    with patch.object(client._session, "request", return_value=auth_resp):
        client._authenticate_password("password123")

    assert client._csrf == "new-csrf"


# --- Fetch ---


def test_fetch_returns_data() -> None:
    client = EmpowerClient()
    client._csrf = "my-csrf"
    api_resp = _mock_response(
        json_data={"spHeader": {"success": True, "csrf": "rotated"}, "spData": {"accounts": []}}
    )

    with patch.object(client._session, "request", return_value=api_resp):
        result = client.fetch("/newaccount/getAccounts2")

    assert result["spData"]["accounts"] == []
    assert client._csrf == "rotated"


def test_fetch_raises_on_api_failure() -> None:
    client = EmpowerClient()
    client._csrf = "my-csrf"
    api_resp = _mock_response(
        json_data={
            "spHeader": {"success": False, "errors": [{"message": "Rate limited"}]},
        }
    )

    with (
        patch.object(client._session, "request", return_value=api_resp),
        pytest.raises(EmpowerAPIError, match="Rate limited"),
    ):
        client.fetch("/newaccount/getAccounts2")


def test_fetch_raises_auth_error_for_expired_session() -> None:
    """Auth-related API errors should raise EmpowerAuthError, not EmpowerAPIError."""
    client = EmpowerClient()
    client._csrf = "my-csrf"

    for message in ("Session expired", "Session not authenticated", "Session no longer valid"):
        api_resp = _mock_response(
            json_data={
                "spHeader": {"success": False, "errors": [{"message": message}]},
            }
        )
        with (
            patch.object(client._session, "request", return_value=api_resp),
            pytest.raises(EmpowerAuthError, match=message),
        ):
            client.fetch("/test/endpoint")


def test_fetch_raises_auth_error_for_none_auth_level() -> None:
    """authLevel=NONE should raise EmpowerAuthError regardless of message."""
    client = EmpowerClient()
    client._csrf = "my-csrf"
    api_resp = _mock_response(
        json_data={
            "spHeader": {
                "success": False,
                "authLevel": "NONE",
                "errors": [{"message": "Something unexpected"}],
            },
        }
    )

    with (
        patch.object(client._session, "request", return_value=api_resp),
        pytest.raises(EmpowerAuthError, match="Something unexpected"),
    ):
        client.fetch("/test/endpoint")


def test_fetch_raises_on_non_json_response() -> None:
    client = EmpowerClient()
    client._csrf = "my-csrf"
    html_resp = _mock_response(text="<html>Login page</html>")

    with (
        patch.object(client._session, "request", return_value=html_resp),
        pytest.raises(EmpowerAPIError, match="expected JSON"),
    ):
        client.fetch("/newaccount/getAccounts2")


# --- Session persistence ---


def test_save_and_load_session(tmp_path: Path) -> None:
    session_path = tmp_path / "session.json"
    client = EmpowerClient(session_path=session_path)
    client._csrf = "saved-csrf"

    client.save_session()

    assert session_path.exists()
    assert session_path.stat().st_mode & 0o777 == 0o600

    # Load into a new client — constructor auto-loads session
    client2 = EmpowerClient(session_path=session_path)
    assert client2._csrf == "saved-csrf"


def test_load_session_rejects_insecure_permissions(tmp_path: Path) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"csrf": "leaked", "cookies": {}}))
    session_path.chmod(0o644)

    # Constructor auto-loads, but should skip insecure file
    client = EmpowerClient(session_path=session_path)
    assert client._csrf == ""  # Should not have loaded


def test_load_session_handles_corrupt_json(tmp_path: Path) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text("not json{{{")
    session_path.chmod(0o600)

    # Constructor auto-loads, but should handle corrupt JSON gracefully
    client = EmpowerClient(session_path=session_path)
    assert client._csrf == ""


def test_load_session_warns_on_empty_object(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An empty `{}` session file should warn instead of silently producing
    an unauthenticated client."""
    session_path = tmp_path / "session.json"
    session_path.write_text("{}")
    session_path.chmod(0o600)

    with caplog.at_level("WARNING", logger="personalcapital2.client"):
        client = EmpowerClient(session_path=session_path)

    assert client._csrf == ""
    assert any("empty or malformed" in rec.message for rec in caplog.records)


def test_load_session_warns_on_missing_keys(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A session file with explicitly empty csrf/cookies should also warn."""
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"csrf": "", "cookies": {}}))
    session_path.chmod(0o600)

    with caplog.at_level("WARNING", logger="personalcapital2.client"):
        client = EmpowerClient(session_path=session_path)

    assert client._csrf == ""
    assert any("empty or malformed" in rec.message for rec in caplog.records)


# --- 2FA flow ---


def test_2fa_sms_flow() -> None:
    client = EmpowerClient()
    client._csrf = "pre-2fa"

    challenge_resp = _mock_response(
        json_data={"spHeader": {"success": True, "csrf": "post-challenge"}}
    )
    verify_resp = _mock_response(json_data={"spHeader": {"success": True, "csrf": "post-verify"}})
    auth_resp = _mock_response(
        json_data={
            "spHeader": {"success": True, "authLevel": "SESSION_AUTHENTICATED", "csrf": "final"}
        }
    )

    side_effects = [challenge_resp, verify_resp, auth_resp]
    with patch.object(client._session, "request", side_effect=side_effects):
        client.send_2fa_challenge(TwoFactorMode.SMS)
        client.verify_2fa_and_login(TwoFactorMode.SMS, "123456", "password")

    assert client._csrf == "final"


def test_2fa_challenge_failure_raises() -> None:
    client = EmpowerClient()
    client._csrf = "pre-2fa"
    challenge_resp = _mock_response(
        json_data={
            "spHeader": {"success": False, "errors": [{"message": "Session no longer valid"}]}
        }
    )

    with (
        patch.object(client._session, "request", return_value=challenge_resp),
        pytest.raises(EmpowerAuthError, match="Session no longer valid"),
    ):
        client.send_2fa_challenge(TwoFactorMode.SMS)


# --- User-Agent configurability ---


def test_default_user_agent() -> None:
    client = EmpowerClient()
    assert client._session.headers["User-Agent"] == DEFAULT_USER_AGENT


def test_custom_user_agent() -> None:
    client = EmpowerClient(user_agent="CustomBot/1.0")
    assert client._session.headers["User-Agent"] == "CustomBot/1.0"


# --- Auth error detection ---


def test_is_auth_error_known_messages() -> None:
    """Known auth error messages should be detected regardless of case."""
    from personalcapital2.client import _is_auth_error

    header: dict[str, object] = {"success": False}
    assert _is_auth_error(header, "Session expired") is True
    assert _is_auth_error(header, "Session not authenticated") is True
    assert _is_auth_error(header, "Session no longer valid") is True
    assert _is_auth_error(header, "session expired") is True  # case insensitive
    # API appends trailing punctuation inconsistently
    assert _is_auth_error(header, "Session not authenticated.") is True
    assert _is_auth_error(header, "Session expired.") is True


def test_is_auth_error_auth_level() -> None:
    """authLevel=NONE or MFA_REQUIRED should be detected as auth errors."""
    from personalcapital2.client import _is_auth_error

    assert _is_auth_error({"authLevel": "NONE"}, "Unknown error") is True
    assert _is_auth_error({"authLevel": "MFA_REQUIRED"}, "Unknown error") is True


def test_is_auth_error_non_auth() -> None:
    """Non-auth errors should not be detected as auth errors."""
    from personalcapital2.client import _is_auth_error

    assert _is_auth_error({"success": False}, "Rate limited") is False
    assert _is_auth_error({"authLevel": "SESSION_AUTHENTICATED"}, "Some error") is False


# --- _request transport-error wrapping ---


def test_request_wraps_connection_error() -> None:
    """ConnectionError from requests should become EmpowerNetworkError."""
    client = EmpowerClient()
    with (
        patch.object(
            client._session, "request", side_effect=requests.ConnectionError("DNS lookup failed")
        ),
        pytest.raises(EmpowerNetworkError, match="DNS lookup failed"),
    ):
        client._request("GET", "https://example.invalid/")


def test_request_wraps_timeout() -> None:
    """Timeout from requests should become EmpowerNetworkError."""
    client = EmpowerClient()
    with (
        patch.object(client._session, "request", side_effect=requests.Timeout("read timed out")),
        pytest.raises(EmpowerNetworkError, match="read timed out"),
    ):
        client._request("POST", "https://example.invalid/")


def test_request_lets_http_error_propagate() -> None:
    """HTTPError (raised by raise_for_status, never by request itself) must NOT
    be converted — _extract_csrf and _identify_user have bespoke status handling."""
    client = EmpowerClient()
    with (
        patch.object(
            client._session, "request", side_effect=requests.HTTPError("500 Server Error")
        ),
        pytest.raises(requests.HTTPError),
    ):
        client._request("GET", "https://example.invalid/")


# --- Session persistence (cookie round-trip / shadowing) ---


def test_session_round_trip_preserves_cookie_attributes(tmp_path: Path) -> None:
    """save_session/load_session preserve a cookie's domain and path, so a
    reloaded cookie keys identically to the one the server set."""
    session_path = tmp_path / "session.json"
    client = EmpowerClient(session_path=session_path)
    client._csrf = "csrf-1"
    client._session.cookies.set(  # pyright: ignore[reportUnknownMemberType]
        "JSESSIONID", "abc", domain=".empower-retirement.com", path="/"
    )
    client.save_session()

    fresh = EmpowerClient(session_path=session_path)  # loads in __init__
    loaded = [c for c in fresh._session.cookies if c.name == "JSESSIONID"]
    assert len(loaded) == 1
    assert loaded[0].value == "abc"
    assert loaded[0].domain == ".empower-retirement.com"
    assert loaded[0].path == "/"
    assert fresh._csrf == "csrf-1"
    assert fresh.has_loaded_session is True


def test_reloaded_cookie_is_overwritten_not_shadowed(tmp_path: Path) -> None:
    """Regression for the 'Session not authenticated' bug: a reloaded cookie
    must be overwritten by a fresh same-name cookie on the same domain, not
    coexist with it. The old domain-less format kept both and the stale one
    shadowed the fresh one, so the server rejected the data call."""
    session_path = tmp_path / "session.json"
    client = EmpowerClient(session_path=session_path)
    client._session.cookies.set(  # pyright: ignore[reportUnknownMemberType]
        "JSESSIONID", "stale", domain=".empower-retirement.com", path="/"
    )
    client.save_session()

    fresh = EmpowerClient(session_path=session_path)
    # Server issues a fresh cookie of the same name/domain on the next login.
    fresh._session.cookies.set(  # pyright: ignore[reportUnknownMemberType]
        "JSESSIONID", "new", domain=".empower-retirement.com", path="/"
    )
    values = [c.value for c in fresh._session.cookies if c.name == "JSESSIONID"]
    assert values == ["new"], f"expected only the fresh cookie, got {values}"


def test_old_format_session_file_is_ignored(tmp_path: Path) -> None:
    """A pre-0.4.0 {name: value} dict session file is ignored (triggers
    re-auth) rather than resurrecting domain-less cookies that would shadow
    fresh ones."""
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"csrf": "x", "cookies": {"JSESSIONID": "stale"}}))
    session_path.chmod(0o600)

    client = EmpowerClient(session_path=session_path)
    assert client.has_loaded_session is False
    assert list(client._session.cookies) == []
