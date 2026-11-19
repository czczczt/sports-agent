"""Legacy run-v1 calculator retained unchanged for migration parity."""

import math
from datetime import date
from typing import Any

FORMULA_VERSION = "run-v1"
RATING_PERIOD_DAYS = 365

_NORMS = (
    ("60m", 6.84, 7.5),
    ("100m", 10.62, 11.75),
    ("200m", 21.65, 24.4),
    ("400m", 47.9, 54.8),
    ("800m", 111, 127),
    ("1000m", 142, 165),
    ("1500m", 228, 259),
    ("1mile", 243, 279),
    ("3000m", 486, 555),
    ("5000m", 846, 965),
    ("10000m", 1760, 2028),
    ("half_marathon", 3900, 4540),
    ("marathon", 8400, 9600),
    ("100km", 24960, 28800),
    ("24h", 245, 216),
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _calculate_score(
    *,
    status: str | None,
    duplicate_of: int | None,
    gender: str | None,
    distance_class: str | None,
    event_date: str | None,
    chip_time_s: float | None,
    gun_time_s: float | None,
    distance_km: float | None,
    norm_value: float | None,
    norm_unit: str | None,
    norm_year: int | None,
) -> tuple[float | None, str | None, dict[str, Any]]:
    breakdown: dict[str, Any] = {
        "sport": "run",
        "class": distance_class,
        "gender": gender,
        "norm_value": norm_value,
        "norm_unit": norm_unit,
        "norm_year": norm_year,
        "time_kind": None,
        "time_s": None,
        "formula": None,
        "points": None,
        "formula_version": FORMULA_VERSION,
    }

    def excluded(reason: str) -> tuple[None, str, dict[str, Any]]:
        breakdown["reason"] = reason
        return None, reason, breakdown

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

    if distance_class == "24h":
        if distance_km is None:
            return excluded("missing_distance")
        if (
            not isinstance(distance_km, (int, float))
            or not math.isfinite(distance_km)
            or distance_km <= 0
        ):
            return excluded("invalid_distance")
        points = distance_km / norm_value * 1000
        breakdown["distance_km"] = distance_km
        breakdown["formula"] = f"{distance_km:g} / {norm_value:g} × 1000"
    else:
        time_kind = "chip" if chip_time_s is not None else "gun"
        seconds = chip_time_s if time_kind == "chip" else gun_time_s
        breakdown["time_kind"] = time_kind
        breakdown["time_s"] = seconds
        if seconds is None:
            return excluded("missing_time")
        if (
            not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds <= 0
        ):
            return excluded("invalid_time")
        points = norm_value / seconds * 1000
        breakdown["formula"] = f"{norm_value:g} / {seconds:g} × 1000"

    if not math.isfinite(points) or points <= 0:
        return excluded("invalid_points")
    breakdown["points"] = points
    return points, None, breakdown
