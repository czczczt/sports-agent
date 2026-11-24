"""Deduplicate aggregator results against an available official protocol."""
from collections import defaultdict

from psycopg.rows import dict_row

AGGREGATORS = ("probeg", "myrunstats")


def _protocol_rows(cursor, event_id):
    return cursor.execute(
        """SELECT r.id, ra.distance_m, r.gender, r.birth_year,
                  search_text(COALESCE(r.full_name_raw, '')) AS name_key,
                  r.chip_time_s, r.gun_time_s, l.athlete_id
           FROM race ra JOIN result r ON r.race_id=ra.id
           LEFT JOIN result_athlete l ON l.result_id=r.id
           WHERE ra.competition_id=%s AND ra.superseded_by_race_id IS NULL
             AND r.status='FIN' AND r.duplicate_of IS NULL
             AND ra.distance_m IS NOT NULL AND r.is_anonymized IS NOT TRUE""", (event_id,),
    ).fetchall()


def _key(row):
    return row["distance_m"], tuple(sorted(row["name_key"].split())), row["gender"]


def _same_finish(aggregated, official):
    return (
        not (aggregated["birth_year"] and official["birth_year"] and
             aggregated["birth_year"] != official["birth_year"])
        and any(aggregated[field] is not None and official[field] is not None and
                abs(aggregated[field] - official[field]) <= 1
                for field in ("chip_time_s", "gun_time_s"))
    )


def _record_ambiguity(cursor, event):
    cursor.execute(
        """INSERT INTO issue (source_id, stage, kind, object_ref, fingerprint, details, assignee)
           VALUES (%s, 'dedup', 'ambiguous_protocol', %s, %s, 'Check competing protocol links and results', 'human')
           ON CONFLICT (fingerprint) DO UPDATE SET last_seen=now(),
                occurrences=issue.occurrences + 1, status='new', resolved_at=NULL""",
        (event["source_id"], str(event["id"]), f"collection:duplicate:{event['id']}"),
    )


def _reconcile(cursor, event):
    cursor.execute(
        """UPDATE result r SET collection_review=false,
                    duplicate_of=CASE WHEN r.collection_duplicate THEN NULL ELSE r.duplicate_of END,
                    collection_duplicate=false
           FROM race ra WHERE ra.competition_id=%s AND ra.id=r.race_id AND r.is_anonymized IS NOT TRUE
             AND (r.collection_duplicate OR r.collection_review)""",
        (event["id"],),
    )
    cursor.execute(
        """UPDATE competition SET canonical_competition_id=NULL, collection_canonical=false
           WHERE id=%s AND collection_canonical""",
        (event["id"],),
    )
    candidates = cursor.execute(
        """SELECT c.id, (c.source_url=agg.primary_protocol_url) IS TRUE AS explicit
           FROM competition agg JOIN competition c
                ON c.date_begin=agg.date_begin AND c.source_id<>agg.source_id
           JOIN source s ON s.id=c.source_id
           WHERE agg.id=%s AND NOT (s.name=ANY(%s))
             AND (c.source_url=agg.primary_protocol_url
                  OR search_text(c.name)=search_text(agg.name))""",
        (event["id"], list(AGGREGATORS)),
    ).fetchall()
    explicit = [candidate for candidate in candidates if candidate["explicit"]]
    if explicit:
        candidates = explicit
    if not candidates:
        return
    if len(explicit) == 1:
        cursor.execute(
            """UPDATE competition SET canonical_competition_id=%s, collection_canonical=true
               WHERE id=%s AND canonical_competition_id IS NULL""",
            (explicit[0]["id"], event["id"]),
        )
    results_by_key = defaultdict(list)
    for candidate in candidates:
        for result in _protocol_rows(cursor, candidate["id"]):
            results_by_key[_key(result)].append(result)
    needs_review = False
    for result in _protocol_rows(cursor, event["id"]):
        key = _key(result)
        if not key[1] or not key[2]:
            continue
        matches = [other for other in results_by_key[key] if _same_finish(result, other)]
        if len(matches) == 1 and len(explicit) == 1:
            official = matches[0]
            cursor.execute(
                "UPDATE result SET duplicate_of=%s, collection_duplicate=true, collection_review=false WHERE id=%s",
                (official["id"], result["id"]),
            )
            if result["athlete_id"] and not official["athlete_id"]:
                cursor.execute(
                    "INSERT INTO result_athlete(result_id, athlete_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (official["id"], result["athlete_id"]),
                )
        elif matches:
            needs_review = True
            cursor.execute("UPDATE result SET collection_review=true WHERE id=%s", (result["id"],))
    if needs_review or len(explicit) > 1:
        _record_ambiguity(cursor, event)


def reconcile_duplicates(connection, competition_id: int) -> None:
    with connection.cursor(row_factory=dict_row) as cursor:
        events = cursor.execute(
            """SELECT agg.id, agg.source_id FROM competition current
               JOIN competition agg ON agg.id=current.id OR (
                    agg.date_begin=current.date_begin AND agg.source_id<>current.source_id
                    AND (agg.primary_protocol_url=current.source_url
                         OR search_text(agg.name)=search_text(current.name)))
               JOIN source s ON s.id=agg.source_id
               WHERE current.id=%s AND s.name=ANY(%s)""",
            (competition_id, list(AGGREGATORS)),
        ).fetchall()
        for event in events:
            _reconcile(cursor, event)
