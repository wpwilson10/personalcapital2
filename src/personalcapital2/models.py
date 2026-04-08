"""Typed dataclass models for Empower API data.

Each model corresponds to a parser output shape with proper types:
date strings become ``datetime.date``, sync metadata is excluded.

Use the ``_*_from_dict`` converter functions to construct models from
parser output dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal  # noqa: TC003 — used at runtime in dataclass fields
from typing import Any

from personalcapital2._validation import (
    safe_decimal,
    safe_decimal_or_none,
)


def _parse_date(s: str) -> date:
    """Convert an ISO-8601 date string (YYYY-MM-DD) to a date object."""
    return date.fromisoformat(s)


def _parse_date_or_none(s: str | None) -> date | None:
    """Convert an ISO-8601 date string to a date object, or None."""
    return date.fromisoformat(s) if s is not None else None


# --- Models ---


@dataclass(frozen=True)
class Account:
    """A linked financial account."""

    user_account_id: int
    account_id: str
    name: str
    firm_name: str
    account_type: str
    account_type_group: str | None
    product_type: str
    currency: str
    is_asset: bool
    is_closed: bool
    created_at: date | None
    balance: Decimal | None
    available_cash: Decimal | None
    account_type_subtype: str | None
    last_refreshed: date | None
    oldest_transaction_date: date | None
    advisory_fee_percentage: Decimal | None
    fees_per_year: Decimal | None
    fund_fees: Decimal | None
    total_fee: Decimal | None


@dataclass(frozen=True)
class Transaction:
    """A financial transaction."""

    user_transaction_id: int
    user_account_id: int
    date: date
    amount: Decimal
    is_cash_in: bool
    is_income: bool
    is_spending: bool
    description: str
    original_description: str | None
    simple_description: str | None
    category_id: int | None
    merchant: str | None
    transaction_type: str | None
    sub_type: str | None
    status: str | None
    currency: str
    merchant_id: str | None
    merchant_type: str | None
    is_duplicate: bool


@dataclass(frozen=True)
class Category:
    """A transaction category."""

    category_id: int
    name: str
    type: str


@dataclass(frozen=True)
class Holding:
    """A point-in-time investment holding snapshot."""

    snapshot_date: date
    user_account_id: int
    ticker: str | None
    cusip: str | None
    description: str
    quantity: Decimal
    price: Decimal
    value: Decimal
    holding_type: str | None
    security_type: str | None
    holding_percentage: Decimal | None
    source: str | None
    cost_basis: Decimal | None
    one_day_percent_change: Decimal | None
    one_day_value_change: Decimal | None
    fees_per_year: Decimal | None
    fund_fees: Decimal | None


@dataclass(frozen=True)
class NetWorthEntry:
    """A daily net worth breakdown."""

    date: date
    networth: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    total_cash: Decimal
    total_investment: Decimal
    total_credit: Decimal
    total_mortgage: Decimal
    total_loan: Decimal
    total_other_assets: Decimal
    total_other_liabilities: Decimal


@dataclass(frozen=True)
class AccountBalance:
    """A daily account balance."""

    date: date
    user_account_id: int
    balance: Decimal


@dataclass(frozen=True)
class AccountBalancesSummary:
    """Summary of account balance history.

    Computed from the parsed balance data (the API does not provide a
    pre-computed summary for this endpoint).
    """

    account_count: int
    latest_date: date | None
    latest_total: Decimal


@dataclass(frozen=True)
class InvestmentPerformance:
    """Daily cumulative investment performance for a single account."""

    date: date
    user_account_id: int
    performance: Decimal | None


@dataclass(frozen=True)
class BenchmarkPerformance:
    """Daily cumulative benchmark performance."""

    date: date
    benchmark: str
    performance: Decimal | None


@dataclass(frozen=True)
class PortfolioVsBenchmark:
    """Daily portfolio vs S&P 500 comparison values."""

    date: date
    portfolio_value: Decimal | None
    sp500_value: Decimal | None


# --- Converters (parser dict → model) ---


def account_from_dict(d: dict[str, Any]) -> Account:
    return Account(
        user_account_id=d["user_account_id"],
        account_id=d["account_id"],
        name=d["name"],
        firm_name=d["firm_name"],
        account_type=d["account_type"],
        account_type_group=d["account_type_group"],
        product_type=d["product_type"],
        currency=d["currency"],
        is_asset=d["is_asset"],
        is_closed=d["is_closed"],
        created_at=_parse_date_or_none(d["created_at"]),
        balance=safe_decimal_or_none(d.get("balance"), "balance"),
        available_cash=safe_decimal_or_none(d.get("available_cash"), "available_cash"),
        account_type_subtype=d.get("account_type_subtype"),
        last_refreshed=_parse_date_or_none(d.get("last_refreshed")),
        oldest_transaction_date=_parse_date_or_none(d.get("oldest_transaction_date")),
        advisory_fee_percentage=safe_decimal_or_none(
            d.get("advisory_fee_percentage"), "advisory_fee_percentage"
        ),
        fees_per_year=safe_decimal_or_none(d.get("fees_per_year"), "fees_per_year"),
        fund_fees=safe_decimal_or_none(d.get("fund_fees"), "fund_fees"),
        total_fee=safe_decimal_or_none(d.get("total_fee"), "total_fee"),
    )


def transaction_from_dict(d: dict[str, Any]) -> Transaction:
    return Transaction(
        user_transaction_id=d["user_transaction_id"],
        user_account_id=d["user_account_id"],
        date=_parse_date(d["date"]),
        amount=safe_decimal(d["amount"], "amount"),
        is_cash_in=d["is_cash_in"],
        is_income=d["is_income"],
        is_spending=d["is_spending"],
        description=d["description"],
        original_description=d["original_description"],
        simple_description=d["simple_description"],
        category_id=d["category_id"],
        merchant=d["merchant"],
        merchant_id=d["merchant_id"],
        merchant_type=d["merchant_type"],
        transaction_type=d["transaction_type"],
        sub_type=d["sub_type"],
        status=d["status"],
        currency=d["currency"],
        is_duplicate=d["is_duplicate"],
    )


def category_from_dict(d: dict[str, Any]) -> Category:
    return Category(
        category_id=d["category_id"],
        name=d["name"],
        type=d["type"],
    )


def holding_from_dict(d: dict[str, Any]) -> Holding:
    return Holding(
        snapshot_date=_parse_date(d["snapshot_date"]),
        user_account_id=d["user_account_id"],
        ticker=d["ticker"],
        cusip=d["cusip"],
        description=d["description"],
        quantity=safe_decimal(d["quantity"], "quantity"),
        price=safe_decimal(d["price"], "price"),
        value=safe_decimal(d["value"], "value"),
        holding_type=d["holding_type"],
        security_type=d["security_type"],
        holding_percentage=safe_decimal_or_none(d["holding_percentage"], "holdingPercentage"),
        source=d["source"],
        cost_basis=safe_decimal_or_none(d.get("cost_basis"), "costBasis"),
        one_day_percent_change=safe_decimal_or_none(
            d.get("one_day_percent_change"), "oneDayPercentChange"
        ),
        one_day_value_change=safe_decimal_or_none(
            d.get("one_day_value_change"), "oneDayValueChange"
        ),
        fees_per_year=safe_decimal_or_none(d.get("fees_per_year"), "feesPerYear"),
        fund_fees=safe_decimal_or_none(d.get("fund_fees"), "fundFees"),
    )


def net_worth_entry_from_dict(d: dict[str, Any]) -> NetWorthEntry:
    return NetWorthEntry(
        date=_parse_date(d["date"]),
        networth=safe_decimal(d["networth"], "networth"),
        total_assets=safe_decimal(d["total_assets"], "total_assets"),
        total_liabilities=safe_decimal(d["total_liabilities"], "total_liabilities"),
        total_cash=safe_decimal(d["total_cash"], "total_cash"),
        total_investment=safe_decimal(d["total_investment"], "total_investment"),
        total_credit=safe_decimal(d["total_credit"], "total_credit"),
        total_mortgage=safe_decimal(d["total_mortgage"], "total_mortgage"),
        total_loan=safe_decimal(d["total_loan"], "total_loan"),
        total_other_assets=safe_decimal(d["total_other_assets"], "total_other_assets"),
        total_other_liabilities=safe_decimal(
            d["total_other_liabilities"], "total_other_liabilities"
        ),
    )


def account_balance_from_dict(d: dict[str, Any]) -> AccountBalance:
    return AccountBalance(
        date=_parse_date(d["date"]),
        user_account_id=d["user_account_id"],
        balance=safe_decimal(d["balance"], "balance"),
    )


def investment_performance_from_dict(d: dict[str, Any]) -> InvestmentPerformance:
    return InvestmentPerformance(
        date=_parse_date(d["date"]),
        user_account_id=d["user_account_id"],
        performance=safe_decimal_or_none(d["performance"], "performance"),
    )


def benchmark_performance_from_dict(d: dict[str, Any]) -> BenchmarkPerformance:
    return BenchmarkPerformance(
        date=_parse_date(d["date"]),
        benchmark=d["benchmark"],
        performance=safe_decimal_or_none(d["performance"], "performance"),
    )


def portfolio_vs_benchmark_from_dict(d: dict[str, Any]) -> PortfolioVsBenchmark:
    return PortfolioVsBenchmark(
        date=_parse_date(d["date"]),
        portfolio_value=safe_decimal_or_none(d["portfolio_value"], "portfolio_value"),
        sp500_value=safe_decimal_or_none(d["sp500_value"], "sp500_value"),
    )


# --- Summary models ---


@dataclass(frozen=True)
class AccountsSummary:
    """Aggregate totals across all linked accounts."""

    networth: Decimal
    assets: Decimal
    liabilities: Decimal
    cash_total: Decimal
    investment_total: Decimal
    credit_card_total: Decimal
    mortgage_total: Decimal
    loan_total: Decimal
    other_asset_total: Decimal
    other_liabilities_total: Decimal


@dataclass(frozen=True)
class TransactionsSummary:
    """Aggregate transaction totals for a date range."""

    money_in: Decimal
    money_out: Decimal
    net_cashflow: Decimal
    average_in: Decimal
    average_out: Decimal
    start_date: date
    end_date: date


@dataclass(frozen=True)
class NetWorthSummary:
    """Change summary for net worth over a date range."""

    date_range_change: Decimal
    date_range_percentage_change: Decimal
    cash_change: Decimal
    cash_percentage_change: Decimal
    investment_change: Decimal
    investment_percentage_change: Decimal
    credit_change: Decimal
    credit_percentage_change: Decimal
    mortgage_change: Decimal
    mortgage_percentage_change: Decimal
    loan_change: Decimal
    loan_percentage_change: Decimal
    other_assets_change: Decimal
    other_assets_percentage_change: Decimal
    other_liabilities_change: Decimal
    other_liabilities_percentage_change: Decimal


@dataclass(frozen=True)
class AccountPerformanceSummary:
    """Performance summary for a single account over a date range."""

    user_account_id: int
    account_name: str
    site_name: str
    current_balance: Decimal
    percent_of_total: Decimal
    income: Decimal
    expense: Decimal
    cash_flow: Decimal
    one_day_balance_value_change: Decimal
    one_day_balance_percentage_change: Decimal
    date_range_balance_value_change: Decimal
    date_range_balance_percentage_change: Decimal
    date_range_performance_value_change: Decimal
    one_day_performance_value_change: Decimal
    balance_as_of_end_date: Decimal
    closed_date: date | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Latest portfolio summary values."""

    last: Decimal
    change: Decimal
    percent_change: Decimal


@dataclass(frozen=True)
class MarketQuote:
    """A single market index or benchmark quote."""

    ticker: str
    last: Decimal
    change: Decimal
    percent_change: Decimal
    long_name: str
    date: date


# --- Summary converters ---


def accounts_summary_from_dict(d: dict[str, Any]) -> AccountsSummary:
    return AccountsSummary(
        networth=safe_decimal(d.get("networth", 0), "networth"),
        assets=safe_decimal(d.get("assets", 0), "assets"),
        liabilities=safe_decimal(d.get("liabilities", 0), "liabilities"),
        cash_total=safe_decimal(d.get("cash_total", 0), "cash_total"),
        investment_total=safe_decimal(d.get("investment_total", 0), "investment_total"),
        credit_card_total=safe_decimal(d.get("credit_card_total", 0), "credit_card_total"),
        mortgage_total=safe_decimal(d.get("mortgage_total", 0), "mortgage_total"),
        loan_total=safe_decimal(d.get("loan_total", 0), "loan_total"),
        other_asset_total=safe_decimal(d.get("other_asset_total", 0), "other_asset_total"),
        other_liabilities_total=safe_decimal(
            d.get("other_liabilities_total", 0), "other_liabilities_total"
        ),
    )


def transactions_summary_from_dict(d: dict[str, Any]) -> TransactionsSummary:
    return TransactionsSummary(
        money_in=safe_decimal(d.get("money_in", 0), "money_in"),
        money_out=safe_decimal(d.get("money_out", 0), "money_out"),
        net_cashflow=safe_decimal(d.get("net_cashflow", 0), "net_cashflow"),
        average_in=safe_decimal(d.get("average_in", 0), "average_in"),
        average_out=safe_decimal(d.get("average_out", 0), "average_out"),
        start_date=_parse_date(d["start_date"]),
        end_date=_parse_date(d["end_date"]),
    )


def net_worth_summary_from_dict(d: dict[str, Any]) -> NetWorthSummary:
    return NetWorthSummary(
        date_range_change=safe_decimal(d.get("date_range_change", 0), "date_range_change"),
        date_range_percentage_change=safe_decimal(
            d.get("date_range_percentage_change", 0), "date_range_percentage_change"
        ),
        cash_change=safe_decimal(d.get("cash_change", 0), "cash_change"),
        cash_percentage_change=safe_decimal(
            d.get("cash_percentage_change", 0), "cash_percentage_change"
        ),
        investment_change=safe_decimal(d.get("investment_change", 0), "investment_change"),
        investment_percentage_change=safe_decimal(
            d.get("investment_percentage_change", 0), "investment_percentage_change"
        ),
        credit_change=safe_decimal(d.get("credit_change", 0), "credit_change"),
        credit_percentage_change=safe_decimal(
            d.get("credit_percentage_change", 0), "credit_percentage_change"
        ),
        mortgage_change=safe_decimal(d.get("mortgage_change", 0), "mortgage_change"),
        mortgage_percentage_change=safe_decimal(
            d.get("mortgage_percentage_change", 0), "mortgage_percentage_change"
        ),
        loan_change=safe_decimal(d.get("loan_change", 0), "loan_change"),
        loan_percentage_change=safe_decimal(
            d.get("loan_percentage_change", 0), "loan_percentage_change"
        ),
        other_assets_change=safe_decimal(d.get("other_assets_change", 0), "other_assets_change"),
        other_assets_percentage_change=safe_decimal(
            d.get("other_assets_percentage_change", 0), "other_assets_percentage_change"
        ),
        other_liabilities_change=safe_decimal(
            d.get("other_liabilities_change", 0), "other_liabilities_change"
        ),
        other_liabilities_percentage_change=safe_decimal(
            d.get("other_liabilities_percentage_change", 0),
            "other_liabilities_percentage_change",
        ),
    )


def account_performance_summary_from_dict(d: dict[str, Any]) -> AccountPerformanceSummary:
    closed = d.get("closed_date")
    return AccountPerformanceSummary(
        user_account_id=d["user_account_id"],
        account_name=d["account_name"],
        site_name=d["site_name"],
        current_balance=safe_decimal(d["current_balance"], "current_balance"),
        percent_of_total=safe_decimal(d["percent_of_total"], "percent_of_total"),
        income=safe_decimal(d.get("income", 0), "income"),
        expense=safe_decimal(d.get("expense", 0), "expense"),
        cash_flow=safe_decimal(d.get("cash_flow", 0), "cash_flow"),
        one_day_balance_value_change=safe_decimal(
            d.get("one_day_balance_value_change", 0), "one_day_balance_value_change"
        ),
        one_day_balance_percentage_change=safe_decimal(
            d.get("one_day_balance_percentage_change", 0), "one_day_balance_percentage_change"
        ),
        date_range_balance_value_change=safe_decimal(
            d.get("date_range_balance_value_change", 0), "date_range_balance_value_change"
        ),
        date_range_balance_percentage_change=safe_decimal(
            d.get("date_range_balance_percentage_change", 0),
            "date_range_balance_percentage_change",
        ),
        date_range_performance_value_change=safe_decimal(
            d.get("date_range_performance_value_change", 0),
            "date_range_performance_value_change",
        ),
        one_day_performance_value_change=safe_decimal(
            d.get("one_day_performance_value_change", 0), "one_day_performance_value_change"
        ),
        balance_as_of_end_date=safe_decimal(
            d.get("balance_as_of_end_date", 0), "balance_as_of_end_date"
        ),
        closed_date=_parse_date_or_none(closed) if closed else None,
    )


def portfolio_snapshot_from_dict(d: dict[str, Any]) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        last=safe_decimal(d["last"], "last"),
        change=safe_decimal(d["change"], "change"),
        percent_change=safe_decimal(d["percent_change"], "percent_change"),
    )


def market_quote_from_dict(d: dict[str, Any]) -> MarketQuote:
    return MarketQuote(
        ticker=d["ticker"],
        last=safe_decimal(d["last"], "last"),
        change=safe_decimal(d["change"], "change"),
        percent_change=safe_decimal(d["percent_change"], "percent_change"),
        long_name=d["long_name"],
        date=_parse_date(d["date"]),
    )


@dataclass(frozen=True)
class SpendingDetail:
    """A single date/amount pair within a spending interval."""

    date: date
    amount: Decimal


@dataclass(frozen=True)
class SpendingSummary:
    """Spending summary for a time interval (MONTH, WEEK, or YEAR)."""

    type: str
    average: Decimal | None
    current: Decimal
    target: Decimal
    details: tuple[SpendingDetail, ...]


def spending_detail_from_dict(d: dict[str, Any]) -> SpendingDetail:
    return SpendingDetail(
        date=_parse_date(d["date"]),
        amount=safe_decimal(d["amount"], "spending_detail.amount"),
    )


def spending_summary_from_dict(d: dict[str, Any]) -> SpendingSummary:
    raw_details: list[dict[str, Any]] = d.get("details", [])
    return SpendingSummary(
        type=d["type"],
        average=safe_decimal_or_none(d.get("average"), "average"),
        current=safe_decimal(d.get("current", 0), "current"),
        target=safe_decimal(d.get("target", 0), "target"),
        details=tuple(spending_detail_from_dict(det) for det in raw_details),
    )


# --- Response containers ---


@dataclass(frozen=True)
class AccountsResult:
    """Response container for get_accounts()."""

    accounts: tuple[Account, ...]
    summary: AccountsSummary


@dataclass(frozen=True)
class TransactionsResult:
    """Response container for get_transactions()."""

    transactions: tuple[Transaction, ...]
    categories: tuple[Category, ...]
    summary: TransactionsSummary


@dataclass(frozen=True)
class HoldingsResult:
    """Response container for get_holdings()."""

    holdings: tuple[Holding, ...]
    total_value: Decimal


@dataclass(frozen=True)
class NetWorthResult:
    """Response container for get_net_worth()."""

    entries: tuple[NetWorthEntry, ...]
    summary: NetWorthSummary


@dataclass(frozen=True)
class AccountBalancesResult:
    """Response container for get_account_balances()."""

    balances: tuple[AccountBalance, ...]
    summary: AccountBalancesSummary


@dataclass(frozen=True)
class PerformanceResult:
    """Response container for get_performance()."""

    investments: tuple[InvestmentPerformance, ...]
    benchmarks: tuple[BenchmarkPerformance, ...]
    account_summaries: tuple[AccountPerformanceSummary, ...]


@dataclass(frozen=True)
class QuotesResult:
    """Response container for get_quotes()."""

    portfolio_vs_benchmark: tuple[PortfolioVsBenchmark, ...]
    snapshot: PortfolioSnapshot
    market_quotes: tuple[MarketQuote, ...]


@dataclass(frozen=True)
class SpendingResult:
    """Response container for get_spending()."""

    intervals: tuple[SpendingSummary, ...]
