"""Tests for typed dataclass models and their from_dict converters."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from personalcapital2.models import (
    Account,
    Transaction,
    account_balance_from_dict,
    account_from_dict,
    account_performance_summary_from_dict,
    accounts_summary_from_dict,
    benchmark_performance_from_dict,
    category_from_dict,
    holding_from_dict,
    investment_performance_from_dict,
    market_quote_from_dict,
    net_worth_entry_from_dict,
    net_worth_summary_from_dict,
    portfolio_snapshot_from_dict,
    portfolio_vs_benchmark_from_dict,
    spending_detail_from_dict,
    spending_summary_from_dict,
    transaction_from_dict,
    transactions_summary_from_dict,
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
        balance=None,
        available_cash=None,
        account_type_subtype=None,
        last_refreshed=None,
        oldest_transaction_date=None,
        advisory_fee_percentage=None,
        fees_per_year=None,
        fund_fees=None,
        total_fee=None,
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
        merchant_id=None,
        merchant_type=None,
        transaction_type=None,
        sub_type=None,
        status=None,
        currency="USD",
        is_duplicate=False,
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
        "balance": 1500.50,
        "available_cash": "200.00",
        "account_type_subtype": "SAVINGS",
        "last_refreshed": "2026-03-01",
        "oldest_transaction_date": "2022-08-31",
        "advisory_fee_percentage": 0.25,
        "fees_per_year": 50.0,
        "fund_fees": 10.0,
        "total_fee": 60.0,
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
    assert acct.balance == Decimal("1500.5")
    assert acct.available_cash == Decimal("200.00")
    assert acct.account_type_subtype == "SAVINGS"
    assert acct.last_refreshed == date(2026, 3, 1)
    assert acct.oldest_transaction_date == date(2022, 8, 31)
    assert acct.advisory_fee_percentage == Decimal("0.25")
    assert acct.fees_per_year == Decimal("50")
    assert acct.fund_fees == Decimal("10")
    assert acct.total_fee == Decimal("60")


def test_account_from_dict_nan_fees_become_none() -> None:
    """NaN fee fields from API should become None in the Account model."""
    d: dict[str, Any] = {
        "user_account_id": 555,
        "account_id": "ACC-555",
        "name": "Investment",
        "firm_name": "Fidelity",
        "account_type": "INVESTMENT",
        "account_type_group": "INVESTMENT",
        "product_type": "INVESTMENT",
        "currency": "USD",
        "is_asset": True,
        "is_closed": False,
        "created_at": "2024-01-01",
        "balance": 50000.0,
        "fees_per_year": "NaN",
        "fund_fees": "NaN",
        "total_fee": "NaN",
        "advisory_fee_percentage": "NaN",
    }
    acct = account_from_dict(d)
    assert acct.fees_per_year is None
    assert acct.fund_fees is None
    assert acct.total_fee is None
    assert acct.advisory_fee_percentage is None
    assert acct.balance == Decimal("50000")


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
    }
    acct = account_from_dict(d)
    assert acct.account_type_group is None
    assert acct.created_at is None
    assert acct.balance is None
    assert acct.available_cash is None
    assert acct.account_type_subtype is None
    assert acct.last_refreshed is None
    assert acct.oldest_transaction_date is None
    assert acct.advisory_fee_percentage is None
    assert acct.fees_per_year is None
    assert acct.fund_fees is None
    assert acct.total_fee is None


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
        "merchant_id": "mid-123",
        "merchant_type": "GROCERY",
        "transaction_type": "Purchase",
        "sub_type": "debit",
        "status": "posted",
        "currency": "USD",
        "is_duplicate": False,
    }
    txn = transaction_from_dict(d)
    assert txn.user_transaction_id == 999
    assert txn.date == date(2026, 1, 20)
    assert txn.amount == Decimal("42.5")
    assert txn.is_spending is True
    assert txn.original_description == "GROCERY STORE #1234"
    assert txn.category_id == 7
    assert txn.merchant == "FreshMart"
    assert txn.merchant_id == "mid-123"
    assert txn.merchant_type == "GROCERY"
    assert txn.sub_type == "debit"
    assert txn.is_duplicate is False


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
        "merchant_id": None,
        "merchant_type": None,
        "transaction_type": None,
        "sub_type": None,
        "status": None,
        "currency": "USD",
        "is_duplicate": False,
    }
    txn = transaction_from_dict(d)
    assert txn.original_description is None
    assert txn.simple_description is None
    assert txn.category_id is None
    assert txn.merchant is None
    assert txn.merchant_id is None
    assert txn.merchant_type is None
    assert txn.transaction_type is None
    assert txn.sub_type is None
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
        "cost_basis": 1500.00,
        "one_day_percent_change": 1.25,
        "one_day_value_change": 21.94,
        "fees_per_year": 5.0,
        "fund_fees": 0.03,
    }
    h = holding_from_dict(d)
    assert h.snapshot_date == date(2026, 3, 18)
    assert h.ticker == "AAPL"
    assert h.cusip == "037833100"
    assert h.quantity == Decimal("10")
    assert h.value == Decimal("1755")
    assert h.holding_percentage == Decimal("0.15")
    assert h.cost_basis == Decimal("1500")
    assert h.one_day_percent_change == Decimal("1.25")
    assert h.one_day_value_change == Decimal("21.94")
    assert h.fees_per_year == Decimal("5")
    assert h.fund_fees == Decimal("0.03")


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
    assert h.cost_basis is None
    assert h.one_day_percent_change is None
    assert h.one_day_value_change is None
    assert h.fees_per_year is None
    assert h.fund_fees is None


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
    }
    ip = investment_performance_from_dict(d)
    assert ip.performance is None


# --- BenchmarkPerformance from_dict ---


def test_benchmark_performance_from_dict() -> None:
    d = {
        "date": "2026-03-15",
        "benchmark": "^INX",
        "performance": 0.1245,
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
    }
    pvb = portfolio_vs_benchmark_from_dict(d)
    assert pvb.portfolio_value is None
    assert pvb.sp500_value is None


# --- Summary model converters ---


def test_accounts_summary_from_dict() -> None:
    d = {
        "networth": 789760.45,
        "assets": 791020.76,
        "liabilities": 1260.32,
        "cash_total": 16762.64,
        "investment_total": 774258.12,
        "credit_card_total": 1260.32,
        "mortgage_total": 0.0,
        "loan_total": 0.0,
        "other_asset_total": 0.0,
        "other_liabilities_total": 0.0,
    }
    s = accounts_summary_from_dict(d)
    assert s.networth == Decimal("789760.45")
    assert s.assets == Decimal("791020.76")
    assert s.liabilities == Decimal("1260.32")
    assert s.cash_total == Decimal("16762.64")
    assert s.investment_total == Decimal("774258.12")
    assert s.credit_card_total == Decimal("1260.32")
    assert s.mortgage_total == Decimal("0")
    assert s.loan_total == Decimal("0")
    assert s.other_asset_total == Decimal("0")
    assert s.other_liabilities_total == Decimal("0")


def test_transactions_summary_from_dict() -> None:
    d = {
        "money_in": 5000.00,
        "money_out": 3200.50,
        "net_cashflow": 1799.50,
        "average_in": 2500.00,
        "average_out": 1600.25,
        "start_date": "2026-01-01",
        "end_date": "2026-03-14",
    }
    s = transactions_summary_from_dict(d)
    assert s.money_in == Decimal("5000")
    assert s.money_out == Decimal("3200.5")
    assert s.net_cashflow == Decimal("1799.5")
    assert s.average_in == Decimal("2500")
    assert s.average_out == Decimal("1600.25")
    assert s.start_date == date(2026, 1, 1)
    assert s.end_date == date(2026, 3, 14)


def test_net_worth_summary_from_dict() -> None:
    d = {
        "date_range_change": 15000.50,
        "date_range_percentage_change": 1.92,
        "cash_change": 2000.00,
        "cash_percentage_change": 0.25,
        "investment_change": 13000.50,
        "investment_percentage_change": 1.68,
        "credit_change": -100.00,
        "credit_percentage_change": -7.94,
        "mortgage_change": 0.0,
        "mortgage_percentage_change": 0.0,
        "loan_change": 0.0,
        "loan_percentage_change": 0.0,
        "other_assets_change": 0.0,
        "other_assets_percentage_change": 0.0,
        "other_liabilities_change": 0.0,
        "other_liabilities_percentage_change": 0.0,
    }
    s = net_worth_summary_from_dict(d)
    assert s.date_range_change == Decimal("15000.5")
    assert s.date_range_percentage_change == Decimal("1.92")
    assert s.cash_change == Decimal("2000")
    assert s.investment_change == Decimal("13000.5")
    assert s.credit_change == Decimal("-100")


def test_account_performance_summary_from_dict() -> None:
    d = {
        "user_account_id": 305886794,
        "account_name": "Brokerage",
        "site_name": "Vanguard",
        "current_balance": 150000.0,
        "percent_of_total": 75.5,
        "income": 1200.0,
        "expense": 50.0,
        "cash_flow": 1150.0,
        "one_day_balance_value_change": -500.0,
        "one_day_balance_percentage_change": -0.33,
        "date_range_balance_value_change": 10000.0,
        "date_range_balance_percentage_change": 7.14,
        "date_range_performance_value_change": 8500.0,
        "one_day_performance_value_change": -450.0,
        "balance_as_of_end_date": 150000.0,
        "closed_date": None,
    }
    s = account_performance_summary_from_dict(d)
    assert s.user_account_id == 305886794
    assert s.account_name == "Brokerage"
    assert s.current_balance == Decimal("150000")
    assert s.percent_of_total == Decimal("75.5")
    assert s.income == Decimal("1200")
    assert s.cash_flow == Decimal("1150")
    assert s.closed_date is None


def test_portfolio_snapshot_from_dict() -> None:
    d = {
        "last": 302.45,
        "change": -2.10,
        "percent_change": -0.69,
    }
    s = portfolio_snapshot_from_dict(d)
    assert s.last == Decimal("302.45")
    assert s.change == Decimal("-2.1")
    assert s.percent_change == Decimal("-0.69")


def test_market_quote_from_dict() -> None:
    d = {
        "ticker": "^INX",
        "last": 5667.56,
        "change": -44.12,
        "percent_change": -0.77,
        "long_name": "S&P 500",
        "date": "2026-03-14",
    }
    q = market_quote_from_dict(d)
    assert q.ticker == "^INX"
    assert q.last == Decimal("5667.56")
    assert q.change == Decimal("-44.12")
    assert q.percent_change == Decimal("-0.77")
    assert q.long_name == "S&P 500"
    assert q.date == date(2026, 3, 14)


# --- Spending converters ---


def test_spending_detail_from_dict() -> None:
    d = {"date": "2026-03-01", "amount": 516.88}
    det = spending_detail_from_dict(d)
    assert det.date == date(2026, 3, 1)
    assert det.amount == Decimal("516.88")


def test_spending_summary_from_dict() -> None:
    d = {
        "type": "MONTH",
        "average": 3683.74,
        "current": 3673.54,
        "target": 2836.88,
        "details": [
            {"date": "2026-03-01", "amount": 516.88},
            {"date": "2026-03-02", "amount": 0},
        ],
    }
    s = spending_summary_from_dict(d)
    assert s.type == "MONTH"
    assert s.average == Decimal("3683.74")
    assert s.current == Decimal("3673.54")
    assert s.target == Decimal("2836.88")
    assert len(s.details) == 2
    assert s.details[0].date == date(2026, 3, 1)
    assert s.details[0].amount == Decimal("516.88")


def test_spending_summary_from_dict_no_average() -> None:
    d: dict[str, Any] = {
        "type": "YEAR",
        "current": 10000.0,
        "target": 30000.0,
        "details": [],
    }
    s = spending_summary_from_dict(d)
    assert s.average is None
    assert s.details == ()
