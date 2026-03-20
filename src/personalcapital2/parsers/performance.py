"""Parse getPerformanceHistories response into investment and benchmark performance dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import (
    is_account_id,
    safe_decimal,
    safe_decimal_or_none,
    validate_and_extract,
    validate_date,
)

log = logging.getLogger(__name__)

# Keys to skip when extracting per-account performance
_SKIP_KEYS = frozenset(
    {"date", "aggregatePerformance", "aggregateAnnotation", "compositeInceptionReturn"}
)

# Known keys for performance history entries (account IDs are dynamic)
_KNOWN_PERF_KEYS = frozenset(
    {
        "date",
        "aggregatePerformance",
        "aggregateAnnotation",
        "compositeInceptionReturn",
    }
)

# Benchmark keys are detected dynamically (any key starting with ^)
_KNOWN_BENCH_KEYS = frozenset({"date"})


def parse_investment_performance(response: dict[str, Any], synced_at: str) -> list[dict[str, Any]]:
    """Parse performanceHistory into per-account investment performance dicts.

    Extracts per-account cumulative returns, filtering out annotation keys
    and aggregate/metadata fields.

    Args:
        response: Raw API response from getPerformanceHistories.
        synced_at: ISO-8601 timestamp of this sync run.

    Returns:
        List of performance dicts with keys: date, user_account_id, performance, synced_at.
    """
    perf_history, _sp_data_keys = validate_and_extract(
        response,
        ["spData", "performanceHistory"],
        _KNOWN_PERF_KEYS,
        "getPerformanceHistories/performance",
    )
    rows: list[dict[str, Any]] = []
    skipped = 0

    for entry in perf_history:
        try:
            date = validate_date(entry["date"], "investment_performance")
            for key, value in entry.items():
                if key in _SKIP_KEYS or not is_account_id(key):
                    continue
                perf_value = safe_decimal_or_none(value, f"performance[{key}]")
                rows.append(
                    {
                        "date": date,
                        "user_account_id": int(key),
                        "performance": perf_value,
                        "synced_at": synced_at,
                    }
                )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed investment performance entry: %s", exc)

    if skipped:
        log.warning(
            "Skipped %d malformed investment performance entries out of %d",
            skipped,
            len(perf_history),
        )
    log.info("Parsed %d investment performance daily entries", len(rows))
    return rows


def parse_benchmark_performance(response: dict[str, Any], synced_at: str) -> list[dict[str, Any]]:
    """Parse benchmarkPerformanceHistory into benchmark performance dicts.

    Args:
        response: Raw API response from getPerformanceHistories.
        synced_at: ISO-8601 timestamp of this sync run.

    Returns:
        List of benchmark dicts with keys: date, benchmark, performance, synced_at.
    """
    bench_history, _sp_data_keys = validate_and_extract(
        response,
        ["spData", "benchmarkPerformanceHistory"],
        _KNOWN_BENCH_KEYS,
        "getPerformanceHistories/benchmark",
    )
    rows: list[dict[str, Any]] = []
    skipped = 0

    for entry in bench_history:
        try:
            date = validate_date(entry["date"], "benchmark_performance")
            for key, value in entry.items():
                if not key.startswith("^"):
                    continue
                if value is None:
                    continue
                rows.append(
                    {
                        "date": date,
                        "benchmark": key,
                        "performance": safe_decimal(value, f"benchmark[{key}]"),
                        "synced_at": synced_at,
                    }
                )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed benchmark performance entry: %s", exc)

    if skipped:
        log.warning(
            "Skipped %d malformed benchmark performance entries out of %d",
            skipped,
            len(bench_history),
        )
    log.info("Parsed %d benchmark performance daily entries", len(rows))
    return rows
