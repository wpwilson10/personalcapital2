"""Tests for the holdings parser."""

from decimal import Decimal

from personalcapital2.parsers.holdings import parse_holdings, parse_holdings_total


def _make_response(holdings: list[dict[str, object]]) -> dict[str, object]:
    return {"spData": {"holdings": holdings}}


def test_parse_holding_with_ticker() -> None:
    response = _make_response(
        [
            {
                "userAccountId": 123,
                "ticker": "VTSAX",
                "cusip": "922908769",
                "description": "Vanguard Total Stock Market Index Fund",
                "quantity": 100.5,
                "price": 120.30,
                "value": 12090.15,
                "holdingType": "Fund",
                "holdingPercentage": 25.5,
                "source": "YODLEE",
            }
        ]
    )
    rows = parse_holdings(response, "2026-03-14")
    assert len(rows) == 1
    row = rows[0]
    assert row["snapshot_date"] == "2026-03-14"
    assert row["ticker"] == "VTSAX"
    assert row["cusip"] == "922908769"
    assert row["quantity"] == Decimal("100.5")
    assert row["value"] == Decimal("12090.15")


def test_empty_ticker_becomes_none() -> None:
    response = _make_response(
        [
            {
                "userAccountId": 456,
                "ticker": "",
                "cusip": "",
                "description": "Employer Restricted Fund",
                "quantity": 50.0,
                "price": 10.0,
                "value": 500.0,
            }
        ]
    )
    rows = parse_holdings(response, "2026-03-14")
    assert rows[0]["ticker"] is None
    assert rows[0]["cusip"] is None


def test_missing_ticker_key() -> None:
    response = _make_response(
        [
            {
                "userAccountId": 789,
                "description": "Cash",
                "quantity": 0.0,
                "price": 1.0,
                "value": 1000.0,
                "holdingType": "Cash",
            }
        ]
    )
    rows = parse_holdings(response, "2026-03-14")
    assert rows[0]["ticker"] is None
    assert rows[0]["cusip"] is None


def test_holdings_with_all_empty_identifiers_skipped() -> None:
    """Holdings with cusip=None, ticker=None, and description='' are skipped."""
    response = _make_response(
        [
            {
                "userAccountId": 123,
                "ticker": "",
                "cusip": "",
                "description": "",
                "quantity": 0.0,
                "price": 0.0,
                "value": 0.0,
            },
            {
                "userAccountId": 123,
                "ticker": "VTSAX",
                "cusip": "922908769",
                "description": "Vanguard Total Stock Market",
                "quantity": 100.0,
                "price": 120.0,
                "value": 12000.0,
            },
        ]
    )
    rows = parse_holdings(response, "2026-03-14")
    # The holding with all-empty identifiers should be skipped
    assert len(rows) == 1
    assert rows[0]["ticker"] == "VTSAX"


def test_empty_holdings() -> None:
    assert parse_holdings(_make_response([]), "2026-03-14") == []


# --- parse_holdings_total ---


def test_parse_holdings_total() -> None:
    response: dict[str, object] = {
        "spData": {
            "holdingsTotalValue": 123456.78,
            "holdings": [],
        }
    }
    result = parse_holdings_total(response)
    assert result == Decimal("123456.78")


def test_parse_holdings_total_missing() -> None:
    response: dict[str, object] = {"spData": {"holdings": []}}
    result = parse_holdings_total(response)
    assert result == Decimal(0)
