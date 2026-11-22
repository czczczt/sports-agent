"""Rating calculators for running, ski, biathlon, triathlon, and trail per SPEC v1.3 §9."""

from __future__ import annotations

from typing import Any

from app.modules.rating.calculators import (
    DEFAULT_RUN_NORMS_2026,
    RUN_FORMULA_VERSION,
    SKI_FORMULA_VERSION,
    TRAIL_FORMULA_VERSION,
    TRIATHLON_FORMULA_VERSION,
    calculate_running_score,
    calculate_ski_score,
    calculate_trail_score,
    calculate_triathlon_score,
    parse_date,
)

FORMULA_VERSION = RUN_FORMULA_VERSION
RATING_PERIOD_DAYS = 365

_NORMS = DEFAULT_RUN_NORMS_2026
_parse_date = parse_date


def _calculate_score(
    *,
    status: str | None,
    duplicate_of: int | None,
    gender: str | None,
    distance_class: str | None = None,
    event_date: str | None,
    chip_time_s: float | None = None,
    gun_time_s: float | None = None,
    distance_km: float | None = None,
    norm_value: float | None = None,
    norm_unit: str | None = None,
    norm_year: int | None = None,
    sport: str = "run",
    finishers_count: int | None = None,
    place: int | None = None,
    leader_time_s: float | None = None,
    median_time_s: float | None = None,
    elevation_gain_m: float | None = None,
    special: str | None = "regular",
    is_rl_series: bool = False,
    rl_points: float | None = None,
    discipline: str | None = None,
    formula_version: str | None = None,
) -> tuple[float | None, str | None, dict[str, Any]]:
    """Диспетчер чистых калькуляторов по видам спорта (SPEC v1.3 §9)."""
    if sport in ("ski", "biathlon"):
        ver = formula_version or SKI_FORMULA_VERSION
        return calculate_ski_score(
            status=status,
            duplicate_of=duplicate_of,
            gender=gender,
            event_date=event_date,
            sport=sport,
            finishers_count=finishers_count,
            place=place,
            chip_time_s=chip_time_s,
            gun_time_s=gun_time_s,
            is_rl_series=is_rl_series,
            rl_points=rl_points,
            formula_version=ver,
        )

    if sport == "triathlon":
        ver = formula_version or TRIATHLON_FORMULA_VERSION
        return calculate_triathlon_score(
            status=status,
            duplicate_of=duplicate_of,
            gender=gender,
            distance_class=distance_class,
            event_date=event_date,
            chip_time_s=chip_time_s,
            gun_time_s=gun_time_s,
            leader_time_s=leader_time_s,
            median_time_s=median_time_s,
            special=special,
            formula_version=ver,
        )

    if sport == "trail":
        ver = formula_version or TRAIL_FORMULA_VERSION
        return calculate_trail_score(
            status=status,
            duplicate_of=duplicate_of,
            gender=gender,
            distance_km=distance_km,
            elevation_gain_m=elevation_gain_m,
            event_date=event_date,
            chip_time_s=chip_time_s,
            gun_time_s=gun_time_s,
            leader_time_s=leader_time_s,
            median_time_s=median_time_s,
            formula_version=ver,
        )

    if sport == "run":
        ver = formula_version or RUN_FORMULA_VERSION
        return calculate_running_score(
            status=status,
            duplicate_of=duplicate_of,
            gender=gender,
            distance_class=distance_class,
            event_date=event_date,
            chip_time_s=chip_time_s,
            gun_time_s=gun_time_s,
            distance_km=distance_km,
            norm_value=norm_value,
            norm_unit=norm_unit,
            norm_year=norm_year,
            discipline=discipline,
            formula_version=ver,
        )

    # Unsupported sport
    breakdown = {
        "sport": sport,
        "class": distance_class,
        "gender": gender,
        "norm_value": norm_value,
        "norm_unit": norm_unit,
        "norm_year": norm_year,
        "time_kind": None,
        "time_s": None,
        "formula": None,
        "points": None,
        "formula_version": formula_version or FORMULA_VERSION,
        "reason": "unsupported_sport",
    }
    return None, "unsupported_sport", breakdown
