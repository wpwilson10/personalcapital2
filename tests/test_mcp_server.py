"""Tests for MCP server tool functions."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

mcp_sdk = pytest.importorskip("mcp", reason="mcp extra not installed")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from personalcapital2.auth import login_suggestion  # noqa: E402
from personalcapital2.exceptions import (  # noqa: E402
    EmpowerAPIError,
    EmpowerAuthError,
    EmpowerNetworkError,
    LoginRejectedError,
    TwoFactorRequiredError,
)
from personalcapital2.mcp_server import (  # noqa: E402
    _check_date_range,
    _render,
    create_server,
)
from personalcapital2.models import (  # noqa: E402
    Account,
    AccountBalance,
    AccountBalancesResult,
    AccountBalancesSummary,
    AccountPerformanceSummary,
    AccountsResult,
    AccountsSummary,
    BenchmarkPerformance,
    Category,
    Holding,
    HoldingsResult,
    InvestmentPerformance,
    MarketQuote,
    NetWorthEntry,
    NetWorthResult,
    NetWorthSummary,
    PerformanceResult,
    PortfolioSnapshot,
    PortfolioVsBenchmark,
    QuotesResult,
    SpendingDetail,
    SpendingResult,
    SpendingSummary,
    Transaction,
    TransactionsResult,
    TransactionsSummary,
)

# --- Fixtures ---


def _mock_accounts_result() -> AccountsResult:
    return AccountsResult(
        accounts=(
            Account(
                user_account_id=1,
                account_id="acct-1",
                name="Checking",
                firm_name="BankCo",
                account_type="BANK",
                account_type_group="BANK",
                product_type="CHECKING",
                currency="USD",
                is_asset=True,
                is_closed=False,
                created_at=date(2020, 1, 15),
                balance=Decimal("5000.50"),
                available_cash=None,
                account_type_subtype=None,
                last_refreshed=date(2026, 4, 1),
                oldest_transaction_date=None,
                advisory_fee_percentage=None,
                fees_per_year=None,
                fund_fees=None,
                total_fee=None,
            ),
        ),
        summary=AccountsSummary(
            networth=Decimal("50000"),
            assets=Decimal("60000"),
            liabilities=Decimal("10000"),
            cash_total=Decimal("5000"),
            investment_total=Decimal("45000"),
            credit_card_total=Decimal("0"),
            mortgage_total=Decimal("0"),
            loan_total=Decimal("10000"),
            other_asset_total=Decimal("0"),
            other_liabilities_total=Decimal("0"),
        ),
    )


def _mock_transactions_result() -> TransactionsResult:
    return TransactionsResult(
        transactions=(
            Transaction(
                user_transaction_id=100,
                user_account_id=1,
                date=date(2026, 3, 15),
                amount=Decimal("42.99"),
                is_cash_in=False,
                is_income=False,
                is_spending=True,
                description="Coffee Shop",
                original_description="COFFEE SHOP #123",
                simple_description="Coffee Shop",
                category_id=7,
                category_name="Dining",
                category_type="EXPENSE",
                merchant=None,
                transaction_type=None,
                sub_type=None,
                status="posted",
                currency="USD",
                merchant_id=None,
                merchant_type=None,
                is_duplicate=False,
            ),
        ),
        categories=(Category(category_id=7, name="Dining", type="EXPENSE"),),
        summary=TransactionsSummary(
            money_in=Decimal("0"),
            money_out=Decimal("42.99"),
            net_cashflow=Decimal("-42.99"),
            average_in=Decimal("0"),
            average_out=Decimal("42.99"),
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        ),
    )


def _mock_holdings_result() -> HoldingsResult:
    return HoldingsResult(
        holdings=(
            Holding(
                snapshot_date=date(2026, 4, 1),
                user_account_id=2,
                ticker="VTI",
                cusip=None,
                description="Vanguard Total Stock Market ETF",
                quantity=Decimal("100"),
                price=Decimal("250.00"),
                value=Decimal("25000"),
                holding_type=None,
                security_type="ETF",
                holding_percentage=Decimal("100"),
                source="EMPOWER",
                cost_basis=Decimal("20000"),
                one_day_percent_change=Decimal("0.2"),
                one_day_value_change=Decimal("50"),
                fees_per_year=Decimal("7.50"),
                fund_fees=None,
            ),
        ),
        total_value=Decimal("25000"),
    )


def _mock_net_worth_result() -> NetWorthResult:
    return NetWorthResult(
        entries=(
            NetWorthEntry(
                date=date(2026, 4, 1),
                networth=Decimal("50000"),
                total_assets=Decimal("60000"),
                total_liabilities=Decimal("10000"),
                total_cash=Decimal("5000"),
                total_investment=Decimal("45000"),
                total_credit=Decimal("0"),
                total_mortgage=Decimal("0"),
                total_loan=Decimal("10000"),
                total_other_assets=Decimal("0"),
                total_other_liabilities=Decimal("0"),
            ),
        ),
        summary=NetWorthSummary(
            date_range_change=Decimal("1000"),
            date_range_percentage_change=Decimal("2.04"),
            cash_change=Decimal("100"),
            cash_percentage_change=Decimal("2.04"),
            investment_change=Decimal("900"),
            investment_percentage_change=Decimal("2.04"),
            credit_change=Decimal("0"),
            credit_percentage_change=Decimal("0"),
            mortgage_change=Decimal("0"),
            mortgage_percentage_change=Decimal("0"),
            loan_change=Decimal("200"),
            loan_percentage_change=Decimal("2.04"),
            other_assets_change=Decimal("0"),
            other_assets_percentage_change=Decimal("0"),
            other_liabilities_change=Decimal("0"),
            other_liabilities_percentage_change=Decimal("0"),
        ),
    )


def _mock_account_balances_result() -> AccountBalancesResult:
    return AccountBalancesResult(
        balances=(
            AccountBalance(date=date(2026, 4, 1), user_account_id=1, balance=Decimal("5000.50")),
        ),
        summary=AccountBalancesSummary(
            account_count=1,
            latest_date=date(2026, 4, 1),
            latest_total=Decimal("5000.50"),
        ),
    )


def _mock_performance_result() -> PerformanceResult:
    return PerformanceResult(
        investments=(
            InvestmentPerformance(
                date=date(2026, 4, 1),
                user_account_id=2,
                performance=Decimal("0.05"),
            ),
        ),
        benchmarks=(
            BenchmarkPerformance(
                date=date(2026, 4, 1),
                benchmark="S&P 500",
                performance=Decimal("0.04"),
            ),
        ),
        account_summaries=(
            AccountPerformanceSummary(
                user_account_id=2,
                account_name="Brokerage",
                site_name="BrokerCo",
                current_balance=Decimal("25000"),
                percent_of_total=Decimal("100"),
                income=Decimal("300"),
                expense=Decimal("50"),
                cash_flow=Decimal("5000"),
                one_day_balance_value_change=Decimal("50"),
                one_day_balance_percentage_change=Decimal("0.2"),
                date_range_balance_value_change=Decimal("1000"),
                date_range_balance_percentage_change=Decimal("4.17"),
                date_range_performance_value_change=Decimal("1250"),
                one_day_performance_value_change=Decimal("50"),
                balance_as_of_end_date=Decimal("25000"),
                closed_date=None,
            ),
        ),
    )


def _mock_quotes_result() -> QuotesResult:
    return QuotesResult(
        portfolio_vs_benchmark=(
            PortfolioVsBenchmark(
                date=date(2026, 4, 1),
                portfolio_value=Decimal("100"),
                sp500_value=Decimal("98"),
            ),
        ),
        snapshot=PortfolioSnapshot(
            last=Decimal("25000"),
            change=Decimal("50"),
            percent_change=Decimal("0.2"),
        ),
        market_quotes=(
            MarketQuote(
                ticker="SPY",
                last=Decimal("520.50"),
                change=Decimal("2.30"),
                percent_change=Decimal("0.44"),
                long_name="SPDR S&P 500 ETF Trust",
                date=date(2026, 4, 1),
            ),
        ),
    )


def _mock_spending_result() -> SpendingResult:
    return SpendingResult(
        intervals=(
            SpendingSummary(
                type="MONTH",
                average=Decimal("2000"),
                current=Decimal("1800"),
                target=Decimal("2500"),
                details=(
                    SpendingDetail(
                        date=date(2026, 3, 15),
                        amount=Decimal("42.99"),
                    ),
                ),
            ),
        ),
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock EmpowerClient with all data methods stubbed."""
    client = MagicMock()
    client.get_accounts.return_value = _mock_accounts_result()
    client.get_transactions.return_value = _mock_transactions_result()
    client.get_holdings.return_value = _mock_holdings_result()
    client.get_net_worth.return_value = _mock_net_worth_result()
    client.get_account_balances.return_value = _mock_account_balances_result()
    client.get_performance.return_value = _mock_performance_result()
    client.get_quotes.return_value = _mock_quotes_result()
    client.get_spending.return_value = _mock_spending_result()
    return client


@pytest.fixture
def session_file(tmp_path: Path) -> Path:
    """Create a fake session file."""
    f = tmp_path / "session.json"
    f.write_text('{"version": 2, "csrf": "test", "cookies": []}')
    f.chmod(0o600)
    return f


@pytest.fixture
def server(session_file: Path) -> Any:
    """Create an MCP server pointing at the fake session file."""
    return create_server(session_path=session_file)


# --- Helper ---


pytestmark = pytest.mark.anyio


async def _call_tool(
    server: Any,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    mock_client: MagicMock | None = None,
    expect_error: bool = False,
) -> str:
    """Call a tool via in-memory MCP transport and return the text content.

    Asserts ``isError`` matches ``expect_error``: tool failures must reach the
    client as ``isError: true``, never as a successful result.

    ``mode="legacy"`` runs the in-memory JSON-RPC streams and initialize
    handshake, matching what a stdio client exercises. The default ``"auto"``
    mode dispatches directly and skips both.
    """
    from mcp import Client

    if mock_client:
        ctx = patch("personalcapital2.mcp_server.EmpowerClient", return_value=mock_client)
    else:
        ctx = patch("personalcapital2.mcp_server.EmpowerClient")

    with ctx:
        async with Client(server, mode="legacy") as client:
            result = await client.call_tool(name, arguments or {})
    assert result.is_error is expect_error, f"{name}: is_error={result.is_error} {result.content}"
    assert len(result.content) > 0
    text_block = result.content[0]
    assert text_block.type == "text"
    return text_block.text


# --- Tool tests ---


async def test_get_accounts(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(server, "get_accounts", mock_client=mock_client)
    data = json.loads(text)
    assert "accounts" in data
    assert "summary" in data
    assert data["summary"]["networth"] == 50000
    assert data["accounts"][0]["name"] == "Checking"


async def test_get_transactions(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_transactions",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "transactions" in data
    assert "categories" in data
    assert "summary" in data
    assert data["transactions"][0]["description"] == "Coffee Shop"


async def test_get_holdings(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(server, "get_holdings", mock_client=mock_client)
    data = json.loads(text)
    assert "holdings" in data
    assert "total_value" in data
    assert data["holdings"][0]["ticker"] == "VTI"


async def test_get_net_worth(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_net_worth",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "entries" in data
    assert "summary" in data
    assert data["entries"][0]["networth"] == 50000


async def test_get_account_balances(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_account_balances",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "balances" in data
    assert "summary" in data
    assert data["balances"][0]["user_account_id"] == 1
    assert data["balances"][0]["balance"] == 5000.5
    assert data["summary"]["account_count"] == 1
    assert data["summary"]["latest_total"] == 5000.5


async def test_get_performance(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_performance",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
            "account_ids": [2],
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "investments" in data
    assert "benchmarks" in data
    assert "account_summaries" in data


async def test_get_performance_account_ids_default_to_all(
    server: Any, mock_client: MagicMock
) -> None:
    await _call_tool(
        server,
        "get_performance",
        {"start_date": "2026-03-01", "end_date": "2026-04-01"},
        mock_client=mock_client,
    )
    mock_client.get_performance.assert_called_once_with(date(2026, 3, 1), date(2026, 4, 1), [])


async def test_get_quotes(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_quotes",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "portfolio_vs_benchmark" in data
    assert "snapshot" in data
    assert "market_quotes" in data
    assert data["snapshot"]["last"] == 25000


async def test_get_spending(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_spending",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "intervals" in data
    assert data["intervals"][0]["type"] == "MONTH"


async def test_get_spending_with_interval(server: Any, mock_client: MagicMock) -> None:
    text = await _call_tool(
        server,
        "get_spending",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
            "interval": "WEEK",
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert "intervals" in data


# --- Error handling tests ---


async def test_auth_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """Auth errors fail the call (isError) with a helpful message, not a traceback."""
    mock_client.get_accounts.side_effect = EmpowerAuthError("Session expired")
    text = await _call_tool(server, "get_accounts", mock_client=mock_client, expect_error=True)
    assert text.startswith("Error executing tool get_accounts: Session expired")
    assert "Error: " not in text  # no doubled prefix on top of the SDK's


async def test_handle_tool_errors_auth_branch_directs_to_mcp_tools(
    server: Any, mock_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With credentials set, the wrapped auth-error message must direct agents at
    start_authentication and complete_authentication, NOT 'pc2 login'. Pins the
    public message contract for every data tool wrapped by _handle_tool_errors.
    """
    monkeypatch.setenv("EMPOWER_EMAIL", "user@example.com")
    monkeypatch.setenv("EMPOWER_PASSWORD", "secret")
    mock_client.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")
    text = await _call_tool(server, "get_accounts", mock_client=mock_client, expect_error=True)
    assert "start_authentication" in text
    assert "complete_authentication" in text
    assert "pc2 login" not in text


async def test_handle_tool_errors_auth_branch_without_credentials_points_to_terminal(
    server: Any, mock_client: MagicMock, monkeypatch: pytest.MonkeyPatch, session_file: Path
) -> None:
    """Without credentials, start_authentication can only fail, so the one next
    step offered is a terminal login by the user, naming the server's session file."""
    monkeypatch.delenv("EMPOWER_EMAIL", raising=False)
    monkeypatch.delenv("EMPOWER_PASSWORD", raising=False)
    mock_client.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")
    text = await _call_tool(server, "get_accounts", mock_client=mock_client, expect_error=True)
    assert login_suggestion(session_file) in text
    assert f"pc2 login --session {session_file}" in text
    assert "start_authentication" not in text


async def test_api_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """API errors fail the call with the error message."""
    mock_client.get_transactions.side_effect = EmpowerAPIError("Rate limited")
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-03-01", "end_date": "2026-03-31"},
        mock_client=mock_client,
        expect_error=True,
    )
    assert "Rate limited" in text


async def test_network_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """Defensive: an un-wrapped requests.RequestException still produces a readable message."""
    mock_client.get_holdings.side_effect = requests.ConnectionError("DNS resolution failed")
    text = await _call_tool(server, "get_holdings", mock_client=mock_client, expect_error=True)
    assert "Network request failed" in text


async def test_empower_network_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """EmpowerNetworkError (typed transport error from client._request) returns
    an agent-friendly retry hint."""
    mock_client.get_holdings.side_effect = EmpowerNetworkError(
        "Request to https://pc-api.empower-retirement.com failed: connection refused"
    )
    text = await _call_tool(server, "get_holdings", mock_client=mock_client, expect_error=True)
    assert "Network request to Empower failed" in text
    assert "Check connection and retry" in text


async def test_value_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """Response-shape drift (ValueError from the validators) must reach the
    model with its detail, not just 'Error executing tool <name>'."""
    mock_client.get_accounts.side_effect = ValueError("missing field 'accounts'")
    text = await _call_tool(server, "get_accounts", mock_client=mock_client, expect_error=True)
    assert text.startswith("Error executing tool get_accounts: Unexpected API response")
    assert "missing field 'accounts'" in text


# --- Date validation tests ---


def test_check_date_range_valid() -> None:
    _check_date_range(date(2026, 1, 1), date(2026, 3, 31))


def test_check_date_range_same_day() -> None:
    _check_date_range(date(2026, 3, 15), date(2026, 3, 15))


def test_check_date_range_reversed() -> None:
    with pytest.raises(ToolError, match=r"start_date .* is after end_date"):
        _check_date_range(date(2026, 3, 31), date(2026, 1, 1))


async def test_reversed_dates_return_error(server: Any, mock_client: MagicMock) -> None:
    """Tools should reject reversed date ranges without hitting the API."""
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-04-01", "end_date": "2026-03-01"},
        mock_client=mock_client,
        expect_error=True,
    )
    assert "start_date" in text
    mock_client.get_transactions.assert_not_called()


# --- Server lifecycle tests ---


async def test_missing_session_file_starts_with_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cold start with no session file: server starts (so the agent can call
    start_authentication to bootstrap) and logs a warning."""
    import logging

    missing = tmp_path / "nonexistent.json"
    srv = create_server(session_path=missing)

    from mcp import Client

    with caplog.at_level(logging.WARNING, logger="personalcapital2.mcp_server"):
        async with Client(srv, mode="legacy"):
            pass

    messages = [r.getMessage() for r in caplog.records]
    assert any("No session file" in m and "start_authentication" in m for m in messages), messages


async def test_missing_session_file_data_tool_directs_agent_to_start_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the cached session is missing and credentials are set, a data tool
    call must return an error string mentioning start_authentication (not
    'pc2 login') — pins the _handle_tool_errors message contract for the
    cold-start path."""
    monkeypatch.setenv("EMPOWER_EMAIL", "user@example.com")
    monkeypatch.setenv("EMPOWER_PASSWORD", "secret")
    missing = tmp_path / "nonexistent.json"
    srv = create_server(session_path=missing)

    # Real EmpowerClient against a missing session — get_accounts will hit
    # the API and fail with EmpowerAuthError, which _handle_tool_errors then
    # rewrites to the agent-friendly message.
    from mcp import Client

    fake_client = MagicMock()
    fake_client.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")

    with patch("personalcapital2.mcp_server.EmpowerClient", return_value=fake_client):
        async with Client(srv, mode="legacy") as client:
            result = await client.call_tool("get_accounts", {})

    assert result.is_error
    assert len(result.content) > 0
    text = result.content[0].text  # type: ignore[union-attr]  # text content has .text
    assert "start_authentication" in text
    assert "complete_authentication" in text
    assert "pc2 login" not in text


# --- Tool registration tests ---


async def test_tools_have_no_output_schema(server: Any) -> None:
    """Verify no tool advertises outputSchema (would break Claude Code,
    anthropics/claude-code#25081). Checks the wire form (camelCase aliases)
    so the test can't pass just because an attribute name changed."""
    tools = await server.list_tools()
    assert tools
    for tool in tools:
        wire = tool.model_dump(by_alias=True, exclude_none=True)
        assert "inputSchema" in wire, f"Tool {tool.name}: unexpected wire shape {wire}"
        assert "outputSchema" not in wire, f"Tool {tool.name} has outputSchema set"


async def test_tools_have_no_annotations(server: Any) -> None:
    """Verify no tools have annotations (would break Claude Code)."""
    tools = await server.list_tools()
    for tool in tools:
        assert tool.annotations is None, f"Tool {tool.name} has annotations set"


async def test_all_tools_registered(server: Any) -> None:
    """Verify all data + auth tools are registered."""
    tools = await server.list_tools()
    names = {t.name for t in tools}
    expected = {
        # Data tools
        "get_accounts",
        "get_transactions",
        "get_holdings",
        "get_net_worth",
        "get_account_balances",
        "get_performance",
        "get_quotes",
        "get_spending",
        # Authentication tools
        "start_authentication",
        "complete_authentication",
    }
    assert names == expected


# --- Transaction limit tests ---
#
# Fixtures put one row per day, ending on _END, oldest first (the order the
# live API returned on 2026-11-21). Truncation keeps the newest whole days.

_END = date(2027, 12, 31)


def _day(i: int, n: int) -> date:
    """Date of row i of n, oldest first, with the last row on _END."""
    return _END - timedelta(days=n - 1 - i)


def _make_many_transactions(n: int) -> TransactionsResult:
    """Create a TransactionsResult with n transactions."""
    txns = tuple(
        Transaction(
            user_transaction_id=i,
            user_account_id=1,
            date=_day(i, n),
            amount=Decimal("10.00"),
            is_cash_in=False,
            is_income=False,
            is_spending=True,
            description=f"Transaction {i}",
            original_description=f"TXN {i}",
            simple_description=None,
            category_id=7,
            category_name="Dining",
            category_type="EXPENSE",
            merchant=None,
            transaction_type=None,
            sub_type=None,
            status="posted",
            currency="USD",
            merchant_id=None,
            merchant_type=None,
            is_duplicate=False,
        )
        for i in range(n)
    )
    return TransactionsResult(
        transactions=txns,
        categories=(Category(category_id=7, name="Dining", type="EXPENSE"),),
        summary=TransactionsSummary(
            money_in=Decimal("0"),
            money_out=Decimal(str(n * 10)),
            net_cashflow=Decimal(str(n * -10)),
            average_in=Decimal("0"),
            average_out=Decimal("10"),
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        ),
    )


async def test_transactions_default_limit(server: Any, mock_client: MagicMock) -> None:
    """Default limit=100 should truncate when there are more than 100 transactions."""
    mock_client.get_transactions.return_value = _make_many_transactions(150)
    # Use a large char cap so only the limit is tested, not the cap
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_transactions",
            {"start_date": "2026-03-01", "end_date": "2026-03-31"},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["transactions"]) == 100
    assert data["truncated"]["transactions"]["showing"] == 100
    assert data["truncated"]["transactions"]["total"] == 150
    # Summary and categories always present
    assert "summary" in data
    assert "categories" in data


async def test_transactions_custom_limit(server: Any, mock_client: MagicMock) -> None:
    """Custom limit should be respected."""
    mock_client.get_transactions.return_value = _make_many_transactions(50)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_transactions",
            {"start_date": "2026-03-01", "end_date": "2026-03-31", "limit": 10},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["transactions"]) == 10
    assert data["truncated"]["transactions"]["showing"] == 10
    assert data["truncated"]["transactions"]["total"] == 50


async def test_transactions_no_truncation_when_under_limit(
    server: Any, mock_client: MagicMock
) -> None:
    """No truncated field when transactions are under the limit."""
    mock_client.get_transactions.return_value = _make_many_transactions(5)
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-03-01", "end_date": "2026-03-31"},
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert len(data["transactions"]) == 5
    assert "truncated" not in data


async def test_transactions_summary_always_present(server: Any, mock_client: MagicMock) -> None:
    """Summary and categories must be present even when transactions are truncated."""
    mock_client.get_transactions.return_value = _make_many_transactions(200)
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-03-01", "end_date": "2026-03-31", "limit": 5},
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert len(data["transactions"]) == 5
    assert data["summary"]["money_out"] == 2000  # Full summary, not truncated
    assert len(data["categories"]) == 1


# --- _render truncation tests ---


@dataclasses.dataclass(frozen=True)
class _Row:
    date: date
    n: int


@dataclasses.dataclass(frozen=True)
class _Result:
    rows: tuple[_Row, ...]
    other: tuple[_Row, ...] = ()
    summary: str = "ok"


def _daily(days: int, per_day: int = 1, *, newest_first: bool = False) -> tuple[_Row, ...]:
    """``per_day`` rows on each of ``days`` days ending on _END."""
    rows = [
        _Row(date=_END - timedelta(days=d), n=d * per_day + k)
        for d in range(days)
        for k in range(per_day)
    ]
    return tuple(rows if newest_first else reversed(rows))


def _dates(data: dict[str, Any], field: str) -> list[str]:
    return [row["date"] for row in data[field]]


def test_render_compact_without_truncation() -> None:
    """Small output passes through as compact JSON with no truncated field."""
    text = _render(_Result(rows=_daily(3)), dated=("rows",), limit=10)
    data = json.loads(text)
    assert "truncated" not in data
    assert len(data["rows"]) == 3
    assert "\n" not in text
    assert ": " not in text


@pytest.mark.parametrize("newest_first", [False, True], ids=["oldest-first", "newest-first"])
def test_render_keeps_newest_days(newest_first: bool) -> None:
    """Truncation keeps the newest days whatever order the API used, in that order."""
    text = _render(_Result(rows=_daily(10, newest_first=newest_first)), dated=("rows",), limit=3)
    data = json.loads(text)
    kept = _dates(data, "rows")
    newest = [(_END - timedelta(days=d)).isoformat() for d in range(3)]
    assert sorted(kept) == sorted(newest)
    assert kept == (newest if newest_first else newest[::-1])
    assert data["truncated"]["rows"] == {"showing": 3, "total": 10}
    assert data["truncated"]["next_end_date"] == (_END - timedelta(days=3)).isoformat()
    assert "end_date=" in data["truncated"]["hint"]
    assert data["summary"] == "ok"


def test_render_never_splits_a_day() -> None:
    """A limit that falls mid-day keeps fewer rows rather than split the day."""
    data = json.loads(_render(_Result(rows=_daily(3, per_day=4)), dated=("rows",), limit=6))
    assert len(data["rows"]) == 4
    assert set(_dates(data, "rows")) == {_END.isoformat()}


def test_render_newest_day_is_whole_even_over_limit() -> None:
    """When one day has more rows than limit, that whole day still comes back."""
    data = json.loads(_render(_Result(rows=_daily(3, per_day=5)), dated=("rows",), limit=2))
    assert len(data["rows"]) == 5
    assert data["truncated"]["rows"] == {"showing": 5, "total": 15}


def test_render_one_cutoff_for_all_dated_lists() -> None:
    """Dated lists in one response share a cutoff, so one end_date pages them all."""
    rows = _daily(10)
    other = tuple(r for r in rows if r.date <= _END - timedelta(days=2))  # ends 2 days earlier
    data = json.loads(_render(_Result(rows=rows, other=other), dated=("rows", "other"), limit=3))
    cutoff = min(_dates(data, "rows"))
    assert len(data["rows"]) == 3
    assert all(d >= cutoff for d in _dates(data, "other"))
    assert data["truncated"]["next_end_date"] < cutoff


def test_render_baseline_row_omits_next_end_date() -> None:
    """If the only omitted rows predate start_date (Empower's baseline row),
    there is no earlier page to point at."""
    start = _END - timedelta(days=4)
    rows = _daily(6)  # oldest row is start - 1 day: the baseline
    data = json.loads(_render(_Result(rows=rows), dated=("rows",), limit=5, start_date=start))
    assert len(data["rows"]) == 5
    assert "next_end_date" not in data["truncated"]
    assert "before start_date" in data["truncated"]["hint"]


def test_render_baseline_before_weekend_start_omits_next_end_date() -> None:
    """start_date on a Sunday: the baseline is the Friday before and the first
    kept day is Monday. Only the baseline was cut, so there's no next page."""
    start = date(2026, 11, 1)  # Sunday
    friday = _Row(date=date(2026, 10, 30), n=0)
    week = tuple(_Row(date=date(2026, 11, 2) + timedelta(days=d), n=d + 1) for d in range(5))
    data = json.loads(
        _render(_Result(rows=(friday, *week)), dated=("rows",), limit=5, start_date=start)
    )
    assert len(data["rows"]) == 5
    assert "next_end_date" not in data["truncated"]
    assert "before start_date" in data["truncated"]["hint"]


def test_render_dated_and_undated_together() -> None:
    """get_quotes shape. The date cut runs first, sized against the undated list
    at full length; when the undated list alone exceeds the cap, the dated list
    keeps its newest day and the undated list is cut too, with both hints."""
    result = _Result(rows=_daily(60), other=_daily(200))
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "3000"}):
        text = _render(result, dated=("rows",), undated=("other",))
    data = json.loads(text)
    assert len(text) <= 3000
    assert max(_dates(data, "rows")) == _END.isoformat()
    assert data["truncated"]["rows"]["total"] == 60
    assert data["truncated"]["other"]["total"] == 200
    hint = data["truncated"]["hint"]
    assert "Showing the newest days" in hint
    assert "(response size cap reached)" in hint


def test_render_char_cap_keeps_newest_days() -> None:
    """Over the character cap, the newest days are kept and the output fits."""
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "2000"}):
        text = _render(_Result(rows=_daily(200)), dated=("rows",))
    data = json.loads(text)
    assert len(text) <= 2000
    assert 0 < len(data["rows"]) < 200
    assert max(_dates(data, "rows")) == _END.isoformat()


def test_render_char_cap_is_soft_for_the_newest_day() -> None:
    """A cap too small for even one day still returns that whole day."""
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "50"}):
        data = json.loads(_render(_Result(rows=_daily(5, per_day=3)), dated=("rows",)))
    assert len(data["rows"]) == 3


def test_render_undated_lists_keep_first_rows() -> None:
    """Undated lists keep their first rows, with a hint that says so."""
    data = json.loads(_render(_Result(rows=_daily(10)), undated=("rows",), limit=4))
    assert [r["n"] for r in data["rows"]] == [r.n for r in _daily(10)[:4]]
    assert data["truncated"]["rows"] == {"showing": 4, "total": 10}
    assert data["truncated"]["hint"] == "Showing the first 4 of 10 rows; pass a larger limit."
    assert "next_end_date" not in data["truncated"]


def test_render_unlisted_fields_are_never_cut() -> None:
    """Fields not named dated/undated (summaries, categories) stay complete."""
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "1000"}):
        data = json.loads(_render(_Result(rows=_daily(100), other=_daily(50)), dated=("rows",)))
    assert len(data["other"]) == 50
    assert "other" not in data["truncated"]


def test_render_env_var_override() -> None:
    """PC2_MCP_MAX_CHARS sets the cap."""
    result = _Result(rows=_daily(200))
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "1000"}):
        assert "truncated" in json.loads(_render(result, dated=("rows",)))
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        assert "truncated" not in json.loads(_render(result, dated=("rows",)))


async def test_balances_truncation_keeps_every_account(server: Any, mock_client: MagicMock) -> None:
    """Balances arrive account by account; the cut keeps whole days, so every
    account shows up for each day kept (not just the first accounts)."""
    days = 10
    balances = tuple(
        AccountBalance(date=_day(i, days), user_account_id=acct, balance=Decimal("1"))
        for acct in (1, 2, 3)
        for i in range(days)
    )
    mock_client.get_account_balances.return_value = AccountBalancesResult(
        balances=balances,
        summary=AccountBalancesSummary(
            account_count=3, latest_date=_END, latest_total=Decimal("3")
        ),
    )
    text = await _call_tool(
        server,
        "get_account_balances",
        {"start_date": "2027-01-01", "end_date": "2027-12-31", "limit": 6},
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert len(data["balances"]) == 6
    assert {b["user_account_id"] for b in data["balances"]} == {1, 2, 3}
    assert len({b["date"] for b in data["balances"]}) == 2


async def test_transactions_paging_reconciles(server: Any, mock_client: MagicMock) -> None:
    """Following next_end_date page by page returns every transaction exactly once."""
    everything = _make_many_transactions(300)

    def by_range(start: date, end: date) -> TransactionsResult:
        txns = tuple(t for t in everything.transactions if start <= t.date <= end)
        return dataclasses.replace(everything, transactions=txns)

    mock_client.get_transactions.side_effect = by_range
    start = everything.transactions[0].date.isoformat()
    end = _END.isoformat()
    seen: list[int] = []
    for _ in range(20):
        data = json.loads(
            await _call_tool(
                server,
                "get_transactions",
                {"start_date": start, "end_date": end, "limit": 70},
                mock_client=mock_client,
            )
        )
        seen.extend(t["user_transaction_id"] for t in data["transactions"])
        if "truncated" not in data:
            break
        end = data["truncated"]["next_end_date"]
    assert sorted(seen) == [t.user_transaction_id for t in everything.transactions]


# --- Net worth limit tests ---


def _make_many_net_worth_entries(n: int) -> NetWorthResult:
    """Create a NetWorthResult with n entries."""
    entries = tuple(
        NetWorthEntry(
            date=_day(i, n),
            networth=Decimal("50000"),
            total_assets=Decimal("60000"),
            total_liabilities=Decimal("10000"),
            total_cash=Decimal("5000"),
            total_investment=Decimal("45000"),
            total_credit=Decimal("0"),
            total_mortgage=Decimal("0"),
            total_loan=Decimal("10000"),
            total_other_assets=Decimal("0"),
            total_other_liabilities=Decimal("0"),
        )
        for i in range(n)
    )
    return NetWorthResult(
        entries=entries,
        summary=NetWorthSummary(
            date_range_change=Decimal("1000"),
            date_range_percentage_change=Decimal("2.04"),
            cash_change=Decimal("100"),
            cash_percentage_change=Decimal("2.04"),
            investment_change=Decimal("900"),
            investment_percentage_change=Decimal("2.04"),
            credit_change=Decimal("0"),
            credit_percentage_change=Decimal("0"),
            mortgage_change=Decimal("0"),
            mortgage_percentage_change=Decimal("0"),
            loan_change=Decimal("200"),
            loan_percentage_change=Decimal("2.04"),
            other_assets_change=Decimal("0"),
            other_assets_percentage_change=Decimal("0"),
            other_liabilities_change=Decimal("0"),
            other_liabilities_percentage_change=Decimal("0"),
        ),
    )


async def test_net_worth_default_limit(server: Any, mock_client: MagicMock) -> None:
    """Default limit=180 should truncate when there are more entries."""
    mock_client.get_net_worth.return_value = _make_many_net_worth_entries(250)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_net_worth",
            {"start_date": "2026-01-01", "end_date": "2026-12-31"},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["entries"]) == 180
    assert data["truncated"]["entries"]["showing"] == 180
    assert data["truncated"]["entries"]["total"] == 250
    assert "summary" in data


async def test_net_worth_custom_limit(server: Any, mock_client: MagicMock) -> None:
    """Custom limit should be respected."""
    mock_client.get_net_worth.return_value = _make_many_net_worth_entries(100)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_net_worth",
            {"start_date": "2026-01-01", "end_date": "2026-12-31", "limit": 30},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["entries"]) == 30
    assert data["truncated"]["entries"]["showing"] == 30
    assert data["truncated"]["entries"]["total"] == 100


async def test_net_worth_no_truncation(server: Any, mock_client: MagicMock) -> None:
    """No truncated field when under limit."""
    mock_client.get_net_worth.return_value = _make_many_net_worth_entries(50)
    text = await _call_tool(
        server,
        "get_net_worth",
        {"start_date": "2026-01-01", "end_date": "2026-03-31"},
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert len(data["entries"]) == 50
    assert "truncated" not in data


# --- Account balances limit tests ---


def _make_many_balances(n: int) -> AccountBalancesResult:
    """Create an AccountBalancesResult with n balance entries."""
    balances = tuple(
        AccountBalance(date=_day(i, n), user_account_id=1, balance=Decimal("5000.50"))
        for i in range(n)
    )
    return AccountBalancesResult(
        balances=balances,
        summary=AccountBalancesSummary(
            account_count=1,
            latest_date=date(2026, 4, 1),
            latest_total=Decimal("5000.50"),
        ),
    )


async def test_account_balances_default_limit(server: Any, mock_client: MagicMock) -> None:
    """Default limit=1000 should truncate when there are more entries."""
    mock_client.get_account_balances.return_value = _make_many_balances(1100)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_account_balances",
            {"start_date": "2026-01-01", "end_date": "2026-12-31"},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["balances"]) == 1000
    assert data["truncated"]["balances"]["showing"] == 1000
    assert data["truncated"]["balances"]["total"] == 1100


async def test_account_balances_custom_limit(server: Any, mock_client: MagicMock) -> None:
    """Custom limit should be respected."""
    mock_client.get_account_balances.return_value = _make_many_balances(100)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_account_balances",
            {"start_date": "2026-01-01", "end_date": "2026-12-31", "limit": 10},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["balances"]) == 10
    assert data["truncated"]["balances"]["showing"] == 10
    assert data["truncated"]["balances"]["total"] == 100


async def test_account_balances_no_truncation(server: Any, mock_client: MagicMock) -> None:
    """No truncated field when under limit."""
    mock_client.get_account_balances.return_value = _make_many_balances(50)
    text = await _call_tool(
        server,
        "get_account_balances",
        {"start_date": "2026-01-01", "end_date": "2026-03-31"},
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert len(data["balances"]) == 50
    assert "truncated" not in data


# --- Holdings limit tests ---


def _make_many_holdings(n: int) -> HoldingsResult:
    """Create a HoldingsResult with n holdings."""
    holdings = tuple(
        Holding(
            snapshot_date=date(2026, 4, 1),
            user_account_id=i % 5,
            ticker=f"TICK{i}",
            cusip=None,
            description=f"Security {i}",
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            value=Decimal("5000"),
            holding_type=None,
            security_type="ETF",
            holding_percentage=Decimal("1"),
            source="EMPOWER",
            cost_basis=Decimal("4000"),
            one_day_percent_change=Decimal("0.1"),
            one_day_value_change=Decimal("5"),
            fees_per_year=Decimal("1.50"),
            fund_fees=None,
        )
        for i in range(n)
    )
    return HoldingsResult(holdings=holdings, total_value=Decimal(str(n * 5000)))


async def test_holdings_default_limit(server: Any, mock_client: MagicMock) -> None:
    """Default limit=100 should truncate when there are more than 100 holdings."""
    mock_client.get_holdings.return_value = _make_many_holdings(150)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(server, "get_holdings", mock_client=mock_client)
    data = json.loads(text)
    assert len(data["holdings"]) == 100
    assert data["truncated"]["holdings"]["showing"] == 100
    assert data["truncated"]["holdings"]["total"] == 150
    assert data["total_value"] == 750000  # Total always present


async def test_holdings_custom_limit(server: Any, mock_client: MagicMock) -> None:
    """Custom limit should be respected."""
    mock_client.get_holdings.return_value = _make_many_holdings(50)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(server, "get_holdings", {"limit": 10}, mock_client=mock_client)
    data = json.loads(text)
    assert len(data["holdings"]) == 10
    assert data["truncated"]["holdings"]["showing"] == 10
    assert data["truncated"]["holdings"]["total"] == 50


async def test_holdings_no_truncation(server: Any, mock_client: MagicMock) -> None:
    """No truncated field when under limit."""
    text = await _call_tool(server, "get_holdings", mock_client=mock_client)
    data = json.loads(text)
    assert len(data["holdings"]) == 1
    assert "truncated" not in data


# --- Performance limit tests ---


def _make_many_performance(n_inv: int, n_bench: int) -> PerformanceResult:
    """Create a PerformanceResult with n_inv investment rows and n_bench benchmark rows."""
    investments = tuple(
        InvestmentPerformance(
            date=_day(i, n_inv),
            user_account_id=i % 3,
            performance=Decimal("0.05"),
        )
        for i in range(n_inv)
    )
    benchmarks = tuple(
        BenchmarkPerformance(
            date=_day(i, n_bench),
            benchmark=f"^BENCH{i % 6}",
            performance=Decimal("0.04"),
        )
        for i in range(n_bench)
    )
    return PerformanceResult(
        investments=investments,
        benchmarks=benchmarks,
        account_summaries=_mock_performance_result().account_summaries,
    )


async def test_performance_default_limit(server: Any, mock_client: MagicMock) -> None:
    """Default limit=500 should truncate when there are more entries."""
    mock_client.get_performance.return_value = _make_many_performance(600, 700)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_performance",
            {
                "start_date": "2026-03-01",
                "end_date": "2026-04-01",
                "account_ids": [2],
            },
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["investments"]) == 500
    assert data["truncated"]["investments"]["showing"] == 500
    assert data["truncated"]["investments"]["total"] == 600
    assert len(data["benchmarks"]) == 500
    assert data["truncated"]["benchmarks"]["showing"] == 500
    assert data["truncated"]["benchmarks"]["total"] == 700
    # Account summaries always present in full
    assert len(data["account_summaries"]) == 1


async def test_performance_custom_limit(server: Any, mock_client: MagicMock) -> None:
    """Custom limit should be respected for both investments and benchmarks."""
    mock_client.get_performance.return_value = _make_many_performance(100, 200)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_performance",
            {
                "start_date": "2026-03-01",
                "end_date": "2026-04-01",
                "account_ids": [2],
                "limit": 50,
            },
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["investments"]) == 50
    assert data["truncated"]["investments"]["showing"] == 50
    assert data["truncated"]["investments"]["total"] == 100
    assert len(data["benchmarks"]) == 50
    assert data["truncated"]["benchmarks"]["showing"] == 50
    assert data["truncated"]["benchmarks"]["total"] == 200


async def test_performance_no_truncation(server: Any, mock_client: MagicMock) -> None:
    """No truncated field when under limit."""
    text = await _call_tool(
        server,
        "get_performance",
        {
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
            "account_ids": [2],
        },
        mock_client=mock_client,
    )
    data = json.loads(text)
    assert len(data["investments"]) == 1
    assert len(data["benchmarks"]) == 1
    assert "truncated" not in data


# --- Negative / zero limit tests ---


async def test_transactions_negative_limit(server: Any, mock_client: MagicMock) -> None:
    """Negative limit fails the call without calling the API."""
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-03-01", "end_date": "2026-03-31", "limit": -1},
        mock_client=mock_client,
        expect_error=True,
    )
    assert "limit must be at least 1" in text
    mock_client.get_transactions.assert_not_called()


async def test_holdings_zero_limit(server: Any, mock_client: MagicMock) -> None:
    """Zero limit fails the call without calling the API."""
    text = await _call_tool(
        server,
        "get_holdings",
        {"limit": 0},
        mock_client=mock_client,
        expect_error=True,
    )
    assert "limit must be at least 1" in text
    mock_client.get_holdings.assert_not_called()


# --- Authentication tools (start_authentication / complete_authentication) ---
#
# Tests call the module-level tool functions directly with a mock Context, so
# we can inspect _AppContext state (pending_2fa_mode, client identity) after
# each call. Going through MCP transport would obscure those assertions.


from typing import ClassVar  # noqa: E402

from personalcapital2.mcp_server import (  # noqa: E402
    _AppContext,
    _get_client,
    complete_authentication,
    start_authentication,
)
from personalcapital2.types import TwoFactorMode as _TwoFactorMode  # noqa: E402


class _FakeAuthClient:
    """Stand-in for EmpowerClient for auth-tool tests.

    Each method's behavior is driven by class-level recipe lists (popped in
    order). Instance counters expose what was called for assertions.
    """

    instances: ClassVar[list[_FakeAuthClient]] = []
    login_recipe: ClassVar[list[BaseException | None]] = []
    send_2fa_recipe: ClassVar[list[BaseException | None]] = []
    verify_2fa_recipe: ClassVar[list[BaseException | None]] = []

    def __init__(self, session_path: Path | None = None) -> None:
        self.session_path = session_path
        self.login_calls = 0
        self.send_2fa_calls = 0
        self.send_2fa_modes: list[_TwoFactorMode] = []
        self.verify_2fa_calls = 0
        self.save_session_calls = 0
        self.load_session_calls = 0
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

    def send_2fa_challenge(self, mode: _TwoFactorMode) -> None:
        self.send_2fa_calls += 1
        self.send_2fa_modes.append(mode)
        err = type(self)._next(type(self).send_2fa_recipe)
        if err is not None:
            raise err

    def verify_2fa_and_login(self, mode: _TwoFactorMode, code: str, password: str) -> None:
        self.verify_2fa_calls += 1
        err = type(self)._next(type(self).verify_2fa_recipe)
        if err is not None:
            raise err

    def save_session(self, path: Path | None = None) -> None:
        self.save_session_calls += 1

    def load_session(self) -> None:
        self.load_session_calls += 1


def _make_ctx(app_ctx: _AppContext) -> Any:
    """Build a minimal mock Context whose request_context.lifespan_context
    points at the test's _AppContext.
    """
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    return ctx


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPOWER_EMAIL", "user@example.com")
    monkeypatch.setenv("EMPOWER_PASSWORD", "secret")


@pytest.fixture
def patch_auth_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace mcp_server.EmpowerClient with the auth-test fake. The fake is
    constructed by start_authentication via EmpowerClient(session_path=...).
    """
    _FakeAuthClient.reset()
    monkeypatch.setattr("personalcapital2.mcp_server.EmpowerClient", _FakeAuthClient)


def _make_app_ctx(tmp_path: Path) -> _AppContext:
    """Build an _AppContext with a sentinel client that tests can assert on
    (e.g. 'app_ctx.client is not original_client' after a successful auth)."""
    sentinel_client = _FakeAuthClient(session_path=tmp_path / "session.json")
    # Reset instances after the sentinel so test assertions see only the
    # clients spawned by start_authentication.
    _FakeAuthClient.instances = []
    return _AppContext(client=sentinel_client, session_path=tmp_path / "session.json")  # type: ignore[arg-type]


def test_start_authentication_no_2fa_required(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    app_ctx = _make_app_ctx(tmp_path)
    _FakeAuthClient.login_recipe = [None]  # device remembered, no 2FA

    result = start_authentication(_make_ctx(app_ctx))

    assert result == "Authenticated."
    assert app_ctx.pending_2fa_mode is None
    fresh = _FakeAuthClient.instances[0]
    assert fresh.login_calls == 1
    assert fresh.send_2fa_calls == 0
    assert fresh.save_session_calls == 1


def test_start_authentication_2fa_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    monkeypatch.setenv("EMPOWER_2FA_MODE", "sms")
    app_ctx = _make_app_ctx(tmp_path)
    original_client = app_ctx.client
    _FakeAuthClient.login_recipe = [TwoFactorRequiredError()]

    result = start_authentication(_make_ctx(app_ctx))

    assert "complete_authentication" in result
    assert "SMS" in result
    assert app_ctx.pending_2fa_mode is _TwoFactorMode.SMS
    fresh = _FakeAuthClient.instances[0]
    assert fresh.send_2fa_modes == [_TwoFactorMode.SMS]
    assert fresh.save_session_calls == 0  # don't save partial-auth state
    # The challenge client is kept apart; data tools keep using the original.
    assert app_ctx.pending_client is fresh
    assert app_ctx.client is original_client


def test_start_authentication_dispatch_failure_says_not_to_retry(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """Each call sends an SMS; when Empower refuses (e.g. it locked text codes),
    the error must not invite an immediate retry."""
    app_ctx = _make_app_ctx(tmp_path)
    _FakeAuthClient.login_recipe = [TwoFactorRequiredError()]
    _FakeAuthClient.send_2fa_recipe = [
        EmpowerAuthError("2FA challenge failed: Text message credential is locked.")
    ]

    with pytest.raises(ToolError) as exc_info:
        start_authentication(_make_ctx(app_ctx))

    msg = str(exc_info.value)
    assert msg.startswith("2FA challenge failed: Text message credential is locked. ")
    assert "don't retry right away" in msg
    assert app_ctx.pending_client is None


def test_start_authentication_missing_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patch_auth_client: None,
) -> None:
    monkeypatch.delenv("EMPOWER_EMAIL", raising=False)
    monkeypatch.delenv("EMPOWER_PASSWORD", raising=False)
    app_ctx = _make_app_ctx(tmp_path)

    with pytest.raises(ToolError) as exc_info:
        start_authentication(_make_ctx(app_ctx))

    result = str(exc_info.value)
    assert "EMPOWER_EMAIL" in result
    assert "EMPOWER_PASSWORD" in result
    assert "env" in result.lower()
    assert login_suggestion(tmp_path / "session.json") in result
    # No fresh client constructed when credentials are missing.
    assert _FakeAuthClient.instances == []


def test_start_authentication_2fa_required_mode_unset_defaults_to_sms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """With EMPOWER_2FA_MODE unset, 2FA defaults to SMS — the only method
    Empower offers — instead of erroring."""
    monkeypatch.delenv("EMPOWER_2FA_MODE", raising=False)
    app_ctx = _make_app_ctx(tmp_path)
    _FakeAuthClient.login_recipe = [TwoFactorRequiredError()]

    result = start_authentication(_make_ctx(app_ctx))

    assert "complete_authentication" in result
    assert "SMS" in result
    assert app_ctx.pending_2fa_mode is _TwoFactorMode.SMS
    fresh = _FakeAuthClient.instances[0]
    assert fresh.send_2fa_modes == [_TwoFactorMode.SMS]


def test_start_authentication_2fa_mode_email_tombstone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """A stale EMPOWER_2FA_MODE=email returns a clear tombstone error (Empower
    removed email 2FA) rather than dispatching a challenge that never arrives."""
    monkeypatch.setenv("EMPOWER_2FA_MODE", "email")
    app_ctx = _make_app_ctx(tmp_path)
    _FakeAuthClient.login_recipe = [TwoFactorRequiredError()]

    with pytest.raises(ToolError) as exc_info:
        start_authentication(_make_ctx(app_ctx))

    result = str(exc_info.value)
    assert "email" in result.lower()
    assert "sms" in result.lower()
    assert app_ctx.pending_2fa_mode is None
    fresh = _FakeAuthClient.instances[0]
    assert fresh.send_2fa_calls == 0


def test_complete_authentication_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """Pre-set pending_2fa_mode (simulating prior start_authentication) then
    verify the code.
    """
    fresh_client = _FakeAuthClient(session_path=tmp_path / "session.json")
    _FakeAuthClient.instances = []  # clear so test assertions see only post-setup
    app_ctx = _make_app_ctx(tmp_path)
    app_ctx.pending_2fa_mode = _TwoFactorMode.SMS
    app_ctx.pending_client = fresh_client  # type: ignore[assignment]  # test double

    result = complete_authentication(_make_ctx(app_ctx), code="123456")

    assert result == "Authenticated."
    assert app_ctx.pending_2fa_mode is None
    assert app_ctx.pending_client is None
    assert fresh_client.verify_2fa_calls == 1
    assert fresh_client.save_session_calls == 1
    # The verified client becomes the data client.
    assert app_ctx.client is fresh_client


@pytest.mark.parametrize(
    ("error", "expected_start", "says_new_code"),
    [
        (
            EmpowerAuthError("2FA verification failed: Incorrect verification code entered."),
            "2FA verification failed: Incorrect verification code entered. Call",
            True,
        ),
        (
            LoginRejectedError("Empower rejected the sign-in (Incorrect password entered.)."),
            "Empower rejected the sign-in (Incorrect password entered.).",
            False,
        ),
    ],
)
def test_complete_authentication_failure_messages(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
    error: EmpowerAuthError,
    expected_start: str,
    says_new_code: bool,
) -> None:
    """A wrong code says once that verification failed and names the next step;
    a rejected password reads as a rejection. Both clear the pending challenge."""
    client = _FakeAuthClient(session_path=tmp_path / "session.json")
    _FakeAuthClient.verify_2fa_recipe = [error]
    app_ctx = _AppContext(
        client=client,  # type: ignore[arg-type]
        session_path=tmp_path / "session.json",
        pending_2fa_mode=_TwoFactorMode.SMS,
        pending_client=client,  # type: ignore[arg-type]
    )

    with pytest.raises(ToolError) as exc_info:
        complete_authentication(_make_ctx(app_ctx), code="0000")

    result = str(exc_info.value)
    assert result.startswith(expected_start)
    assert result.count("2FA verification failed") <= 1
    assert ".." not in result
    assert ("Call start_authentication to send a new code." in result) is says_new_code
    assert app_ctx.pending_2fa_mode is None
    assert app_ctx.pending_client is None


def test_complete_authentication_no_pending_challenge(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    app_ctx = _make_app_ctx(tmp_path)
    assert app_ctx.pending_2fa_mode is None  # precondition

    with pytest.raises(ToolError) as exc_info:
        complete_authentication(_make_ctx(app_ctx), code="123456")

    result = str(exc_info.value)
    assert "No pending 2FA challenge" in result
    assert "start_authentication" in result
    # No verify call happened.
    assert app_ctx.client.verify_2fa_calls == 0  # type: ignore[attr-defined]


def test_start_authentication_replaces_client_on_success(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """Pin the fresh-client contract: a successful auth replaces app_ctx.client
    with the fresh instance. Without this guard, a future 'reuse the existing
    client' simplification could silently regress stale-cookie isolation."""
    app_ctx = _make_app_ctx(tmp_path)
    original_client = app_ctx.client
    _FakeAuthClient.login_recipe = [None]

    result = start_authentication(_make_ctx(app_ctx))

    assert result == "Authenticated."
    assert app_ctx.client is not original_client
    assert app_ctx.client is _FakeAuthClient.instances[0]


def test_start_authentication_keeps_old_client_on_failure(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """The other half of the fresh-client contract: on a failed login, the
    existing client stays put. Transient errors must not lose state."""
    app_ctx = _make_app_ctx(tmp_path)
    original_client = app_ctx.client
    _FakeAuthClient.login_recipe = [EmpowerAuthError("Bad credentials")]

    with pytest.raises(ToolError, match="Authentication failed"):
        start_authentication(_make_ctx(app_ctx))

    assert app_ctx.client is original_client
    assert app_ctx.pending_2fa_mode is None


def test_start_authentication_login_rejected(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """A rejection reads differently from a transient failure, and keeps the old client."""
    app_ctx = _make_app_ctx(tmp_path)
    original_client = app_ctx.client
    _FakeAuthClient.login_recipe = [
        LoginRejectedError("Empower rejected the sign-in (113: Please use a valid email address.).")
    ]

    with pytest.raises(ToolError) as exc_info:
        start_authentication(_make_ctx(app_ctx))

    result = str(exc_info.value)
    assert result.startswith("Empower rejected the sign-in (113:")
    assert "Authentication failed" not in result
    assert app_ctx.client is original_client


def test_start_authentication_no_2fa_clears_pending_mode(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    """Pin Bug 2: stale pending_2fa_mode from an earlier attempt must be
    cleared on a successful no-2FA login (e.g. user retried after partial
    flow and the device is now remembered)."""
    app_ctx = _make_app_ctx(tmp_path)
    app_ctx.pending_2fa_mode = _TwoFactorMode.SMS  # stale state from prior attempt
    _FakeAuthClient.login_recipe = [None]

    start_authentication(_make_ctx(app_ctx))

    assert app_ctx.pending_2fa_mode is None
    assert app_ctx.pending_client is None


def test_get_client_reloads_session_during_2fa_window(
    tmp_path: Path,
    patch_auth_client: None,
) -> None:
    """An abandoned 2FA challenge must not stop data tools from picking up a
    session saved by `pc2 login` in a terminal. The data client reloads from
    disk on every call; the challenge client's in-memory cookies (which
    load_session() would replace, not merge) are never touched."""
    data_client = _FakeAuthClient(session_path=tmp_path / "session.json")
    challenge_client = _FakeAuthClient(session_path=tmp_path / "session.json")
    _FakeAuthClient.instances = []
    app_ctx = _AppContext(
        client=data_client,  # type: ignore[arg-type]
        session_path=tmp_path / "session.json",
        pending_2fa_mode=_TwoFactorMode.SMS,
        pending_client=challenge_client,  # type: ignore[arg-type]
    )

    assert _get_client(_make_ctx(app_ctx)) is data_client
    assert data_client.load_session_calls == 1
    assert challenge_client.load_session_calls == 0


async def test_server_info_reports_package_version(server: Any) -> None:
    """mcp 2.x sends an empty serverInfo.version unless one is passed."""
    from importlib.metadata import version

    from mcp import Client

    async with Client(server, mode="legacy") as client:
        info = client.server_info
    assert info is not None
    assert info.name == "empower"
    assert info.version == version("personalcapital2")
