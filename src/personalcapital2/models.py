"""Typed dataclass models for Empower API data.

Each model corresponds to a parser output shape with proper types:
date strings become ``datetime.date``, sync metadata is excluded.

Use the ``_*_from_dict`` converter functions to construct models from
parser output dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


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


@dataclass(frozen=True)
class Transaction:
    """A financial transaction."""

    user_transaction_id: int
    user_account_id: int
    date: date
    amount: float
    is_cash_in: bool
    is_income: bool
    is_spending: bool
    description: str
    original_description: str | None
    simple_description: str | None
    category_id: int | None
    merchant: str | None
    transaction_type: str | None
    status: str | None
    currency: str


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
    quantity: float
    price: float
    value: float
    holding_type: str | None
    security_type: str | None
    holding_percentage: float | None
    source: str | None


@dataclass(frozen=True)
class NetWorthEntry:
    """A daily net worth breakdown."""

    date: date
    networth: float
    total_assets: float
    total_liabilities: float
    total_cash: float
    total_investment: float
    total_credit: float
    total_mortgage: float
    total_loan: float
    total_other_assets: float
    total_other_liabilities: float


@dataclass(frozen=True)
class AccountBalance:
    """A daily account balance."""

    date: date
    user_account_id: int
    balance: float


@dataclass(frozen=True)
class InvestmentPerformance:
    """Daily cumulative investment performance for a single account."""

    date: date
    user_account_id: int
    performance: float | None


@dataclass(frozen=True)
class BenchmarkPerformance:
    """Daily cumulative benchmark performance."""

    date: date
    benchmark: str
    performance: float


@dataclass(frozen=True)
class PortfolioVsBenchmark:
    """Daily portfolio vs S&P 500 comparison values."""

    date: date
    portfolio_value: float | None
    sp500_value: float | None


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
    )


def transaction_from_dict(d: dict[str, Any]) -> Transaction:
    return Transaction(
        user_transaction_id=d["user_transaction_id"],
        user_account_id=d["user_account_id"],
        date=_parse_date(d["date"]),
        amount=d["amount"],
        is_cash_in=d["is_cash_in"],
        is_income=d["is_income"],
        is_spending=d["is_spending"],
        description=d["description"],
        original_description=d["original_description"],
        simple_description=d["simple_description"],
        category_id=d["category_id"],
        merchant=d["merchant"],
        transaction_type=d["transaction_type"],
        status=d["status"],
        currency=d["currency"],
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
        quantity=d["quantity"],
        price=d["price"],
        value=d["value"],
        holding_type=d["holding_type"],
        security_type=d["security_type"],
        holding_percentage=d["holding_percentage"],
        source=d["source"],
    )


def net_worth_entry_from_dict(d: dict[str, Any]) -> NetWorthEntry:
    return NetWorthEntry(
        date=_parse_date(d["date"]),
        networth=d["networth"],
        total_assets=d["total_assets"],
        total_liabilities=d["total_liabilities"],
        total_cash=d["total_cash"],
        total_investment=d["total_investment"],
        total_credit=d["total_credit"],
        total_mortgage=d["total_mortgage"],
        total_loan=d["total_loan"],
        total_other_assets=d["total_other_assets"],
        total_other_liabilities=d["total_other_liabilities"],
    )


def account_balance_from_dict(d: dict[str, Any]) -> AccountBalance:
    return AccountBalance(
        date=_parse_date(d["date"]),
        user_account_id=d["user_account_id"],
        balance=d["balance"],
    )


def investment_performance_from_dict(d: dict[str, Any]) -> InvestmentPerformance:
    return InvestmentPerformance(
        date=_parse_date(d["date"]),
        user_account_id=d["user_account_id"],
        performance=d["performance"],
    )


def benchmark_performance_from_dict(d: dict[str, Any]) -> BenchmarkPerformance:
    return BenchmarkPerformance(
        date=_parse_date(d["date"]),
        benchmark=d["benchmark"],
        performance=d["performance"],
    )


def portfolio_vs_benchmark_from_dict(d: dict[str, Any]) -> PortfolioVsBenchmark:
    return PortfolioVsBenchmark(
        date=_parse_date(d["date"]),
        portfolio_value=d["portfolio_value"],
        sp500_value=d["sp500_value"],
    )
