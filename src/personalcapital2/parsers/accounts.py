"""Parse getAccounts2 response into structured account dicts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from personalcapital2._validation import validate_and_extract

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
        "lastRefreshed",
        "siteId",
        "originalFirmName",
        "originalAccountName",
        "aggregatingInstitutionId",
    }
)


def _epoch_ms_to_iso(epoch_ms: int | float) -> str:
    """Convert epoch milliseconds to ISO-8601 date string."""
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def parse_accounts(response: dict[str, Any], synced_at: str) -> list[dict[str, Any]]:
    """Parse getAccounts2 response into account row dicts.

    Args:
        response: Raw API response from getAccounts2.
        synced_at: ISO-8601 timestamp of this sync run.

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
                    "updated_at": synced_at,
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed account: %s", exc)

    if skipped:
        log.warning("Skipped %d malformed accounts out of %d", skipped, len(raw_accounts))
    log.info("Parsed %d accounts", len(rows))
    return rows
