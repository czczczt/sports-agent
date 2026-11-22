"""Rating calculation pure functions for running, ski, biathlon, triathlon, and trail."""

from app.modules.rating.calculators.base import (
    VALID_SPORTS,
    ScoreBreakdown,
    parse_date,
    sanitize_float,
)
from app.modules.rating.calculators.running import (
    DEFAULT_RUN_NORMS_2026,
    calculate_running_score,
)
from app.modules.rating.calculators.running import (
    FORMULA_VERSION as RUN_FORMULA_VERSION,
)
from app.modules.rating.calculators.ski import (
    FORMULA_VERSION as SKI_FORMULA_VERSION,
)
from app.modules.rating.calculators.ski import (
    calculate_ski_score,
)
from app.modules.rating.calculators.trail import (
    FORMULA_VERSION as TRAIL_FORMULA_VERSION,
)
from app.modules.rating.calculators.trail import (
    calculate_trail_score,
)
from app.modules.rating.calculators.triathlon import (
    FORMULA_VERSION as TRIATHLON_FORMULA_VERSION,
)
from app.modules.rating.calculators.triathlon import (
    TRIATHLON_K_MAP,
    TRIATHLON_RMAX,
    calculate_triathlon_score,
)

__all__ = [
    "ScoreBreakdown",
    "VALID_SPORTS",
    "parse_date",
    "sanitize_float",
    "DEFAULT_RUN_NORMS_2026",
    "RUN_FORMULA_VERSION",
    "calculate_running_score",
    "SKI_FORMULA_VERSION",
    "calculate_ski_score",
    "TRIATHLON_FORMULA_VERSION",
    "TRIATHLON_RMAX",
    "TRIATHLON_K_MAP",
    "calculate_triathlon_score",
    "TRAIL_FORMULA_VERSION",
    "calculate_trail_score",
]
