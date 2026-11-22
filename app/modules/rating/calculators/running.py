"""Pure running rating calculator per SPEC v1.3 §9.1 and §9.7."""

from __future__ import annotations

from typing import Any

from app.modules.rating.calculators.base import (
    ScoreBreakdown,
    sanitize_float,
)

FORMULA_VERSION = "run-v1"

# Default customer norms for 2026 (seconds, except 24h which is achieved km)
DEFAULT_RUN_NORMS_2026: tuple[tuple[str, float, float], ...] = (
    ("60m", 6.84, 7.5),
    ("100m", 10.62, 11.75),
    ("200m", 21.65, 24.4),
    ("400m", 47.9, 54.8),
    ("800m", 111.0, 127.0),
    ("1000m", 142.0, 165.0),
    ("1500m", 228.0, 259.0),
    ("1mile", 243.0, 279.0),
    ("3000m", 486.0, 555.0),
    ("5000m", 846.0, 965.0),
    ("10000m", 1760.0, 2028.0),
    ("half_marathon", 3900.0, 4540.0),
    ("marathon", 8400.0, 9600.0),
    ("100km", 24960.0, 28800.0),
    ("24h", 245.0, 216.0),
)


def calculate_running_score(
    *,
    status: str | None,
    duplicate_of: int | None,
    gender: str | None,
    distance_class: str | None = None,
    event_date: str | None = None,
    chip_time_s: float | None = None,
    gun_time_s: float | None = None,
    distance_km: float | None = None,
    norm_value: float | None = None,
    norm_unit: str | None = None,
    norm_year: int | None = None,
    discipline: str | None = None,
    formula_version: str = FORMULA_VERSION,
) -> ScoreBreakdown:
    """Pure calculator: result parameters + norm -> ScoreBreakdown."""
    breakdown: dict[str, Any] = {
        "sport": "run",
        "class": distance_class,
        "discipline": discipline,
        "gender": gender,
        "norm_value": norm_value,
        "norm_unit": norm_unit,
        "norm_year": norm_year,
        "time_kind": None,
        "time_s": None,
        "formula": None,
        "points": None,
        "formula_version": formula_version,
    }

    def excluded(reason: str) -> ScoreBreakdown:
        breakdown["reason"] = reason
        return ScoreBreakdown(None, reason, breakdown)

    if duplicate_of is not None:
        return excluded("duplicate")
    if status != "FIN":
        return excluded("not_finisher")
    if gender not in ("M", "F"):
        return excluded("unknown_gender")
    if not event_date:
        return excluded("missing_date")
    if not distance_class:
        return excluded("unclassified_distance")
    if norm_value is None:
        return excluded("missing_norm")

    sanitized_norm = sanitize_float(norm_value)
    if sanitized_norm is None or sanitized_norm <= 0:
        return excluded("invalid_norm")

    if distance_class == "24h":
        sanitized_km = sanitize_float(distance_km)
        if sanitized_km is None:
            return excluded("missing_distance" if distance_km is None else "invalid_distance")
        if sanitized_km <= 0:
            return excluded("invalid_distance")
        pts = (sanitized_km / sanitized_norm) * 1000.0
        breakdown["distance_km"] = sanitized_km
        breakdown["points"] = pts
        breakdown["formula"] = f"{sanitized_km:g} / {sanitized_norm:g} × 1000"
        return ScoreBreakdown(pts, None, breakdown)

    # Standard timed distances: chip time preferred, gun time fallback
    time_kind = "chip" if chip_time_s is not None else "gun"
    time_val = chip_time_s if time_kind == "chip" else gun_time_s
    if time_val is None:
        return excluded("missing_time")

    sanitized_time = sanitize_float(time_val)
    if sanitized_time is None or sanitized_time <= 0:
        return excluded("invalid_time")

    pts = (sanitized_norm / sanitized_time) * 1000.0
    breakdown["time_kind"] = time_kind
    breakdown["time_s"] = sanitized_time
    breakdown["points"] = pts
    breakdown["formula"] = f"{sanitized_norm:g} / {sanitized_time:g} × 1000"
    return ScoreBreakdown(pts, None, breakdown)
