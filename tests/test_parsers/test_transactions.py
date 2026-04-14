"""Tests for the transactions parser."""

from decimal import Decimal
from typing import Any

from personalcapital2.parsers.transactions import (
    extract_categories,
    parse_transactions,
    parse_transactions_summary,
)


def _make_response(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"spData": {"transactions": transactions}}


SAMPLE_TXN = {
    "userTransactionId": 100001,
    "userAccountId": 123,
    "transactionDate": "2026-01-15",
    "amount": 33.64,
    "isCashIn": False,
    "isCashOut": True,
    "isIncome": False,
    "isSpending": True,
    "description": "Uber",
    "originalDescription": "Uber *trip",
    "simpleDescription": "Uber",
    "categoryId": 39,
    "categoryName": "Travel",
    "categoryType": "EXPENSE",
    "merchant": "Uber",
    "merchantId": "abc123",
    "merchantType": "RIDE_SHARE",
    "transactionType": "Payment",
    "subType": "debit",
    "status": "posted",
    "currency": "USD",
    "isDuplicate": False,
}


def test_parse_transaction() -> None:
    response = _make_response([SAMPLE_TXN])
    rows = parse_transactions(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["user_transaction_id"] == 100001
    assert row["date"] == "2026-01-15"
    assert row["amount"] == Decimal("33.64")
    assert row["is_cash_in"] is False
    assert row["is_spending"] is True
    assert row["description"] == "Uber"
    assert row["category_id"] == 39
    assert row["category_name"] == "Travel"
    assert row["category_type"] == "EXPENSE"
    assert row["merchant_id"] == "abc123"
    assert row["merchant_type"] == "RIDE_SHARE"
    assert row["sub_type"] == "debit"
    assert row["is_duplicate"] is False


def test_parse_transaction_missing_optional_new_fields() -> None:
    """Transactions missing merchantId/merchantType/subType get None; isDuplicate defaults False."""
    minimal_txn = {
        "userTransactionId": 100099,
        "userAccountId": 123,
        "transactionDate": "2026-01-15",
        "amount": 10.0,
        "description": "Test",
    }
    response = _make_response([minimal_txn])
    rows = parse_transactions(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["category_name"] is None
    assert row["category_type"] is None
    assert row["merchant_id"] is None
    assert row["merchant_type"] is None
    assert row["sub_type"] is None
    assert row["is_duplicate"] is False


def test_extract_categories_deduplicates() -> None:
    txn2 = {**SAMPLE_TXN, "userTransactionId": 100002}
    txn3 = {
        **SAMPLE_TXN,
        "userTransactionId": 100003,
        "categoryId": 27,
        "categoryName": "Groceries",
        "categoryType": "EXPENSE",
    }
    response = _make_response([SAMPLE_TXN, txn2, txn3])
    categories = extract_categories(response)
    assert len(categories) == 2
    ids = {c["category_id"] for c in categories}
    assert ids == {39, 27}


def test_income_transaction() -> None:
    income_txn = {
        **SAMPLE_TXN,
        "userTransactionId": 100004,
        "isCashIn": True,
        "isCashOut": False,
        "isIncome": True,
        "isSpending": False,
        "categoryType": "INCOME",
    }
    response = _make_response([income_txn])
    rows = parse_transactions(response)
    assert rows[0]["is_cash_in"] is True
    assert rows[0]["is_income"] is True


def test_malformed_transaction_skipped_not_crash() -> None:
    """A transaction missing a required key like userTransactionId is skipped, not crash."""
    malformed = {
        # missing userTransactionId
        "userAccountId": 123,
        "transactionDate": "2026-01-15",
        "amount": 10.0,
        "isCashIn": False,
        "isSpending": True,
        "description": "Bad txn",
        "categoryId": 39,
        "categoryName": "Travel",
        "categoryType": "EXPENSE",
    }
    response = _make_response([SAMPLE_TXN, malformed])
    rows = parse_transactions(response)
    # The valid transaction should be parsed, the malformed one skipped
    assert len(rows) == 1
    assert rows[0]["user_transaction_id"] == 100001


def test_empty_transactions() -> None:
    response = _make_response([])
    assert parse_transactions(response) == []
    assert extract_categories(response) == []


# --- parse_transactions_summary ---


def test_parse_transactions_summary() -> None:
    response: dict[str, Any] = {
        "spData": {
            "moneyIn": 5000.00,
            "moneyOut": 3200.50,
            "netCashflow": 1799.50,
            "averageIn": 2500.00,
            "averageOut": 1600.25,
            "startDate": "2026-01-01",
            "endDate": "2026-03-14",
            "transactions": [],
        }
    }
    result = parse_transactions_summary(response)
    assert result["money_in"] == 5000.00
    assert result["money_out"] == 3200.50
    assert result["net_cashflow"] == 1799.50
    assert result["average_in"] == 2500.00
    assert result["average_out"] == 1600.25
    assert result["start_date"] == "2026-01-01"
    assert result["end_date"] == "2026-03-14"


def test_parse_transactions_summary_missing_sp_data() -> None:
    result = parse_transactions_summary({})
    assert result == {}
