"""Tests for the performance parser."""

from decimal import Decimal

from personalcapital2.parsers.performance import (
    parse_account_summaries,
    parse_benchmark_performance,
    parse_investment_performance,
)


def test_parse_investment_performance() -> None:
    response = {
        "spData": {
            "performanceHistory": [
                {
                    "date": "2026-03-13",
                    "aggregatePerformance": 47.24,
                    "aggregateAnnotation": "Accurate performance data unavailable",
                    "compositeInceptionReturn": 1.47,
                    "305886794": 72.23,
                    "305886794Annotation": "performance data is not accurate",
                    "1511350375": 0.08,
                },
            ]
        }
    }
    rows = parse_investment_performance(response)
    assert len(rows) == 2

    by_account = {r["user_account_id"]: r for r in rows}
    assert by_account[305886794]["performance"] == Decimal("72.23")
    assert by_account[1511350375]["performance"] == Decimal("0.08")
    assert by_account[305886794]["date"] == "2026-03-13"


def test_parse_benchmark_performance() -> None:
    response = {
        "spData": {
            "benchmarkPerformanceHistory": [
                {
                    "date": "2026-03-13",
                    "^PC_US_BONDS": 41.46,
                    "^PC_BLENDED": 284.55,
                    "^PC_INTL_STOCKS": 147.85,
                    "^PC_INTL_BONDS": -9.36,
                    "^PC_US_STOCKS": 554.0,
                    "^PC_ALTERNATIVES": 154.34,
                },
            ]
        }
    }
    rows = parse_benchmark_performance(response)
    assert len(rows) == 6

    by_bench = {r["benchmark"]: r for r in rows}
    assert by_bench["^PC_US_STOCKS"]["performance"] == Decimal("554.0")
    assert by_bench["^PC_INTL_BONDS"]["performance"] == Decimal("-9.36")
    assert by_bench["^PC_BLENDED"]["date"] == "2026-03-13"


def test_skips_annotation_keys() -> None:
    response = {
        "spData": {
            "performanceHistory": [
                {
                    "date": "2026-03-13",
                    "aggregatePerformance": 47.24,
                    "305886794Annotation": "not accurate",
                    "305886794": 72.23,
                },
            ]
        }
    }
    rows = parse_investment_performance(response)
    assert len(rows) == 1
    assert rows[0]["user_account_id"] == 305886794


def test_empty_performance() -> None:
    response: dict[str, object] = {
        "spData": {"performanceHistory": [], "benchmarkPerformanceHistory": []}
    }
    assert parse_investment_performance(response) == []
    assert parse_benchmark_performance(response) == []


# --- parse_account_summaries ---


def test_parse_account_summaries() -> None:
    response = {
        "spData": {
            "accountSummaries": [
                {
                    "userAccountId": 305886794,
                    "accountName": "Brokerage",
                    "siteName": "Vanguard",
                    "currentBalance": 150000.0,
                    "percentOfTotal": 75.5,
                    "income": 1200.0,
                    "expense": 50.0,
                    "cashFlow": 1150.0,
                    "oneDayBalanceValueChange": -500.0,
                    "oneDayBalancePercentageChange": -0.33,
                    "dateRangeBalanceValueChange": 10000.0,
                    "dateRangeBalancePercentageChange": 7.14,
                    "dateRangePerformanceValueChange": 8500.0,
                    "oneDayPerformanceValueChange": -450.0,
                    "balanceAsOfEndDate": 150000.0,
                    "closedDate": "",
                }
            ],
            "performanceHistory": [],
        }
    }
    rows = parse_account_summaries(response)
    assert len(rows) == 1
    row = rows[0]
    assert row["user_account_id"] == 305886794
    assert row["account_name"] == "Brokerage"
    assert row["site_name"] == "Vanguard"
    assert row["current_balance"] == 150000.0
    assert row["percent_of_total"] == 75.5
    assert row["income"] == 1200.0
    assert row["expense"] == 50.0
    assert row["cash_flow"] == 1150.0
    assert row["one_day_balance_value_change"] == -500.0
    assert row["date_range_balance_value_change"] == 10000.0
    assert row["date_range_performance_value_change"] == 8500.0
    assert row["balance_as_of_end_date"] == 150000.0
    assert row["closed_date"] is None


def test_investment_performance_nan_coerced_to_none() -> None:
    """NaN in per-account performance should become None, not skip the entry."""
    response = {
        "spData": {
            "performanceHistory": [
                {
                    "date": "2026-03-13",
                    "aggregatePerformance": 47.24,
                    "305886794": "NaN",
                    "1511350375": 0.08,
                },
            ]
        }
    }
    rows = parse_investment_performance(response)
    assert len(rows) == 2
    by_acct = {r["user_account_id"]: r for r in rows}
    assert by_acct[305886794]["performance"] is None
    assert by_acct[1511350375]["performance"] == Decimal("0.08")


def test_parse_account_summaries_empty() -> None:
    response: dict[str, object] = {"spData": {"performanceHistory": []}}
    rows = parse_account_summaries(response)
    assert rows == []
