"""Tests for the API response validation utility."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from personalcapital2._validation import validate_and_extract

if TYPE_CHECKING:
    import pytest

_KNOWN_KEYS = frozenset({"id", "name", "value"})


def _make_response(
    items: list[dict[str, Any]],
    list_key: str = "items",
    extra_sp_keys: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sp_data: dict[str, Any] = {list_key: items}
    if extra_sp_keys:
        sp_data.update(extra_sp_keys)
    return {"spData": sp_data}


def test_valid_response_extracts_items() -> None:
    items: list[dict[str, Any]] = [{"id": 1, "name": "Test", "value": 42}]
    response = _make_response(items)
    result, sp_keys = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")
    assert result == items
    assert "items" in sp_keys


def test_returns_sp_data_keys() -> None:
    response = _make_response([], extra_sp_keys={"metadata": {"count": 0}})
    _, sp_keys = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")
    assert sp_keys == frozenset({"items", "metadata"})


def test_missing_sp_data_returns_empty() -> None:
    result, sp_keys = validate_and_extract({}, ["spData", "items"], _KNOWN_KEYS, "test")
    assert result == []
    assert sp_keys == frozenset()


def test_missing_key_in_path_returns_empty() -> None:
    response: dict[str, Any] = {"spData": {"other": []}}
    result, sp_keys = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")
    assert result == []
    assert "other" in sp_keys  # spData keys are still returned


def test_non_list_at_path_returns_empty() -> None:
    response: dict[str, Any] = {"spData": {"items": "not a list"}}
    result, sp_keys = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")
    assert result == []
    assert "items" in sp_keys


def test_unknown_keys_logged_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    items: list[dict[str, Any]] = [{"id": 1, "name": "Test", "value": 42, "newField": "surprise"}]
    response = _make_response(items)

    with caplog.at_level(logging.DEBUG, logger="personalcapital2._validation"):
        result, _ = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")

    assert len(result) == 1
    assert any("newField" in record.message for record in caplog.records)


def test_known_keys_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    items: list[dict[str, Any]] = [{"id": 1, "name": "Test", "value": 42}]
    response = _make_response(items)

    with caplog.at_level(logging.DEBUG, logger="personalcapital2._validation"):
        validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert not debug_records


def test_empty_list_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    response = _make_response([])

    with caplog.at_level(logging.DEBUG, logger="personalcapital2._validation"):
        result, _ = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")

    assert result == []
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert not debug_records


def test_validate_date_rejects_impossible_calendar_dates() -> None:
    """Dates that match YYYY-MM-DD format but don't exist should be rejected."""
    import pytest

    from personalcapital2._validation import validate_date

    with pytest.raises(ValueError, match="invalid calendar date"):
        validate_date("2026-02-30", "test")

    with pytest.raises(ValueError, match="invalid calendar date"):
        validate_date("2026-13-01", "test")


def test_validate_and_extract_returns_empty_when_items_not_dicts() -> None:
    """If the list at the key path contains non-dicts (e.g. strings), return empty."""
    response: dict[str, Any] = {"spData": {"items": ["a", "b", "c"]}}
    result, sp_keys = validate_and_extract(response, ["spData", "items"], _KNOWN_KEYS, "test")
    assert result == []
    assert "items" in sp_keys


def test_safe_float_converts_valid_numbers() -> None:
    from personalcapital2._validation import safe_float

    assert safe_float(42, "test") == 42.0
    assert safe_float(3.14, "test") == 3.14
    assert safe_float("99.5", "test") == 99.5
    assert safe_float(0, "test") == 0.0
    assert safe_float(-7.5, "test") == -7.5


def test_safe_float_rejects_nan_and_infinity() -> None:
    import math

    import pytest

    from personalcapital2._validation import safe_float

    with pytest.raises(ValueError, match="non-finite"):
        safe_float(float("nan"), "test")
    with pytest.raises(ValueError, match="non-finite"):
        safe_float(float("inf"), "test")
    with pytest.raises(ValueError, match="non-finite"):
        safe_float(float("-inf"), "test")
    with pytest.raises(ValueError, match="non-finite"):
        safe_float(math.nan, "test")


def test_safe_float_rejects_non_numeric_types() -> None:
    import pytest

    from personalcapital2._validation import safe_float

    with pytest.raises(ValueError, match="cannot convert list"):
        safe_float([1, 2, 3], "test")
    with pytest.raises(ValueError, match="cannot convert dict"):
        safe_float({"a": 1}, "test")


def test_safe_float_or_none_returns_none_for_none() -> None:
    from personalcapital2._validation import safe_float_or_none

    assert safe_float_or_none(None, "test") is None


def test_safe_float_or_none_converts_valid_numbers() -> None:
    from personalcapital2._validation import safe_float_or_none

    assert safe_float_or_none(42, "test") == 42.0
    assert safe_float_or_none(3.14, "test") == 3.14
    assert safe_float_or_none("99.5", "test") == 99.5


def test_parsers_use_validation() -> None:
    """Smoke test that all parsers still work after validation integration."""
    from personalcapital2.parsers.accounts import parse_accounts
    from personalcapital2.parsers.history import parse_account_balances, parse_net_worth
    from personalcapital2.parsers.holdings import parse_holdings
    from personalcapital2.parsers.performance import (
        parse_benchmark_performance,
        parse_investment_performance,
    )
    from personalcapital2.parsers.quotes import parse_portfolio_vs_benchmark
    from personalcapital2.parsers.transactions import extract_categories, parse_transactions

    synced_at = "2026-03-14T10:00:00"
    empty: dict[str, Any] = {}

    # All parsers should handle missing spData gracefully
    assert parse_accounts(empty, synced_at) == []
    assert parse_transactions(empty, synced_at) == []
    assert extract_categories(empty) == []
    assert parse_holdings(empty, "2026-03-14") == []
    assert parse_net_worth(empty, synced_at) == []
    assert parse_account_balances(empty, synced_at) == []
    assert parse_investment_performance(empty, synced_at) == []
    assert parse_benchmark_performance(empty, synced_at) == []
    assert parse_portfolio_vs_benchmark(empty, synced_at) == []
