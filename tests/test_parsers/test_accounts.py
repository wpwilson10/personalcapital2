"""Tests for the accounts parser."""

from decimal import Decimal
from typing import Any

from personalcapital2.parsers.accounts import parse_accounts, parse_accounts_summary


def _make_response(accounts: list[dict[str, object]]) -> dict[str, object]:
    return {"spData": {"accounts": accounts}}


def test_parse_basic_account() -> None:
    response = _make_response(
        [
            {
                "userAccountId": 123,
                "accountId": "100_200_123",
                "name": "My Checking",
                "firmName": "Chase",
                "accountTypeNew": "CHECKING",
                "accountTypeGroup": "BANK",
                "productType": "BANK",
                "currency": "USD",
                "isAsset": True,
                "createdDate": 1441151585000,  # 2015-09-02 UTC
                "closedDate": "",
            }
        ]
    )
    rows = parse_accounts(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["user_account_id"] == 123
    assert row["account_id"] == "100_200_123"
    assert row["name"] == "My Checking"
    assert row["firm_name"] == "Chase"
    assert row["account_type"] == "CHECKING"
    assert row["is_asset"] is True
    assert row["is_closed"] is False
    assert row["created_at"] == "2015-09-01"  # UTC conversion of epoch ms


def test_closed_account() -> None:
    response = _make_response(
        [
            {
                "userAccountId": 456,
                "name": "Old Card",
                "firmName": "Citi",
                "accountTypeNew": "CREDIT_CARD",
                "productType": "CREDIT_CARD",
                "isAsset": False,
                "createdDate": 1500000000000,
                "closedDate": "2024-06-15",
            }
        ]
    )
    rows = parse_accounts(response)
    assert len(rows) == 1
    assert rows[0]["is_closed"] is True


def test_fallback_to_account_type_when_no_new() -> None:
    response = _make_response(
        [
            {
                "userAccountId": 789,
                "name": "Savings",
                "firmName": "Ally",
                "accountType": "Savings",
                "productType": "BANK",
                "isAsset": True,
                "createdDate": 0,
                "closedDate": "",
            }
        ]
    )
    rows = parse_accounts(response)
    assert rows[0]["account_type"] == "Savings"
    assert rows[0]["created_at"] is None  # createdDate of 0 should be None


def test_empty_response() -> None:
    response = _make_response([])
    rows = parse_accounts(response)
    assert rows == []


def test_malformed_account_skipped_not_crash() -> None:
    """An account missing userAccountId is skipped, not crash."""
    malformed: dict[str, object] = {
        # missing userAccountId
        "name": "Bad Account",
        "firmName": "Bank",
        "accountTypeNew": "CHECKING",
        "productType": "BANK",
        "isAsset": True,
        "createdDate": 1441151585000,
        "closedDate": "",
    }
    valid: dict[str, object] = {
        "userAccountId": 123,
        "name": "Good Account",
        "firmName": "Chase",
        "accountTypeNew": "CHECKING",
        "productType": "BANK",
        "isAsset": True,
        "createdDate": 1441151585000,
        "closedDate": "",
    }
    response = _make_response([malformed, valid])
    rows = parse_accounts(response)
    assert len(rows) == 1
    assert rows[0]["user_account_id"] == 123


def test_account_id_defaults_to_empty_string() -> None:
    """When accountId is missing from the API response, account_id defaults to ''."""
    response = _make_response(
        [
            {
                "userAccountId": 999,
                "name": "No Account ID",
                "firmName": "Bank",
                "accountTypeNew": "SAVINGS",
                "productType": "BANK",
                "isAsset": True,
                "createdDate": 1500000000000,
                "closedDate": "",
                # accountId intentionally omitted
            }
        ]
    )
    rows = parse_accounts(response)
    assert len(rows) == 1
    assert rows[0]["account_id"] == ""


def test_missing_sp_data() -> None:
    rows = parse_accounts({})
    assert rows == []


# --- parse_accounts_summary ---


def test_parse_accounts_summary() -> None:
    response: dict[str, Any] = {
        "spData": {
            "networth": 789760.45,
            "assets": 791020.76,
            "liabilities": 1260.32,
            "cashAccountsTotal": 16762.64,
            "investmentAccountsTotal": 774258.12,
            "creditCardAccountsTotal": 1260.32,
            "mortgageAccountsTotal": 0.0,
            "loanAccountsTotal": 0.0,
            "otherAssetAccountsTotal": 0.0,
            "otherLiabilitiesAccountsTotal": 0.0,
            "accounts": [],
        }
    }
    result = parse_accounts_summary(response)
    assert result["networth"] == 789760.45
    assert result["assets"] == 791020.76
    assert result["liabilities"] == 1260.32
    assert result["cash_total"] == 16762.64
    assert result["investment_total"] == 774258.12
    assert result["credit_card_total"] == 1260.32
    assert result["mortgage_total"] == 0.0
    assert result["loan_total"] == 0.0
    assert result["other_asset_total"] == 0.0
    assert result["other_liabilities_total"] == 0.0


def test_account_with_nan_fees_not_dropped() -> None:
    """Accounts with NaN in optional fee fields should be included, not skipped."""
    response = _make_response(
        [
            {
                "userAccountId": 555,
                "name": "Investment Account",
                "firmName": "Fidelity",
                "accountTypeNew": "INVESTMENT",
                "productType": "INVESTMENT",
                "isAsset": True,
                "createdDate": 1500000000000,
                "closedDate": "",
                "feesPerYear": "NaN",
                "fundFees": "NaN",
                "totalFee": "NaN",
                "advisoryFeePercentage": "NaN",
                "balance": 50000.0,
            }
        ]
    )
    rows = parse_accounts(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["user_account_id"] == 555
    assert row["fees_per_year"] is None
    assert row["fund_fees"] is None
    assert row["total_fee"] is None
    assert row["advisory_fee_percentage"] is None
    assert row["balance"] == Decimal("50000")


def test_parse_accounts_summary_missing_sp_data() -> None:
    result = parse_accounts_summary({})
    assert result == {}
