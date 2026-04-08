"""Parse getQuotes response into portfolio vs benchmark comparison dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import (
    is_non_finite,
    safe_decimal,
    safe_decimal_or_none,
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


def parse_portfolio_vs_benchmark(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse getQuotes -> histories into portfolio vs benchmark dicts.

    Extracts the "YOU" (portfolio) and "^INX" (S&P 500) series.

    Args:
        response: Raw API response from getQuotes.

    Returns:
        List of dicts with keys: date, portfolio_value, sp500_value.
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
                    "portfolio_value": safe_decimal_or_none(you_value, "portfolio_value"),
                    "sp500_value": safe_decimal_or_none(inx_value, "sp500_value"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed quote entry: %s", exc)

    if skipped:
        log.warning("Skipped %d malformed quote entries out of %d", skipped, len(histories))
    log.info("Parsed %d portfolio vs benchmark daily entries", len(rows))
    return rows


def parse_portfolio_snapshot(response: dict[str, Any]) -> dict[str, Any]:
    """Extract latest portfolio snapshot from spData.latestPortfolio.

    Returns:
        Dict with keys: last, change, percent_change.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("Missing spData in quotes response")
        return {}
    sp_data: dict[str, Any] = response["spData"]
    if not isinstance(sp_data.get("latestPortfolio"), dict):
        log.warning("Missing latestPortfolio in quotes response")
        return {}
    lp: dict[str, Any] = sp_data["latestPortfolio"]
    return {
        "last": lp.get("last", 0),
        "change": lp.get("change", 0),
        "percent_change": lp.get("percentChange", 0),
    }


def parse_market_quotes(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract market quotes from spData.latestQuotes.

    Skips fields with NaN values (bid, ask, volume).

    Returns:
        List of dicts with keys: ticker, last, change, percent_change, long_name, date.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("Missing spData in quotes response")
        return []
    sp_data: dict[str, Any] = response["spData"]
    if not isinstance(sp_data.get("latestQuotes"), list):
        log.warning("latestQuotes is not a list")
        return []
    raw_quotes: list[Any] = sp_data["latestQuotes"]

    quotes: list[dict[str, Any]] = [q for q in raw_quotes if isinstance(q, dict)]
    rows: list[dict[str, Any]] = []
    skipped = len(raw_quotes) - len(quotes)
    for q in quotes:
        try:
            last_val = q.get("last")
            if last_val is None or is_non_finite(last_val):
                skipped += 1
                continue
            rows.append(
                {
                    "ticker": q["ticker"],
                    "last": safe_decimal(last_val, "last"),
                    "change": safe_decimal(q.get("change", 0), "change"),
                    "percent_change": safe_decimal(q.get("percentChange", 0), "percentChange"),
                    "long_name": q.get("longName", ""),
                    "date": validate_date(q["date"], "market_quote"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed market quote: %s", exc)

    if skipped:
        log.warning("Skipped %d malformed/invalid quotes out of %d", skipped, len(raw_quotes))
    log.info("Parsed %d market quotes", len(rows))
    return rows
