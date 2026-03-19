"""Parse getHoldings response into structured holding snapshot dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import (
    safe_float,
    safe_float_or_none,
    validate_and_extract,
)

log = logging.getLogger(__name__)

_KNOWN_KEYS = frozenset(
    {
        "userAccountId",
        "ticker",
        "cusip",
        "description",
        "quantity",
        "price",
        "value",
        "holdingType",
        "holdingPercentage",
        "source",
        "costBasis",
        "unrealizedGainLoss",
        "unrealizedGainLossPercent",
        "securityType",
        "securityStyle",
        "securityClassification",
        "marketCap",
        "bondMaturityDate",
        "bondDuration",
        "bondCouponRate",
        "externalSystemId",
        "accountName",
        "firmName",
        "fundFees",
        "isCash",
        "isShort",
    }
)


def parse_holdings(response: dict[str, Any], snapshot_date: str) -> list[dict[str, Any]]:
    """Parse getHoldings response into holding snapshot dicts.

    Args:
        response: Raw API response from getHoldings.
        snapshot_date: ISO-8601 date for this snapshot (typically today).

    Returns:
        List of holding dicts with normalized keys.
    """
    raw_holdings, _sp_data_keys = validate_and_extract(
        response, ["spData", "holdings"], _KNOWN_KEYS, "getHoldings"
    )
    rows: list[dict[str, Any]] = []
    skipped = 0

    for h in raw_holdings:
        try:
            ticker = h.get("ticker") or None  # normalize empty string to None
            cusip = h.get("cusip") or None
            description = h.get("description", "")

            # Validate that at least one identifier exists for the holding key
            holding_key = cusip or ticker or description
            if not holding_key:
                log.warning(
                    "Skipping holding with no identifier (cusip/ticker/description all empty) "
                    "in account %s",
                    h.get("userAccountId"),
                )
                skipped += 1
                continue

            user_account_id = h.get("userAccountId")
            if user_account_id is None:
                log.warning("Skipping holding with no userAccountId: %s", holding_key)
                skipped += 1
                continue

            # Require quantity/price/value keys to exist; null/0 is valid
            missing_keys = [k for k in ("quantity", "price", "value") if k not in h]
            if missing_keys:
                log.warning(
                    "Skipping holding %s: missing key(s) %s",
                    holding_key,
                    missing_keys,
                )
                skipped += 1
                continue

            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "user_account_id": user_account_id,
                    "ticker": ticker,
                    "cusip": cusip,
                    "description": description,
                    "quantity": safe_float(h.get("quantity", 0.0), "quantity"),
                    "price": safe_float(h.get("price", 0.0), "price"),
                    "value": safe_float(h.get("value", 0.0), "value"),
                    "holding_type": h.get("holdingType"),
                    "security_type": h.get("securityType"),
                    "holding_percentage": safe_float_or_none(
                        h.get("holdingPercentage"), "holdingPercentage"
                    ),
                    "source": h.get("source"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed holding: %s", exc)

    # Deduplicate by the composite key that the DB enforces
    # (snapshot_date, user_account_id, holding_key) where
    # holding_key = COALESCE(cusip, ticker, description).
    # If duplicates exist, keep the one with the highest value.
    seen: dict[tuple[str, int | None, str], int] = {}
    deduplicated: list[dict[str, Any]] = []
    for row in rows:
        holding_key = row["cusip"] or row["ticker"] or row["description"]
        composite = (row["snapshot_date"], row["user_account_id"], holding_key)
        if composite in seen:
            existing_idx = seen[composite]
            existing_val = deduplicated[existing_idx]["value"]
            if row["value"] > existing_val:
                log.warning(
                    "Duplicate holding key %s in account %s "
                    "— keeping higher value ($%.2f over $%.2f)",
                    holding_key,
                    row["user_account_id"],
                    row["value"],
                    existing_val,
                )
                deduplicated[existing_idx] = row
            else:
                log.warning(
                    "Duplicate holding key %s in account %s "
                    "— skipping lower value ($%.2f, keeping $%.2f)",
                    holding_key,
                    row["user_account_id"],
                    row["value"],
                    existing_val,
                )
        else:
            seen[composite] = len(deduplicated)
            deduplicated.append(row)

    if len(deduplicated) < len(rows):
        log.warning("Deduplicated %d holdings down to %d", len(rows), len(deduplicated))

    if skipped:
        log.warning("Skipped %d malformed/invalid holdings out of %d", skipped, len(raw_holdings))
    log.info("Parsed %d holdings for %s", len(deduplicated), snapshot_date)
    return deduplicated
