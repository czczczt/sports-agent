"""Base types and shared constants for rating calculators (SPEC v1.3 §9)."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, NamedTuple


class ScoreBreakdown(NamedTuple):
    points: float | None
    reason: str | None
    breakdown: dict[str, Any]


VALID_SPORTS = {"run", "ski", "biathlon", "triathlon", "trail"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def sanitize_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)) and math.isfinite(val):
        return float(val)
    return None
