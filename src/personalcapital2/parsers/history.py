"""Parse getHistories response into net worth and account balance dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import (
    is_account_id,
    safe_float,
    validate_and_extract,
    validate_date,
)

log = logging.getLogger(__name__)

_KNOWN_NW_KEYS = frozenset(
    {
        "date",
        "networth",
        "totalAssets",
        "totalLiabilities",
        "totalCash",
        "totalInvestment",
        "totalCredit",
        "totalMortgage",
        "totalLoan",
        "totalOtherAssets",
        "totalOtherLiabilities",
        "cashChange",
        "investmentChange",
        "creditChange",
        "loanChange",
        "mortgageChange",
        "otherAssetsChange",
        "otherLiabilitiesChange",
    }
)

_KNOWN_BAL_KEYS = frozenset(
    {
        "date",
        "balances",
    }
)


def parse_net_worth(response: dict[str, Any], synced_at: str) -> list[dict[str, Any]]:
    """Parse getHistories -> networthHistories into daily net worth dicts.

    Filters out zero-value rows where all financial fields are 0 — these are
    padding Empower inserts before any accounts were linked.

    Args:
        response: Raw API response from getHistories.
        synced_at: ISO-8601 timestamp of this sync run.

    Returns:
        List of net worth dicts with normalized keys.
    """
    nw_histories, _sp_data_keys = validate_and_extract(
        response,
        ["spData", "networthHistories"],
        _KNOWN_NW_KEYS,
        "getHistories/networth",
    )
    rows: list[dict[str, Any]] = []
    skipped_zeros = 0
    skipped_errors = 0

    for entry in nw_histories:
        try:
            networth = safe_float(entry.get("networth", 0.0), "networth")
            total_assets = safe_float(entry.get("totalAssets", 0.0), "totalAssets")
            total_liabilities = safe_float(entry.get("totalLiabilities", 0.0), "totalLiabilities")

            # Skip zero-padding rows (pre-account-linking)
            if networth == 0.0 and total_assets == 0.0 and total_liabilities == 0.0:
                skipped_zeros += 1
                continue

            rows.append(
                {
                    "date": validate_date(entry["date"], "net_worth"),
                    "networth": networth,
                    "total_assets": total_assets,
                    "total_liabilities": total_liabilities,
                    "total_cash": safe_float(entry.get("totalCash", 0.0), "totalCash"),
                    "total_investment": safe_float(
                        entry.get("totalInvestment", 0.0), "totalInvestment"
                    ),
                    "total_credit": safe_float(entry.get("totalCredit", 0.0), "totalCredit"),
                    "total_mortgage": safe_float(entry.get("totalMortgage", 0.0), "totalMortgage"),
                    "total_loan": safe_float(entry.get("totalLoan", 0.0), "totalLoan"),
                    "total_other_assets": safe_float(
                        entry.get("totalOtherAssets", 0.0), "totalOtherAssets"
                    ),
                    "total_other_liabilities": safe_float(
                        entry.get("totalOtherLiabilities", 0.0), "totalOtherLiabilities"
                    ),
                    "synced_at": synced_at,
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped_errors += 1
            log.warning("Skipping malformed net worth entry: %s", exc)

    if skipped_zeros:
        log.info("Filtered out %d zero-value net worth rows", skipped_zeros)
    if skipped_errors:
        log.warning(
            "Skipped %d malformed net worth entries out of %d",
            skipped_errors,
            len(nw_histories),
        )
    log.info("Parsed %d net worth daily entries", len(rows))
    return rows


def parse_account_balances(response: dict[str, Any], synced_at: str) -> list[dict[str, Any]]:
    """Parse getHistories -> histories into daily account balance dicts.

    Filters out:
    - Annotation keys (non-numeric) from the balances dict
    - Leading zero-balance rows per account (pre-linking padding)

    Args:
        response: Raw API response from getHistories.
        synced_at: ISO-8601 timestamp of this sync run.

    Returns:
        List of balance dicts with keys: date, user_account_id, balance, synced_at.
    """
    histories, _sp_data_keys = validate_and_extract(
        response,
        ["spData", "histories"],
        _KNOWN_BAL_KEYS,
        "getHistories/balances",
    )

    # First pass: collect all rows grouped by account to detect leading zeros
    account_rows: dict[int, list[dict[str, Any]]] = {}
    skipped_errors = 0
    for entry in histories:
        try:
            date = validate_date(entry["date"], "account_balance")
            balances: dict[str, Any] = entry.get("balances", {})

            for key, value in balances.items():
                if not is_account_id(key):
                    continue
                account_id = int(key)
                row = {
                    "date": date,
                    "user_account_id": account_id,
                    "balance": safe_float(value, f"balance[{key}]"),
                    "synced_at": synced_at,
                }
                if account_id not in account_rows:
                    account_rows[account_id] = []
                account_rows[account_id].append(row)
        except (KeyError, ValueError, TypeError) as exc:
            skipped_errors += 1
            log.warning("Skipping malformed balance entry: %s", exc)

    if skipped_errors:
        log.warning(
            "Skipped %d malformed balance entries out of %d",
            skipped_errors,
            len(histories),
        )

    # Second pass: filter leading zeros per account
    rows: list[dict[str, Any]] = []
    total_skipped = 0
    for _account_id, acct_rows in account_rows.items():
        # Sort by date to find where real data starts
        acct_rows.sort(key=lambda r: r["date"])
        first_nonzero_idx = 0
        for i, row in enumerate(acct_rows):
            if row["balance"] != 0.0:
                first_nonzero_idx = i
                break
        else:
            # All zeros — still include them (account might legitimately be empty)
            rows.extend(acct_rows)
            continue

        skipped = first_nonzero_idx
        total_skipped += skipped
        rows.extend(acct_rows[first_nonzero_idx:])

    if total_skipped:
        log.info("Filtered out %d leading zero-balance rows", total_skipped)
    log.info("Parsed %d account balance daily entries", len(rows))
    return rows
