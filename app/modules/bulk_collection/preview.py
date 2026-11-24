"""Find protocol alternatives and build a read-only approval preview."""
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from itertools import combinations

from psycopg.rows import dict_row

from app.pipeline.collection_repository import norm_name
from app.pipeline.duplicates import AGGREGATORS
from parser_running.normalize import km_to_m


@dataclass
class Event:
    key: str
    source_id: int
    source: str
    priority: int
    external_id: str
    title: str
    date: date | None
    city: str | None
    url: str | None
    canonical_url: str | None
    draft_id: int | None = None
    competition_id: int | None = None
    planned: bool = False
    planned_end: date | None = None
    races: list = field(default_factory=list)

    @property
    def identity(self):
        return self.source_id, self.external_id


@dataclass
class Protocol:
    event: Event
    external_id: str
    label: str
    distance_m: int | None
    sport: str
    relay: bool
    participants: int
    url: str | None
    final: bool | None
    item: dict | None = None
    race_id: int | None = None
    results: list = field(default_factory=list)

    @property
    def key(self):
        return f"{self.event.key}:{self.external_id}"

    def preview(self):
        event = self.event
        return {
            "key": self.key, "draft_id": event.draft_id, "source": event.source,
            "title": event.title, "date": event.date.isoformat() if event.date else None,
            "city": event.city, "url": self.url or event.url, "race_name": self.label,
            "distance_m": self.distance_m, "sport": self.sport, "relay": self.relay,
            "participants": self.participants, "is_final": self.final,
            "published": event.competition_id is not None, "planned": event.planned,
        }


@dataclass
class RaceGroup:
    protocols: list[Protocol]
    preferred: Protocol | None
    warning: str | None
    replaced_versions: list[Protocol] = field(default_factory=list)

    @property
    def drafts(self):
        return [protocol for protocol in self.protocols if protocol.event.draft_id is not None]

    @property
    def key(self):
        return min(protocol.key for protocol in self.drafts)

    def preview(self):
        race = self.preferred or self.drafts[0]
        return {
            "key": self.key, "label": race.label, "distance_m": race.distance_m,
            "sport": race.sport, "relay": race.relay, "participants": race.participants,
            "warning": self.warning, "preferred_protocol_key": self.preferred.key if self.preferred else None,
            "protocols": [protocol.preview() for protocol in self.protocols],
        }


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _trigrams(value):
    return {
        word[index:index + 3]
        for token in re.findall(r"[^\W_]+", (value or "").casefold().replace("ё", "е"))
        for word in [f"  {token} "]
        for index in range(len(word) - 2)
    }


def _similar_title(left, right):
    left_trigrams, right_trigrams = _trigrams(left), _trigrams(right)
    union = left_trigrams | right_trigrams
    return bool(union) and len(left_trigrams & right_trigrams) / len(union) >= 0.85


def _city(value):
    return tuple(word for word in norm_name(value).split() if word not in {"г", "город"})


def _event_match(left, right):
    if left.identity == right.identity:
        return True
    if left.date is None or right.date is None or (left.planned and right.planned):
        return False
    if left.planned or right.planned:
        planned, actual = (left, right) if left.planned else (right, left)
        in_window = planned.date <= actual.date <= (planned.planned_end or planned.date)
        if not in_window:
            return False
    elif abs((left.date - right.date).days) > 1:
        return False
    left_city, right_city = _city(left.city), _city(right.city)
    return (not left_city or not right_city or left_city == right_city) and _similar_title(left.title, right.title)


def _race_match(left, right):
    if left.event is right.event:
        return False
    if left.event.identity == right.event.identity:
        return left.external_id == right.external_id
    if left.sport != right.sport or left.relay != right.relay:
        return False
    if left.distance_m and right.distance_m:
        return abs(left.distance_m - right.distance_m) <= 0.01 * max(left.distance_m, right.distance_m)
    return False


def _finishes(rows):
    finishes = defaultdict(list)
    for row in rows:
        if row["status"] != "FIN" or row.get("is_anonymized"):
            continue
        name = norm_name(row.get("full_name_raw"))
        timing = next(
            (row[key] for key in ("chip_time_s", "gun_time_s", "official_time_s") if row.get(key) is not None),
            None,
        )
        if name and timing is not None:
            finishes[name].append(timing)
    return finishes


def _matched_count(left, right):
    left_finishes, right_finishes = _finishes(left.results), _finishes(right.results)
    matched = 0
    for name in left_finishes.keys() & right_finishes.keys():
        left_times, right_times = sorted(left_finishes[name]), sorted(right_finishes[name])
        i = j = 0
        while i < len(left_times) and j < len(right_times):
            difference = left_times[i] - right_times[j]
            if abs(difference) <= 1:
                matched += 1
                i += 1
                j += 1
            elif difference < 0:
                i += 1
            else:
                j += 1
    return matched


def _groups(items, edges):
    neighbors = defaultdict(list)
    for left, right in edges:
        neighbors[left].append(right)
        neighbors[right].append(left)
    visited = set()
    for first in items:
        if first in visited:
            continue
        stack, group = [first], []
        visited.add(first)
        while stack:
            current = stack.pop()
            group.append(items[current])
            for neighbor in neighbors[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        yield group


def _drafts(cursor, batch_id):
    rows = cursor.execute(
        """SELECT d.id, d.source_id, s.name AS source, COALESCE(s.priority, 1) AS priority,
                  d.event_code, d.status, d.error, d.payload, d.summary, d.resolved_races,
                  COALESCE(d.payload_hash, md5(d.payload::text)) AS payload_hash
           FROM bulk_draft d JOIN source s ON s.id=d.source_id
           WHERE d.batch_id=%s ORDER BY d.id""",
        (batch_id,),
    ).fetchall()
    events = {}
    for draft in rows:
        if draft["payload"] is None:
            continue
        comp = draft["payload"]["competition"]
        event = Event(
            f"draft:{draft['id']}", draft["source_id"], draft["source"], draft["priority"],
            str(comp["external_id"]), comp["title"], date.fromisoformat(comp["date_begin"][:10]),
            comp.get("place"), comp.get("url"), comp.get("canonical_url"), draft_id=draft["id"],
        )
        for item in draft["payload"]["races"]:
            race = item["race"]
            external_id = str(race["external_id"])
            if external_id not in draft["resolved_races"] and draft["status"] == "ready":
                event.races.append(Protocol(
                    event, external_id, race.get("name_raw") or "Дистанция",
                    km_to_m(race.get("distance_km")), race["sport"],
                    race.get("race_type") == "relay", len(item["rows"]), race.get("url"),
                    race.get("is_final"), item=item, results=item["rows"],
                ))
        events[draft["id"]] = event
    return rows, events


def _published(cursor, drafts):
    dates = sorted({event.date for event in drafts.values()})
    source_ids = list({event.source_id for event in drafts.values()})
    external_ids = list({event.external_id for event in drafts.values()})
    rows = cursor.execute(
        """SELECT c.id, c.source_id, s.name AS source, COALESCE(s.priority, 1) AS priority,
                  c.external_id, c.name, CASE WHEN c.status='planned'
                      THEN COALESCE(c.planned_date_start, c.date_begin) ELSE c.date_begin END AS date,
                  c.location, c.source_url, c.primary_protocol_url, c.status,
                  COALESCE(c.planned_date_end, c.date_end) AS planned_end, c.xmin::text AS revision,
                  COALESCE(c.sport_type, c.sport, 'run') AS sport
           FROM competition c JOIN source s ON s.id=c.source_id
           WHERE (c.source_id=ANY(%s) AND c.external_id=ANY(%s))
              OR (c.status='done' AND EXISTS (
                    SELECT 1 FROM unnest(%s::date[]) d WHERE c.date_begin BETWEEN d - 1 AND d + 1))
              OR (c.status='planned' AND EXISTS (
                    SELECT 1 FROM unnest(%s::date[]) d
                    WHERE d BETWEEN COALESCE(c.planned_date_start,c.date_begin)
                                AND COALESCE(c.planned_date_end,c.date_end,c.date_begin)))
           ORDER BY c.id""",
        (source_ids, external_ids, dates, dates),
    ).fetchall()
    published, revisions, sports = {}, [], {}
    for row in rows:
        event = Event(
            f"published:{row['id']}", row["source_id"], row["source"], row["priority"],
            row["external_id"], row["name"] or "Соревнование", row["date"], row["location"],
            row["source_url"], row["primary_protocol_url"], competition_id=row["id"],
            planned=row["status"] == "planned", planned_end=row["planned_end"],
        )
        if any(_event_match(event, draft) for draft in drafts.values()):
            published[row["id"]] = event
            revisions.append((event.key, row["revision"], row["priority"]))
            sports[row["id"]] = row["sport"]
    rows = cursor.execute(
        """SELECT ra.id, ra.competition_id, ra.external_id, ra.name, ra.distance_m,
                  COALESCE(ra.sport_type,ra.sport) AS sport, ra.race_type, ra.source_url,
                  ra.is_final_protocol, ra.xmin::text AS revision,
                  COUNT(r.id) AS participants,
                  md5(string_agg(r.id::text || ':' || r.xmin::text, ',' ORDER BY r.id)) AS result_revision
           FROM race ra LEFT JOIN result r ON r.race_id=ra.id
           WHERE ra.competition_id=ANY(%s) AND ra.superseded_by_race_id IS NULL
           GROUP BY ra.id ORDER BY ra.id""",
        (list(published),),
    ).fetchall()
    races = {}
    for row in rows:
        event = published[row["competition_id"]]
        protocol = Protocol(
            event, row["external_id"], row["name"] or "Дистанция", row["distance_m"],
            row["sport"] or sports[event.competition_id], row["race_type"] == "relay",
            row["participants"], row["source_url"], row["is_final_protocol"], race_id=row["id"],
        )
        event.races.append(protocol)
        races[row["id"]] = protocol
        revisions.append((protocol.key, row["revision"], row["result_revision"]))
    for row in cursor.execute(
        """SELECT race_id, status, full_name_raw, chip_time_s, gun_time_s, official_time_s
           FROM result WHERE race_id=ANY(%s) AND is_anonymized IS NOT TRUE AND duplicate_of IS NULL
             AND status='FIN'""",
        (list(races),),
    ).fetchall():
        races[row["race_id"]].results.append(row)
    for event in published.values():
        if event.planned and not event.races:
            event.races.append(Protocol(event, "planned", "Запланированный старт", None,
                                        sports[event.competition_id], False, 0, None, None))
    return published, revisions


def _links_to(other, protocol):
    url = (other.event.canonical_url or "").rstrip("/")
    return bool(url and url in {(protocol.event.url or "").rstrip("/"), (protocol.url or "").rstrip("/")})


def _preference(protocol, protocols):
    explicit_primary = any(_links_to(other, protocol) for other in protocols if other is not protocol)
    return (
        protocol.final is not True, not explicit_primary, protocol.event.source in AGGREGATORS,
        protocol.event.priority, -protocol.participants, protocol.event.draft_id is None, protocol.key,
    )


def _race_groups(events, event_edges):
    protocols = {
        protocol.key: protocol for event in events for protocol in event.races
        if event.draft_id is not None or protocol.participants or event.planned
    }
    draft_races = [protocol for protocol in protocols.values() if protocol.event.draft_id is not None]
    pairs = []
    for a, b in combinations(protocols.values(), 2):
        if frozenset((a.event.key, b.event.key)) not in event_edges:
            continue
        if a.event.planned or b.event.planned:
            continue
        if _race_match(a, b):
            pairs.append((a.key, b.key))
    same_identity_published = {
        b.key: b for a in draft_races for b in protocols.values()
        if b.event.competition_id is not None and not b.event.planned
        and a.event.identity == b.event.identity and a.external_id == b.external_id
    }
    # A published copy of the same source protocol is the previous version of an update.
    for key in same_identity_published:
        protocols.pop(key)
    pairs = [(a, b) for a, b in pairs if a in protocols and b in protocols]

    groups = []
    for group in _groups(protocols, pairs):
        drafts = [p for p in group if p.event.draft_id is not None]
        if not drafts:
            continue
        planned = [
            protocol for event in events for protocol in event.races
            if event.planned and any(
                frozenset((event.key, pending.event.key)) in event_edges
                and event.races[0].sport == pending.sport for pending in drafts
            )
        ]
        # A planned event may have several advertised distances. Its matching race
        # is shown when available, with a single event-level alternative otherwise.
        planned_by_event = {}
        for protocol in planned:
            previous = planned_by_event.get(protocol.event.key)
            if previous is None or any(_race_match(protocol, pending) for pending in drafts):
                planned_by_event[protocol.event.key] = protocol
        alternatives = group + list(planned_by_event.values())
        warning = None
        if planned_by_event:
            warning = "Возможный дубль: запланированный старт требует ручного подтверждения."
        elif len({protocol.event.key for protocol in group}) < len(group):
            warning = "Возможный дубль: несколько близких дистанций одной площадки."
        else:
            for a, b in combinations(group, 2):
                if not _race_match(a, b) or not _event_match(a.event, b.event):
                    warning = "Возможный дубль: несколько неоднозначных соответствий."
                    break
                smaller, larger = sorted((a.participants, b.participants))
                matched = _matched_count(a, b)
                explicit = _links_to(a, b) or _links_to(b, a)
                if not smaller or matched < 0.98 * smaller or (not explicit and matched < 0.95 * larger):
                    warning = (
                        "Возможный дубль: названия, даты и дистанции близки, "
                        f"но по имени и времени совпали {matched} из {smaller} строк меньшего протокола."
                    )
                    break
        preferred = None if warning else min(group, key=lambda p: _preference(p, group))
        previous_versions = [
            published for published in same_identity_published.values()
            if any(_race_match(published, draft) for draft in drafts)
        ]
        groups.append(RaceGroup(alternatives, preferred, warning, previous_versions))
    return groups


def build_preview(connection, job_id):
    with connection.cursor(row_factory=dict_row) as cursor:
        batch = cursor.execute(
            "SELECT publication_status, publication_error FROM bulk_batch WHERE id=%s", (job_id,),
        ).fetchone()
        if batch is None:
            raise KeyError(job_id)
        drafts, draft_events = _drafts(cursor, job_id)
        published, revisions = _published(cursor, draft_events)
    published_identities = {event.identity for event in published.values()}
    draft_summaries = []
    for draft in drafts:
        summary = {key: draft[key] for key in ("id", "source", "event_code", "status", "error")}
        summary.update(draft["summary"] or {})
        if event := draft_events.get(draft["id"]):
            summary.update(
                title=event.title, date=event.date.isoformat(), city=event.city,
                participants=sum(len(item["rows"]) for item in draft["payload"]["races"]),
                is_new=event.identity not in published_identities,
            )
        draft_summaries.append(summary)

    events = {event.key: event for event in draft_events.values() if event.races}
    events.update((event.key, event) for event in published.values())
    edges = [
        (a.key, b.key) for a, b in combinations(events.values(), 2)
        if (a.races or a.draft_id is not None) and (b.races or b.draft_id is not None)
        and _event_match(a, b)
    ]
    event_edges = {frozenset(pair) for pair in edges}
    groups, result_events = {}, []
    for event_group in _groups(events, edges):
        race_groups = _race_groups(event_group, event_edges)
        if not race_groups:
            continue
        groups.update((group.key, group) for group in race_groups)
        ids = sorted({p.event.draft_id for group in race_groups for p in group.drafts})
        representative = min(
            (group.preferred or group.drafts[0] for group in race_groups),
            key=lambda p: _preference(p, [q for group in race_groups for q in group.protocols]),
        ).event
        result_events.append({
            "key": race_groups[0].key, "draft_ids": ids, "title": representative.title,
            "date": representative.date.isoformat() if representative.date else None,
            "city": representative.city, "source": representative.source,
            "participants": sum((group.preferred or group.drafts[0]).participants for group in race_groups),
            "is_new": all(draft_events[key].identity not in published_identities for key in ids),
            "races": [group.preview() for group in race_groups],
        })

    preview = {
        **batch, "drafts": draft_summaries, "events": result_events,
        "preview_revision": fingerprint(([
            (draft["id"], draft["status"], draft["payload_hash"], draft["resolved_races"], draft["priority"])
            for draft in drafts
        ], revisions)),
    }
    return preview, drafts, groups
