"""MCP tool server for Empower (Personal Capital) financial data.

Exposes EmpowerClient methods as MCP tools over stdio transport.
Requires the ``mcp`` optional extra: ``pip install personalcapital2[mcp]``

Usage:
    pc2 mcp              # start server (requires prior: pc2 login)

Client config (Claude Code / Claude Desktop):
    {
        "mcpServers": {
            "empower": {
                "type": "stdio",
                "command": "pc2",
                "args": ["mcp"],
                "env": {"PC2_SESSION_PATH": "~/.config/personalcapital2/session.json"}
            }
        }
    }
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
from datetime import date
from functools import wraps
from pathlib import Path  # noqa: TC003 — needed at runtime by lifespan
from typing import TYPE_CHECKING, Any, Literal

import requests

if TYPE_CHECKING:
    from collections.abc import Callable
from mcp.server.fastmcp import Context, FastMCP

from personalcapital2._serialization import serialize_result
from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError, EmpowerNetworkError

log = logging.getLogger(__name__)

_DEFAULT_MAX_CHARS = 50_000


@dataclasses.dataclass
class _AppContext:
    """Lifespan state shared across all tool invocations."""

    client: EmpowerClient


def _get_client(ctx: Context) -> EmpowerClient:
    """Extract the EmpowerClient from the MCP context.

    Reloads the session from disk on each call so the long-running server
    picks up fresh sessions after the user re-authenticates with ``pc2 login``.
    """
    app_ctx: _AppContext = ctx.request_context.lifespan_context
    app_ctx.client.load_session()
    return app_ctx.client


def _validate_date_range(start_date: date, end_date: date) -> str | None:
    """Return an error message if start_date > end_date, else None."""
    if start_date > end_date:
        return (
            f"Error: start_date ({start_date}) is after end_date ({end_date}). "
            "Swap them so start_date <= end_date."
        )
    return None


def _get_max_chars() -> int:
    """Read max output characters from environment, falling back to default."""
    env = os.environ.get("PC2_MCP_MAX_CHARS")
    if env is not None:
        try:
            return int(env)
        except ValueError:
            log.warning("Invalid PC2_MCP_MAX_CHARS=%r, using default %d", env, _DEFAULT_MAX_CHARS)
    return _DEFAULT_MAX_CHARS


def _apply_limit(serialized: str, field: str, limit: int) -> str:
    """Limit a specific list field in serialized JSON output.

    If the field has more than ``limit`` items, truncates the list and adds
    a ``truncated`` metadata field to the JSON output.
    """
    if limit < 1:
        return serialized
    data: dict[str, Any] = json.loads(serialized)
    items = data.get(field)
    if not isinstance(items, list) or len(items) <= limit:
        return serialized
    total = len(items)
    data[field] = items[:limit]
    truncated: dict[str, Any] = data.get("truncated") or {}
    truncated[field] = {"showing": limit, "total": total}
    data["truncated"] = truncated
    return json.dumps(data, indent=2)


def _enforce_char_cap(serialized: str) -> str:
    """Truncate list fields if output exceeds the character cap.

    Iteratively finds the largest list field and uses binary search to fit
    it within the cap. Repeats for additional list fields if still over.
    Adds a ``truncated`` metadata field when truncation occurs.

    The cap is configurable via the ``PC2_MCP_MAX_CHARS`` environment variable
    (default: 50,000 characters, roughly 12,500 tokens).
    """
    max_chars = _get_max_chars()
    if len(serialized) <= max_chars:
        return serialized

    data: dict[str, Any] = json.loads(serialized)

    # Seed truncation metadata from any prior _apply_limit call
    truncated_info: dict[str, Any] = {}
    prior = data.get("truncated")
    if isinstance(prior, dict):
        truncated_info = {k: v for k, v in prior.items() if k != "hint"}

    # Track which fields have already been fully truncated
    exhausted: set[str] = set()

    while True:
        # Find the largest non-exhausted list field
        largest_key: str | None = None
        largest_len = 0
        for key, value in data.items():
            if key == "truncated":
                continue
            if isinstance(value, list) and len(value) > largest_len and key not in exhausted:
                largest_key = key
                largest_len = len(value)

        if largest_key is None or largest_len == 0:
            return serialized if not truncated_info else json.dumps(data, indent=2)

        items: list[Any] = data[largest_key]

        # Preserve the original total from a prior _apply_limit truncation
        prior_info = truncated_info.get(largest_key)
        if isinstance(prior_info, dict) and "total" in prior_info:
            total: int = prior_info["total"]
        else:
            total = len(items)

        # Binary search for the maximum number of items that fit
        lo, hi = 0, len(items)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            data[largest_key] = items[:mid]
            truncated_info[largest_key] = {"showing": mid, "total": total}
            data["truncated"] = {
                **truncated_info,
                "hint": "Narrow the date range or request fewer accounts.",
            }
            if len(json.dumps(data, indent=2)) <= max_chars:
                lo = mid
            else:
                hi = mid - 1

        data[largest_key] = items[:lo]
        truncated_info[largest_key] = {"showing": lo, "total": total}
        data["truncated"] = {
            **truncated_info,
            "hint": "Narrow the date range or request fewer accounts.",
        }

        if len(json.dumps(data, indent=2)) <= max_chars:
            break

        exhausted.add(largest_key)

    return json.dumps(data, indent=2)


def _handle_tool_errors[**P](fn: Callable[P, str]) -> Callable[P, str]:
    """Decorator that catches client exceptions and returns agent-friendly error strings.

    Wraps tool functions so the LLM agent gets a readable error message
    instead of a raw Python traceback.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except EmpowerAuthError as exc:
            log.warning("Auth error in tool call: %s", exc)
            return (
                f"Error: {exc}\n\n"
                "Session is expired or invalid. "
                "The user needs to re-authenticate by running: pc2 login"
            )
        except EmpowerNetworkError as exc:
            log.warning("Network error in tool call: %s", exc)
            return f"Error: Network request to Empower failed — {exc}. Check connection and retry."
        except EmpowerAPIError as exc:
            log.warning("API error in tool call: %s", exc)
            return f"Error: {exc}"
        except requests.RequestException as exc:
            # Defensive fallback: client._request wraps these as EmpowerNetworkError,
            # so this branch shouldn't fire in practice — kept in case a future code
            # path bypasses _request().
            log.warning("Unwrapped network error in tool call: %s", exc)
            return f"Error: Network request failed — {exc}"

    return wrapper


def create_server(session_path: Path | None = None) -> FastMCP:
    """Create and return a configured MCP server.

    Args:
        session_path: Path to the session file. Defaults to DEFAULT_SESSION_PATH.
    """
    resolved_path = session_path or DEFAULT_SESSION_PATH

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[_AppContext]:
        if not resolved_path.exists():
            raise FileNotFoundError(
                f"No session file at {resolved_path}. Authenticate first by running: pc2 login"
            )
        client = EmpowerClient(session_path=resolved_path)
        yield _AppContext(client=client)

    mcp = FastMCP(
        name="empower",
        lifespan=lifespan,
    )

    # --- Tools ---
    #
    # All tools are synchronous functions calling the requests-based EmpowerClient.
    # FastMCP runs sync tools in a thread pool, so they won't block the event loop.
    #
    # All tools use structured_output=False to avoid generating outputSchema,
    # which causes Claude Code to silently drop all tools (anthropics/claude-code#25081).

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_accounts(ctx: Context) -> str:
        """List all linked financial accounts with aggregate summary.

        Returns accounts with balances, types, and firm names, plus a summary
        with net worth, total assets, and total liabilities.
        No parameters required.

        Errors: returns an error message if the session is expired (re-run `pc2 login`).
        """
        client = _get_client(ctx)
        result = client.get_accounts()
        return _enforce_char_cap(serialize_result(result))

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_transactions(ctx: Context, start_date: date, end_date: date, limit: int = 100) -> str:
        """Fetch transactions within a date range.

        Returns transactions with amounts, descriptions, categories, and merchant info,
        plus unique categories and a cashflow summary (money in, money out, net).
        The summary and categories are always returned in full regardless of limit.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            limit: Maximum number of transactions to return (default 100).
                Use a smaller value for quick lookups or a larger value when
                you need more detail. Summary is always complete.

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        if limit < 1:
            return "Error: limit must be at least 1."
        client = _get_client(ctx)
        result = client.get_transactions(start_date, end_date)
        output = serialize_result(result)
        output = _apply_limit(output, "transactions", limit)
        return _enforce_char_cap(output)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_holdings(ctx: Context, limit: int = 100) -> str:
        """Fetch current investment holdings across all accounts.

        Returns individual holdings with security info, quantities, prices,
        cost basis, and fees, plus the total portfolio value.

        Args:
            limit: Maximum number of holdings to return (default 100).
                Use a smaller value for quick lookups or a larger value when
                you need more detail. Total value is always complete.

        Errors: returns an error message if the session is expired (re-run `pc2 login`).
        """
        if limit < 1:
            return "Error: limit must be at least 1."
        client = _get_client(ctx)
        result = client.get_holdings()
        output = serialize_result(result)
        output = _apply_limit(output, "holdings", limit)
        return _enforce_char_cap(output)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_net_worth(ctx: Context, start_date: date, end_date: date, limit: int = 180) -> str:
        """Fetch daily net worth history with change summary.

        Returns daily net worth entries broken down by asset/liability category,
        plus a summary with percentage and value changes over the period.
        The summary is always returned in full regardless of limit.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            limit: Maximum number of daily entries to return (default 180).
                Use a smaller value for quick lookups or a larger value when
                you need more detail. Summary is always complete.

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        if limit < 1:
            return "Error: limit must be at least 1."
        client = _get_client(ctx)
        result = client.get_net_worth(start_date, end_date)
        output = serialize_result(result)
        output = _apply_limit(output, "entries", limit)
        return _enforce_char_cap(output)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_account_balances(
        ctx: Context, start_date: date, end_date: date, limit: int = 500
    ) -> str:
        """Fetch daily account balance history for all accounts.

        Returns daily balances for each account, with account ID and balance
        amount, plus a summary with account count, latest date, and total
        balance. The summary is always returned in full regardless of limit.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            limit: Maximum number of balance entries to return (default 500).
                Use a smaller value for quick lookups or a larger value when
                you need more detail. Summary is always complete.

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        if limit < 1:
            return "Error: limit must be at least 1."
        client = _get_client(ctx)
        result = client.get_account_balances(start_date, end_date)
        output = serialize_result(result)
        output = _apply_limit(output, "balances", limit)
        return _enforce_char_cap(output)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_performance(
        ctx: Context,
        start_date: date,
        end_date: date,
        account_ids: list[int],
        limit: int = 500,
    ) -> str:
        """Fetch daily investment performance and benchmark comparisons.

        Use get_holdings (not get_accounts) to discover account IDs — get_accounts
        may not list all accounts that have holdings (e.g. employer 401k plans,
        crypto exchanges). For large portfolios, query a few accounts at a time.

        Returns daily investment performance per account, daily benchmark (S&P 500)
        performance, and per-account summaries with balance, fees, income, and returns.
        Account summaries are always returned in full regardless of limit.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            account_ids: List of investment account IDs (integers). Use get_holdings to
                find user_account_id values for investment accounts.
            limit: Maximum number of entries to return for each of the investments
                and benchmarks lists (default 500). Account summaries are always
                complete. Use a smaller value for quick lookups.

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        if limit < 1:
            return "Error: limit must be at least 1."
        client = _get_client(ctx)
        result = client.get_performance(start_date, end_date, account_ids)
        output = serialize_result(result)
        output = _apply_limit(output, "investments", limit)
        output = _apply_limit(output, "benchmarks", limit)
        return _enforce_char_cap(output)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_quotes(ctx: Context, start_date: date, end_date: date) -> str:
        """Fetch portfolio vs S&P 500 comparison, portfolio snapshot, and market quotes.

        Returns daily portfolio vs benchmark values, a current portfolio snapshot
        (last value, change, percent change), and individual market quote data.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        client = _get_client(ctx)
        result = client.get_quotes(start_date, end_date)
        return _enforce_char_cap(serialize_result(result))

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_spending(
        ctx: Context,
        start_date: date | None = None,
        end_date: date | None = None,
        interval: Literal["MONTH", "WEEK", "YEAR"] = "MONTH",
    ) -> str:
        """Fetch current spending summary. The API ignores date range and interval
        parameters — it always returns current-period spending for all three
        interval types (MONTH, WEEK, YEAR) regardless of what you send.

        Returns spending data with average, current, and target amounts plus
        daily details within each interval.

        Args:
            start_date: Optional. Sent to API but has no observable effect on
                results. Defaults to today.
            end_date: Optional. Sent to API but has no observable effect on
                results. Defaults to today.
            interval: Sent to API but has no observable effect — all three intervals
                are always returned. Defaults to MONTH.

        Errors: returns an error message if the session is expired (re-run `pc2 login`).
        """
        today = date.today()
        effective_start = start_date or today
        effective_end = end_date or today
        client = _get_client(ctx)
        result = client.get_spending(effective_start, effective_end, interval)
        return _enforce_char_cap(serialize_result(result))

    return mcp
