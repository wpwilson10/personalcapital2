"""Tests for the quotes parser."""

from decimal import Decimal
from typing import Any

from personalcapital2.parsers.quotes import (
    parse_market_quotes,
    parse_portfolio_snapshot,
    parse_portfolio_vs_benchmark,
)


def test_parse_both_series() -> None:
    response = {
        "spData": {
            "histories": [
                {"date": "2026-03-13", "YOU": 302.45, "^INX": 351.4},
                {"date": "2026-03-12", "YOU": 305.10, "^INX": 353.2},
            ]
        }
    }
    rows = parse_portfolio_vs_benchmark(response)
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
    rows = parse_portfolio_vs_benchmark(response)
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
    rows = parse_portfolio_vs_benchmark(response)
    assert rows == []


def test_empty_histories() -> None:
    response: dict[str, object] = {"spData": {"histories": []}}
    assert parse_portfolio_vs_benchmark(response) == []


# --- parse_portfolio_snapshot and parse_market_quotes ---


def test_parse_portfolio_snapshot() -> None:
    response: dict[str, Any] = {
        "spData": {
            "latestPortfolio": {
                "last": 302.45,
                "change": -2.10,
                "percentChange": -0.69,
            },
            "histories": [],
        }
    }
    result = parse_portfolio_snapshot(response)
    assert result["last"] == 302.45
    assert result["change"] == -2.10
    assert result["percent_change"] == -0.69


def test_parse_portfolio_snapshot_missing() -> None:
    response: dict[str, object] = {"spData": {"histories": []}}
    result = parse_portfolio_snapshot(response)
    assert result == {}


def test_parse_market_quotes() -> None:
    response = {
        "spData": {
            "latestQuotes": [
                {
                    "ticker": "^INX",
                    "last": 5667.56,
                    "change": -44.12,
                    "percentChange": -0.77,
                    "longName": "S&P 500",
                    "date": "2026-03-14",
                }
            ],
            "histories": [],
        }
    }
    rows = parse_market_quotes(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "^INX"
    assert row["last"] == Decimal("5667.56")
    assert row["change"] == Decimal("-44.12")
    assert row["percent_change"] == Decimal("-0.77")
    assert row["long_name"] == "S&P 500"
    assert row["date"] == "2026-03-14"


def test_parse_market_quotes_skips_nan() -> None:
    response = {
        "spData": {
            "latestQuotes": [
                {
                    "ticker": "^INX",
                    "last": float("nan"),
                    "change": 0.0,
                    "percentChange": 0.0,
                    "longName": "S&P 500",
                    "date": "2026-03-14",
                },
                {
                    "ticker": "^DJI",
                    "last": 42000.0,
                    "change": -100.0,
                    "percentChange": -0.24,
                    "longName": "Dow Jones",
                    "date": "2026-03-14",
                },
            ],
            "histories": [],
        }
    }
    rows = parse_market_quotes(response)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "^DJI"
