from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.api.auth import _create_token
from app.modules.rating.repository import RatingRepository


@pytest.mark.asyncio
async def test_rating_hidden_athlete_is_filtered_and_ranks_contiguous():
    mock_session = AsyncMock()
    repo = RatingRepository(mock_session)

    # 3 athletes in rating_entry, but athlete 2 is hidden in athlete table
    mock_entries = [
        {
            "rank": 1,
            "athlete_id": 1,
            "display_name": "Иванов Иван",
            "birth_year": 1990,
            "gender": "M",
            "points": 1000.0,
            "best_points": 1000.0,
            "starts_count": 2,
        },
        # Athlete 2 was hidden in SQL JOIN athlete a ON a.id = re.athlete_id WHERE a.is_hidden = FALSE
        {
            "rank": 3,
            "athlete_id": 3,
            "display_name": "Сидоров Сидор",
            "birth_year": 1995,
            "gender": "M",
            "points": 800.0,
            "best_points": 800.0,
            "starts_count": 1,
        },
    ]

    async def mock_fetchrow(query, *args):
        if "FROM rating_entry" in query:
            return {"period_start": "2025-11-23", "period_end": "2026-11-23"}
        return None

    async def mock_fetch(query, *args):
        if "FROM rating_entry re" in query:
            return mock_entries
        if "FROM rating_snapshot" in query:
            # Snapshot 30 days ago: athlete 3 had rank 4
            return [{"athlete_id": 3, "rank": 4}]
        return []

    async def mock_fetchval(query, *args):
        return len(mock_entries)

    repo.fetchrow = mock_fetchrow
    repo.fetch = mock_fetch
    repo.fetchval = mock_fetchval
    repo._published_version = AsyncMock(return_value=None)

    page = await repo.get_rating_page(sport="run")

    assert page["sport"] == "run"
    assert len(page["rows"]) == 2
    # Gaps are eliminated: ranks are strictly contiguous 1 and 2
    assert page["rows"][0]["rank"] == 1
    assert page["rows"][0]["athlete_id"] == 1
    assert page["rows"][0]["rank_delta"] is None

    assert page["rows"][1]["rank"] == 2
    assert page["rows"][1]["athlete_id"] == 3
    # Rank delta: prev_rank (4) - current_rank (2) = +2
    assert page["rows"][1]["rank_delta"] == 2


@pytest.mark.asyncio
async def test_rating_as_of_cut_does_not_mutate_snapshots():
    mock_session = AsyncMock()
    repo = RatingRepository(mock_session)

    cut_results = [
        {
            "athlete_id": 10,
            "display_name": "Лыжник Петр",
            "birth_year": 1988,
            "gender": "M",
            "points": 950.0,
            "best_points": 950.0,
            "starts_count": 3,
        }
    ]

    async def mock_fetch(query, *args):
        if "FROM athlete a" in query and "c.date_begin BETWEEN" in query:
            return cut_results
        return []

    repo.fetch = mock_fetch

    page = await repo.get_rating_page(sport="ski", as_of=date(2026, 3, 1))

    assert page["sport"] == "ski"
    assert page["as_of"] == "2026-03-01"
    assert len(page["rows"]) == 1
    assert page["rows"][0]["rank"] == 1
    assert page["rows"][0]["points"] == 950.0
    # No SQL execute was called on session (pure read-only calculation on the fly)
    assert not mock_session.execute.called


def test_rating_api_as_of_forbidden_for_regular_user_and_allowed_for_captain(client):
    regular_token = _create_token("user", "user", "User One")
    _create_token("captain", "captain", "Ski Captain")
    _create_token("admin", "admin", "Admin One")

    # 1. Unauthenticated request -> 401 Unauthorized
    res_guest = client.get("/api/rating?as_of=2026-02-01")
    assert res_guest.status_code == 401

    # 2. Regular user with as_of -> 403 Forbidden
    res_user = client.get(
        "/api/rating?as_of=2026-02-01",
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert res_user.status_code == 403

    # 3. Standard rating without as_of -> 200 OK for regular user
    res_pub = client.get("/api/rating?sport=ski", headers={"Authorization": f"Bearer {regular_token}"})
    assert res_pub.status_code == 200
    data = res_pub.json()
    assert data["sport"] == "ski"
