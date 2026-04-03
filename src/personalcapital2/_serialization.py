"""Shared JSON serialization for Decimal and date types.

Used by both the CLI and MCP server to produce consistent JSON output.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from decimal import Decimal


def json_default(obj: object) -> int | float | str:
    """JSON serializer for Decimal and date objects.

    Decimals that are exact integers serialize as int (e.g. 150000 not 150000.0).
    All other Decimals serialize as float, which is lossless for values within
    float64 range - sufficient for financial data (IEEE 754 has 15-17 significant
    digits, far exceeding any dollar amount or percentage the API returns).

    Dates serialize as ISO-8601 strings.

    Raises TypeError for any other type to avoid silently masking bugs.
    """
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def serialize_result(result: object) -> str:
    """Serialize a dataclass instance (or list of them) to a JSON string.

    Handles nested dataclasses, Decimal, date, and tuple fields.
    """
    data = dataclasses.asdict(result)  # pyright: ignore[reportArgumentType] — result is a dataclass instance
    return json.dumps(data, default=json_default, indent=2)
