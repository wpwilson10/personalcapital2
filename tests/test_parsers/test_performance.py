"""Tests for the performance parser."""

from decimal import Decimal

from personalcapital2.parsers.performance import (
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
    rows = parse_investment_performance(response, "2026-03-14T10:00:00")
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
    rows = parse_benchmark_performance(response, "2026-03-14T10:00:00")
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
    rows = parse_investment_performance(response, "2026-03-14T10:00:00")
    assert len(rows) == 1
    assert rows[0]["user_account_id"] == 305886794


def test_empty_performance() -> None:
    response: dict[str, object] = {
        "spData": {"performanceHistory": [], "benchmarkPerformanceHistory": []}
    }
    assert parse_investment_performance(response, "2026-03-14T10:00:00") == []
    assert parse_benchmark_performance(response, "2026-03-14T10:00:00") == []
