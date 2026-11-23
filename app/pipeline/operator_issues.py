"""Queue source metadata issues for operator review."""
from hashlib import sha256


def _fingerprint(source_id: int, competition_id: int, kind: str, reference: str) -> str:
    key = f"{source_id}:{competition_id}:{kind}:{reference}"
    return "collection:metadata:" + sha256(key.encode()).hexdigest()


def record_issue(connection, source_id: int, competition_id: int, kind: str, reference: str) -> None:
    connection.execute(
        """INSERT INTO issue (source_id, stage, kind, object_ref, fingerprint, details, assignee)
           VALUES (%s, 'metadata', %s, %s, %s, %s, 'human')
           ON CONFLICT (fingerprint) DO UPDATE SET status='new', resolved_at=NULL,
               last_seen=now(), occurrences=issue.occurrences + 1""",
        (source_id, kind, str(competition_id),
         _fingerprint(source_id, competition_id, kind, reference), reference),
    )


def check_elevation(
    connection, source_id: int, competition_id: int, race: dict, elevation_gain_m: float | None,
) -> None:
    if race["sport"] != "trail":
        return
    reference = str(race["external_id"])
    kind = "missing_elevation_gain"
    if elevation_gain_m is None:
        record_issue(connection, source_id, competition_id, kind, reference)
    else:
        connection.execute(
            """UPDATE issue SET status='resolved', resolved_at=now(), last_seen=now()
               WHERE fingerprint=%s AND status='new'""",
            (_fingerprint(source_id, competition_id, kind, reference),),
        )
