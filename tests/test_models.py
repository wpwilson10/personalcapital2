"""Tests for typed dataclass models and their from_dict converters."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from personalcapital2.models import (
    Account,
    Transaction,
    account_balance_from_dict,
    account_from_dict,
    benchmark_performance_from_dict,
    category_from_dict,
    holding_from_dict,
    investment_performance_from_dict,
    net_worth_entry_from_dict,
    portfolio_vs_benchmark_from_dict,
    transaction_from_dict,
)

# --- Frozen / immutable checks ---


def test_account_is_frozen() -> None:
    acct = Account(
        user_account_id=1,
        account_id="A1",
        name="Checking",
        firm_name="Bank",
        account_type="BANK",
        account_type_group="CASH",
        product_type="CHECKING",
        currency="USD",
        is_asset=True,
        is_closed=False,
        created_at=date(2024, 1, 1),
    )
    with pytest.raises(AttributeError):
        acct.name = "Other"  # type: ignore[misc]


def test_transaction_is_frozen() -> None:
    txn = Transaction(
        user_transaction_id=1,
        user_account_id=2,
        date=date(2024, 3, 15),
        amount=Decimal("50"),
        is_cash_in=False,
        is_income=False,
        is_spending=True,
        description="Coffee",
        original_description=None,
        simple_description=None,
        category_id=None,
        merchant=None,
        transaction_type=None,
        status=None,
        currency="USD",
    )
    with pytest.raises(AttributeError):
        txn.amount = Decimal("100")  # type: ignore[misc]


# --- Account from_dict ---


def test_account_from_dict() -> None:
    d = {
        "user_account_id": 123,
        "account_id": "ACC-456",
        "name": "My Checking",
        "firm_name": "Big Bank",
        "account_type": "BANK",
        "account_type_group": "CASH",
        "product_type": "CHECKING",
        "currency": "USD",
        "is_asset": True,
        "is_closed": False,
        "created_at": "2023-06-15",
        "updated_at": "2026-03-18T00:00:00",  # should be ignored
    }
    acct = account_from_dict(d)
    assert acct.user_account_id == 123
    assert acct.account_id == "ACC-456"
    assert acct.name == "My Checking"
    assert acct.firm_name == "Big Bank"
    assert acct.account_type == "BANK"
    assert acct.account_type_group == "CASH"
    assert acct.product_type == "CHECKING"
    assert acct.currency == "USD"
    assert acct.is_asset is True
    assert acct.is_closed is False
    assert acct.created_at == date(2023, 6, 15)


def test_account_from_dict_none_optional_fields() -> None:
    d = {
        "user_account_id": 1,
        "account_id": "",
        "name": "",
        "firm_name": "",
        "account_type": "",
        "account_type_group": None,
        "product_type": "",
        "currency": "USD",
        "is_asset": False,
        "is_closed": False,
        "created_at": None,
        "updated_at": "",
    }
    acct = account_from_dict(d)
    assert acct.account_type_group is None
    assert acct.created_at is None


# --- Transaction from_dict ---


def test_transaction_from_dict() -> None:
    d = {
        "user_transaction_id": 999,
        "user_account_id": 123,
        "date": "2026-01-20",
        "amount": 42.50,
        "is_cash_in": False,
        "is_income": False,
        "is_spending": True,
        "description": "Grocery Store",
        "original_description": "GROCERY STORE #1234",
        "simple_description": "Grocery",
        "category_id": 7,
        "merchant": "FreshMart",
        "transaction_type": "Purchase",
        "status": "posted",
        "currency": "USD",
        "synced_at": "2026-03-18T00:00:00",  # should be ignored
    }
    txn = transaction_from_dict(d)
    assert txn.user_transaction_id == 999
    assert txn.date == date(2026, 1, 20)
    assert txn.amount == Decimal("42.5")
    assert txn.is_spending is True
    assert txn.original_description == "GROCERY STORE #1234"
    assert txn.category_id == 7
    assert txn.merchant == "FreshMart"


def test_transaction_from_dict_none_optional_fields() -> None:
    d = {
        "user_transaction_id": 1,
        "user_account_id": 2,
        "date": "2026-01-01",
        "amount": 0.0,
        "is_cash_in": False,
        "is_income": False,
        "is_spending": False,
        "description": "",
        "original_description": None,
        "simple_description": None,
        "category_id": None,
        "merchant": None,
        "transaction_type": None,
        "status": None,
        "currency": "USD",
        "synced_at": "",
    }
    txn = transaction_from_dict(d)
    assert txn.original_description is None
    assert txn.simple_description is None
    assert txn.category_id is None
    assert txn.merchant is None
    assert txn.transaction_type is None
    assert txn.status is None


# --- Category from_dict ---


def test_category_from_dict() -> None:
    d = {"category_id": 5, "name": "Groceries", "type": "EXPENSE"}
    cat = category_from_dict(d)
    assert cat.category_id == 5
    assert cat.name == "Groceries"
    assert cat.type == "EXPENSE"


# --- Holding from_dict ---


def test_holding_from_dict() -> None:
    d = {
        "snapshot_date": "2026-03-18",
        "user_account_id": 456,
        "ticker": "AAPL",
        "cusip": "037833100",
        "description": "Apple Inc",
        "quantity": 10.0,
        "price": 175.50,
        "value": 1755.00,
        "holding_type": "stock",
        "security_type": "equity",
        "holding_percentage": 0.15,
        "source": "broker",
    }
    h = holding_from_dict(d)
    assert h.snapshot_date == date(2026, 3, 18)
    assert h.ticker == "AAPL"
    assert h.cusip == "037833100"
    assert h.quantity == Decimal("10")
    assert h.value == Decimal("1755")
    assert h.holding_percentage == Decimal("0.15")


def test_holding_from_dict_none_optional_fields() -> None:
    d = {
        "snapshot_date": "2026-03-18",
        "user_account_id": 1,
        "ticker": None,
        "cusip": None,
        "description": "Cash",
        "quantity": 1.0,
        "price": 100.0,
        "value": 100.0,
        "holding_type": None,
        "security_type": None,
        "holding_percentage": None,
        "source": None,
    }
    h = holding_from_dict(d)
    assert h.ticker is None
    assert h.cusip is None
    assert h.holding_type is None
    assert h.holding_percentage is None
    assert h.source is None


# --- NetWorthEntry from_dict ---


def test_net_worth_entry_from_dict() -> None:
    d = {
        "date": "2026-03-01",
        "networth": 150000.0,
        "total_assets": 200000.0,
        "total_liabilities": 50000.0,
        "total_cash": 30000.0,
        "total_investment": 170000.0,
        "total_credit": 5000.0,
        "total_mortgage": 40000.0,
        "total_loan": 5000.0,
        "total_other_assets": 0.0,
        "total_other_liabilities": 0.0,
        "synced_at": "2026-03-18T00:00:00",  # should be ignored
    }
    nw = net_worth_entry_from_dict(d)
    assert nw.date == date(2026, 3, 1)
    assert nw.networth == Decimal("150000")
    assert nw.total_assets == Decimal("200000")
    assert nw.total_liabilities == Decimal("50000")


# --- AccountBalance from_dict ---


def test_account_balance_from_dict() -> None:
    d = {
        "date": "2026-02-28",
        "user_account_id": 789,
        "balance": 5432.10,
        "synced_at": "2026-03-18T00:00:00",  # should be ignored
    }
    bal = account_balance_from_dict(d)
    assert bal.date == date(2026, 2, 28)
    assert bal.user_account_id == 789
    assert bal.balance == Decimal("5432.1")


# --- InvestmentPerformance from_dict ---


def test_investment_performance_from_dict() -> None:
    d = {
        "date": "2026-03-15",
        "user_account_id": 100,
        "performance": 0.0823,
        "synced_at": "",
    }
    ip = investment_performance_from_dict(d)
    assert ip.date == date(2026, 3, 15)
    assert ip.user_account_id == 100
    assert ip.performance == Decimal("0.0823")


def test_investment_performance_from_dict_none_performance() -> None:
    d = {
        "date": "2026-03-15",
        "user_account_id": 100,
        "performance": None,
        "synced_at": "",
    }
    ip = investment_performance_from_dict(d)
    assert ip.performance is None


# --- BenchmarkPerformance from_dict ---


def test_benchmark_performance_from_dict() -> None:
    d = {
        "date": "2026-03-15",
        "benchmark": "^INX",
        "performance": 0.1245,
        "synced_at": "",
    }
    bp = benchmark_performance_from_dict(d)
    assert bp.date == date(2026, 3, 15)
    assert bp.benchmark == "^INX"
    assert bp.performance == Decimal("0.1245")


# --- PortfolioVsBenchmark from_dict ---


def test_portfolio_vs_benchmark_from_dict() -> None:
    d = {
        "date": "2026-03-15",
        "portfolio_value": 105.5,
        "sp500_value": 103.2,
        "synced_at": "",
    }
    pvb = portfolio_vs_benchmark_from_dict(d)
    assert pvb.date == date(2026, 3, 15)
    assert pvb.portfolio_value == Decimal("105.5")
    assert pvb.sp500_value == Decimal("103.2")


def test_portfolio_vs_benchmark_from_dict_none_values() -> None:
    d = {
        "date": "2026-01-01",
        "portfolio_value": None,
        "sp500_value": None,
        "synced_at": "",
    }
    pvb = portfolio_vs_benchmark_from_dict(d)
    assert pvb.portfolio_value is None
    assert pvb.sp500_value is None


# --- synced_at / updated_at silently ignored ---


def test_synced_at_in_dict_is_ignored() -> None:
    """Extra keys like synced_at in the parser dict should not cause errors."""
    d = {
        "date": "2026-01-01",
        "user_account_id": 1,
        "balance": 100.0,
        "synced_at": "2026-03-18T12:00:00",
    }
    bal = account_balance_from_dict(d)
    assert bal.balance == Decimal("100")
    assert not hasattr(bal, "synced_at")


def test_updated_at_in_dict_is_ignored() -> None:
    """Extra keys like updated_at in the parser dict should not cause errors."""
    d = {
        "user_account_id": 1,
        "account_id": "",
        "name": "",
        "firm_name": "",
        "account_type": "",
        "account_type_group": None,
        "product_type": "",
        "currency": "USD",
        "is_asset": False,
        "is_closed": False,
        "created_at": None,
        "updated_at": "2026-03-18T00:00:00",
    }
    acct = account_from_dict(d)
    assert not hasattr(acct, "updated_at")
