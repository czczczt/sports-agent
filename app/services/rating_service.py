"""Compatibility entry points for the preserved run-v1 calculator and async reads.

Schema setup now belongs to Alembic. The legacy synchronous SQLite rebuild is
retired; stage 0 imports published scores and ranks without recalculating them.
"""

from app.modules.rating.calculator import (
    _NORMS,
    FORMULA_VERSION,
    RATING_PERIOD_DAYS,
    _calculate_score,
    _parse_date,
)

__all__ = [
    "FORMULA_VERSION",
    "RATING_PERIOD_DAYS",
    "_NORMS",
    "_calculate_score",
    "_parse_date",
    "get_rating_me_row",
    "get_rating_norms",
    "get_rating_page",
]

from app.modules.rating.repository import RatingRepository


async def get_rating_page(session, **kwargs):
    return await RatingRepository(session).get_rating_page(**kwargs)


async def get_rating_me_row(session, athlete_id, gender=None):
    return await RatingRepository(session).get_rating_me_row(athlete_id, gender)


async def get_rating_norms(session, year=2026):
    return await RatingRepository(session).get_rating_norms(year)
