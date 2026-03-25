"""Tests for the spending parser."""

from typing import Any

from personalcapital2.parsers.spending import parse_spending


def test_parse_spending_happy_path() -> None:
    response: dict[str, Any] = {
        "spData": {
            "intervals": [
                {
                    "type": "MONTH",
                    "average": 3683.74,
                    "current": 3673.54,
                    "target": 2836.88,
                    "details": [
                        {"date": "2026-03-01", "amount": 516.88},
                        {"date": "2026-03-02", "amount": 0},
                    ],
                }
            ]
        }
    }
    rows = parse_spending(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["type"] == "MONTH"
    assert row["average"] == 3683.74
    assert row["current"] == 3673.54
    assert row["target"] == 2836.88
    assert len(row["details"]) == 2
    assert row["details"][0]["date"] == "2026-03-01"
    from decimal import Decimal

    assert row["details"][0]["amount"] == Decimal("516.88")


def test_parse_spending_multiple_intervals() -> None:
    response: dict[str, Any] = {
        "spData": {
            "intervals": [
                {
                    "type": "MONTH",
                    "average": 3000.0,
                    "current": 2500.0,
                    "target": 2000.0,
                    "details": [],
                },
                {
                    "type": "WEEK",
                    "average": 700.0,
                    "current": 0.0,
                    "target": 500.0,
                    "details": [],
                },
                {
                    "type": "YEAR",
                    "current": 10000.0,
                    "target": 30000.0,
                    "details": [{"date": "2026-01-01", "amount": 3000.0}],
                },
            ]
        }
    }
    rows = parse_spending(response)
    assert len(rows) == 3
    assert rows[0]["type"] == "MONTH"
    assert rows[1]["type"] == "WEEK"
    assert rows[2]["type"] == "YEAR"
    # YEAR interval has no average
    assert rows[2]["average"] is None


def test_parse_spending_missing_sp_data() -> None:
    assert parse_spending({}) == []


def test_parse_spending_missing_intervals() -> None:
    response: dict[str, Any] = {"spData": {}}
    assert parse_spending(response) == []


def test_parse_spending_empty_intervals() -> None:
    response: dict[str, Any] = {"spData": {"intervals": []}}
    assert parse_spending(response) == []
