"""Parse getQuotes response into portfolio vs benchmark comparison dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import (
    safe_float_or_none,
    validate_and_extract,
    validate_date,
)

log = logging.getLogger(__name__)

_KNOWN_KEYS = frozenset(
    {
        "date",
        "YOU",
        "^INX",
        "^DJI",
        "^IXIC",
    }
)


def parse_portfolio_vs_benchmark(response: dict[str, Any], synced_at: str) -> list[dict[str, Any]]:
    """Parse getQuotes -> histories into portfolio vs benchmark dicts.

    Extracts the "YOU" (portfolio) and "^INX" (S&P 500) series.

    Args:
        response: Raw API response from getQuotes.
        synced_at: ISO-8601 timestamp of this sync run.

    Returns:
        List of dicts with keys: date, portfolio_value, sp500_value, synced_at.
    """
    histories, _sp_data_keys = validate_and_extract(
        response, ["spData", "histories"], _KNOWN_KEYS, "getQuotes"
    )
    rows: list[dict[str, Any]] = []
    skipped = 0

    for entry in histories:
        try:
            you_value = entry.get("YOU")
            inx_value = entry.get("^INX")

            # Skip entries that have neither series
            if you_value is None and inx_value is None:
                continue

            rows.append(
                {
                    "date": validate_date(entry["date"], "portfolio_vs_benchmark"),
                    "portfolio_value": safe_float_or_none(you_value, "portfolio_value"),
                    "sp500_value": safe_float_or_none(inx_value, "sp500_value"),
                    "synced_at": synced_at,
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed quote entry: %s", exc)

    if skipped:
        log.warning("Skipped %d malformed quote entries out of %d", skipped, len(histories))
    log.info("Parsed %d portfolio vs benchmark daily entries", len(rows))
    return rows
