"""Publish an immutable running rating within the caller's transaction."""
from datetime import date

from app.modules.rating.publication_repository import RatingPublicationRepository
from app.pipeline.errors import PilotRejected
from app.services.rating_service import recalculate_rating_sync


def publish_rating(
    connection, run_id: int, *, as_of: date | None = None, affected_sports: set[str] | None = None,
    require_running: bool = True,
) -> int | None:
    repository = RatingPublicationRepository(connection)
    previous_id, existing_id, legacy = repository.prepare(run_id)
    if existing_id is not None:
        return existing_id
    summary = recalculate_rating_sync(connection, as_of=as_of, commit=False, affected_sports=affected_sports)
    count = summary["athletes_rated"]
    if not count and not require_running and previous_id is None and not legacy:
        return None
    if not count:
        raise PilotRejected("Cannot publish an empty running rating")
    comparable = repository.comparable_count(previous_id, summary)
    if (
        comparable is None
        and previous_id is None
        and legacy
        and legacy[:2] == (summary["period_start"], summary["period_end"])
    ):
        comparable = legacy[2]
    if comparable is not None and count * 5 < comparable * 4:
        raise PilotRejected("Running rating shrank below 80% of the comparable published version")
    return repository.publish(run_id, summary)
