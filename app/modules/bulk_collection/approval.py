"""Approve selected bulk protocols and publish their rating in one transaction."""
import logging
from collections import defaultdict
from datetime import date, timedelta

from psycopg.types.json import Jsonb

from app.modules.bulk_collection.preview import _event_match, _race_match, build_preview, fingerprint
from app.modules.rating.calculator import RATING_PERIOD_DAYS
from app.modules.runs.repository import complete
from app.pipeline.collection_repository import save_event
from app.pipeline.errors import PilotRejected
from app.pipeline.rating_publication import publish_rating
from app.services.rating_service import recalculate_rating_sync

logger = logging.getLogger(__name__)


class BulkConflict(Exception):
    """The published data or a draft changed after the preview."""


class BulkPublicationFailed(Exception):
    """Publication rolled back; the caller must retain the batch failure status."""


def preview_job(connection, job_id):
    preview, _, _ = build_preview(connection, job_id)
    return preview


def _resolve(groups, selected, requested):
    invalid = requested.keys() - groups.keys()
    if invalid:
        raise ValueError("В предпросмотре больше нет выбранной спорной дистанции.")
    decisions = []
    for key, group in groups.items():
        selected_drafts = [draft for draft in group.drafts if draft.event.draft_id in selected]
        choice = requested.get(key)
        if not selected_drafts:
            if choice:
                raise ValueError("Выбран протокол дистанции, которая не включена в утверждение.")
            continue
        if choice:
            winner = next((protocol for protocol in group.protocols if protocol.key == choice), None)
            if winner is None or (winner.event.draft_id and winner.event.draft_id not in selected):
                raise ValueError("Выбранный протокол недоступен для утверждения.")
        else:
            winner = group.preferred
            if winner and winner.event.draft_id and winner.event.draft_id not in selected:
                winner = None
        if winner and not winner.event.planned:
            directly_matched = [
                draft for draft in selected_drafts
                if draft is winner
                or (_event_match(winner.event, draft.event) and _race_match(winner, draft))
            ]
            if directly_matched:
                decisions.append((group, winner, directly_matched))
    return decisions


def _reject_superseded_drafts(connection, decisions, drafts):
    for _, _, selected in decisions:
        for draft in selected:
            draft_row = drafts[draft.event.draft_id]
            newer = connection.execute(
                """SELECT 1 FROM bulk_draft
                   WHERE source_id=%s AND event_code=%s AND id>%s
                     AND resolved_races ? %s LIMIT 1""",
                (draft_row["source_id"], draft_row["event_code"],
                 draft.event.draft_id, draft.external_id),
            ).fetchone()
            if newer:
                raise BulkConflict(
                    "Эта дистанция уже утверждена из более нового черновика. Обнови пакет."
                )


def _save_winners(connection, decisions, drafts):
    winners, race_decisions = defaultdict(set), defaultdict(set)
    for _, winner, selected in decisions:
        if winner.event.draft_id is not None:
            winners[winner.event.draft_id].add(winner.external_id)
        for draft in selected:
            race_decisions[draft.event.draft_id].add(draft.external_id)
    for draft_id, race_ids in winners.items():
        draft = drafts[draft_id]
        event = draft["payload"]
        resolved_keys = draft["resolved_races"].keys() | race_decisions[draft_id]
        save_event(
            connection, draft["source_id"], event,
            selected_race_ids=race_ids,
            defer_event_update=len(resolved_keys) < len(event["races"]), reconcile=False,
        )


def _winner_ids(connection, winner):
    if winner.race_id is not None:
        return winner.race_id, winner.event.competition_id
    return connection.execute(
        """SELECT ra.id, c.id FROM race ra JOIN competition c ON c.id=ra.competition_id
           WHERE c.source_id=%s AND c.external_id=%s AND ra.external_id=%s""",
        (*winner.event.identity, winner.external_id),
    ).fetchone()


def _retain_linked_athletes(connection, race_id, previous_ids):
    connection.execute(
        """WITH names AS (
               SELECT r.id, r.race_id, r.gender, r.birth_year, l.athlete_id,
                      (SELECT string_agg(part, ' ' ORDER BY part)
                       FROM regexp_split_to_table(search_text(r.full_name_raw), '[^[:alnum:]]+') part
                       WHERE part <> '') AS name_key,
                      COALESCE(r.chip_time_s,r.gun_time_s,r.official_time_s) AS finish_time
               FROM result r LEFT JOIN result_athlete l ON l.result_id=r.id
               WHERE (r.race_id=%s OR r.race_id=ANY(%s))
                 AND r.status='FIN' AND r.is_anonymized IS NOT TRUE
           ),
           matched AS (
               SELECT winner.id, previous.athlete_id,
                      COUNT(*) OVER (PARTITION BY previous.id) AS possible_results
               FROM names winner JOIN names previous
                 ON winner.race_id=%s AND previous.race_id<>%s AND winner.name_key=previous.name_key
                AND (winner.gender IS NULL OR previous.gender IS NULL OR winner.gender=previous.gender)
                AND (winner.birth_year IS NULL OR previous.birth_year IS NULL OR winner.birth_year=previous.birth_year)
                AND abs(winner.finish_time - previous.finish_time) <= 1
               WHERE previous.athlete_id IS NOT NULL
           )
           INSERT INTO result_athlete(result_id, athlete_id)
           SELECT id, min(athlete_id) FROM matched
           GROUP BY id HAVING max(possible_results)=1 AND count(DISTINCT athlete_id)=1
           ON CONFLICT DO NOTHING""",
        (race_id, sorted(previous_ids), race_id, race_id),
    )


def _publish_choices(connection, decisions, drafts, job_id, user_id):
    _save_winners(connection, decisions, drafts)
    resolved, changed, audit = defaultdict(dict), 0, []
    affected_sports = set()
    today = date.today()
    period_start = today - timedelta(days=RATING_PERIOD_DAYS)
    for group, winner, selected in decisions:
        race_id, event_id = _winner_ids(connection, winner)
        reactivated = connection.execute(
            """UPDATE race SET superseded_by_race_id=NULL
               WHERE id=%s AND superseded_by_race_id IS NOT NULL""",
            (race_id,),
        ).rowcount
        prior = {
            protocol.race_id for protocol in group.protocols + group.replaced_versions
            if protocol.race_id is not None and protocol.race_id != race_id and not protocol.event.planned
            and _event_match(winner.event, protocol.event) and _race_match(winner, protocol)
        }
        superseded = connection.execute(
            """UPDATE race SET superseded_by_race_id=%s
               WHERE id=ANY(%s) AND superseded_by_race_id IS DISTINCT FROM %s""",
            (race_id, sorted(prior), race_id),
        ).rowcount if prior else 0

        if prior:
            _retain_linked_athletes(connection, race_id, prior)
        if superseded or reactivated:
            connection.execute(
                """UPDATE result SET duplicate_of=CASE WHEN collection_duplicate THEN NULL ELSE duplicate_of END,
                             collection_duplicate=false, collection_review=false
                   WHERE race_id=%s AND (collection_duplicate OR collection_review)""",
                (race_id,),
            )

        if winner.item is not None or reactivated or superseded:
            changed += 1
            affected_sports.update(
                "ski" if protocol.sport == "biathlon" else protocol.sport
                for protocol in [winner, *group.protocols, *group.replaced_versions]
                if (protocol is winner or protocol.race_id is not None)
                and not protocol.event.planned and not protocol.relay and protocol.event.date
                and period_start <= protocol.event.date <= today
            )
        for draft in selected:
            resolved[draft.event.draft_id][draft.external_id] = {
                "protocol_key": winner.key, "published_race_id": race_id,
            }
        audit.append({"race_key": group.key, "protocol_key": winner.key, "race_id": race_id,
                      "superseded_race_ids": sorted(prior), "draft_ids": [p.event.draft_id for p in selected]})

    version_id = None
    if "run" in affected_sports:
        run_id = connection.execute(
            """INSERT INTO pilot_run(source_id,event_code,status,phase)
               VALUES (%s,%s,'succeeded','done') RETURNING id""",
            (decisions[0][1].event.source_id, f"bulk:{job_id}"),
        ).fetchone()[0]
        version_id = publish_rating(
            connection, run_id, as_of=today, affected_sports=affected_sports, require_running=False,
        )
        complete(connection, run_id, changed, version_id)
    elif affected_sports:
        recalculate_rating_sync(connection, as_of=today, commit=False, affected_sports=affected_sports)
    if audit:
        connection.execute(
            """INSERT INTO audit_log(user_id,action,entity,entity_id,diff,created_at)
               VALUES (%s,'approve_bulk_protocols','bulk_batch',%s,%s,now())""",
            (user_id, job_id, Jsonb({"decisions": audit, "rating_version_id": version_id})),
        )
    return resolved, changed, version_id


def approve_job(connection, job_id, draft_ids, resolutions, preview_revision, *, user_id=None):
    requested = {item["race_key"]: item["protocol_key"] for item in resolutions}
    if len(requested) != len(resolutions) or not draft_ids:
        raise ValueError("Выбери черновики и укажи один протокол для каждой спорной дистанции.")
    selected = set(draft_ids)
    request_key = fingerprint((preview_revision, sorted(selected), requested))
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('collection:publication', 0))")
    batch = connection.execute(
        "SELECT publication_status FROM bulk_batch WHERE id=%s FOR UPDATE", (job_id,),
    ).fetchone()
    if batch is None:
        raise KeyError(job_id)
    replay = connection.execute(
        "SELECT result FROM bulk_approval WHERE batch_id=%s AND request_key=%s", (job_id, request_key),
    ).fetchone()
    if replay:
        return replay[0]

    connection.execute("LOCK TABLE bulk_draft, competition, race, result IN SHARE ROW EXCLUSIVE MODE")
    preview, draft_rows, groups = build_preview(connection, job_id)
    if preview["preview_revision"] != preview_revision:
        raise BulkConflict("Данные изменились. Обнови предпросмотр и повтори утверждение.")
    drafts = {draft["id"]: draft for draft in draft_rows}
    if selected - drafts.keys() or any(drafts[draft_id]["status"] not in {"ready", "approved"} for draft_id in selected):
        raise ValueError("К утверждению доступны только проверенные черновики этого пакета.")
    decisions = _resolve(groups, selected, requested)
    _reject_superseded_drafts(connection, decisions, drafts)
    try:
        with connection.transaction():
            resolved, count, version_id = _publish_choices(connection, decisions, drafts, job_id, user_id)
            approved = {draft_id for draft_id in selected if drafts[draft_id]["status"] == "approved"}
            for draft_id, new_decisions in resolved.items():
                draft = drafts[draft_id]
                all_decisions = draft["resolved_races"] | new_decisions
                status = "approved" if len(all_decisions) == len(draft["payload"]["races"]) else "ready"
                if status == "approved":
                    approved.add(draft_id)
                connection.execute(
                    """UPDATE bulk_draft SET resolved_races=%s,status=%s,
                              approved_at=CASE WHEN %s='approved' THEN now() ELSE approved_at END
                       WHERE id=%s""",
                    (Jsonb(all_decisions), status, status, draft_id),
                )
            status = "published" if decisions else batch[0]
            if decisions:
                connection.execute(
                    "UPDATE bulk_batch SET publication_status=%s,publication_error=NULL WHERE id=%s",
                    (status, job_id),
                )
            result = {
                "approved_draft_ids": sorted(approved), "pending_draft_ids": sorted(selected - approved),
                "published_races": count, "rating_version_id": version_id, "publication_status": status,
            }
            connection.execute(
                "INSERT INTO bulk_approval(batch_id,request_key,result) VALUES (%s,%s,%s)",
                (job_id, request_key, Jsonb(result)),
            )
            return result
    except Exception as exc:
        if isinstance(exc, PilotRejected):
            detail = str(exc)
        else:
            logger.error(
                "Bulk protocol publication failed: type=%s sqlstate=%s",
                type(exc).__name__, getattr(exc, "sqlstate", None),
            )
            detail = "Не удалось опубликовать протоколы и пересчитать рейтинг."
        connection.execute(
            "UPDATE bulk_batch SET publication_status='failed',publication_error=%s WHERE id=%s",
            (detail, job_id),
        )
        raise BulkPublicationFailed(detail) from exc
