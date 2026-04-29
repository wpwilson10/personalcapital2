"""Tests for the pc2 CLI."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from personalcapital2.cli import (
    EXIT_API,
    EXIT_AUTH,
    EXIT_NETWORK,
    EXIT_USAGE,
    AgentArgumentParser,
    _parse_account_ids,
    _parse_date,
    _serialize_csv,
    _serialize_json,
    _validate_dates,
    build_parser,
    main,
)
from personalcapital2.exceptions import (
    EmpowerAPIError,
    EmpowerAuthError,
    EmpowerNetworkError,
)
from personalcapital2.models import (
    Account,
    AccountBalance,
    AccountBalancesResult,
    AccountBalancesSummary,
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

# --- _parse_date unit tests ---


def test_parse_date_iso() -> None:
    assert _parse_date("2026-01-15") == date(2026, 1, 15)


def test_parse_date_today() -> None:
    assert _parse_date("today") == date.today()


def test_parse_date_days_ago() -> None:
    assert _parse_date("30d") == date.today() - timedelta(days=30)


def test_parse_date_zero_days() -> None:
    assert _parse_date("0d") == date.today()


def test_parse_date_month_begin() -> None:
    result = _parse_date("mb")
    assert result.day == 1
    assert result.month == date.today().month
    assert result.year == date.today().year


def test_parse_date_month_begin_back() -> None:
    result = _parse_date("mb-3")
    today = date.today()
    expected_month = today.month - 3
    expected_year = today.year
    while expected_month < 1:
        expected_month += 12
        expected_year -= 1
    assert result == date(expected_year, expected_month, 1)


def test_parse_date_month_end() -> None:
    result = _parse_date("me")
    assert result.month == date.today().month
    # Last day of current month
    import calendar

    expected_day = calendar.monthrange(date.today().year, date.today().month)[1]
    assert result.day == expected_day


def test_parse_date_month_end_back() -> None:
    result = _parse_date("me-1")
    today = date.today()
    expected_month = today.month - 1
    expected_year = today.year
    if expected_month < 1:
        expected_month += 12
        expected_year -= 1
    import calendar

    expected_day = calendar.monthrange(expected_year, expected_month)[1]
    assert result == date(expected_year, expected_month, expected_day)


def test_parse_date_month_begin_wraps_year() -> None:
    """mb-N that crosses a year boundary."""
    result = _parse_date("mb-12")
    today = date.today()
    expected_month = today.month - 12
    expected_year = today.year
    while expected_month < 1:
        expected_month += 12
        expected_year -= 1
    assert result == date(expected_year, expected_month, 1)


def test_parse_date_year_begin() -> None:
    result = _parse_date("yb")
    assert result == date(date.today().year, 1, 1)


def test_parse_date_year_begin_back() -> None:
    result = _parse_date("yb-2")
    assert result == date(date.today().year - 2, 1, 1)


def test_parse_date_year_end() -> None:
    result = _parse_date("ye")
    assert result == date(date.today().year, 12, 31)


def test_parse_date_year_end_back() -> None:
    result = _parse_date("ye-1")
    assert result == date(date.today().year - 1, 12, 31)


def test_parse_date_invalid() -> None:
    with pytest.raises(Exception, match="invalid date"):
        _parse_date("not-a-date")


def test_parse_date_invalid_iso() -> None:
    with pytest.raises(Exception, match="invalid date"):
        _parse_date("2026-13-01")


# --- _parse_account_ids unit tests ---


def test_parse_account_ids_single() -> None:
    assert _parse_account_ids("100") == [100]


def test_parse_account_ids_multiple() -> None:
    assert _parse_account_ids("100,200,300") == [100, 200, 300]


def test_parse_account_ids_with_spaces() -> None:
    assert _parse_account_ids("100, 200, 300") == [100, 200, 300]


def test_parse_account_ids_empty() -> None:
    with pytest.raises(Exception, match="must not be empty"):
        _parse_account_ids("")


def test_parse_account_ids_non_numeric() -> None:
    with pytest.raises(Exception, match="must be comma-separated integers"):
        _parse_account_ids("abc,def")


# --- Serialization unit tests ---


def _sample_account() -> Account:
    return Account(
        user_account_id=100,
        account_id="A-1",
        name="Checking",
        firm_name="Big Bank",
        account_type="BANK",
        account_type_group="CASH",
        product_type="CHECKING",
        currency="USD",
        is_asset=True,
        is_closed=False,
        created_at=date(2024, 1, 1),
        balance=Decimal("5000"),
        available_cash=None,
        account_type_subtype=None,
        last_refreshed=None,
        oldest_transaction_date=None,
        advisory_fee_percentage=None,
        fees_per_year=None,
        fund_fees=None,
        total_fee=None,
    )


def _sample_transaction() -> Transaction:
    return Transaction(
        user_transaction_id=500,
        user_account_id=100,
        date=date(2026, 1, 15),
        amount=Decimal("42.50"),
        is_cash_in=False,
        is_income=False,
        is_spending=True,
        description="Coffee Shop",
        original_description="COFFEE SHOP #99",
        simple_description="Coffee",
        category_id=3,
        category_name="Food/Dining",
        category_type="EXPENSE",
        merchant="Java Joe",
        merchant_id=None,
        merchant_type=None,
        transaction_type="Purchase",
        sub_type=None,
        status="posted",
        currency="USD",
        is_duplicate=False,
    )


def test_serialize_json_models() -> None:
    items: list[object] = [_sample_account()]
    result = _serialize_json(items)
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["user_account_id"] == 100
    assert parsed[0]["name"] == "Checking"


def test_serialize_json_empty() -> None:
    assert _serialize_json([]) == "[]"


def test_serialize_json_dates_become_strings() -> None:
    items: list[object] = [_sample_account()]
    result = _serialize_json(items)
    parsed = json.loads(result)
    assert parsed[0]["created_at"] == "2024-01-01"


def test_json_default_raises_on_unknown_type() -> None:
    from personalcapital2.cli import _json_default

    with pytest.raises(TypeError, match="not JSON serializable"):
        _json_default(object())


def test_serialize_csv_models() -> None:
    items: list[object] = [_sample_account()]
    result = _serialize_csv(items)
    lines = result.strip().split("\n")
    assert len(lines) == 2  # header + 1 row
    assert "user_account_id" in lines[0]
    assert "100" in lines[1]


def test_serialize_csv_empty() -> None:
    assert _serialize_csv([]) == ""


def test_serialize_csv_none_fields() -> None:
    """None fields should serialize as empty string in CSV."""
    txn = Transaction(
        user_transaction_id=1,
        user_account_id=2,
        date=date(2026, 1, 1),
        amount=Decimal("10"),
        is_cash_in=False,
        is_income=False,
        is_spending=True,
        description="Test",
        original_description=None,
        simple_description=None,
        category_id=None,
        category_name=None,
        category_type=None,
        merchant=None,
        merchant_id=None,
        merchant_type=None,
        transaction_type=None,
        sub_type=None,
        status=None,
        currency="USD",
        is_duplicate=False,
    )
    items: list[object] = [txn]
    result = _serialize_csv(items)
    # csv.DictWriter writes None as empty string
    parsed_lines = result.strip().split("\n")
    assert len(parsed_lines) == 2


# --- build_parser tests ---


def test_parser_has_subcommands() -> None:
    parser = build_parser()
    # Parse a known subcommand
    args = parser.parse_args(["accounts"])
    assert args.command == "accounts"


def test_parser_transactions_defaults_dates() -> None:
    parser = build_parser()
    args = parser.parse_args(["transactions"])
    assert args.start == date.today() - timedelta(days=30)
    assert args.end == date.today()


def test_parser_version(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "pc2" in captured.out


def test_parser_performance_requires_account_ids() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["performance", "--start", "today", "--end", "today"])


def test_parser_format_default_json() -> None:
    parser = build_parser()
    args = parser.parse_args(["accounts"])
    assert args.format == "json"


def test_parser_format_csv() -> None:
    parser = build_parser()
    args = parser.parse_args(["--format", "csv", "accounts"])
    assert args.format == "csv"


def test_parser_raw_endpoint() -> None:
    parser = build_parser()
    args = parser.parse_args(["raw", "/newaccount/getAccounts2"])
    assert args.endpoint == "/newaccount/getAccounts2"


def test_parser_raw_data_pairs() -> None:
    parser = build_parser()
    args = parser.parse_args(["raw", "/endpoint", "--data", "key1=val1", "--data", "key2=val2"])
    assert args.data == ["key1=val1", "key2=val2"]


def test_parser_is_agent_argument_parser() -> None:
    """build_parser returns AgentArgumentParser for structured errors."""
    parser = build_parser()
    assert isinstance(parser, AgentArgumentParser)


def test_parser_format_after_subcommand() -> None:
    """--format works after the subcommand (not just before)."""
    parser = build_parser()
    args = parser.parse_args(["accounts", "--format", "csv"])
    assert args.format == "csv"


def test_parser_format_before_and_after_identical() -> None:
    """Both positions produce the same result."""
    parser = build_parser()
    args_before = parser.parse_args(["--format", "csv", "accounts"])
    args_after = parser.parse_args(["accounts", "--format", "csv"])
    assert args_before.format == args_after.format == "csv"


def test_parser_session_after_subcommand(tmp_path: Path) -> None:
    """--session works after the subcommand."""
    from pathlib import Path as _Path

    parser = build_parser()
    session_path = str(tmp_path / "test.json")
    args = parser.parse_args(["accounts", "--session", session_path])
    assert args.session == _Path(session_path)


def test_parser_format_default_not_overridden_by_subparser() -> None:
    """When --format is not passed, the main parser default (json) is used."""
    parser = build_parser()
    args = parser.parse_args(["accounts"])
    assert args.format == "json"


# --- Structured argparse error tests ---


def test_argparse_error_is_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Argparse errors produce JSON to stderr, not plain text."""
    with pytest.raises(SystemExit) as exc_info:
        main(["transactions", "--start", "bad-date"])

    assert exc_info.value.code == EXIT_USAGE
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "UsageError"
    assert "error" in err
    # Nothing to stdout
    assert captured.out == ""


def test_argparse_unknown_flag_is_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Unknown flags produce structured JSON errors."""
    with pytest.raises(SystemExit) as exc_info:
        main(["accounts", "--bogus"])

    assert exc_info.value.code == EXIT_USAGE
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "UsageError"


def test_argparse_account_ids_error_has_suggestion(capsys: pytest.CaptureFixture[str]) -> None:
    """Account-ids validation errors include a suggestion to list accounts."""
    with pytest.raises(SystemExit) as exc_info:
        main(["performance", "--start", "today", "--end", "today", "--account-ids", "abc"])

    assert exc_info.value.code == EXIT_USAGE
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "UsageError"
    assert err["suggestion"] == "List account IDs with: pc2 accounts"


# --- Help text tests ---


def test_help_shows_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    """Top-level --help includes exit code documentation."""
    with pytest.raises(SystemExit):
        main(["--help"])

    captured = capsys.readouterr()
    assert "exit codes:" in captured.out
    assert "authentication error" in captured.out
    assert "usage error" in captured.out


def test_help_shows_examples(capsys: pytest.CaptureFixture[str]) -> None:
    """Top-level --help includes usage examples."""
    with pytest.raises(SystemExit):
        main(["--help"])

    captured = capsys.readouterr()
    assert "examples:" in captured.out
    assert "pc2 accounts" in captured.out


def test_transactions_help_shows_examples(capsys: pytest.CaptureFixture[str]) -> None:
    """Subcommand --help includes examples."""
    with pytest.raises(SystemExit):
        main(["transactions", "--help"])

    captured = capsys.readouterr()
    assert "examples:" in captured.out
    assert "pc2 transactions" in captured.out


def test_snapshot_help_shows_format_behavior(capsys: pytest.CaptureFixture[str]) -> None:
    """snapshot --help explains format-dependent output."""
    with pytest.raises(SystemExit):
        main(["snapshot", "--help"])

    captured = capsys.readouterr()
    assert "output varies by format:" in captured.out
    assert "market quotes table only" in captured.out


# --- Helper to create a fake session file ---


def _create_session(tmp_path: Path) -> Path:
    """Create a valid session file and return its path."""
    session_path = tmp_path / "session.json"
    session_data: dict[str, str | dict[str, str]] = {
        "csrf": "test-csrf-token",
        "cookies": {},
    }
    session_path.write_text(json.dumps(session_data))
    session_path.chmod(0o600)
    return session_path


# --- Shared test fixtures ---


def _sample_accounts_summary() -> AccountsSummary:
    return AccountsSummary(
        networth=Decimal("100000"),
        assets=Decimal("120000"),
        liabilities=Decimal("20000"),
        cash_total=Decimal("5000"),
        investment_total=Decimal("115000"),
        credit_card_total=Decimal("2000"),
        mortgage_total=Decimal("18000"),
        loan_total=Decimal("0"),
        other_asset_total=Decimal("0"),
        other_liabilities_total=Decimal("0"),
    )


def _sample_transactions_summary() -> TransactionsSummary:
    return TransactionsSummary(
        money_in=Decimal("1000"),
        money_out=Decimal("500"),
        net_cashflow=Decimal("500"),
        average_in=Decimal("1000"),
        average_out=Decimal("500"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )


def _sample_net_worth_summary() -> NetWorthSummary:
    return NetWorthSummary(
        date_range_change=Decimal("5000"),
        date_range_percentage_change=Decimal("3.45"),
        cash_change=Decimal("0"),
        cash_percentage_change=Decimal("0"),
        investment_change=Decimal("0"),
        investment_percentage_change=Decimal("0"),
        credit_change=Decimal("0"),
        credit_percentage_change=Decimal("0"),
        mortgage_change=Decimal("0"),
        mortgage_percentage_change=Decimal("0"),
        loan_change=Decimal("0"),
        loan_percentage_change=Decimal("0"),
        other_assets_change=Decimal("0"),
        other_assets_percentage_change=Decimal("0"),
        other_liabilities_change=Decimal("0"),
        other_liabilities_percentage_change=Decimal("0"),
    )


# --- Command integration tests (mock EmpowerClient) ---


def test_cmd_accounts_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    result = AccountsResult(
        accounts=(_sample_account(),),
        summary=_sample_accounts_summary(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_accounts.return_value = result
        main(["--session", str(session), "accounts"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert len(parsed) == 1
    assert parsed[0]["user_account_id"] == 100


def test_cmd_accounts_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    result = AccountsResult(
        accounts=(_sample_account(),),
        summary=_sample_accounts_summary(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_accounts.return_value = result
        main(["--format", "csv", "--session", str(session), "accounts"])

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert "user_account_id" in lines[0]
    assert "100" in lines[1]


def test_cmd_transactions_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    result = TransactionsResult(
        transactions=(_sample_transaction(),),
        categories=(Category(category_id=3, name="Food", type="EXPENSE"),),
        summary=_sample_transactions_summary(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_transactions.return_value = result
        main(
            [
                "--session",
                str(session),
                "transactions",
                "--start",
                "2026-01-01",
                "--end",
                "2026-01-31",
            ]
        )

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["amount"] == 42.50


def test_cmd_categories_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    cat = Category(category_id=7, name="Groceries", type="EXPENSE")
    result = TransactionsResult(
        transactions=(),
        categories=(cat,),
        summary=_sample_transactions_summary(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_transactions.return_value = result
        main(["--session", str(session), "categories", "--start", "mb", "--end", "today"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["name"] == "Groceries"


def test_cmd_holdings_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    holding = Holding(
        snapshot_date=date(2026, 3, 19),
        user_account_id=200,
        ticker="VTI",
        cusip="922908769",
        description="Vanguard Total Stock Mkt ETF",
        quantity=Decimal("50"),
        price=Decimal("250"),
        value=Decimal("12500"),
        holding_type="etf",
        security_type="equity",
        holding_percentage=Decimal("0.75"),
        source="broker",
        cost_basis=Decimal("10000"),
        one_day_percent_change=Decimal("0.5"),
        one_day_value_change=Decimal("62.50"),
        fees_per_year=None,
        fund_fees=None,
    )
    result = HoldingsResult(holdings=(holding,), total_value=Decimal("12500"))

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_holdings.return_value = result
        main(["--session", str(session), "holdings"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["ticker"] == "VTI"


def test_cmd_net_worth_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    nw = NetWorthEntry(
        date=date(2026, 3, 1),
        networth=Decimal("150000"),
        total_assets=Decimal("200000"),
        total_liabilities=Decimal("50000"),
        total_cash=Decimal("30000"),
        total_investment=Decimal("170000"),
        total_credit=Decimal("5000"),
        total_mortgage=Decimal("40000"),
        total_loan=Decimal("5000"),
        total_other_assets=Decimal("0"),
        total_other_liabilities=Decimal("0"),
    )
    result = NetWorthResult(entries=(nw,), summary=_sample_net_worth_summary())

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_net_worth.return_value = result
        main(["--session", str(session), "net-worth", "--start", "mb", "--end", "today"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["networth"] == 150000.0


def test_cmd_balances_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    bal = AccountBalance(date=date(2026, 3, 15), user_account_id=789, balance=Decimal("5432.10"))

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_account_balances.return_value = AccountBalancesResult(
            balances=(bal,),
            summary=AccountBalancesSummary(
                account_count=1,
                latest_date=date(2026, 3, 15),
                latest_total=Decimal("5432.10"),
            ),
        )
        main(["--session", str(session), "balances", "--start", "mb", "--end", "today"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["balance"] == 5432.10


def test_cmd_performance_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    perf = InvestmentPerformance(
        date=date(2026, 3, 15), user_account_id=300, performance=Decimal("0.0823")
    )
    result = PerformanceResult(
        investments=(perf,),
        benchmarks=(),
        account_summaries=(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_performance.return_value = result
        main(
            [
                "--session",
                str(session),
                "performance",
                "--start",
                "mb",
                "--end",
                "today",
                "--account-ids",
                "300",
            ]
        )

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["performance"] == 0.0823


def test_cmd_benchmarks_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    bench = BenchmarkPerformance(
        date=date(2026, 3, 15), benchmark="^INX", performance=Decimal("0.1245")
    )
    result = PerformanceResult(
        investments=(),
        benchmarks=(bench,),
        account_summaries=(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_performance.return_value = result
        main(
            [
                "--session",
                str(session),
                "benchmarks",
                "--start",
                "mb",
                "--end",
                "today",
                "--account-ids",
                "300",
            ]
        )

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["benchmark"] == "^INX"


def test_cmd_portfolio_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    pvb = PortfolioVsBenchmark(
        date=date(2026, 3, 15),
        portfolio_value=Decimal("105.5"),
        sp500_value=Decimal("103.2"),
    )
    result = QuotesResult(
        portfolio_vs_benchmark=(pvb,),
        snapshot=PortfolioSnapshot(
            last=Decimal("780000"), change=Decimal("-4500"), percent_change=Decimal("-0.58")
        ),
        market_quotes=(),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_quotes.return_value = result
        main(["--session", str(session), "portfolio", "--start", "mb", "--end", "today"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["portfolio_value"] == 105.5


def test_cmd_snapshot_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    snapshot = PortfolioSnapshot(
        last=Decimal("780000"), change=Decimal("-4500"), percent_change=Decimal("-0.58")
    )
    quote = MarketQuote(
        ticker="^INX",
        last=Decimal("6624.7"),
        change=Decimal("-91.39"),
        percent_change=Decimal("-1.36"),
        long_name="S&P 500",
        date=date(2026, 3, 15),
    )
    result = QuotesResult(
        portfolio_vs_benchmark=(),
        snapshot=snapshot,
        market_quotes=(quote,),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_quotes.return_value = result
        main(["--session", str(session), "snapshot", "--start", "mb", "--end", "today"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["snapshot"]["last"] == 780000
    assert parsed["market_quotes"][0]["ticker"] == "^INX"


def test_cmd_snapshot_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    snapshot = PortfolioSnapshot(
        last=Decimal("780000"), change=Decimal("-4500"), percent_change=Decimal("-0.58")
    )
    quote = MarketQuote(
        ticker="^INX",
        last=Decimal("6624.7"),
        change=Decimal("-91.39"),
        percent_change=Decimal("-1.36"),
        long_name="S&P 500",
        date=date(2026, 3, 15),
    )
    result = QuotesResult(
        portfolio_vs_benchmark=(),
        snapshot=snapshot,
        market_quotes=(quote,),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_quotes.return_value = result
        main(
            [
                "--format",
                "csv",
                "--session",
                str(session),
                "snapshot",
                "--start",
                "mb",
                "--end",
                "today",
            ]
        )

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert "ticker" in lines[0]
    assert "^INX" in lines[1]


def test_cmd_spending_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    summary = SpendingSummary(
        type="MONTH",
        average=Decimal("3683.74"),
        current=Decimal("3673.54"),
        target=Decimal("2836.88"),
        details=(SpendingDetail(date=date(2026, 3, 1), amount=Decimal("516.88")),),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_spending.return_value = SpendingResult(intervals=(summary,))
        main(
            [
                "--session",
                str(session),
                "spending",
                "--start",
                "mb",
                "--end",
                "today",
                "--interval",
                "MONTH",
            ]
        )

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["type"] == "MONTH"
    assert parsed[0]["current"] == 3673.54


def test_cmd_raw_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    raw_response: dict[str, Any] = {"spHeader": {"success": True}, "spData": {"key": "value"}}

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.fetch.return_value = raw_response
        main(["--session", str(session), "raw", "/test/endpoint", "--data", "key=value"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["spData"]["key"] == "value"

    # Verify fetch was called with correct args
    instance.fetch.assert_called_once_with("/test/endpoint", {"key": "value"})


def test_cmd_raw_no_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    raw_response: dict[str, Any] = {"spHeader": {"success": True}, "spData": {}}

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.fetch.return_value = raw_response
        main(["--session", str(session), "raw", "/test/endpoint"])

    instance.fetch.assert_called_once_with("/test/endpoint", None)


# --- Error handling tests ---


def test_auth_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Auth error during fetch + re-auth that also fails → EXIT_AUTH with the
    re-auth's error surfaced (run_authenticated retries once before propagating)."""
    session = _create_session(tmp_path)

    with (
        patch("personalcapital2.auth.EmpowerClient") as mock_cls,
        patch("personalcapital2.auth.authenticate") as mock_auth,
    ):
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_accounts.side_effect = EmpowerAuthError("Session expired")
        # re-auth itself fails (e.g. no TTY in CI) — InteractiveAuthRequired is
        # a subclass of EmpowerAuthError, propagates to main() unchanged.
        from personalcapital2.exceptions import InteractiveAuthRequired

        mock_auth.side_effect = InteractiveAuthRequired("Login requires an interactive terminal.")
        with pytest.raises(SystemExit) as exc_info:
            main(["--session", str(session), "accounts"])

    assert exc_info.value.code == EXIT_AUTH
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "EmpowerAuthError"
    assert "interactive terminal" in err["error"]
    assert err["suggestion"] == "pc2 login"


def test_api_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_accounts.side_effect = EmpowerAPIError("Server error")
        with pytest.raises(SystemExit) as exc_info:
            main(["--session", str(session), "accounts"])

    assert exc_info.value.code == EXIT_API
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "EmpowerAPIError"


def test_no_session_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No cached session + non-TTY environment → first fetch raises auth error
    → run_authenticated calls authenticate() → mocked authenticate raises
    InteractiveAuthRequired → structured JSON."""
    from personalcapital2.exceptions import InteractiveAuthRequired

    session_path = tmp_path / "nonexistent.json"

    with (
        # Mock EmpowerClient so the operation fails deterministically with an
        # auth error (mimics the server returning "Session not authenticated"
        # for a request with no cookies) — without this, run_authenticated would
        # build a real client and hit the network.
        patch("personalcapital2.auth.EmpowerClient") as mock_cls,
        patch("personalcapital2.auth.authenticate") as mock_auth,
        pytest.raises(SystemExit) as exc_info,
    ):
        instance = mock_cls.return_value
        instance.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")
        mock_auth.side_effect = InteractiveAuthRequired("Login requires an interactive terminal.")
        main(["--session", str(session_path), "accounts"])

    assert exc_info.value.code == EXIT_AUTH
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "EmpowerAuthError"
    assert "interactive terminal" in err["error"]
    assert err["suggestion"] == "pc2 login"


def test_no_command_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == EXIT_USAGE
    captured = capsys.readouterr()
    assert "pc2" in captured.out


# --- Auth command tests ---


def test_cmd_login(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = tmp_path / "session.json"

    with patch("personalcapital2.cli.authenticate") as mock_auth:
        mock_client = MagicMock()
        mock_auth.return_value = mock_client
        main(["--session", str(session), "login"])

    # cmd_login delegates entirely to authenticate(), which saves at its tail.
    mock_auth.assert_called_once_with(session_path=session)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["authenticated"] is True
    assert parsed["session_path"] == str(session)


def test_cmd_login_not_tty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Non-TTY login: authenticate() raises InteractiveAuthRequired (subclass of
    EmpowerAuthError) → main() emits structured JSON via _error()."""
    from personalcapital2.exceptions import InteractiveAuthRequired

    session = tmp_path / "session.json"

    with (
        patch("personalcapital2.cli.authenticate") as mock_auth,
        pytest.raises(SystemExit) as exc_info,
    ):
        mock_auth.side_effect = InteractiveAuthRequired(
            "Login requires an interactive terminal or EMPOWER_EMAIL/EMPOWER_PASSWORD env vars."
        )
        main(["--session", str(session), "login"])

    assert exc_info.value.code == EXIT_AUTH
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "EmpowerAuthError"
    assert "interactive terminal" in err["error"]
    assert "suggestion" in err


def test_cmd_logout_deletes_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)
    assert session.exists()

    main(["--session", str(session), "logout"])

    assert not session.exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["deleted"] is True
    assert parsed["session_path"] == str(session)


def test_cmd_logout_no_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = tmp_path / "nonexistent.json"

    main(["--session", str(session), "logout"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["deleted"] is False
    assert parsed["session_path"] == str(session)


def test_cmd_status_exists(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = _create_session(tmp_path)

    main(["--session", str(session), "status"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["exists"] is True
    assert parsed["session_path"] == str(session)
    assert "age_seconds" in parsed
    assert "age_human" in parsed


def test_cmd_status_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session = tmp_path / "nonexistent.json"

    main(["--session", str(session), "status"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["exists"] is False
    assert parsed["session_path"] == str(session)
    assert "age_seconds" not in parsed


# --- CSV nested field serialization tests ---


def test_serialize_csv_nested_fields() -> None:
    """Nested dataclass fields should serialize as JSON strings, not Python repr."""
    summary = SpendingSummary(
        type="MONTH",
        average=Decimal("2000"),
        current=Decimal("1800"),
        target=Decimal("2500"),
        details=(SpendingDetail(date=date(2026, 3, 15), amount=Decimal("42.99")),),
    )
    items: list[object] = [summary]
    result = _serialize_csv(items)
    lines = result.strip().split("\n")
    assert len(lines) == 2

    # Parse the CSV row to extract the details column
    import csv
    import io

    reader = csv.DictReader(io.StringIO(result))
    row = next(reader)
    # details column should be valid JSON, not Python repr
    details = json.loads(row["details"])
    assert isinstance(details, list)
    assert details[0]["date"] == "2026-03-15"
    assert details[0]["amount"] == 42.99


def test_cmd_spending_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Spending CSV output should have valid JSON in the details column."""
    session = _create_session(tmp_path)
    result = SpendingResult(
        intervals=(
            SpendingSummary(
                type="MONTH",
                average=Decimal("2000"),
                current=Decimal("1800"),
                target=Decimal("2500"),
                details=(SpendingDetail(date=date(2026, 3, 15), amount=Decimal("42.99")),),
            ),
        ),
    )

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_spending.return_value = result
        main(
            [
                "--format",
                "csv",
                "--session",
                str(session),
                "spending",
                "--start",
                "mb",
                "--end",
                "today",
            ]
        )

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2
    assert "details" in lines[0]
    # The details cell should not contain Python repr
    assert "datetime.date" not in captured.out
    assert "Decimal" not in captured.out


# --- Date validation tests ---


def test_validate_dates_valid() -> None:
    """Valid date range should not raise."""
    _validate_dates(date(2026, 1, 1), date(2026, 3, 31))


def test_validate_dates_same_day() -> None:
    """Same-day range should not raise."""
    _validate_dates(date(2026, 3, 15), date(2026, 3, 15))


def test_validate_dates_reversed(capsys: pytest.CaptureFixture[str]) -> None:
    """Reversed dates should exit with EXIT_USAGE and structured JSON error."""
    with pytest.raises(SystemExit) as exc_info:
        _validate_dates(date(2026, 3, 31), date(2026, 1, 1))
    assert exc_info.value.code == EXIT_USAGE
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "UsageError"
    assert "start date" in err["error"]
    assert "suggestion" in err


def test_cmd_transactions_reversed_dates(tmp_path: Path) -> None:
    """Reversed dates should exit before calling the API."""
    session = _create_session(tmp_path)
    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "--session",
                    str(session),
                    "transactions",
                    "--start",
                    "today",
                    "--end",
                    "30d",
                ]
            )
        assert exc_info.value.code == EXIT_USAGE
        instance.get_transactions.assert_not_called()


# --- Network error and recovery (Task 10 additions) ---


def test_network_error_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """EmpowerNetworkError surfaces as EXIT_NETWORK with structured JSON."""
    session = _create_session(tmp_path)

    with patch("personalcapital2.auth.EmpowerClient") as mock_cls:
        instance = mock_cls.return_value
        instance._csrf = "test-csrf-token"
        instance.load_session = MagicMock()
        instance.get_accounts.side_effect = EmpowerNetworkError(
            "Request to https://x failed: connection refused"
        )
        with pytest.raises(SystemExit) as exc_info:
            main(["--session", str(session), "accounts"])

    assert exc_info.value.code == EXIT_NETWORK
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err["type"] == "EmpowerNetworkError"
    assert "Network error reaching Empower" in err["error"]
    assert "Check connection and retry" in err["error"]


def test_data_command_recovers_from_stale_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: first fetch raises EmpowerAuthError → run_authenticated calls
    authenticate() → mocked authenticate returns a fresh client whose fetch
    succeeds → command output is normal."""
    session = _create_session(tmp_path)

    stale_client = MagicMock()
    stale_client._csrf = "stale"
    stale_client.load_session = MagicMock()
    stale_client.get_accounts.side_effect = EmpowerAuthError("Session not authenticated")

    fresh_result = AccountsResult(
        accounts=(_sample_account(),),
        summary=_sample_accounts_summary(),
    )
    fresh_client = MagicMock()
    fresh_client.get_accounts.return_value = fresh_result

    with (
        patch("personalcapital2.auth.EmpowerClient", return_value=stale_client),
        patch("personalcapital2.auth.authenticate", return_value=fresh_client) as mock_auth,
    ):
        main(["--session", str(session), "accounts"])

    mock_auth.assert_called_once()
    # First call (stale) raised, second call (fresh) returned the result.
    assert stale_client.get_accounts.call_count == 1
    assert fresh_client.get_accounts.call_count == 1
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["user_account_id"] == 100
