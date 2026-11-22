"""Pure triathlon rating calculator per SPEC v1.3 §9.3 and §9.7."""

from __future__ import annotations

from typing import Any

from app.modules.rating.calculators.base import (
    ScoreBreakdown,
    sanitize_float,
)

FORMULA_VERSION = "triathlon-v1"

TRIATHLON_RMAX: dict[str, float] = {
    "full": 10000.0,
    "half": 5000.0,
    "olympic": 2500.0,
    "sprint": 1250.0,
    "supersprint": 625.0,
    "indoor": 625.0,
}

# K coefficients are fixed by formula version; modifying them requires a new formula_version.
TRIATHLON_K_MAP: dict[str, float] = {
    "regular": 1.0,
    "worlds": 1.10,
    "kona": 1.15,
}


def calculate_triathlon_score(
    *,
    status: str | None,
    duplicate_of: int | None,
    gender: str | None,
    distance_class: str | None,
    event_date: str | None = None,
    chip_time_s: float | None = None,
    gun_time_s: float | None = None,
    leader_time_s: float | None = None,
    median_time_s: float | None = None,
    special: str | None = "regular",
    formula_version: str = FORMULA_VERSION,
) -> ScoreBreakdown:
    """Pure calculator: result parameters -> ScoreBreakdown.

    Formula: (Rmax × (1 − (Ta − Tl) / Tl) + Bmed) × K.
    Bmed = 2 × max(0, (Tmed − Ta) / 60).
    """
    breakdown: dict[str, Any] = {
        "sport": "triathlon",
        "class": distance_class,
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
    if not distance_class or distance_class not in TRIATHLON_RMAX:
        return excluded("unclassified_distance")

    r_max = TRIATHLON_RMAX[distance_class]
    k = TRIATHLON_K_MAP.get(special or "regular", 1.0)

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

    b_med = 2.0 * max(0.0, (t_med - t_a) / 60.0)
    raw_pts = (r_max * (1.0 - (t_a - t_l) / t_l) + b_med) * k
    pts = max(0.0, raw_pts)

    breakdown["time_kind"] = time_kind
    breakdown["time_s"] = t_a
    breakdown["leader_time_s"] = t_l
    breakdown["median_time_s"] = t_med
    breakdown["r_max"] = r_max
    breakdown["k"] = k
    breakdown["b_med"] = b_med
    breakdown["points"] = pts
    breakdown["formula"] = (
        f"max(0, ({r_max:g} × (1 - ({t_a:g} - {t_l:g}) / {t_l:g}) + {b_med:.2f}) × {k:g})"
    )
    return ScoreBreakdown(pts, None, breakdown)
