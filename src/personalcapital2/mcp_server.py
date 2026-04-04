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
import logging
from collections.abc import (
    AsyncIterator,  # noqa: TC003 — needed at runtime by SDK
)
from contextlib import asynccontextmanager
from datetime import date  # noqa: TC003 — needed at runtime by Pydantic schema generation
from functools import wraps
from pathlib import Path  # noqa: TC003 — needed at runtime by lifespan
from typing import Literal

import requests
from mcp.server.fastmcp import Context, FastMCP

from personalcapital2._serialization import serialize_result
from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError

log = logging.getLogger(__name__)


@dataclasses.dataclass
class _AppContext:
    """Lifespan state shared across all tool invocations."""

    client: EmpowerClient


def _get_client(ctx: Context) -> EmpowerClient:
    """Extract the EmpowerClient from the MCP context."""
    app_ctx: _AppContext = ctx.request_context.lifespan_context
    return app_ctx.client


def _validate_date_range(start_date: date, end_date: date) -> str | None:
    """Return an error message if start_date > end_date, else None."""
    if start_date > end_date:
        return (
            f"Error: start_date ({start_date}) is after end_date ({end_date}). "
            "Swap them so start_date <= end_date."
        )
    return None


def _handle_tool_errors(fn: object) -> object:
    """Decorator that catches client exceptions and returns agent-friendly error strings.

    Wraps tool functions so the LLM agent gets a readable error message
    instead of a raw Python traceback.
    """

    @wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> str:
        try:
            return fn(*args, **kwargs)  # pyright: ignore[reportCallIssue] — fn is callable returning str
        except EmpowerAuthError as exc:
            log.warning("Auth error in tool call: %s", exc)
            return (
                f"Error: {exc}\n\n"
                "Session is expired or invalid. "
                "The user needs to re-authenticate by running: pc2 login"
            )
        except EmpowerAPIError as exc:
            log.warning("API error in tool call: %s", exc)
            return f"Error: {exc}"
        except requests.RequestException as exc:
            log.warning("Network error in tool call: %s", exc)
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
        return serialize_result(result)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_transactions(ctx: Context, start_date: date, end_date: date) -> str:
        """Fetch transactions within a date range.

        Returns transactions with amounts, descriptions, categories, and merchant info,
        plus unique categories and a cashflow summary (money in, money out, net).

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        client = _get_client(ctx)
        result = client.get_transactions(start_date, end_date)
        return serialize_result(result)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_holdings(ctx: Context) -> str:
        """Fetch current investment holdings across all accounts.

        Returns individual holdings with security info, quantities, prices,
        cost basis, and fees, plus the total portfolio value.
        No parameters required.

        Errors: returns an error message if the session is expired (re-run `pc2 login`).
        """
        client = _get_client(ctx)
        result = client.get_holdings()
        return serialize_result(result)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_net_worth(ctx: Context, start_date: date, end_date: date) -> str:
        """Fetch daily net worth history with change summary.

        Returns daily net worth entries broken down by asset/liability category,
        plus a summary with percentage and value changes over the period.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        client = _get_client(ctx)
        result = client.get_net_worth(start_date, end_date)
        return serialize_result(result)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_account_balances(ctx: Context, start_date: date, end_date: date) -> str:
        """Fetch daily account balance history for all accounts.

        Returns balances grouped by date, each with account ID and balance amount.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        client = _get_client(ctx)
        result = client.get_account_balances(start_date, end_date)
        return serialize_result(result)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_performance(
        ctx: Context, start_date: date, end_date: date, account_ids: list[int]
    ) -> str:
        """Fetch daily investment performance and benchmark comparisons.

        Returns daily investment performance per account, daily benchmark (S&P 500)
        performance, and per-account summaries with balance, fees, income, and returns.
        Use get_accounts first to discover valid account IDs.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            account_ids: List of investment account IDs (integers). Get these from get_accounts.

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        client = _get_client(ctx)
        result = client.get_performance(start_date, end_date, account_ids)
        return serialize_result(result)

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
        return serialize_result(result)

    @mcp.tool(structured_output=False)
    @_handle_tool_errors
    def get_spending(
        ctx: Context,
        start_date: date,
        end_date: date,
        interval: Literal["MONTH", "WEEK", "YEAR"] = "MONTH",
    ) -> str:
        """Fetch spending summary grouped by time interval.

        Returns spending data broken down by interval, with average, current,
        and target amounts plus daily details within each interval.

        Args:
            start_date: Start of date range (ISO format: YYYY-MM-DD).
            end_date: End of date range (ISO format: YYYY-MM-DD).
            interval: Grouping interval — MONTH, WEEK, or YEAR. Defaults to MONTH.

        Errors: returns an error message if the session is expired (re-run `pc2 login`)
        or if start_date is after end_date.
        """
        if err := _validate_date_range(start_date, end_date):
            return err
        client = _get_client(ctx)
        result = client.get_spending(start_date, end_date, interval)
        return serialize_result(result)

    return mcp
