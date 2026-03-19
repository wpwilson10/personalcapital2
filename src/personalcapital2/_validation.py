"""Shared API response validation for Empower parsers.

Validates response structure and detects API changes by comparing
actual response keys against a known set. Unknown keys are logged
at DEBUG level to surface new API fields without noise.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime as _dt
from typing import Any

log = logging.getLogger(__name__)


def validate_and_extract(
    response: dict[str, Any],
    key_path: list[str],
    known_keys: frozenset[str],
    endpoint_name: str,
) -> tuple[list[dict[str, Any]], frozenset[str]]:
    """Traverse a response dict, validate structure, and detect unknown keys.

    Args:
        response: Raw API response dict.
        key_path: Sequence of keys to traverse (e.g. ["spData", "transactions"]).
        known_keys: Expected keys on each item in the extracted list.
        endpoint_name: Human-readable endpoint name for log messages.

    Returns:
        Tuple of (extracted list of dicts, set of top-level spData keys).
        Returns ([], frozenset()) if the response structure is invalid.
    """
    if not isinstance(response.get("spData"), dict):
        log.warning("%s: missing or invalid spData in response", endpoint_name)
        return [], frozenset()

    # Re-bind after guard: response["spData"] returns Any (not narrowed to dict[Unknown])
    sp_data: dict[str, Any] = response["spData"]
    sp_data_keys: frozenset[str] = frozenset(str(k) for k in sp_data)

    # Traverse key_path starting from spData
    current: dict[str, Any] | list[Any] | None = sp_data
    path_to_traverse = key_path[1:] if key_path and key_path[0] == "spData" else key_path
    for i, key in enumerate(path_to_traverse):
        if not isinstance(current, dict):
            log.warning(
                "%s: expected dict at path %s, got %s",
                endpoint_name,
                key_path[: i + 1],
                type(current).__name__,
            )
            return [], sp_data_keys

        current = current.get(key)
        if current is None:
            log.warning("%s: missing key '%s' in response path", endpoint_name, key)
            return [], sp_data_keys

    if not isinstance(current, list):
        log.warning(
            "%s: expected list at path %s, got %s",
            endpoint_name,
            key_path,
            type(current).__name__,
        )
        return [], sp_data_keys

    # Verify items are actually dicts (API could return list of scalars)
    if current and not isinstance(current[0], dict):
        log.warning(
            "%s: expected list of dicts at path %s, got list of %s",
            endpoint_name,
            key_path,
            type(current[0]).__name__,
        )
        return [], sp_data_keys

    result: list[dict[str, Any]] = current

    # Check for unknown keys in the first item (representative sample)
    if result:
        first_item = result[0]
        sample_keys = frozenset(str(k) for k in first_item)
        unknown = sample_keys - known_keys
        if unknown:
            log.debug(
                "%s: unknown keys in response items: %s",
                endpoint_name,
                sorted(unknown),
            )

    return result, sp_data_keys


_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(date_str: object, context: str) -> str:
    """Validate that a date string matches YYYY-MM-DD format and is a real calendar date.

    Raises ValueError if the format is invalid or the date doesn't exist.
    """
    if not isinstance(date_str, str) or not _DATE_PATTERN.match(date_str):
        msg = f"{context}: invalid date format: {date_str!r} (expected YYYY-MM-DD)"
        raise ValueError(msg)
    # Validate actual calendar date (regex allows impossible dates like Feb 30)
    try:
        _dt.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        msg = f"{context}: invalid calendar date: {date_str!r}"
        raise ValueError(msg) from None
    return date_str


def safe_float(value: object, context: str) -> float:
    """Convert a value to float, rejecting NaN and Infinity.

    Raises ValueError if the value cannot be converted or is non-finite.
    """
    if not isinstance(value, int | float | str):
        msg = f"{context}: cannot convert {type(value).__name__} to float"
        raise ValueError(msg)
    result = float(value)
    if not math.isfinite(result):
        msg = f"{context}: non-finite value: {result}"
        raise ValueError(msg)
    return result


def safe_float_or_none(value: object, context: str) -> float | None:
    """Convert a value to float or None, rejecting NaN and Infinity."""
    if value is None:
        return None
    return safe_float(value, context)
