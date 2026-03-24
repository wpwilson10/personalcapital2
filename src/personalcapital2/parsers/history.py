"""Parse getHistories response into net worth and account balance dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import (
    is_account_id,
    safe_decimal,
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


def parse_net_worth(response: dict[str, Any], synced_at: str = "") -> list[dict[str, Any]]:
    """Parse getHistories -> networthHistories into daily net worth dicts.

    Filters out zero-value rows where all financial fields are 0 — these are
    padding Empower inserts before any accounts were linked.

    Args:
        response: Raw API response from getHistories.
        synced_at: Deprecated, unused. Kept for backward compatibility.

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
            networth = safe_decimal(entry.get("networth", 0.0), "networth")
            total_assets = safe_decimal(entry.get("totalAssets", 0.0), "totalAssets")
            total_liabilities = safe_decimal(entry.get("totalLiabilities", 0.0), "totalLiabilities")

            # Skip zero-padding rows (pre-account-linking)
            if not networth and not total_assets and not total_liabilities:
                skipped_zeros += 1
                continue

            rows.append(
                {
                    "date": validate_date(entry["date"], "net_worth"),
                    "networth": networth,
                    "total_assets": total_assets,
                    "total_liabilities": total_liabilities,
                    "total_cash": safe_decimal(entry.get("totalCash", 0.0), "totalCash"),
                    "total_investment": safe_decimal(
                        entry.get("totalInvestment", 0.0), "totalInvestment"
                    ),
                    "total_credit": safe_decimal(entry.get("totalCredit", 0.0), "totalCredit"),
                    "total_mortgage": safe_decimal(
                        entry.get("totalMortgage", 0.0), "totalMortgage"
                    ),
                    "total_loan": safe_decimal(entry.get("totalLoan", 0.0), "totalLoan"),
                    "total_other_assets": safe_decimal(
                        entry.get("totalOtherAssets", 0.0), "totalOtherAssets"
                    ),
                    "total_other_liabilities": safe_decimal(
                        entry.get("totalOtherLiabilities", 0.0), "totalOtherLiabilities"
                    ),
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


def parse_account_balances(response: dict[str, Any], synced_at: str = "") -> list[dict[str, Any]]:
    """Parse getHistories -> histories into daily account balance dicts.

    Filters out:
    - Annotation keys (non-numeric) from the balances dict
    - Leading zero-balance rows per account (pre-linking padding)

    Args:
        response: Raw API response from getHistories.
        synced_at: Deprecated, unused. Kept for backward compatibility.

    Returns:
        List of balance dicts with keys: date, user_account_id, balance.
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
                    "balance": safe_decimal(value, f"balance[{key}]"),
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
            if row["balance"]:
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


def parse_net_worth_summary(response: dict[str, Any]) -> dict[str, Any]:
    """Extract net worth change summary from spData.networthSummary.

    Returns:
        Dict with normalized keys for NetWorthSummary.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("Missing spData in history response")
        return {}
    sp_data: dict[str, Any] = response["spData"]
    if not isinstance(sp_data.get("networthSummary"), dict):
        log.warning("Missing networthSummary in history response")
        return {}
    nw_summary: dict[str, Any] = sp_data["networthSummary"]
    return {
        "date_range_change": nw_summary.get("dateRangeChange", 0),
        "date_range_percentage_change": nw_summary.get("dateRangePercentageChange", 0),
        "cash_change": nw_summary.get("dateRangeCashChange", 0),
        "cash_percentage_change": nw_summary.get("dateRangeCashPercentageChange", 0),
        "investment_change": nw_summary.get("dateRangeInvestmentChange", 0),
        "investment_percentage_change": nw_summary.get("dateRangeInvestmentPercentageChange", 0),
        "credit_change": nw_summary.get("dateRangeCreditChange", 0),
        "credit_percentage_change": nw_summary.get("dateRangeCreditPercentageChange", 0),
        "mortgage_change": nw_summary.get("dateRangeMortgageChange", 0),
        "mortgage_percentage_change": nw_summary.get("dateRangeMortgagePercentageChange", 0),
        "loan_change": nw_summary.get("dateRangeLoanChange", 0),
        "loan_percentage_change": nw_summary.get("dateRangeLoanPercentageChange", 0),
        "other_assets_change": nw_summary.get("dateRangeOtherAssetsChange", 0),
        "other_assets_percentage_change": nw_summary.get("dateRangeOtherAssetsPercentageChange", 0),
        "other_liabilities_change": nw_summary.get("dateRangeOtherLiabilitiesChange", 0),
        "other_liabilities_percentage_change": nw_summary.get(
            "dateRangeOtherLiabilitiesPercentageChange", 0
        ),
    }
