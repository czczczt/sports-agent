"""Pure ski and biathlon rating calculator per SPEC v1.3 §9.2 and §9.7."""

from __future__ import annotations

from typing import Any

from app.modules.rating.calculators.base import (
    ScoreBreakdown,
    sanitize_float,
)

FORMULA_VERSION = "ski-v1"


def calculate_ski_score(
    *,
    status: str | None,
    duplicate_of: int | None,
    gender: str | None,
    event_date: str | None = None,
    sport: str = "ski",
    finishers_count: int | None = None,
    place: int | None = None,
    chip_time_s: float | None = None,
    gun_time_s: float | None = None,
    is_rl_series: bool = False,
    rl_points: float | None = None,
    formula_version: str = FORMULA_VERSION,
) -> ScoreBreakdown:
    """Pure calculator: result parameters -> ScoreBreakdown.

    Race points: 100 × (finishers - place + 1) / finishers.
    Russialoppet marathon: rl_points ÷ 7.
    """
    breakdown: dict[str, Any] = {
        "sport": sport,
        "class": None,
        "gender": gender,
        "norm_value": None,
        "norm_unit": None,
        "norm_year": None,
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
    if sport not in ("ski", "biathlon"):
        return excluded("unsupported_sport")
    if gender not in ("M", "F"):
        return excluded("unknown_gender")
    if not event_date:
        return excluded("missing_date")

    if is_rl_series:
        sanitized_rl = sanitize_float(rl_points)
        if sanitized_rl is not None and sanitized_rl > 0:
            pts = sanitized_rl / 7.0
            breakdown["points"] = pts
            breakdown["formula"] = f"{sanitized_rl:g} / 7"
            return ScoreBreakdown(pts, None, breakdown)
        return excluded("rl_series_excluded_from_place_scoring")

    if finishers_count is None:
        return excluded("missing_finishers_count")
    sanitized_finishers = sanitize_float(finishers_count)
    if sanitized_finishers is None or sanitized_finishers <= 0:
        return excluded("invalid_finishers_count")

    if place is None:
        return excluded("missing_place")
    sanitized_place = sanitize_float(place)
    if sanitized_place is None or sanitized_place <= 0 or sanitized_place > sanitized_finishers:
        return excluded("invalid_place")

    pts = 100.0 * (sanitized_finishers - sanitized_place + 1.0) / sanitized_finishers
    time_kind = "chip" if chip_time_s is not None else ("gun" if gun_time_s is not None else None)
    seconds = chip_time_s if time_kind == "chip" else (gun_time_s if time_kind == "gun" else None)

    breakdown["place"] = int(sanitized_place)
    breakdown["finishers_count"] = int(sanitized_finishers)
    breakdown["time_kind"] = time_kind
    breakdown["time_s"] = sanitize_float(seconds)
    breakdown["points"] = pts
    breakdown["formula"] = f"100 × ({sanitized_finishers:g} - {sanitized_place:g} + 1) / {sanitized_finishers:g}"
    return ScoreBreakdown(pts, None, breakdown)
