"""Client for Empower's (Personal Capital) internal API.

Vendored and rewritten from community libraries:
- haochi/personalcapital (MIT) — original reverse-engineering
- traviscook21/personalcapital (MIT) — URL migration fix (Dec 2025)

Changes from upstream:
- Type hints throughout, pyright strict compatible
- JSON session persistence instead of pickle (no arbitrary code execution risk)
- Fixed silent exception bugs (LoginFailedException created but never raised)
- Request timeouts to prevent hangs
- File permissions on session data (chmod 600)
- Cleaned up public API surface
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError, TwoFactorRequiredError
from personalcapital2.models import (
    AccountBalancesResult,
    AccountsResult,
    HoldingsResult,
    NetWorthResult,
    PerformanceResult,
    PortfolioSnapshot,
    QuotesResult,
    SpendingResult,
    TransactionsResult,
    account_balance_from_dict,
    account_from_dict,
    account_performance_summary_from_dict,
    accounts_summary_from_dict,
    benchmark_performance_from_dict,
    category_from_dict,
    holding_from_dict,
    investment_performance_from_dict,
    market_quote_from_dict,
    net_worth_entry_from_dict,
    net_worth_summary_from_dict,
    portfolio_snapshot_from_dict,
    portfolio_vs_benchmark_from_dict,
    spending_summary_from_dict,
    transaction_from_dict,
    transactions_summary_from_dict,
)
from personalcapital2.parsers import (
    extract_categories,
    parse_account_balances,
    parse_account_summaries,
    parse_accounts,
    parse_accounts_summary,
    parse_benchmark_performance,
    parse_holdings,
    parse_holdings_total,
    parse_investment_performance,
    parse_market_quotes,
    parse_net_worth,
    parse_net_worth_summary,
    parse_portfolio_snapshot,
    parse_portfolio_vs_benchmark,
    parse_spending,
    parse_transactions,
    parse_transactions_summary,
)
from personalcapital2.types import TwoFactorMode

log = logging.getLogger(__name__)

BASE_URL = "https://pc-api.empower-retirement.com"
FRONTEND_URL = "https://participant.empower-retirement.com"
API_URL = f"{BASE_URL}/api"
LOGIN_PAGE = f"{BASE_URL}/page/login/goHome"

CSRF_PATTERN = re.compile(r"window\.csrf\s*=\s*'([a-f0-9-]+)'")

DEFAULT_SESSION_DIR = Path("~/.config/personalcapital2").expanduser()
_env_session = os.environ.get("PC2_SESSION_PATH")
DEFAULT_SESSION_PATH = (
    Path(_env_session).expanduser() if _env_session else DEFAULT_SESSION_DIR / "session.json"
)

_AUTH_ERROR_PATTERNS: tuple[str, ...] = (
    "session not authenticated",
    "session expired",
    "session no longer valid",
)

_AUTH_FAILURE_LEVELS: frozenset[str] = frozenset({"NONE", "MFA_REQUIRED"})


def _is_auth_error(sp_header: dict[str, Any], error_message: str) -> bool:
    """Detect whether an API error indicates an authentication failure.

    Checks the structured ``authLevel`` field first (most reliable), then
    falls back to substring matching against known error message patterns.
    Uses substring matching because the API appends trailing punctuation
    inconsistently (e.g. "Session not authenticated." vs "Session not authenticated").
    """
    auth_level = sp_header.get("authLevel")
    if isinstance(auth_level, str) and auth_level in _AUTH_FAILURE_LEVELS:
        return True
    msg = error_message.lower()
    return any(pattern in msg for pattern in _AUTH_ERROR_PATTERNS)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class EmpowerClient:
    """Client for Empower's internal REST API.

    Usage:
        client = EmpowerClient()
        client.login("email", "password")  # may raise TwoFactorRequired
        data = client.fetch("/newaccount/getAccounts2")
    """

    def __init__(
        self,
        session_path: Path | None = None,
        *,
        timeout: int = 30,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._session = requests.Session()
        self._timeout = timeout

        # Retry transient HTTP errors with exponential backoff.
        # POST is included because Empower uses POST for all endpoints,
        # including read-only data queries. The only non-idempotent POSTs
        # are 2FA challenge endpoints (SMS/email), but retries are limited
        # to server errors (5xx/429) where the original request likely
        # failed before any side effects.
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))

        # The frontend lives on participant.empower-retirement.com and makes
        # cross-origin requests to pc-api.empower-retirement.com. The API
        # checks Origin/Referer and returns HTML instead of JSON if they
        # don't match the expected frontend domain.
        self._session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Origin": FRONTEND_URL,
                "Referer": f"{FRONTEND_URL}/",
            }
        )
        self._csrf = ""
        self._session_path = session_path
        if session_path is not None:
            self.load_session()

    # --- Authentication ---

    def login(self, username: str, password: str) -> None:
        """Authenticate with Empower.

        Raises:
            TwoFactorRequired: if 2FA is needed before password auth.
            EmpowerAuthError: if login fails for any other reason.
        """
        if self._session_path:
            self.load_session()

        csrf = self._extract_csrf()
        if csrf is None:
            raise EmpowerAuthError("Failed to extract CSRF token from login page")

        csrf, auth_level = self._identify_user(username, csrf)
        if csrf is None or auth_level is None:
            raise EmpowerAuthError("Failed to identify user — no CSRF or auth level returned")

        self._csrf = csrf

        if auth_level == "NONE":
            raise EmpowerAuthError(
                "identifyUser returned authLevel=NONE — account may be rate-limited "
                "or credentials are invalid. Wait a few minutes and retry."
            )

        if auth_level not in ("USER_REMEMBERED", "SESSION_AUTHENTICATED"):
            raise TwoFactorRequiredError()

        self._authenticate_password(password)

    def send_2fa_challenge(self, mode: TwoFactorMode) -> None:
        """Send a 2FA challenge (SMS or email) without completing the flow."""
        self._send_2fa_challenge(mode)

    def verify_2fa_and_login(self, mode: TwoFactorMode, code: str, password: str) -> None:
        """Verify 2FA code and authenticate with password."""
        self._verify_2fa_code(mode, code)
        self._authenticate_password(password)

    # --- Convenience Methods ---

    def get_accounts(self) -> AccountsResult:
        """Fetch all linked accounts with aggregate summary."""
        response = self.fetch("/newaccount/getAccounts2")
        rows = parse_accounts(response)
        summary_dict = parse_accounts_summary(response)
        return AccountsResult(
            accounts=tuple(account_from_dict(r) for r in rows),
            summary=accounts_summary_from_dict(summary_dict),
        )

    def get_transactions(self, start: date, end: date) -> TransactionsResult:
        """Fetch transactions within a date range with categories and summary."""
        response = self.fetch(
            "/transaction/getUserTransactions",
            {
                "sort_cols": "transactionTime",
                "sort_rev": "true",
                "page": "0",
                "rows_per_page": "-1",
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "component": "DATAGRID",
            },
        )
        txn_rows = parse_transactions(response)
        cat_rows = extract_categories(response)
        summary_dict = parse_transactions_summary(response)
        return TransactionsResult(
            transactions=tuple(transaction_from_dict(r) for r in txn_rows),
            categories=tuple(category_from_dict(r) for r in cat_rows),
            summary=transactions_summary_from_dict(summary_dict),
        )

    def get_holdings(self) -> HoldingsResult:
        """Fetch current investment holdings with total value."""
        response = self.fetch(
            "/invest/getHoldings",
            {
                "userAccountIds": "[]",
                "classificationStyles": '["none"]',
                "consolidateMultipleAccounts": "false",
            },
        )
        today = date.today().isoformat()
        rows = parse_holdings(response, snapshot_date=today)
        total = parse_holdings_total(response)
        return HoldingsResult(
            holdings=tuple(holding_from_dict(r) for r in rows),
            total_value=total,
        )

    def get_net_worth(self, start: date, end: date) -> NetWorthResult:
        """Fetch daily net worth history with change summary."""
        response = self.fetch(
            "/account/getHistories",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "interval": "DAY",
                "types": '["networth"]',
                "includeNetworthCategoryDetails": "true",
            },
        )
        rows = parse_net_worth(response)
        summary_dict = parse_net_worth_summary(response)
        return NetWorthResult(
            entries=tuple(net_worth_entry_from_dict(r) for r in rows),
            summary=net_worth_summary_from_dict(summary_dict),
        )

    def get_account_balances(self, start: date, end: date) -> AccountBalancesResult:
        """Fetch daily account balance history for a date range."""
        response = self.fetch(
            "/account/getHistories",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "interval": "DAY",
                "types": '["balances"]',
                "includeNetworthCategoryDetails": "true",
            },
        )
        rows = parse_account_balances(response)
        return AccountBalancesResult(
            balances=tuple(account_balance_from_dict(r) for r in rows),
        )

    def get_performance(self, start: date, end: date, account_ids: list[int]) -> PerformanceResult:
        """Fetch investment performance, benchmarks, and account summaries.

        Args:
            start: Start date for the performance window.
            end: End date for the performance window.
            account_ids: List of investment account userAccountIds. Use
                get_holdings() to discover these — get_accounts() may not
                list all accounts that have holdings.
        """
        response = self.fetch(
            "/account/getPerformanceHistories",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "interval": "DAY",
                "requireBenchmark": "true",
                "userAccountIds": json.dumps(account_ids),
            },
        )
        inv_rows = parse_investment_performance(response)
        bench_rows = parse_benchmark_performance(response)
        summary_rows = parse_account_summaries(response)
        return PerformanceResult(
            investments=tuple(investment_performance_from_dict(r) for r in inv_rows),
            benchmarks=tuple(benchmark_performance_from_dict(r) for r in bench_rows),
            account_summaries=tuple(account_performance_summary_from_dict(r) for r in summary_rows),
        )

    def get_quotes(self, start: date, end: date) -> QuotesResult:
        """Fetch portfolio vs benchmark history, snapshot, and market quotes."""
        response = self.fetch(
            "/invest/getQuotes",
            {
                "userAccountIds": "[]",
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "intervalType": "DAY",
                "includeHistory": "true",
                "includeYOUHistory": "true",
            },
        )
        pvb_rows = parse_portfolio_vs_benchmark(response)
        snapshot_dict = parse_portfolio_snapshot(response)
        quote_rows = parse_market_quotes(response)
        snapshot = (
            portfolio_snapshot_from_dict(snapshot_dict)
            if snapshot_dict
            else PortfolioSnapshot(last=Decimal(0), change=Decimal(0), percent_change=Decimal(0))
        )
        return QuotesResult(
            portfolio_vs_benchmark=tuple(portfolio_vs_benchmark_from_dict(r) for r in pvb_rows),
            snapshot=snapshot,
            market_quotes=tuple(market_quote_from_dict(r) for r in quote_rows),
        )

    _VALID_SPENDING_INTERVALS = frozenset({"MONTH", "WEEK", "YEAR"})

    def get_spending(self, start: date, end: date, interval: str = "MONTH") -> SpendingResult:
        """Fetch current spending summary.

        Note: the Empower API ignores the date range and interval parameters,
        always returning current-period spending for all three interval types
        (MONTH, WEEK, YEAR).

        Args:
            start: Start date (sent to API but not observed to filter results).
            end: End date (sent to API but not observed to filter results).
            interval: Interval type — MONTH, WEEK, or YEAR (sent to API but
                all three intervals are always returned).

        Raises:
            ValueError: If interval is not MONTH, WEEK, or YEAR.
        """
        if interval not in self._VALID_SPENDING_INTERVALS:
            raise ValueError(f"Invalid interval {interval!r} — must be one of: MONTH, WEEK, YEAR")
        response = self.fetch(
            "/account/getUserSpending",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "intervalType": interval,
            },
        )
        rows = parse_spending(response)
        return SpendingResult(
            intervals=tuple(spending_summary_from_dict(r) for r in rows),
        )

    # --- Data Fetching ---

    def fetch(self, endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch data from an API endpoint. Returns the parsed JSON response."""
        payload: dict[str, Any] = {
            "lastServerChangeId": "-1",
            "csrf": self._csrf,
            "apiClient": "WEB",
        }
        if data is not None:
            payload.update(data)

        response = self._session.post(
            f"{API_URL}{endpoint}",
            data=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()

        result = self._parse_json(response, endpoint)

        # Validate API-level success (HTTP 200 doesn't guarantee success)
        sp_header = result.get("spHeader", {})
        if sp_header.get("success") is False:
            errors = sp_header.get("errors", [])
            msg = errors[0].get("message", "Unknown API error") if errors else "Unknown API error"
            if _is_auth_error(sp_header, msg):
                raise EmpowerAuthError(f"{endpoint}: {msg}")
            raise EmpowerAPIError(f"{endpoint}: {msg}")

        # Update CSRF if rotated
        if "csrf" in sp_header:
            self._csrf = sp_header["csrf"]

        return result

    # --- Session Persistence ---

    def save_session(self, path: Path | None = None) -> None:
        """Save session cookies and CSRF token to a JSON file (chmod 600).

        Uses atomic write (write to temp file, then rename) to prevent
        corrupt or world-readable session files on crash.
        """
        target = path or self._session_path
        if target is None:
            raise ValueError("No session path configured")

        target.parent.mkdir(parents=True, exist_ok=True)

        cookies: dict[str, str] = requests.utils.dict_from_cookiejar(  # type: ignore[no-untyped-call] — requests.utils is untyped
            self._session.cookies
        )
        session_data: dict[str, str | dict[str, str]] = {
            "csrf": self._csrf,
            "cookies": cookies,
        }

        # Atomic write: write to temp file, chmod, then rename (POSIX atomic)
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(session_data))
            tmp.chmod(0o600)
            tmp.rename(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        log.info("Session saved to %s", target)

    def load_session(self) -> None:
        """Reload session (CSRF token + cookies) from disk.

        No-op if no session path is configured or the file doesn't exist.
        Rejects files with insecure permissions (group/world-readable).

        Useful for long-running processes (e.g. MCP servers) that need to
        pick up a fresh session after the user re-authenticates.
        """
        if self._session_path is None or not self._session_path.exists():
            return

        # Verify permissions before loading — reject world/group-readable session files
        file_mode = self._session_path.stat().st_mode
        if file_mode & 0o077:
            log.warning(
                "Session file %s has insecure permissions (%o) — skipping load. Run: chmod 600 %s",
                self._session_path,
                file_mode & 0o777,
                self._session_path,
            )
            return

        try:
            data = json.loads(self._session_path.read_text())
            self._csrf = data.get("csrf", "")
            cookies = data.get("cookies", {})
            self._session.cookies = requests.utils.cookiejar_from_dict(cookies)  # type: ignore[no-untyped-call] — requests.utils is untyped
            log.info("Loaded session from %s", self._session_path)
        except (json.JSONDecodeError, KeyError, ValueError, AttributeError) as err:
            log.warning("Could not load session: %s", err)

    # --- Private Methods ---

    def _parse_json(self, response: requests.Response, context: str) -> dict[str, Any]:
        """Parse JSON from a response, raising a clear error on non-JSON (e.g. HTML)."""
        try:
            raw: object = response.json()
        except json.JSONDecodeError as exc:
            body_preview = response.text[:200]
            raise EmpowerAPIError(
                f"{context}: expected JSON response, got: {body_preview}"
            ) from exc
        if not isinstance(raw, dict):
            raise EmpowerAPIError(f"{context}: expected JSON object, got {type(raw).__name__}")
        # response.json() returns Any; isinstance narrows to dict[Unknown, Unknown]
        # which pyright strict can't assign to dict[str, Any] without a cast
        result: dict[str, Any] = raw  # type: ignore[reportUnknownVariableType] — validated by isinstance above
        return result

    def _extract_csrf(self) -> str | None:
        """Fetch the login page and extract the CSRF token."""
        response = self._session.get(LOGIN_PAGE, timeout=self._timeout)
        match = CSRF_PATTERN.search(response.text)
        if match:
            return match.group(1)
        log.warning("CSRF pattern not found in login page response")
        return None

    def _identify_user(self, username: str, csrf: str) -> tuple[str | None, str | None]:
        """Send username to get a session CSRF token and auth level."""
        data = {
            "username": username,
            "csrf": csrf,
            "apiClient": "WEB",
            "bindDevice": "false",
            "skipLinkAccount": "false",
            "redirectTo": "",
            "skipFirstUse": "",
            "referrerId": "",
        }

        response = self._session.post(
            f"{API_URL}/login/identifyUser",
            data=data,
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            log.error("identifyUser returned HTTP %d", response.status_code)
            raise EmpowerAuthError(f"identifyUser failed with HTTP {response.status_code}")
        if response.status_code != 200:
            log.warning("identifyUser returned unexpected HTTP %d", response.status_code)
            return None, None

        result = self._parse_json(response, "identifyUser")
        header = result.get("spHeader", {})
        auth_level = header.get("authLevel")
        errors = header.get("errors", [])
        log.info(
            "identifyUser: authLevel=%s, success=%s, errors=%s, status=%s",
            auth_level,
            header.get("success"),
            errors,
            header.get("SP_HEADER_VERSION"),
        )
        return header.get("csrf"), auth_level

    def _authenticate_password(self, password: str) -> None:
        """Submit password. Raises on failure or if MFA is still required."""
        data = {
            "bindDevice": "true",
            "deviceName": "",
            "redirectTo": "",
            "skipFirstUse": "",
            "skipLinkAccount": "false",
            "referrerId": "",
            "passwd": password,
            "apiClient": "WEB",
            "csrf": self._csrf,
        }

        try:
            response = self._session.post(
                f"{API_URL}/credential/authenticatePassword",
                data=data,
                timeout=self._timeout,
            )
        finally:
            # Clear password from the dict so it doesn't appear in tracebacks
            data.pop("passwd", None)
        response.raise_for_status()

        result = self._parse_json(response, "authenticatePassword")
        header = result.get("spHeader", {})

        if header.get("success") is False:
            errors = header.get("errors", [])
            msg = errors[0].get("message", "Unknown error") if errors else "Unknown error"
            raise EmpowerAuthError(f"Password auth failed: {msg}")

        if header.get("authLevel") == "MFA_REQUIRED":
            raise TwoFactorRequiredError()

        # Update CSRF if the server rotated it
        if "csrf" in header:
            self._csrf = header["csrf"]

    def _send_2fa_challenge(self, mode: TwoFactorMode) -> None:
        """Request a 2FA code via SMS or email."""
        endpoints = {
            TwoFactorMode.SMS: "/credential/challengeSms",
            TwoFactorMode.EMAIL: "/credential/challengeEmail",
        }
        challenge_types = {
            TwoFactorMode.SMS: "challengeSMS",
            TwoFactorMode.EMAIL: "challengeEmail",
        }
        data = {
            "challengeReason": "DEVICE_AUTH",
            "challengeMethod": "OP",
            "challengeType": challenge_types[mode],
            "apiClient": "WEB",
            "bindDevice": "false",
            "csrf": self._csrf,
        }
        response = self._session.post(
            f"{API_URL}{endpoints[mode]}",
            data=data,
            timeout=self._timeout,
        )
        response.raise_for_status()

        result = self._parse_json(response, f"2FA challenge ({mode.value})")
        header = result.get("spHeader", {})
        if header.get("success") is False:
            errors = header.get("errors", [])
            log.warning(
                "2FA challenge response: authLevel=%s, errors=%s", header.get("authLevel"), errors
            )
            msg = (
                errors[0].get("message", "2FA challenge failed")
                if errors
                else "2FA challenge failed"
            )
            raise EmpowerAuthError(f"2FA challenge failed: {msg}")

        # Update CSRF if rotated during 2FA flow
        if "csrf" in header:
            self._csrf = header["csrf"]

    def _verify_2fa_code(self, mode: TwoFactorMode, code: str) -> None:
        """Submit the 2FA verification code."""
        endpoints = {
            TwoFactorMode.SMS: "/credential/authenticateSms",
            TwoFactorMode.EMAIL: "/credential/authenticateEmailByCode",
        }
        data = {
            "challengeReason": "DEVICE_AUTH",
            "challengeMethod": "OP",
            "apiClient": "WEB",
            "bindDevice": "false",
            "code": code,
            "csrf": self._csrf,
        }
        response = self._session.post(
            f"{API_URL}{endpoints[mode]}",
            data=data,
            timeout=self._timeout,
        )
        response.raise_for_status()

        result = self._parse_json(response, f"2FA verify ({mode.value})")
        header = result.get("spHeader", {})
        if header.get("success") is False:
            errors = header.get("errors", [])
            msg = (
                errors[0].get("message", "2FA verification failed")
                if errors
                else "2FA verification failed"
            )
            raise EmpowerAuthError(f"2FA verification failed: {msg}")

        # Update CSRF if rotated during 2FA flow
        if "csrf" in header:
            self._csrf = header["csrf"]
