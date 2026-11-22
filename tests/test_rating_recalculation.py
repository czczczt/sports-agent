from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.modules.rating.calculator import FORMULA_VERSION
from app.modules.rating.repository import RatingRepository


@pytest.mark.asyncio
async def test_recalculate_rating_aggregates_and_ranks():
    mock_session = AsyncMock()
    repo = RatingRepository(mock_session)

    # Mock norms
    norms = [
        {"distance_class": "10000m", "gender": "M", "value": 1760.0, "unit": "s", "year": 2026},
    ]

    # Mock results
    results = [
        {
            "id": 101,
            "status": "FIN",
            "duplicate_of": None,
            "gender": "M",
            "chip_time_s": 2000.0,
            "gun_time_s": 2050.0,
            "distance_km": None,
            "distance_type": "10000m",
            "discipline": None,
            "date_begin": date(2026, 5, 1),
            "athlete_id": 1,
        },
        {
            "id": 102,
            "status": "FIN",
            "duplicate_of": None,
            "gender": "M",
            "chip_time_s": 1800.0,
            "gun_time_s": 1810.0,
            "distance_km": None,
            "distance_type": "10000m",
            "discipline": None,
            "date_begin": date(2026, 6, 1),
            "athlete_id": 2,
        },
    ]

    aggregates = [
        {"athlete_id": 2, "points": 950.0, "best_points": 950.0, "starts_count": 1},
        {"athlete_id": 1, "points": 800.0, "best_points": 800.0, "starts_count": 1},
    ]

    async def mock_fetch(query, *args):
        if "rating_norm" in query:
            return norms
        if "FROM result r" in query:
            return results
        if "GROUP BY a.id" in query:
            return aggregates
        return []

    repo.fetch = mock_fetch

    result = await repo.recalculate_rating(as_of=date(2026, 11, 20))

    assert result["formula_version"] == FORMULA_VERSION
    assert result["results_scored"] == 2
    assert result["athletes_rated"] == 2
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_recalculate_rating_multi_sport():
    mock_session = AsyncMock()
    repo = RatingRepository(mock_session)

    norms = [
        {"distance_class": "10000m", "gender": "M", "value": 1760.0, "unit": "s", "year": 2026},
    ]

    results = [
        # Ski race with place
        {
            "id": 201,
            "race_id": 10,
            "status": "FIN",
            "duplicate_of": None,
            "gender": "M",
            "position": 1,
            "position_gender": 1,
            "sport": "ski",
            "date_begin": date(2026, 2, 1),
            "athlete_id": 10,
        },
        # Triathlon race
        {
            "id": 202,
            "race_id": 20,
            "status": "FIN",
            "duplicate_of": None,
            "gender": "M",
            "chip_time_s": 7200.0,
            "scoring_class": "olympic",
            "sport": "triathlon",
            "special": "regular",
            "date_begin": date(2026, 6, 1),
            "athlete_id": 11,
        },
        # Trail race with elevation gain
        {
            "id": 203,
            "race_id": 30,
            "status": "FIN",
            "duplicate_of": None,
            "gender": "M",
            "chip_time_s": 21600.0,
            "distance_km": 50.0,
            "elevation_gain_m": 2500.0,
            "sport": "trail",
            "date_begin": date(2026, 8, 1),
            "athlete_id": 12,
        },
    ]

    aggregates = []

    async def mock_fetch(query, *args):
        if "rating_norm" in query:
            return norms
        if "FROM result r" in query:
            return results
        if "GROUP BY a.id" in query:
            return aggregates
        return []

    repo.fetch = mock_fetch

    result = await repo.recalculate_rating(as_of=date(2026, 11, 20))
    # All 3 multi-sport results scored successfully
    assert result["results_scored"] == 3
    assert mock_session.commit.called

