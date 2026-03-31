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

# Known non-account keys for performance history entries.
# Also used to skip when extracting per-account performance (account IDs are dynamic).
_KNOWN_PERF_KEYS = frozenset(
    {"date", "aggregatePerformance", "aggregateAnnotation", "compositeInceptionReturn"}
)

# Benchmark keys are detected dynamically (any key starting with ^)
_KNOWN_BENCH_KEYS = frozenset({"date"})


def parse_investment_performance(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse performanceHistory into per-account investment performance dicts.

    Extracts per-account cumulative returns, filtering out annotation keys
    and aggregate/metadata fields.

    Args:
        response: Raw API response from getPerformanceHistories.

    Returns:
        List of performance dicts with keys: date, user_account_id, performance.
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
                if key in _KNOWN_PERF_KEYS or not is_account_id(key):
                    continue
                perf_value = safe_decimal_or_none(value, f"performance[{key}]")
                rows.append(
                    {
                        "date": date,
                        "user_account_id": int(key),
                        "performance": perf_value,
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


def parse_benchmark_performance(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse benchmarkPerformanceHistory into benchmark performance dicts.

    Args:
        response: Raw API response from getPerformanceHistories.

    Returns:
        List of benchmark dicts with keys: date, benchmark, performance.
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


def parse_account_summaries(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract per-account performance summaries from spData.accountSummaries.

    Returns:
        List of dicts with normalized keys for AccountPerformanceSummary.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("Missing spData in performance response")
        return []
    sp_data: dict[str, Any] = response["spData"]
    if not isinstance(sp_data.get("accountSummaries"), list):
        log.warning("accountSummaries is not a list")
        return []
    raw_summaries: list[Any] = sp_data["accountSummaries"]

    summaries: list[dict[str, Any]] = [s for s in raw_summaries if isinstance(s, dict)]
    rows: list[dict[str, Any]] = []
    skipped = len(raw_summaries) - len(summaries)
    for s in summaries:
        try:
            closed_date = s.get("closedDate") or None
            rows.append(
                {
                    "user_account_id": s["userAccountId"],
                    "account_name": s.get("accountName", ""),
                    "site_name": s.get("siteName", ""),
                    "current_balance": s.get("currentBalance", 0),
                    "percent_of_total": s.get("percentOfTotal", 0),
                    "income": s.get("income", 0),
                    "expense": s.get("expense", 0),
                    "cash_flow": s.get("cashFlow", 0),
                    "one_day_balance_value_change": s.get("oneDayBalanceValueChange", 0),
                    "one_day_balance_percentage_change": s.get("oneDayBalancePercentageChange", 0),
                    "date_range_balance_value_change": s.get("dateRangeBalanceValueChange", 0),
                    "date_range_balance_percentage_change": s.get(
                        "dateRangeBalancePercentageChange", 0
                    ),
                    "date_range_performance_value_change": s.get(
                        "dateRangePerformanceValueChange", 0
                    ),
                    "one_day_performance_value_change": s.get("oneDayPerformanceValueChange", 0),
                    "balance_as_of_end_date": s.get("balanceAsOfEndDate", 0),
                    "closed_date": closed_date,
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed account summary: %s", exc)

    if skipped:
        log.warning(
            "Skipped %d malformed account summaries out of %d",
            skipped,
            len(raw_summaries),
        )
    log.info("Parsed %d account performance summaries", len(rows))
    return rows
