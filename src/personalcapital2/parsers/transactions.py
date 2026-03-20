"""Parse getUserTransactions response into structured transaction and category dicts."""

from __future__ import annotations

import logging
from typing import Any

from personalcapital2._validation import safe_decimal, validate_and_extract, validate_date

log = logging.getLogger(__name__)

_KNOWN_KEYS = frozenset(
    {
        "userTransactionId",
        "userAccountId",
        "transactionDate",
        "amount",
        "isCashIn",
        "isCashOut",
        "isIncome",
        "isSpending",
        "description",
        "originalDescription",
        "simpleDescription",
        "categoryId",
        "categoryName",
        "categoryType",
        "merchant",
        "transactionType",
        "status",
        "currency",
        "isDuplicate",
        "isEdited",
        "isInterest",
        "isCredit",
        "isDebit",
        "runningBalance",
        "accountRef",
        "originalCategoryId",
        "transactionTypeId",
        "price",
        "quantity",
        "memo",
        "catKeyword",
    }
)


def _extract_raw_transactions(
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate response and extract raw transaction dicts. Shared by both parsers."""
    raw_txns, _sp_data_keys = validate_and_extract(
        response, ["spData", "transactions"], _KNOWN_KEYS, "getUserTransactions"
    )
    return raw_txns


def extract_categories(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract unique categories from transactions response.

    Returns:
        List of dicts with keys: category_id, name, type.
    """
    raw_txns = _extract_raw_transactions(response)

    seen: dict[int, dict[str, Any]] = {}
    for txn in raw_txns:
        cat_id = txn.get("categoryId")
        if cat_id is None:
            continue
        if cat_id in seen:
            # Log conflicts where the same category ID has different names
            existing_name = seen[cat_id]["name"]
            new_name = txn.get("categoryName", "")
            if new_name and new_name != existing_name:
                log.debug(
                    "Category %d: name conflict '%s' vs '%s' — keeping first",
                    cat_id,
                    existing_name,
                    new_name,
                )
            continue
        seen[cat_id] = {
            "category_id": cat_id,
            "name": txn.get("categoryName", ""),
            "type": txn.get("categoryType", ""),
        }

    categories = list(seen.values())
    log.info("Extracted %d unique categories", len(categories))
    return categories


def parse_transactions(response: dict[str, Any], synced_at: str = "") -> list[dict[str, Any]]:
    """Parse getUserTransactions response into transaction row dicts.

    All values are passed through from the API without modification.

    Note: the Empower API has a known issue where ``is_spending`` can be
    ``True`` on refunds and reimbursements (e.g. a refund may have
    ``is_spending=True, is_cash_in=True, transaction_type='Refund'``).
    Consumers should check ``transaction_type`` to distinguish refunds
    from actual spending rather than relying on ``is_spending`` alone.

    Args:
        response: Raw API response from getUserTransactions.
        synced_at: Deprecated, unused. Kept for backward compatibility.

    Returns:
        List of transaction dicts with normalized keys.
    """
    raw_txns = _extract_raw_transactions(response)
    rows: list[dict[str, Any]] = []
    skipped = 0

    for txn in raw_txns:
        try:
            # Pass through the raw amount from the API — almost always positive,
            # but some transfers use negative values. Direction is indicated by
            # isCashIn/isCashOut booleans (though these can be unreliable, e.g.
            # refunds sometimes have isSpending=True). Don't normalize here.
            amount = safe_decimal(txn["amount"], "transaction.amount")

            rows.append(
                {
                    "user_transaction_id": txn["userTransactionId"],
                    "user_account_id": txn["userAccountId"],
                    "date": validate_date(txn["transactionDate"], "transaction"),
                    "amount": amount,
                    "is_cash_in": txn.get("isCashIn", False),
                    "is_income": txn.get("isIncome", False),
                    "is_spending": txn.get("isSpending", False),
                    "description": txn.get("description", ""),
                    "original_description": txn.get("originalDescription"),
                    "simple_description": txn.get("simpleDescription"),
                    "category_id": txn.get("categoryId"),
                    "merchant": txn.get("merchant"),
                    "transaction_type": txn.get("transactionType"),
                    "status": txn.get("status"),
                    "currency": txn.get("currency", "USD"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            log.warning("Skipping malformed transaction: %s", exc)

    if skipped:
        log.warning("Skipped %d malformed transactions out of %d", skipped, len(raw_txns))
    log.info("Parsed %d transactions", len(rows))
    return rows
