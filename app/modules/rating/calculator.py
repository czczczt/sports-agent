"""Rating calculators for running, ski, biathlon, triathlon, and trail per SPEC v1.3 §9."""

import math
from datetime import date
from typing import Any

FORMULA_VERSION = "run-v1"
RATING_PERIOD_DAYS = 365

VALID_SPORTS = {"run", "ski", "biathlon", "triathlon", "trail"}

TRIATHLON_RMAX = {
    "full": 10000,
    "half": 5000,
    "olympic": 2500,
    "sprint": 1250,
    "supersprint": 625,
    "indoor": 625,
}

TRIATHLON_K_MAP = {
    "regular": 1.0,
    "worlds": 1.10,
    "kona": 1.15,
}

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
) -> tuple[float | None, str | None, dict[str, Any]]:
    """Расчёт баллов для бега, лыж, биатлона, триатлона и трейла (SPEC v1.3 §9)."""
    breakdown: dict[str, Any] = {
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
        "formula_version": FORMULA_VERSION,
    }

    def excluded(reason: str) -> tuple[None, str, dict[str, Any]]:
        breakdown["reason"] = reason
        return None, reason, breakdown

    if duplicate_of is not None:
        return excluded("duplicate")
    if status != "FIN":
        return excluded("not_finisher")
    if sport not in VALID_SPORTS:
        return excluded("unsupported_sport")
    if gender not in ("M", "F"):
        return excluded("unknown_gender")
    if not event_date:
        return excluded("missing_date")

    # 1. ЛЫЖНЫЕ ГОНКИ И БИАТЛОН (SPEC v1.3 §9.2)
    if sport in ("ski", "biathlon"):
        if is_rl_series:
            if rl_points is not None and isinstance(rl_points, (int, float)) and math.isfinite(rl_points) and rl_points > 0:
                pts = rl_points / 7.0
                breakdown["points"] = pts
                breakdown["formula"] = f"{rl_points:g} / 7"
                return pts, None, breakdown
            return excluded("rl_series_excluded_from_place_scoring")

        if finishers_count is None:
            return excluded("missing_finishers_count")
        if not isinstance(finishers_count, (int, float)) or not math.isfinite(finishers_count) or finishers_count <= 0:
            return excluded("invalid_finishers_count")
        if place is None:
            return excluded("missing_place")
        if not isinstance(place, (int, float)) or not math.isfinite(place) or place <= 0 or place > finishers_count:
            return excluded("invalid_place")

        pts = 100.0 * (finishers_count - place + 1) / finishers_count
        time_kind = "chip" if chip_time_s is not None else ("gun" if gun_time_s is not None else None)
        seconds = chip_time_s if time_kind == "chip" else (gun_time_s if time_kind == "gun" else None)
        breakdown["place"] = place
        breakdown["finishers_count"] = finishers_count
        breakdown["time_kind"] = time_kind
        breakdown["time_s"] = seconds
        breakdown["points"] = pts
        breakdown["formula"] = f"100 × ({finishers_count:g} - {place:g} + 1) / {finishers_count:g}"
        return pts, None, breakdown

    # 2. ТРИАТЛОН (SPEC v1.3 §9.3)
    if sport == "triathlon":
        if not distance_class or distance_class not in TRIATHLON_RMAX:
            return excluded("unclassified_distance")
        r_max = TRIATHLON_RMAX[distance_class]
        k = TRIATHLON_K_MAP.get(special or "regular", 1.0)

        time_kind = "chip" if chip_time_s is not None else "gun"
        t_a = chip_time_s if time_kind == "chip" else gun_time_s
        if t_a is None:
            return excluded("missing_time")
        if not isinstance(t_a, (int, float)) or not math.isfinite(t_a) or t_a <= 0:
            return excluded("invalid_time")

        if leader_time_s is None:
            return excluded("missing_leader_time")
        if not isinstance(leader_time_s, (int, float)) or not math.isfinite(leader_time_s) or leader_time_s <= 0:
            return excluded("invalid_leader_time")

        if median_time_s is None:
            return excluded("missing_median_time")
        if not isinstance(median_time_s, (int, float)) or not math.isfinite(median_time_s) or median_time_s <= 0:
            return excluded("invalid_median_time")

        b_med = 2.0 * max(0.0, (median_time_s - t_a) / 60.0)
        raw_pts = (r_max * (1.0 - (t_a - leader_time_s) / leader_time_s) + b_med) * k
        pts = max(0.0, raw_pts)
        breakdown["time_kind"] = time_kind
        breakdown["time_s"] = t_a
        breakdown["leader_time_s"] = leader_time_s
        breakdown["median_time_s"] = median_time_s
        breakdown["r_max"] = r_max
        breakdown["k"] = k
        breakdown["b_med"] = b_med
        breakdown["points"] = pts
        breakdown["formula"] = f"max(0, ({r_max:g} × (1 - ({t_a:g} - {leader_time_s:g}) / {leader_time_s:g}) + {b_med:.2f}) × {k:g})"
        return pts, None, breakdown

    # 3. ТРЕЙЛ (SPEC v1.3 §9.4)
    if sport == "trail":
        if elevation_gain_m is None:
            return excluded("missing_elevation_gain")
        if not isinstance(elevation_gain_m, (int, float)) or not math.isfinite(elevation_gain_m) or elevation_gain_m <= 0:
            return excluded("invalid_elevation_gain")

        if distance_km is None:
            return excluded("missing_distance")
        if not isinstance(distance_km, (int, float)) or not math.isfinite(distance_km) or distance_km <= 0:
            return excluded("invalid_distance")

        time_kind = "chip" if chip_time_s is not None else "gun"
        t_a = chip_time_s if time_kind == "chip" else gun_time_s
        if t_a is None:
            return excluded("missing_time")
        if not isinstance(t_a, (int, float)) or not math.isfinite(t_a) or t_a <= 0:
            return excluded("invalid_time")

        if leader_time_s is None:
            return excluded("missing_leader_time")
        if not isinstance(leader_time_s, (int, float)) or not math.isfinite(leader_time_s) or leader_time_s <= 0:
            return excluded("invalid_leader_time")

        if median_time_s is None:
            return excluded("missing_median_time")
        if not isinstance(median_time_s, (int, float)) or not math.isfinite(median_time_s) or median_time_s <= 0:
            return excluded("invalid_median_time")

        r_max = 10.0 * (distance_km + elevation_gain_m / 100.0)
        b_med = 2.0 * max(0.0, (median_time_s - t_a) / 60.0)
        raw_pts = r_max * (1.0 - (t_a - leader_time_s) / leader_time_s) + b_med
        pts = max(0.0, raw_pts)
        breakdown["distance_km"] = distance_km
        breakdown["elevation_gain_m"] = elevation_gain_m
        breakdown["time_kind"] = time_kind
        breakdown["time_s"] = t_a
        breakdown["leader_time_s"] = leader_time_s
        breakdown["median_time_s"] = median_time_s
        breakdown["r_max"] = r_max
        breakdown["b_med"] = b_med
        breakdown["points"] = pts
        breakdown["formula"] = f"max(0, 10 × ({distance_km:g} + {elevation_gain_m:g} / 100) × (1 - ({t_a:g} - {leader_time_s:g}) / {leader_time_s:g}) + {b_med:.2f})"
        return pts, None, breakdown

    # 4. БЕГ (RUN - по умолчанию)
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
