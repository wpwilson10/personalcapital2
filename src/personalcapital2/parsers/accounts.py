"""Parse getAccounts2 response into structured account dicts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from personalcapital2._validation import safe_decimal_or_none, validate_and_extract

log = logging.getLogger(__name__)

_KNOWN_KEYS = frozenset(
    {
        "userAccountId",
        "accountId",
        "name",
        "firmName",
        "accountType",
        "accountTypeNew",
        "accountTypeGroup",
        "productType",
        "currency",
        "isAsset",
        "createdDate",
        "closedDate",
        "isOnUs",
        "isOnUsBank",
        "isAccountNumberValidated",
        "isAccountUsedInFunding",
        "isTaxDeferredOrNonTaxable",
        "isEsog",
        "isPlaidAccount",
        "nextAction",
        "loginFields",
        "isHome",
        "isIAVEligible",
        "isTransferEligibleForFunding",
        "isExcludeFromHousehold",
        "isManual",
        "isPaymentFromCapable",
        "balance",
        "availableCash",
        "accountTypeSubtype",
        "lastRefreshed",
        "oldestTransactionDate",
        "advisoryFeePercentage",
        "feesPerYear",
        "fundFees",
        "totalFee",
        "siteId",
        "originalFirmName",
        "originalAccountName",
        "aggregatingInstitutionId",
    }
)


def _epoch_ms_to_iso(epoch_ms: int | float) -> str:
    """Convert epoch milliseconds to ISO-8601 date string."""
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def parse_accounts(response: dict[str, Any], synced_at: str = "") -> list[dict[str, Any]]:
    """Parse getAccounts2 response into account row dicts.

    Args:
        response: Raw API response from getAccounts2.
        synced_at: Deprecated, unused. Kept for backward compatibility.

    Returns:
        List of account dicts with normalized keys.
    """
    raw_accounts, _sp_data_keys = validate_and_extract(
        response, ["spData", "accounts"], _KNOWN_KEYS, "getAccounts2"
    )
    rows: list[dict[str, Any]] = []
    skipped = 0

    for acct in raw_accounts:
        try:
            created_date = acct.get("createdDate")
            created_at: str | None = None
            if isinstance(created_date, int | float) and created_date > 0:
                created_at = _epoch_ms_to_iso(created_date)

            closed_date = acct.get("closedDate", "")
            is_closed = bool(closed_date)

            last_refreshed_raw = acct.get("lastRefreshed")
            last_refreshed: str | None = None
            if isinstance(last_refreshed_raw, int | float) and last_refreshed_raw > 0:
                last_refreshed = _epoch_ms_to_iso(last_refreshed_raw)

            oldest_txn_date = acct.get("oldestTransactionDate") or None

            # availableCash comes as a string from the API (e.g. "0.00")
            available_cash_raw = acct.get("availableCash")
            available_cash = (
                safe_decimal_or_none(available_cash_raw, "availableCash")
                if available_cash_raw
                else None
            )

            acct_type_subtype = acct.get("accountTypeSubtype") or None

            rows.append(
                {
                    "user_account_id": acct["userAccountId"],
                    "account_id": acct.get("accountId", ""),
                    "name": acct.get("name", ""),
                    "firm_name": acct.get("firmName", ""),
                    "account_type": acct.get("accountTypeNew", acct.get("accountType", "")),
                    "account_type_group": acct.get("accountTypeGroup"),
                    "product_type": acct.get("productType", ""),
                    "currency": acct.get("currency", "USD"),
                    "is_asset": acct.get("isAsset", False),
                    "is_closed": is_closed,
                    "created_at": created_at,
                    "balance": safe_decimal_or_none(acct.get("balance"), "balance"),
                    "available_cash": available_cash,
                    "account_type_subtype": acct_type_subtype,
                    "last_refreshed": last_refreshed,
                    "oldest_transaction_date": oldest_txn_date,
                    "advisory_fee_percentage": safe_decimal_or_none(
                        acct.get("advisoryFeePercentage"), "advisoryFeePercentage"
                    ),
                    "fees_per_year": safe_decimal_or_none(acct.get("feesPerYear"), "feesPerYear"),
                    "fund_fees": safe_decimal_or_none(acct.get("fundFees"), "fundFees"),
                    "total_fee": safe_decimal_or_none(acct.get("totalFee"), "totalFee"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed account: %s", exc)

    if skipped:
        log.warning("Skipped %d malformed accounts out of %d", skipped, len(raw_accounts))
    log.info("Parsed %d accounts", len(rows))
    return rows


def parse_accounts_summary(response: dict[str, Any]) -> dict[str, Any]:
    """Extract account summary totals from spData top-level fields.

    Returns:
        Dict with normalized keys for AccountsSummary.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("Missing spData in accounts response")
        return {}
    sp_data: dict[str, Any] = response["spData"]
    return {
        "networth": sp_data.get("networth", 0),
        "assets": sp_data.get("assets", 0),
        "liabilities": sp_data.get("liabilities", 0),
        "cash_total": sp_data.get("cashAccountsTotal", 0),
        "investment_total": sp_data.get("investmentAccountsTotal", 0),
        "credit_card_total": sp_data.get("creditCardAccountsTotal", 0),
        "mortgage_total": sp_data.get("mortgageAccountsTotal", 0),
        "loan_total": sp_data.get("loanAccountsTotal", 0),
        "other_asset_total": sp_data.get("otherAssetAccountsTotal", 0),
        "other_liabilities_total": sp_data.get("otherLiabilitiesAccountsTotal", 0),
    }
