"""Tests for the quotes parser."""

from decimal import Decimal

from personalcapital2.parsers.quotes import parse_portfolio_vs_benchmark


def test_parse_both_series() -> None:
    response = {
        "spData": {
            "histories": [
                {"date": "2026-03-13", "YOU": 302.45, "^INX": 351.4},
                {"date": "2026-03-12", "YOU": 305.10, "^INX": 353.2},
            ]
        }
    }
    rows = parse_portfolio_vs_benchmark(response, "2026-03-14T10:00:00")
    assert len(rows) == 2
    assert rows[0]["portfolio_value"] == Decimal("302.45")
    assert rows[0]["sp500_value"] == Decimal("351.4")
    assert rows[0]["date"] == "2026-03-13"


def test_missing_you_series() -> None:
    """Early dates may only have ^INX data."""
    response = {
        "spData": {
            "histories": [
                {"date": "1999-12-31", "^INX": 0.0},
            ]
        }
    }
    rows = parse_portfolio_vs_benchmark(response, "2026-03-14T10:00:00")
    assert len(rows) == 1
    assert rows[0]["portfolio_value"] is None
    assert rows[0]["sp500_value"] == Decimal("0.0")


def test_skips_entries_with_neither_series() -> None:
    response = {
        "spData": {
            "histories": [
                {"date": "2026-03-13", "^PC_US_STOCKS": 774.45},
            ]
        }
    }
    rows = parse_portfolio_vs_benchmark(response, "2026-03-14T10:00:00")
    assert rows == []


def test_empty_histories() -> None:
    response: dict[str, object] = {"spData": {"histories": []}}
    assert parse_portfolio_vs_benchmark(response, "2026-03-14T10:00:00") == []
