"""The publication boundary for a collected draft."""
from datetime import date

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.modules.bulk_collection import approval
from app.pipeline.collection_repository import save_event
from app.pipeline.errors import PilotRejected


def _event(code, seconds, *, date_begin="2020-06-14"):
    return {
        "competition": {
            "external_id": code, "title": "Летний тестовый забег", "date_begin": date_begin,
            "place": "Екатеринбург", "sport": "run", "url": f"https://example.com/{code}",
        },
        "races": [{
            "race": {
                "external_id": "5k", "name_raw": "5 км", "distance_km": 5,
                "sport": "run", "race_type": "individual", "is_final": True,
                "place_by": "gun", "total_count": 1,
            },
            "rows": [{
                "external_participant_id": "runner", "full_name_raw": "Елена Ветрова",
                "gender": "F", "status": "FIN", "place_abs": 1, "gun_time_s": seconds,
            }],
        }],
    }


def _source(connection, name):
    return connection.execute(
        "INSERT INTO source(name,base_url,platform) VALUES (%s,'https://example.com',%s) RETURNING id",
        (name, name),
    ).fetchone()[0]


def _draft(connection, source_id, payload):
    batch = connection.execute("INSERT INTO bulk_batch DEFAULT VALUES RETURNING id").fetchone()[0]
    connection.execute(
        "INSERT INTO bulk_source(batch_id,source_id,status,is_automatic) VALUES (%s,%s,'completed',false)",
        (batch, source_id),
    )
    draft = connection.execute(
        """INSERT INTO bulk_draft(batch_id,source_id,event_code,status,payload)
           VALUES (%s,%s,%s,'ready',%s) RETURNING id""",
        (batch, source_id, payload["competition"]["external_id"], Jsonb(payload)),
    ).fetchone()[0]
    return batch, draft


def _command(preview, draft_id):
    [event] = preview["events"]
    [race] = [race for race in event["races"] if race["warning"]]
    assert race["warning"]
    [candidate] = [protocol for protocol in race["protocols"] if protocol["published"]]
    assert candidate["participants"] == 1
    [protocol] = [protocol for protocol in race["protocols"] if protocol["draft_id"] == draft_id]
    return [draft_id], [{"race_key": race["key"], "protocol_key": protocol["key"]}], preview["preview_revision"]


def test_replace_published_protocol_after_refreshing_stale_preview(migrated_url):
    with psycopg.connect(migrated_url) as connection:
        old_source = _source(connection, "existing-timing")
        new_source = _source(connection, "competing-timing")
        save_event(connection, old_source, _event("old", 1200))
        payload = _event("new", 1250)
        [another_race] = _event("new", 1500)["races"]
        another_race["race"].update(external_id="10k", name_raw="10 км", distance_km=10)
        payload["races"].append(another_race)
        batch, draft_id = _draft(connection, new_source, payload)
        initial = approval.preview_job(connection, batch)
        partial = approval.approve_job(connection, batch, [draft_id], [], initial["preview_revision"])
        assert partial["published_races"] == 1
        assert partial["pending_draft_ids"] == [draft_id]
        old_command = _command(approval.preview_job(connection, batch), draft_id)

    with psycopg.connect(migrated_url) as connection:
        connection.execute("UPDATE result SET gun_time_s=1210 WHERE gun_time_s=1200")
    with psycopg.connect(migrated_url) as connection:
        with pytest.raises(approval.BulkConflict):
            approval.approve_job(connection, batch, *old_command)
        assert connection.execute("SELECT count(*) FROM web_result").fetchone() == (2,)

    with psycopg.connect(migrated_url) as connection:
        command = _command(approval.preview_job(connection, batch), draft_id)
        result = approval.approve_job(connection, batch, *command)
        assert result["approved_draft_ids"] == [draft_id]
        assert result["rating_version_id"] is None
        assert connection.execute("SELECT gun_time_s FROM web_result ORDER BY gun_time_s").fetchall() == [(1250.0,), (1500.0,)]
        assert connection.execute("SELECT count(*) FROM web_race").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM web_event").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM result").fetchone() == (3,)
        assert connection.execute("SELECT count(*) FROM pilot_run").fetchone() == (0,)


def test_older_draft_cannot_replace_a_later_resolved_race(migrated_url):
    with psycopg.connect(migrated_url) as connection:
        source = _source(connection, "same-timing")
        old_batch, old_draft = _draft(connection, source, _event("same", 1300))
        new_batch, new_draft = _draft(connection, source, _event("same", 1200))
        connection.execute(
            "UPDATE bulk_draft SET event_code='catalog-slug' WHERE id=ANY(%s)",
            ([old_draft, new_draft],),
        )
        new_preview = approval.preview_job(connection, new_batch)
        approval.approve_job(connection, new_batch, [new_draft], [], new_preview["preview_revision"])

        old_preview = approval.preview_job(connection, old_batch)
        with pytest.raises(approval.BulkConflict, match="более нового черновика"):
            approval.approve_job(
                connection, old_batch, [old_draft], [], old_preview["preview_revision"],
            )

        assert connection.execute("SELECT gun_time_s FROM web_result").fetchall() == [(1200.0,)]


def test_transitive_race_group_does_not_supersede_independent_race(migrated_url):
    with psycopg.connect(migrated_url) as connection:
        published_source = _source(connection, "published-5080")
        published = _event("published", 1300)
        published["races"][0]["race"].update(distance_km=5.08, name_raw="5,08 км")
        save_event(connection, published_source, published)
        published_race_id = connection.execute("SELECT id FROM race").fetchone()[0]

        first_source = _source(connection, "draft-5000")
        second_source = _source(connection, "draft-5040")
        batch = connection.execute("INSERT INTO bulk_batch DEFAULT VALUES RETURNING id").fetchone()[0]
        draft_ids = []
        for source_id, code, distance in (
            (first_source, "first", 5.0), (second_source, "second", 5.04),
        ):
            payload = _event(code, 1200)
            payload["races"][0]["race"].update(distance_km=distance, name_raw=f"{distance} км")
            connection.execute(
                "INSERT INTO bulk_source(batch_id,source_id,status,is_automatic) "
                "VALUES (%s,%s,'completed',false)",
                (batch, source_id),
            )
            draft_ids.append(connection.execute(
                """INSERT INTO bulk_draft(batch_id,source_id,event_code,status,payload)
                   VALUES (%s,%s,%s,'ready',%s) RETURNING id""",
                (batch, source_id, code, Jsonb(payload)),
            ).fetchone()[0])

        preview = approval.preview_job(connection, batch)
        [race] = preview["events"][0]["races"]
        winner = next(protocol for protocol in race["protocols"] if protocol["draft_id"] == draft_ids[0])
        result = approval.approve_job(
            connection, batch, draft_ids,
            [{"race_key": race["key"], "protocol_key": winner["key"]}],
            preview["preview_revision"],
        )

        assert result["approved_draft_ids"] == draft_ids
        assert connection.execute(
            "SELECT superseded_by_race_id FROM race WHERE id=%s", (published_race_id,),
        ).fetchone() == (None,)
        assert connection.execute("SELECT count(*) FROM web_race").fetchone() == (2,)


def test_failed_rating_rolls_back_approval_and_persists_error(migrated_url, monkeypatch):
    def reject_rating(*args, **kwargs):
        raise PilotRejected("Тестовая ошибка рейтинга")

    monkeypatch.setattr(approval, "publish_rating", reject_rating)
    today = date.today().isoformat()
    with psycopg.connect(migrated_url) as connection:
        old_source = _source(connection, "published-timing")
        new_source = _source(connection, "draft-timing")
        save_event(connection, old_source, _event("old", 1200, date_begin=today))
        batch, draft_id = _draft(connection, new_source, _event("new", 1250, date_begin=today))
        command = _command(approval.preview_job(connection, batch), draft_id)
        with pytest.raises(approval.BulkPublicationFailed, match="Тестовая ошибка рейтинга"):
            approval.approve_job(connection, batch, *command)

    with psycopg.connect(migrated_url) as connection:
        assert connection.execute("SELECT gun_time_s FROM web_result").fetchall() == [(1200.0,)]
        assert connection.execute("SELECT count(*) FROM competition").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM pilot_run").fetchone() == (0,)
        preview = approval.preview_job(connection, batch)
        assert preview["publication_status"] == "failed"
        assert preview["publication_error"] == "Тестовая ошибка рейтинга"
        assert preview["drafts"][0]["status"] == "ready"


def test_trail_approval_scores_only_the_affected_sport(migrated_url):
    with psycopg.connect(migrated_url) as connection:
        source = _source(connection, "trail-timing")
        event = _event("trail", 1200, date_begin=date.today().isoformat())
        event["competition"]["sport"] = "trail"
        [race] = event["races"]
        race["race"].update(sport="trail", elevation_gain_m=400)
        race["rows"][0].update(club_raw="Сбер", birth_year=1991)
        batch, draft_id = _draft(connection, source, event)
        preview = approval.preview_job(connection, batch)

        result = approval.approve_job(connection, batch, [draft_id], [], preview["preview_revision"])
        assert result["rating_version_id"] is None
        assert result["approved_draft_ids"] == [draft_id]
        assert connection.execute(
            "SELECT sport, formula_version, points FROM rating_entry",
        ).fetchall() == [("trail", "trail-v1", 90.0)]
        assert connection.execute("SELECT count(*) FROM pilot_run").fetchone() == (0,)
