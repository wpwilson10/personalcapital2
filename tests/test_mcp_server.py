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

mcp_sdk = pytest.importorskip("mcp", reason="mcp extra not installed")

from personalcapital2.mcp_server import _serialize_list, create_server  # noqa: E402
from personalcapital2.models import (  # noqa: E402
    Account,
    AccountBalance,
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
    client.get_account_balances.return_value = [
        AccountBalance(date=date(2026, 4, 1), user_account_id=1, balance=Decimal("5000.50")),
    ]
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
    assert isinstance(data, list)
    assert data[0]["user_account_id"] == 1
    assert data[0]["balance"] == 5000.5


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


# --- Error tests ---


async def test_missing_session_file(tmp_path: Path) -> None:
    """Server should raise when session file doesn't exist."""
    missing = tmp_path / "nonexistent.json"
    srv = create_server(session_path=missing)

    from mcp.shared.memory import create_connected_server_and_client_session

    with pytest.raises(BaseException) as exc_info:
        async with create_connected_server_and_client_session(srv._mcp_server):
            pass

    # The FileNotFoundError is wrapped in ExceptionGroup by anyio
    exc_text = str(exc_info.value)
    if hasattr(exc_info.value, "exceptions"):
        exc_text = " ".join(str(e) for e in exc_info.value.exceptions)  # type: ignore[union-attr]
    assert "No session file" in exc_text


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


async def test_all_eight_tools_registered(server: Any) -> None:
    """Verify all 8 tools are registered."""
    tools = await server.list_tools()
    names = {t.name for t in tools}
    expected = {
        "get_accounts",
        "get_transactions",
        "get_holdings",
        "get_net_worth",
        "get_account_balances",
        "get_performance",
        "get_quotes",
        "get_spending",
    }
    assert names == expected


# --- Serialization tests ---


def test_serialize_list_with_account_balances() -> None:
    items = [
        AccountBalance(date=date(2026, 4, 1), user_account_id=1, balance=Decimal("5000.50")),
        AccountBalance(date=date(2026, 4, 2), user_account_id=1, balance=Decimal("5100")),
    ]
    text = _serialize_list(items)
    data = json.loads(text)
    assert len(data) == 2
    assert data[0]["date"] == "2026-04-01"
    assert data[0]["balance"] == 5000.5
    # Integer Decimals serialize as int
    assert data[1]["balance"] == 5100
    assert isinstance(data[1]["balance"], int)
