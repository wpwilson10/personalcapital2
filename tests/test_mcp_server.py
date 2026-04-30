"""Tests for MCP server tool functions."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

mcp_sdk = pytest.importorskip("mcp", reason="mcp extra not installed")

from personalcapital2.exceptions import (  # noqa: E402
    EmpowerAPIError,
    EmpowerAuthError,
    EmpowerNetworkError,
    TwoFactorRequiredError,
)
from personalcapital2.mcp_server import (  # noqa: E402
    _apply_limit,
    _enforce_char_cap,
    _validate_date_range,
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
    f.write_text('{"csrf": "test", "cookies": {}}')
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
) -> str:
    """Call a tool via in-memory MCP transport and return the text content."""
    from mcp.shared.memory import create_connected_server_and_client_session

    if mock_client:
        ctx = patch("personalcapital2.mcp_server.EmpowerClient", return_value=mock_client)
    else:
        ctx = patch("personalcapital2.mcp_server.EmpowerClient")

    with ctx:
        async with create_connected_server_and_client_session(
            server._mcp_server,
        ) as client_session:
            result = await client_session.call_tool(name, arguments or {})
    assert not result.isError, f"Tool {name} returned error: {result.content}"
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
    """Auth errors should return a helpful message, not a traceback."""
    mock_client.get_accounts.side_effect = EmpowerAuthError("Session expired")
    text = await _call_tool(server, "get_accounts", mock_client=mock_client)
    assert "Error:" in text
    assert "Session expired" in text


async def test_handle_tool_errors_auth_branch_directs_to_mcp_tools(
    server: Any, mock_client: MagicMock
) -> None:
    """The wrapped auth-error message must direct agents at start_authentication
    and complete_authentication, NOT 'pc2 login'. Pins the public message
    contract for every data tool wrapped by _handle_tool_errors.
    """
    mock_client.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")
    text = await _call_tool(server, "get_accounts", mock_client=mock_client)
    assert "start_authentication" in text
    assert "complete_authentication" in text
    assert "pc2 login" not in text


async def test_api_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """API errors should return the error message."""
    mock_client.get_transactions.side_effect = EmpowerAPIError("Rate limited")
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-03-01", "end_date": "2026-03-31"},
        mock_client=mock_client,
    )
    assert "Error:" in text
    assert "Rate limited" in text


async def test_network_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """Defensive: an un-wrapped requests.RequestException still produces a readable message."""
    mock_client.get_holdings.side_effect = requests.ConnectionError("DNS resolution failed")
    text = await _call_tool(server, "get_holdings", mock_client=mock_client)
    assert "Error:" in text
    assert "Network request failed" in text


async def test_empower_network_error_returns_message(server: Any, mock_client: MagicMock) -> None:
    """EmpowerNetworkError (typed transport error from client._request) returns
    an agent-friendly retry hint."""
    mock_client.get_holdings.side_effect = EmpowerNetworkError(
        "Request to https://pc-api.empower-retirement.com failed: connection refused"
    )
    text = await _call_tool(server, "get_holdings", mock_client=mock_client)
    assert "Error:" in text
    assert "Network request to Empower failed" in text
    assert "Check connection and retry" in text


# --- Date validation tests ---


def test_validate_date_range_valid() -> None:
    assert _validate_date_range(date(2026, 1, 1), date(2026, 3, 31)) is None


def test_validate_date_range_same_day() -> None:
    assert _validate_date_range(date(2026, 3, 15), date(2026, 3, 15)) is None


def test_validate_date_range_reversed() -> None:
    result = _validate_date_range(date(2026, 3, 31), date(2026, 1, 1))
    assert result is not None
    assert "start_date" in result
    assert "end_date" in result


async def test_reversed_dates_return_error(server: Any, mock_client: MagicMock) -> None:
    """Tools should reject reversed date ranges without hitting the API."""
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-04-01", "end_date": "2026-03-01"},
        mock_client=mock_client,
    )
    assert "Error:" in text
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

    from mcp.shared.memory import create_connected_server_and_client_session

    with caplog.at_level(logging.WARNING, logger="personalcapital2.mcp_server"):
        async with create_connected_server_and_client_session(srv._mcp_server):
            pass

    messages = [r.getMessage() for r in caplog.records]
    assert any("No session file" in m and "start_authentication" in m for m in messages), messages


async def test_missing_session_file_data_tool_directs_agent_to_start_authentication(
    tmp_path: Path,
) -> None:
    """When the cached session is missing, a data tool call must return an
    error string mentioning start_authentication (not 'pc2 login') — pins the
    _handle_tool_errors message contract for the cold-start path."""
    missing = tmp_path / "nonexistent.json"
    srv = create_server(session_path=missing)

    # Real EmpowerClient against a missing session — get_accounts will hit
    # the API and fail with EmpowerAuthError, which _handle_tool_errors then
    # rewrites to the agent-friendly message.
    from mcp.shared.memory import create_connected_server_and_client_session

    fake_client = MagicMock()
    fake_client.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")

    with patch("personalcapital2.mcp_server.EmpowerClient", return_value=fake_client):
        async with create_connected_server_and_client_session(srv._mcp_server) as session:
            result = await session.call_tool("get_accounts", {})

    assert len(result.content) > 0
    text = result.content[0].text  # type: ignore[union-attr]  # text content has .text
    assert "start_authentication" in text
    assert "complete_authentication" in text
    assert "pc2 login" not in text


# --- Tool registration tests ---


async def test_tools_have_no_output_schema(server: Any) -> None:
    """Verify no tools have outputSchema (would break Claude Code)."""
    tools = await server.list_tools()
    for tool in tools:
        assert tool.outputSchema is None, f"Tool {tool.name} has outputSchema set"


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


def _make_many_transactions(n: int) -> TransactionsResult:
    """Create a TransactionsResult with n transactions."""
    txns = tuple(
        Transaction(
            user_transaction_id=i,
            user_account_id=1,
            date=date(2026, 3, 15),
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


# --- Character cap tests ---


def test_apply_limit_under_limit() -> None:
    """_apply_limit should pass through when under limit."""
    data = json.dumps({"items": [1, 2, 3], "summary": "ok"})
    result = _apply_limit(data, "items", 10)
    assert result == data  # Unchanged


def test_apply_limit_over_limit() -> None:
    """_apply_limit should truncate and add metadata."""
    data = json.dumps({"items": list(range(20)), "summary": "ok"})
    result = _apply_limit(data, "items", 5)
    parsed = json.loads(result)
    assert len(parsed["items"]) == 5
    assert parsed["truncated"]["items"]["showing"] == 5
    assert parsed["truncated"]["items"]["total"] == 20
    assert parsed["summary"] == "ok"  # Other fields untouched


def test_enforce_char_cap_under_limit() -> None:
    """_enforce_char_cap should pass through small outputs."""
    small = json.dumps({"entries": [1, 2, 3]})
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "10000"}):
        result = _enforce_char_cap(small)
    assert result == small


def test_enforce_char_cap_over_limit() -> None:
    """_enforce_char_cap should truncate the largest list and add metadata."""
    # Create output that exceeds 500 chars
    big_list = [{"value": f"item-{i:04d}", "data": "x" * 50} for i in range(100)]
    data = json.dumps({"entries": big_list, "summary": {"total": 100}}, indent=2)
    assert len(data) > 500  # Sanity check

    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "500"}):
        result = _enforce_char_cap(data)

    assert len(result) <= 500
    parsed = json.loads(result)
    assert parsed["truncated"]["entries"]["total"] == 100
    assert parsed["truncated"]["entries"]["showing"] < 100
    assert "hint" in parsed["truncated"]
    assert parsed["summary"] == {"total": 100}  # Summary untouched


def test_enforce_char_cap_env_var_override() -> None:
    """PC2_MCP_MAX_CHARS env var should override the default."""
    big_list = list(range(200))
    data = json.dumps({"items": big_list}, indent=2)

    # With a very small cap, it should truncate
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "100"}):
        result = _enforce_char_cap(data)
    parsed = json.loads(result)
    assert "truncated" in parsed

    # With a large cap, it should pass through
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        result = _enforce_char_cap(data)
    assert json.loads(result) == {"items": big_list}


def test_enforce_char_cap_preserves_prior_total() -> None:
    """When _apply_limit truncates first, _enforce_char_cap must keep the original total."""
    # Simulate _apply_limit already truncated 500 -> 100, setting truncated metadata
    items = [{"value": f"item-{i:04d}", "data": "x" * 50} for i in range(100)]
    data = json.dumps(
        {
            "entries": items,
            "summary": "ok",
            "truncated": {"entries": {"showing": 100, "total": 500}},
        },
        indent=2,
    )

    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "2000"}):
        result = _enforce_char_cap(data)

    parsed = json.loads(result)
    assert parsed["truncated"]["entries"]["total"] == 500  # Original total preserved
    assert parsed["truncated"]["entries"]["showing"] < 100


def test_enforce_char_cap_no_list_fields() -> None:
    """_enforce_char_cap should not crash when there are no list fields to truncate."""
    # Create a large string-only payload
    data = json.dumps({"text": "x" * 1000, "number": 42})
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "100"}):
        result = _enforce_char_cap(data)
    # Can't truncate — returns original
    assert result == data


def test_enforce_char_cap_multi_list() -> None:
    """_enforce_char_cap should truncate multiple list fields to fit within the cap."""
    # Simulate PerformanceResult-like data with 3 large list fields
    list_a = [{"id": i, "data": "a" * 30} for i in range(50)]
    list_b = [{"id": i, "data": "b" * 30} for i in range(40)]
    list_c = [{"id": i, "data": "c" * 30} for i in range(30)]
    data = json.dumps(
        {"investments": list_a, "benchmarks": list_b, "summaries": list_c},
        indent=2,
    )
    # Cap is small enough that truncating only the largest list isn't sufficient
    cap = len(data) // 4
    assert cap < len(data)

    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": str(cap)}):
        result = _enforce_char_cap(data)

    assert len(result) <= cap
    parsed = json.loads(result)
    assert "truncated" in parsed
    # At least two fields should have been truncated
    truncated_fields = [k for k in parsed["truncated"] if k != "hint"]
    assert len(truncated_fields) >= 2


# --- Net worth limit tests ---


def _make_many_net_worth_entries(n: int) -> NetWorthResult:
    """Create a NetWorthResult with n entries."""
    entries = tuple(
        NetWorthEntry(
            date=date(2026, 1, 1),
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
        for _ in range(n)
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
        AccountBalance(date=date(2026, 4, 1), user_account_id=1, balance=Decimal("5000.50"))
        for _ in range(n)
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
    """Default limit=500 should truncate when there are more entries."""
    mock_client.get_account_balances.return_value = _make_many_balances(600)
    with patch.dict("os.environ", {"PC2_MCP_MAX_CHARS": "999999"}):
        text = await _call_tool(
            server,
            "get_account_balances",
            {"start_date": "2026-01-01", "end_date": "2026-12-31"},
            mock_client=mock_client,
        )
    data = json.loads(text)
    assert len(data["balances"]) == 500
    assert data["truncated"]["balances"]["showing"] == 500
    assert data["truncated"]["balances"]["total"] == 600


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
            date=date(2026, 4, 1),
            user_account_id=i % 3,
            performance=Decimal("0.05"),
        )
        for i in range(n_inv)
    )
    benchmarks = tuple(
        BenchmarkPerformance(
            date=date(2026, 4, 1),
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


def test_apply_limit_negative() -> None:
    """_apply_limit should be a no-op for negative limits."""
    data = json.dumps({"items": [1, 2, 3, 4, 5], "summary": "ok"})
    result = _apply_limit(data, "items", -1)
    assert result == data  # Unchanged


def test_apply_limit_zero() -> None:
    """_apply_limit should be a no-op for limit=0."""
    data = json.dumps({"items": [1, 2, 3, 4, 5], "summary": "ok"})
    result = _apply_limit(data, "items", 0)
    assert result == data  # Unchanged


async def test_transactions_negative_limit(server: Any, mock_client: MagicMock) -> None:
    """Negative limit should return an error without calling the API."""
    text = await _call_tool(
        server,
        "get_transactions",
        {"start_date": "2026-03-01", "end_date": "2026-03-31", "limit": -1},
        mock_client=mock_client,
    )
    assert "Error:" in text
    assert "limit must be at least 1" in text
    mock_client.get_transactions.assert_not_called()


async def test_holdings_zero_limit(server: Any, mock_client: MagicMock) -> None:
    """Zero limit should return an error without calling the API."""
    text = await _call_tool(
        server,
        "get_holdings",
        {"limit": 0},
        mock_client=mock_client,
    )
    assert "Error:" in text
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
    _FakeAuthClient.login_recipe = [TwoFactorRequiredError()]

    result = start_authentication(_make_ctx(app_ctx))

    assert "complete_authentication" in result
    assert "SMS" in result
    assert app_ctx.pending_2fa_mode is _TwoFactorMode.SMS
    fresh = _FakeAuthClient.instances[0]
    assert fresh.send_2fa_modes == [_TwoFactorMode.SMS]
    assert fresh.save_session_calls == 0  # don't save partial-auth state


def test_start_authentication_missing_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patch_auth_client: None,
) -> None:
    monkeypatch.delenv("EMPOWER_EMAIL", raising=False)
    monkeypatch.delenv("EMPOWER_PASSWORD", raising=False)
    app_ctx = _make_app_ctx(tmp_path)

    result = start_authentication(_make_ctx(app_ctx))

    assert "EMPOWER_EMAIL" in result
    assert "EMPOWER_PASSWORD" in result
    assert "env" in result.lower()
    # No fresh client constructed when credentials are missing.
    assert _FakeAuthClient.instances == []


def test_start_authentication_2fa_required_but_mode_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    monkeypatch.delenv("EMPOWER_2FA_MODE", raising=False)
    app_ctx = _make_app_ctx(tmp_path)
    _FakeAuthClient.login_recipe = [TwoFactorRequiredError()]

    result = start_authentication(_make_ctx(app_ctx))

    assert "EMPOWER_2FA_MODE" in result
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
    app_ctx = _AppContext(
        client=fresh_client,  # type: ignore[arg-type]
        session_path=tmp_path / "session.json",
        pending_2fa_mode=_TwoFactorMode.SMS,
    )

    result = complete_authentication(_make_ctx(app_ctx), code="123456")

    assert result == "Authenticated."
    assert app_ctx.pending_2fa_mode is None
    assert fresh_client.verify_2fa_calls == 1
    assert fresh_client.save_session_calls == 1


def test_complete_authentication_no_pending_challenge(
    tmp_path: Path,
    auth_env: None,
    patch_auth_client: None,
) -> None:
    app_ctx = _make_app_ctx(tmp_path)
    assert app_ctx.pending_2fa_mode is None  # precondition

    result = complete_authentication(_make_ctx(app_ctx), code="123456")

    assert "no pending 2FA challenge" in result
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

    result = start_authentication(_make_ctx(app_ctx))

    assert "authentication failed" in result
    assert app_ctx.client is original_client
    assert app_ctx.pending_2fa_mode is None


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


def test_get_client_skips_load_session_during_2fa_window(
    tmp_path: Path,
    patch_auth_client: None,
) -> None:
    """Pin Bug 1: load_session() replaces (not merges) cookies, which would
    clobber the in-memory challenge cookies that complete_authentication needs.
    The gate in _get_client must skip the reload while pending_2fa_mode is set.
    """
    fresh_client = _FakeAuthClient(session_path=tmp_path / "session.json")
    _FakeAuthClient.instances = []
    app_ctx = _AppContext(
        client=fresh_client,  # type: ignore[arg-type]
        session_path=tmp_path / "session.json",
        pending_2fa_mode=_TwoFactorMode.SMS,
    )
    ctx = _make_ctx(app_ctx)

    _get_client(ctx)
    assert fresh_client.load_session_calls == 0, (
        "load_session must NOT be called while pending_2fa_mode is set"
    )

    # Clear the gate; subsequent calls reload as before.
    app_ctx.pending_2fa_mode = None
    _get_client(ctx)
    assert fresh_client.load_session_calls == 1
