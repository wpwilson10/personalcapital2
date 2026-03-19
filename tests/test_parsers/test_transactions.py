"""Tests for the transactions parser."""

from typing import Any

from personalcapital2.parsers.transactions import extract_categories, parse_transactions


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
    "transactionType": "Payment",
    "status": "posted",
    "currency": "USD",
}


def test_parse_transaction() -> None:
    response = _make_response([SAMPLE_TXN])
    rows = parse_transactions(response, "2026-03-14T10:00:00")
    assert len(rows) == 1
    row = rows[0]
    assert row["user_transaction_id"] == 100001
    assert row["date"] == "2026-01-15"
    assert row["amount"] == 33.64
    assert row["is_cash_in"] is False
    assert row["is_spending"] is True
    assert row["description"] == "Uber"
    assert row["category_id"] == 39
    assert row["synced_at"] == "2026-03-14T10:00:00"


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
    rows = parse_transactions(response, "2026-03-14T10:00:00")
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
    rows = parse_transactions(response, "2026-03-14T10:00:00")
    # The valid transaction should be parsed, the malformed one skipped
    assert len(rows) == 1
    assert rows[0]["user_transaction_id"] == 100001


def test_empty_transactions() -> None:
    response = _make_response([])
    assert parse_transactions(response, "2026-03-14T10:00:00") == []
    assert extract_categories(response) == []
