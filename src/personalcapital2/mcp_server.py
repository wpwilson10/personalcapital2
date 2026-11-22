"""MCP tool server for Empower (Personal Capital) financial data.

Exposes EmpowerClient methods as MCP tools over stdio transport.
Requires the ``mcp`` optional extra: ``pip install "personalcapital2[mcp]"``

Usage:
    pc2 mcp              # start server (cold start OK — agent can bootstrap
                         # via start_authentication if no session is cached)

Client config (Claude Code / Claude Desktop):
    {
        "mcpServers": {
            "empower": {
                "type": "stdio",
                "command": "pc2",
                "args": ["mcp"],
                "env": {
                    "PC2_SESSION_PATH": "~/.config/personalcapital2/session.json",
                    "EMPOWER_EMAIL": "you@example.com",
                    "EMPOWER_PASSWORD": "..."
                }
            }
        }
    }

Errors: every tool failure raises ``ToolError``, so the client sees
``isError: true`` with the text ``Error executing tool <name>: <message>``.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from collections.abc import (
    AsyncIterator,  # noqa: TC003 — needed at runtime by SDK
)
from contextlib import asynccontextmanager
from datetime import date, timedelta
from functools import wraps
from importlib.metadata import version as _package_version
from pathlib import Path  # noqa: TC003 — needed at runtime by lifespan
from typing import TYPE_CHECKING, Any, Literal

import requests

if TYPE_CHECKING:
    from collections.abc import Callable
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from personalcapital2._serialization import serialize_result
from personalcapital2.auth import parse_2fa_mode_env
from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import (
    EmpowerAPIError,
    EmpowerAuthError,
    EmpowerNetworkError,
    LoginRejectedError,
    TwoFactorRequiredError,
)
from personalcapital2.types import TwoFactorMode

log = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = 50_000

# Room left for the ``truncated`` metadata when checking a cut against the cap
# (about 300 characters with two lists cut and both hints).
_META_RESERVE = 500

# A JSON object decoded from a serialized result. Values are whatever JSON holds
# (lists of row dicts, nested summaries, scalars), hence Any.
_Json = dict[str, Any]


@dataclasses.dataclass
class _AppContext:
    """Lifespan state shared across all tool invocations."""

    client: EmpowerClient
    session_path: Path
    pending_2fa_mode: TwoFactorMode | None = None
    # The client a 2FA challenge was sent from. complete_authentication verifies
    # against its in-memory cookies, so it is kept apart from ``client``, which
    # data tools reload from disk on every call.
    pending_client: EmpowerClient | None = None


def _get_client(ctx: Context[_AppContext]) -> EmpowerClient:
    """Extract the EmpowerClient from the MCP context.

    Reloads the session from disk on each call so the long-running server
    picks up fresh sessions after re-authentication — whether via
    ``pc2 login`` from another terminal or via ``start_authentication`` /
    ``complete_authentication`` MCP tools. That holds during a pending 2FA
    challenge too: the challenge lives on ``pending_client``, so an abandoned
    challenge never stops a terminal login from being picked up.
    """
    app_ctx: _AppContext = ctx.request_context.lifespan_context
    app_ctx.client.load_session()
    return app_ctx.client


def _has_credentials() -> bool:
    return bool(os.getenv("EMPOWER_EMAIL") and os.getenv("EMPOWER_PASSWORD"))


_TERMINAL_LOGIN = "Ask the user to run `pc2 login` in a terminal, then retry."


def _check_date_range(start_date: date, end_date: date) -> None:
    """Fail the tool call if start_date > end_date."""
    if start_date > end_date:
        raise ToolError(
            f"start_date ({start_date}) is after end_date ({end_date}). "
            "Swap them so start_date <= end_date."
        )


def _check_limit(limit: int) -> None:
    """Fail the tool call if limit < 1."""
    if limit < 1:
        raise ToolError("limit must be at least 1.")


def _get_max_chars() -> int:
    """Read max output characters from environment, falling back to default."""
    env = os.environ.get("PC2_MCP_MAX_CHARS")
    if env is not None:
        try:
            return int(env)
        except ValueError:
            log.warning("Invalid PC2_MCP_MAX_CHARS=%r, using default %d", env, _DEFAULT_MAX_CHARS)
    return _DEFAULT_MAX_CHARS


# --- Response rendering and truncation ---
#
# Truncation only selects rows; it never changes a value. Dated lists keep the
# newest whole days (so paging back with end_date never splits or repeats a
# day); undated lists keep their first rows. Summaries are never cut.


def _dump(data: _Json) -> str:
    """Compact JSON: agents don't need indentation, and it costs ~30% of the cap."""
    return json.dumps(data, separators=(",", ":"))


def _cut_dated(
    data: _Json,
    fields: tuple[str, ...],
    limit: int | None,
    max_chars: int,
    cuts: dict[str, dict[str, int]],
    start_date: date | None,
) -> tuple[str, str | None] | None:
    """Keep the newest whole days that fit.

    Returns ``(cutoff, next_end_date)``, or None if nothing was cut.
    ``next_end_date`` is None when every omitted row predates ``start_date``
    (Empower's baseline row), since there is no earlier page to fetch.

    One cutoff applies to every dated list in the response. The newest day is
    always kept whole, even when it alone exceeds ``limit`` or the cap.
    """
    full: dict[str, list[Any]] = {f: data[f] for f in fields if isinstance(data.get(f), list)}
    dates = sorted({row["date"] for rows in full.values() for row in rows}, reverse=True)
    if not dates:
        return None

    def keep_from(cutoff: str) -> None:
        for field, rows in full.items():
            data[field] = [row for row in rows if row["date"] >= cutoff]

    def fits() -> bool:
        if limit is not None and any(len(data[f]) > limit for f in full):
            return False
        return len(_dump(data)) + _META_RESERVE <= max_chars

    keep_from(dates[-1])
    if fits():
        return None

    # Binary search for the most days (newest first) that fit; at least one.
    lo, hi = 1, len(dates) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        keep_from(dates[mid - 1])
        if fits():
            lo = mid
        else:
            hi = mid - 1
    cutoff = dates[lo - 1]
    keep_from(cutoff)

    for field, rows in full.items():
        if len(data[field]) < len(rows):
            cuts[field] = {"showing": len(data[field]), "total": len(rows)}
    if not cuts:
        return None
    start = start_date.isoformat() if start_date is not None else ""
    more_in_range = any(start <= row["date"] < cutoff for rows in full.values() for row in rows)
    if not more_in_range:
        return cutoff, None
    return cutoff, (date.fromisoformat(cutoff) - timedelta(days=1)).isoformat()


def _cut_undated(
    data: _Json,
    fields: tuple[str, ...],
    limit: int | None,
    max_chars: int,
    cuts: dict[str, dict[str, int]],
) -> None:
    """Keep the first rows of undated lists: up to ``limit``, then to fit the cap."""
    present = [f for f in fields if isinstance(data.get(f), list)]
    totals = {f: len(data[f]) for f in present}
    if limit is not None:
        for field in present:
            data[field] = data[field][:limit]

    # Shrink the largest list first until the output fits.
    for field in sorted(present, key=lambda f: len(data[f]), reverse=True):
        if len(_dump(data)) + _META_RESERVE <= max_chars:
            break
        rows: list[Any] = data[field]
        lo, hi = 0, len(rows)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            data[field] = rows[:mid]
            if len(_dump(data)) + _META_RESERVE <= max_chars:
                lo = mid
            else:
                hi = mid - 1
        data[field] = rows[:lo]

    for field in present:
        if len(data[field]) < totals[field]:
            cuts[field] = {"showing": len(data[field]), "total": totals[field]}


def _render(
    result: object,
    *,
    dated: tuple[str, ...] = (),
    undated: tuple[str, ...] = (),
    limit: int | None = None,
    start_date: date | None = None,
) -> str:
    """Serialize a result for a tool response, truncating lists to fit.

    ``dated`` lists keep the newest whole days; ``undated`` lists keep their
    first rows. Any other field (summaries, categories) is always complete.
    When something is cut, a ``truncated`` object reports
    ``{field: {showing, total}}``, a ``hint``, and — for dated lists, when the
    omitted rows fall inside the requested range — ``next_end_date``.
    """
    data: _Json = json.loads(serialize_result(result))
    max_chars = _get_max_chars()
    cuts: dict[str, dict[str, int]] = {}

    dated_cut = _cut_dated(data, dated, limit, max_chars, cuts, start_date) if dated else None
    if undated:
        _cut_undated(data, undated, limit, max_chars, cuts)
    if not cuts:
        return _dump(data)

    truncated: _Json = dict(cuts)
    hints: list[str] = []
    if dated_cut is not None:
        cutoff, next_end = dated_cut
        if next_end is not None:
            truncated["next_end_date"] = next_end
            hints.append(
                f"Showing the newest days, from {cutoff}. For earlier rows, call again "
                f"with the same start_date and end_date={next_end}."
            )
        else:
            hints.append(
                f"Showing the newest days, from {cutoff}. The omitted rows are "
                "dated before start_date."
            )
    for field in undated:
        if field in cuts:
            shown, total = cuts[field]["showing"], cuts[field]["total"]
            if limit is not None and shown == limit:
                hints.append(f"Showing the first {shown} of {total} {field}; pass a larger limit.")
            else:
                hints.append(
                    f"Showing the first {shown} of {total} {field} (response size cap reached)."
                )
    truncated["hint"] = " ".join(hints)
    data["truncated"] = truncated
    return _dump(data)


def _handle_tool_errors[**P](fn: Callable[P, str]) -> Callable[P, str]:
    """Decorator that turns client exceptions into ``ToolError`` with an agent-friendly message.

    ``ToolError`` reaches the client as ``isError: true`` with the message intact
    (prefixed by the SDK with ``Error executing tool <name>:``). Any other
    escaping exception would reach the model only as that prefix.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except EmpowerAuthError as exc:
            log.warning("Auth error in tool call: %s", exc)
            # One next step, and one that can work: without credentials,
            # start_authentication always fails.
            if _has_credentials():
                next_step = (
                    "Call start_authentication to begin re-auth, then "
                    "complete_authentication with the verification code if 2FA is required."
                )
            else:
                next_step = (
                    "This server has no EMPOWER_EMAIL/EMPOWER_PASSWORD to sign in with. "
                    + _TERMINAL_LOGIN
                )
            raise ToolError(f"{exc}\n\nSession is expired or invalid. {next_step}") from exc
        except EmpowerNetworkError as exc:
            log.warning("Network error in tool call: %s", exc)
            raise ToolError(
                f"Network request to Empower failed — {exc}. Check connection and retry."
            ) from exc
        except EmpowerAPIError as exc:
            log.warning("API error in tool call: %s", exc)
            raise ToolError(str(exc)) from exc
        except requests.RequestException as exc:
            # Defensive fallback: client._request wraps these as EmpowerNetworkError,
            # so this branch shouldn't fire in practice — kept in case a future code
            # path bypasses _request().
            log.warning("Unwrapped network error in tool call: %s", exc)
            raise ToolError(f"Network request failed — {exc}") from exc
        except ValueError as exc:
            # The response validators raise ValueError when the API's response
            # shape drifts.
            log.warning("Unexpected API response in tool call: %s", exc)
            raise ToolError(f"Unexpected API response — {exc}") from exc

    return wrapper


def start_authentication(ctx: Context[_AppContext]) -> str:
    """Re-authenticate when the cached session is stale.

    Reads EMPOWER_EMAIL and EMPOWER_PASSWORD from the MCP server's
    environment. If the device is remembered, completes authentication
    directly. Otherwise dispatches a 2FA challenge via SMS; call
    complete_authentication next with the verification code.

    Each call that hits the 2FA branch dispatches a fresh SMS — call
    sparingly to avoid spamming the user. State is process-local; if the
    MCP server restarts mid-flow, call this again to begin a new challenge.

    Errors: the call fails (isError) when credentials are missing, Empower
    rejects the sign-in, or the network fails.
    """
    app_ctx: _AppContext = ctx.request_context.lifespan_context
    email = os.getenv("EMPOWER_EMAIL")
    password = os.getenv("EMPOWER_PASSWORD")
    if not email or not password:
        raise ToolError(
            "EMPOWER_EMAIL and/or EMPOWER_PASSWORD not set, so this server can't sign in. "
            f"{_TERMINAL_LOGIN} To sign in from chat instead, add both to the "
            "'env' block of the MCP server config and restart the MCP server."
        )

    # Mint a fresh client per attempt (mirrors authenticate() at auth.py).
    # Stale cookies on the lifespan client could confuse client.login().
    # Only commit fresh_client to app_ctx on success — failure leaves the
    # existing client untouched so transient errors don't lose state.
    fresh_client = EmpowerClient(session_path=app_ctx.session_path)
    try:
        fresh_client.login(email, password)
    except TwoFactorRequiredError:
        # SMS is the only method Empower offers, so EMPOWER_2FA_MODE is
        # optional and defaults to SMS; a stale 'email' value still gets a
        # clear tombstone error from parse_2fa_mode_env.
        env_mode = os.getenv("EMPOWER_2FA_MODE", "").strip().lower()
        try:
            mode = parse_2fa_mode_env(env_mode) if env_mode else TwoFactorMode.SMS
        except EmpowerAuthError as exc:
            raise ToolError(str(exc)) from exc
        try:
            fresh_client.send_2fa_challenge(mode)
        except EmpowerNetworkError as exc:
            raise ToolError(
                f"Network failure dispatching 2FA challenge — {exc}. "
                "Check connection and try again."
            ) from exc
        except (EmpowerAuthError, EmpowerAPIError) as exc:
            raise ToolError(f"2FA challenge dispatch failed: {exc}") from exc
        # Keep the partial-auth-state client so complete_authentication can
        # verify against the same cookies the challenge was issued on. It stays
        # out of app_ctx.client so data tools keep reloading the session file.
        app_ctx.pending_client = fresh_client
        app_ctx.pending_2fa_mode = mode
        return (
            f"2FA challenge sent via {mode.value}. "
            "Call complete_authentication with the verification code."
        )
    except EmpowerNetworkError as exc:
        raise ToolError(
            f"Network failure during login — {exc}. Check connection and try again."
        ) from exc
    except LoginRejectedError as exc:
        # Message starts "Empower rejected the sign-in", distinct from transient failures.
        raise ToolError(str(exc)) from exc
    except (EmpowerAuthError, EmpowerAPIError) as exc:
        raise ToolError(f"Authentication failed: {exc}") from exc

    # No-2FA path: device remembered, login completed directly.
    # Clear pending_2fa_mode in case a prior start_authentication call set
    # it (e.g. user retried after partial 2FA flow and device is now
    # remembered).
    fresh_client.save_session()
    app_ctx.client = fresh_client
    app_ctx.pending_2fa_mode = None
    app_ctx.pending_client = None
    return "Authenticated."


def complete_authentication(ctx: Context[_AppContext], code: str) -> str:
    """Submit the 2FA verification code to complete authentication.

    Call this after start_authentication has dispatched a 2FA challenge.
    Pass the verification code that was sent to the user's phone via SMS.

    Errors: the call fails (isError) on a wrong code (call
    start_authentication for a new one), a rejected password, or no pending
    challenge.
    """
    app_ctx: _AppContext = ctx.request_context.lifespan_context
    pending_client = app_ctx.pending_client
    if app_ctx.pending_2fa_mode is None or pending_client is None:
        raise ToolError("No pending 2FA challenge. Call start_authentication first.")
    password = os.getenv("EMPOWER_PASSWORD")
    if not password:
        raise ToolError(
            "EMPOWER_PASSWORD no longer set. "
            "Restart the MCP server with the env var set and try again."
        )
    mode = app_ctx.pending_2fa_mode
    try:
        pending_client.verify_2fa_and_login(mode, code, password)
    except EmpowerNetworkError as exc:
        # Don't clear pending_2fa_mode — the code may still be valid;
        # the agent can retry complete_authentication once connectivity
        # recovers without dispatching a fresh challenge.
        raise ToolError(
            f"Network failure during 2FA verification — {exc}. Try complete_authentication again."
        ) from exc
    except LoginRejectedError as exc:
        # The code was accepted but Empower rejected the password.
        app_ctx.pending_2fa_mode = None
        app_ctx.pending_client = None
        raise ToolError(str(exc)) from exc
    except (EmpowerAuthError, EmpowerAPIError) as exc:
        # Wrong code or server rejection — clear state so the agent can
        # restart cleanly via start_authentication. The client's message
        # already starts "2FA verification failed: ...".
        app_ctx.pending_2fa_mode = None
        app_ctx.pending_client = None
        raise ToolError(
            f"{str(exc).rstrip('.')}. Call start_authentication to send a new code."
        ) from exc
    pending_client.save_session()
    app_ctx.client = pending_client
    app_ctx.pending_2fa_mode = None
    app_ctx.pending_client = None
    return "Authenticated."


def create_server(session_path: Path | None = None) -> MCPServer[_AppContext]:
    """Create and return a configured MCP server.

    Args:
        session_path: Path to the session file. Defaults to DEFAULT_SESSION_PATH.
    """
    resolved_path = session_path or DEFAULT_SESSION_PATH

    @asynccontextmanager
    async def lifespan(server: MCPServer[_AppContext]) -> AsyncIterator[_AppContext]:
        # No-session is OK at startup — agents bootstrap via start_authentication.
        # EmpowerClient's constructor calls load_session() which is a no-op for
        # missing files (client.py:522), so the unauthenticated client is safe
        # to construct here; tool calls return auth errors directing the agent
        # at start_authentication.
        if not resolved_path.exists():
            log.warning(
                "No session file at %s; agent must call start_authentication "
                "before data tools work.",
                resolved_path,
            )
        client = EmpowerClient(session_path=resolved_path)
        yield _AppContext(client=client, session_path=resolved_path)

    mcp = MCPServer(
        name="empower",
        version=_package_version("personalcapital2"),
        lifespan=lifespan,
    )

    # --- Authentication tools ---
    #
    # Two tools (not one stateful tool) for LLM ergonomics: each has a single
    # clear purpose. State (pending_2fa_mode) lives on _AppContext so the
    # verification code can be collected from the user mid-conversation.
    #
    # These deliberately do NOT use @_handle_tool_errors — that decorator
    # would direct callers BACK to start_authentication on EmpowerAuthError,
    # producing a self-referential error loop. Errors are raised as ToolError
    # inside the module-level start_authentication / complete_authentication
    # implementations.

    mcp.tool(structured_output=False)(start_authentication)
    mcp.tool(structured_output=False)(complete_authentication)

    # --- Tools ---
    #
    # All tools are synchronous functions calling the requests-based EmpowerClient.
    # MCPServer runs sync tools in a worker thread, so they won't block the event loop.
    #
    # All tools use structured_output=False to avoid generating outputSchema,
    # which causes Claude Code to silently drop all tools (anthropics/claude-code#25081).

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_accounts(ctx: Context[_AppContext]) -> str:
        """List all linked financial accounts with aggregate summary.

        Returns accounts with balances, types, and firm names, plus a summary
        with net worth, total assets, and total liabilities.
        No parameters required.

        Errors: the call fails (isError) if the session is expired, with a
        message saying to call start_authentication, then
        complete_authentication with the verification code if 2FA is required.
        """
        client = _get_client(ctx)
        return _render(client.get_accounts(), undated=("accounts",))

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_transactions(
        ctx: Context[_AppContext], start_date: date, end_date: date, limit: int = 100
    ) -> str:
        """Fetch transactions within a date range.

        Returns transactions with amounts, descriptions, categories, and merchant info,
        plus unique categories and a cashflow summary (money in, money out, net)
        for the whole requested range. The summary and categories are always complete.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            limit: Maximum number of transactions to return (default 100).
                When there are more, the newest whole days are kept and
                ``truncated.next_end_date`` says where to page back from. The
                newest day is always returned in full, even if it alone
                exceeds limit.

        Errors: the call fails (isError) if start_date is after end_date or
        limit < 1. If the session is expired, it fails with a message saying to call
        start_authentication, then complete_authentication with the
        verification code if 2FA is required.
        """
        _check_date_range(start_date, end_date)
        _check_limit(limit)
        client = _get_client(ctx)
        result = client.get_transactions(start_date, end_date)
        return _render(result, dated=("transactions",), limit=limit, start_date=start_date)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_holdings(ctx: Context[_AppContext], limit: int = 100) -> str:
        """Fetch current investment holdings across all accounts.

        Returns individual holdings with security info, quantities, prices,
        cost basis, and fees, plus the total portfolio value.

        Args:
            limit: Maximum number of holdings to return (default 100). The
                first holdings are kept. Total value is always complete.

        Errors: the call fails (isError) if limit < 1.
        If the session is expired, it fails with a message saying to call
        start_authentication, then complete_authentication with the
        verification code if 2FA is required.
        """
        _check_limit(limit)
        client = _get_client(ctx)
        return _render(client.get_holdings(), undated=("holdings",), limit=limit)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_net_worth(
        ctx: Context[_AppContext], start_date: date, end_date: date, limit: int = 180
    ) -> str:
        """Fetch daily net worth history with change summary.

        Returns daily net worth entries broken down by asset/liability category,
        plus a summary with percentage and value changes over the requested range.
        The summary is always complete.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            limit: Maximum number of daily entries to return (default 180).
                When there are more, the newest days are kept and
                ``truncated.next_end_date`` says where to page back from.

        Errors: the call fails (isError) if start_date is after end_date or
        limit < 1. If the session is expired, it fails with a message saying to call
        start_authentication, then complete_authentication with the
        verification code if 2FA is required.
        """
        _check_date_range(start_date, end_date)
        _check_limit(limit)
        client = _get_client(ctx)
        result = client.get_net_worth(start_date, end_date)
        return _render(result, dated=("entries",), limit=limit, start_date=start_date)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_account_balances(
        ctx: Context[_AppContext], start_date: date, end_date: date, limit: int = 500
    ) -> str:
        """Fetch daily account balance history for all accounts.

        Returns daily balances for each account, with account ID and balance
        amount, plus a summary with account count, latest date, and total
        balance. The summary is always complete.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            limit: Maximum number of balance entries to return (default 500).
                When there are more, the newest whole days are kept (every
                account for each day shown) and ``truncated.next_end_date``
                says where to page back from. The newest day is always
                returned in full, even if it alone exceeds limit.

        Errors: the call fails (isError) if start_date is after end_date or
        limit < 1. If the session is expired, it fails with a message saying to call
        start_authentication, then complete_authentication with the
        verification code if 2FA is required.
        """
        _check_date_range(start_date, end_date)
        _check_limit(limit)
        client = _get_client(ctx)
        result = client.get_account_balances(start_date, end_date)
        return _render(result, dated=("balances",), limit=limit, start_date=start_date)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_performance(
        ctx: Context[_AppContext],
        start_date: date,
        end_date: date,
        account_ids: list[int],
        limit: int = 500,
    ) -> str:
        """Fetch daily investment performance and benchmark comparisons.

        Use get_holdings (not get_accounts) to discover account IDs — get_accounts
        may not list all accounts that have holdings (e.g. employer 401k plans,
        crypto exchanges). An empty list returns every investment account. IDs
        Empower doesn't recognize return empty investments and account_summaries
        (benchmarks still come back). For large portfolios, query a few accounts
        at a time.

        Returns daily investment performance per account, daily performance of
        Empower's benchmark indexes (^PC_US_STOCKS, ^PC_US_BONDS, ^PC_INTL_STOCKS,
        ^PC_INTL_BONDS, ^PC_ALTERNATIVES, ^PC_BLENDED; not the S&P 500), and
        per-account summaries with balance, income, and returns. Account
        summaries are always complete. Histories start with a baseline row
        (value 0) on the trading day before start_date, or the first available
        date.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            account_ids: List of investment account IDs (integers). Use get_holdings to
                find user_account_id values for investment accounts.
            limit: Maximum number of entries to return for each of the investments
                and benchmarks lists (default 500). When there are more, the
                newest whole days are kept for both lists and
                ``truncated.next_end_date`` says where to page back from. The
                newest day is always returned in full, even if it alone
                exceeds limit.

        Errors: the call fails (isError) if start_date is after end_date or
        limit < 1. If the session is expired, it fails with a message saying to call
        start_authentication, then complete_authentication with the
        verification code if 2FA is required.
        """
        _check_date_range(start_date, end_date)
        _check_limit(limit)
        client = _get_client(ctx)
        result = client.get_performance(start_date, end_date, account_ids)
        return _render(
            result, dated=("investments", "benchmarks"), limit=limit, start_date=start_date
        )

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_quotes(ctx: Context[_AppContext], start_date: date, end_date: date) -> str:
        """Fetch portfolio vs S&P 500 comparison, portfolio snapshot, and market quotes.

        Returns daily portfolio vs S&P 500 values, a current portfolio snapshot
        (last value, change, percent change), and individual market quote data.
        In portfolio_vs_benchmark, portfolio_value and sp500_value are Empower's
        "YOU" and "^INX" series: cumulative percent change since the first day,
        not dollar values. The series starts with a baseline row (value 0) on
        the trading day before start_date. If the response is too large, the
        newest days of portfolio_vs_benchmark are kept and
        ``truncated.next_end_date`` says where to page back from.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).

        Errors: the call fails (isError) if start_date is after end_date.
        If the session is expired, it fails with a message saying to call
        start_authentication, then complete_authentication with the
        verification code if 2FA is required.
        """
        _check_date_range(start_date, end_date)
        client = _get_client(ctx)
        result = client.get_quotes(start_date, end_date)
        return _render(
            result,
            dated=("portfolio_vs_benchmark",),
            undated=("market_quotes",),
            start_date=start_date,
        )

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_spending(
        ctx: Context[_AppContext],
        start_date: date | None = None,
        end_date: date | None = None,
        interval: Literal["MONTH", "WEEK", "YEAR"] = "MONTH",
    ) -> str:
        """Fetch current spending summary. The API ignores date range and interval
        parameters — it always returns current-period spending for all three
        interval types (MONTH, WEEK, YEAR) regardless of what you send.

        Returns spending data with average, current, and target amounts plus
        details within each interval (daily for MONTH and WEEK, monthly for YEAR).

        Args:
            start_date: Optional. Sent to API but has no observable effect on
                results. Defaults to today.
            end_date: Optional. Sent to API but has no observable effect on
                results. Defaults to today.
            interval: Sent to API but has no observable effect — all three intervals
                are always returned. Defaults to MONTH.

        Errors: the call fails (isError) if the session is expired, with a
        message saying to call start_authentication, then
        complete_authentication with the verification code if 2FA is required.
        """
        today = date.today()
        effective_start = start_date or today
        effective_end = end_date or today
        client = _get_client(ctx)
        result = client.get_spending(effective_start, effective_end, interval)
        return _render(result, undated=("intervals",))

    return mcp
