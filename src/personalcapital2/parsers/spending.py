"""Parse getUserSpending response into structured spending dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import safe_decimal, validate_date

log = logging.getLogger(__name__)


def parse_spending(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse getUserSpending response into spending interval dicts.

    Each interval contains a type (MONTH, WEEK, YEAR), summary values,
    and daily/monthly spending details.

    Args:
        response: Raw API response from getUserSpending.

    Returns:
        List of spending interval dicts with normalized keys.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("Missing spData in spending response")
        return []
    sp_data: dict[str, Any] = response["spData"]
    if not isinstance(sp_data.get("intervals"), list):
        log.warning("Missing intervals in spending response")
        return []
    raw_intervals: list[Any] = sp_data["intervals"]

    intervals: list[dict[str, Any]] = [i for i in raw_intervals if isinstance(i, dict)]
    rows: list[dict[str, Any]] = []
    skipped = len(raw_intervals) - len(intervals)

    for interval in intervals:
        try:
            details: list[dict[str, Any]] = []
            if isinstance(interval.get("details"), list):
                raw_details: list[Any] = interval["details"]
                detail_dicts: list[dict[str, Any]] = [d for d in raw_details if isinstance(d, dict)]
                for d in detail_dicts:
                    details.append(
                        {
                            "date": validate_date(d["date"], "spending_detail"),
                            "amount": safe_decimal(d.get("amount", 0), "spending_detail.amount"),
                        }
                    )

            rows.append(
                {
                    "type": interval.get("type", ""),
                    "average": interval.get("average"),
                    "current": interval.get("current", 0),
                    "target": interval.get("target", 0),
                    "details": details,
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed spending interval: %s", exc)

    if skipped:
        log.warning(
            "Skipped %d malformed spending intervals out of %d", skipped, len(raw_intervals)
        )
    log.info("Parsed %d spending intervals", len(rows))
    return rows
