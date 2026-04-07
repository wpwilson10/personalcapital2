"""Tests for the Empower API client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from personalcapital2.client import DEFAULT_USER_AGENT, EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError, TwoFactorRequiredError
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
    with patch.object(client._session, "get", return_value=_mock_response(text=html)):
        csrf = client._extract_csrf()
    assert csrf == "abc-123-def"


def test_extract_csrf_returns_none_on_missing_pattern() -> None:
    client = EmpowerClient()
    html = "<html><body>No CSRF here</body></html>"
    with patch.object(client._session, "get", return_value=_mock_response(text=html)):
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

    with (
        patch.object(client._session, "get", return_value=csrf_page),
        patch.object(client._session, "post", side_effect=[identify_resp, auth_resp]),
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
        patch.object(client._session, "get", return_value=csrf_page),
        patch.object(client._session, "post", return_value=identify_resp),
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
        patch.object(client._session, "get", return_value=csrf_page),
        patch.object(client._session, "post", return_value=identify_resp),
        pytest.raises(EmpowerAuthError, match="rate-limited"),
    ):
        client.login("user@example.com", "password123")


def test_login_raises_on_missing_csrf() -> None:
    client = EmpowerClient()
    csrf_page = _mock_response(text="<html>no csrf</html>")

    with (
        patch.object(client._session, "get", return_value=csrf_page),
        pytest.raises(EmpowerAuthError, match="CSRF"),
    ):
        client.login("user@example.com", "password123")


# --- Fetch ---


def test_fetch_returns_data() -> None:
    client = EmpowerClient()
    client._csrf = "my-csrf"
    api_resp = _mock_response(
        json_data={"spHeader": {"success": True, "csrf": "rotated"}, "spData": {"accounts": []}}
    )

    with patch.object(client._session, "post", return_value=api_resp):
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
        patch.object(client._session, "post", return_value=api_resp),
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
            patch.object(client._session, "post", return_value=api_resp),
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
        patch.object(client._session, "post", return_value=api_resp),
        pytest.raises(EmpowerAuthError, match="Something unexpected"),
    ):
        client.fetch("/test/endpoint")


def test_fetch_raises_on_non_json_response() -> None:
    client = EmpowerClient()
    client._csrf = "my-csrf"
    html_resp = _mock_response(text="<html>Login page</html>")

    with (
        patch.object(client._session, "post", return_value=html_resp),
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


# --- 2FA flow ---


def test_2fa_sms_flow() -> None:
    client = EmpowerClient()
    client._csrf = "pre-2fa"

    challenge_resp = _mock_response(
        json_data={"spHeader": {"success": True, "csrf": "post-challenge"}}
    )
    verify_resp = _mock_response(json_data={"spHeader": {"success": True, "csrf": "post-verify"}})
    auth_resp = _mock_response(json_data={"spHeader": {"success": True, "csrf": "final"}})

    side_effects = [challenge_resp, verify_resp, auth_resp]
    with patch.object(client._session, "post", side_effect=side_effects):
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
        patch.object(client._session, "post", return_value=challenge_resp),
        pytest.raises(EmpowerAuthError, match="Session no longer valid"),
    ):
        client.send_2fa_challenge(TwoFactorMode.EMAIL)


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
