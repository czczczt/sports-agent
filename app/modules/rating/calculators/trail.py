"""Pure trail running rating calculator per SPEC v1.3 §9.4 and §9.7."""

from __future__ import annotations

from typing import Any

from app.modules.rating.calculators.base import (
    ScoreBreakdown,
    sanitize_float,
)

FORMULA_VERSION = "trail-v1"


def calculate_trail_score(
    *,
    status: str | None,
    duplicate_of: int | None,
    gender: str | None,
    distance_km: float | None,
    elevation_gain_m: float | None,
    event_date: str | None = None,
    chip_time_s: float | None = None,
    gun_time_s: float | None = None,
    leader_time_s: float | None = None,
    median_time_s: float | None = None,
    formula_version: str = FORMULA_VERSION,
) -> ScoreBreakdown:
    """Pure calculator: result parameters -> ScoreBreakdown.

    Formula: max(0, 10 × (km + D+ / 100) × (1 − (Ta − Tl) / Tl) + Bmed), K=1.
    Trail race without positive elevation gain (D+) is non-scoring (missing_elevation_gain).
    """
    breakdown: dict[str, Any] = {
        "sport": "trail",
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
    if gender not in ("M", "F"):
        return excluded("unknown_gender")
    if not event_date:
        return excluded("missing_date")

    # D+ check: trail without positive elevation gain is strictly non-scoring
    if elevation_gain_m is None:
        return excluded("missing_elevation_gain")
    d_plus = sanitize_float(elevation_gain_m)
    if d_plus is None or d_plus <= 0:
        return excluded("invalid_elevation_gain")

    if distance_km is None:
        return excluded("missing_distance")
    km = sanitize_float(distance_km)
    if km is None or km <= 0:
        return excluded("invalid_distance")

    time_kind = "chip" if chip_time_s is not None else "gun"
    t_a_raw = chip_time_s if time_kind == "chip" else gun_time_s
    if t_a_raw is None:
        return excluded("missing_time")
    t_a = sanitize_float(t_a_raw)
    if t_a is None or t_a <= 0:
        return excluded("invalid_time")

    if leader_time_s is None:
        return excluded("missing_leader_time")
    t_l = sanitize_float(leader_time_s)
    if t_l is None or t_l <= 0:
        return excluded("invalid_leader_time")

    if median_time_s is None:
        return excluded("missing_median_time")
    t_med = sanitize_float(median_time_s)
    if t_med is None or t_med <= 0:
        return excluded("invalid_median_time")

    r_max = 10.0 * (km + d_plus / 100.0)
    b_med = 2.0 * max(0.0, (t_med - t_a) / 60.0)
    raw_pts = r_max * (1.0 - (t_a - t_l) / t_l) + b_med
    pts = max(0.0, raw_pts)

    breakdown["distance_km"] = km
    breakdown["elevation_gain_m"] = d_plus
    breakdown["time_kind"] = time_kind
    breakdown["time_s"] = t_a
    breakdown["leader_time_s"] = t_l
    breakdown["median_time_s"] = t_med
    breakdown["r_max"] = r_max
    breakdown["b_med"] = b_med
    breakdown["points"] = pts
    breakdown["formula"] = (
        f"max(0, 10 × ({km:g} + {d_plus:g} / 100) × (1 - ({t_a:g} - {t_l:g}) / {t_l:g}) + {b_med:.2f})"
    )
    return ScoreBreakdown(pts, None, breakdown)
