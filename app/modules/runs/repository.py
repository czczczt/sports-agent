"""Pilot SQL; callers own connection lifetime and transaction boundaries."""

RUN_COLUMNS = "r.id,r.source_id,r.event_code,r.status,r.phase,r.processed_distances,r.error,r.rating_version_id,r.created_at,r.updated_at"


class RunRepository:
    def __init__(self, connection):
        self.connection = connection

    async def one(self, query, params=()):
        cursor = await self.connection.execute(query, params)
        return await cursor.fetchone()

    async def prepare_source(self, code, base_url, platform, parse_method, sport_types):
        await self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"pilot:{code}",)
        )
        await self.connection.execute(
            "INSERT INTO source(name,base_url,platform,parse_method,sport_types) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(name) DO NOTHING",
            (code, base_url, platform, parse_method, sport_types),
        )
        return await self.one("SELECT id,enabled FROM source WHERE name=%s", (code,))

    async def active(self, source_id):
        return await self.one("SELECT id FROM pilot_run WHERE source_id=%s AND status IN ('queued','running')", (source_id,))

    async def create(self, source_id, event_code):
        row = await self.one(
            "INSERT INTO pilot_run(source_id,event_code,status,phase) VALUES (%s,%s,'queued','queued') RETURNING id",
            (source_id, event_code),
        )
        return row['id']

    async def get(self, run_id):
        return await self.one(
            f"SELECT {RUN_COLUMNS},s.name AS source FROM pilot_run r JOIN source s ON s.id=r.source_id WHERE r.id=%s",
            (run_id,),
        )

    async def claim(self, run_id):
        row = await self.one("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS locked", (f'pilot:{run_id}',))
        return row['locked']

    async def claim_collection_source(self, source_id):
        # Shared by both collectors, including jobs recovered after a stalled heartbeat.
        await self.connection.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (f"collection-source:{source_id}",),
        )

    async def phase(self, run_id, phase):
        await self.connection.execute(
            "UPDATE pilot_run SET status='running',phase=%s,error=NULL,updated_at=now() WHERE id=%s", (phase, run_id),
        )

    async def failure(self, run_id, error, final):
        await self.connection.execute(
            "UPDATE pilot_run SET status=%s,phase=%s,error=%s,updated_at=now() WHERE id=%s",
            ('failed' if final else 'running', 'failed' if final else 'retrying', error, run_id),
        )


def complete(connection, run_id, count, version_id):
    connection.execute(
        "UPDATE pilot_run SET status='succeeded',phase='done',processed_distances=%s,"
        "rating_version_id=%s,error=NULL,updated_at=now() WHERE id=%s",
        (count, version_id, run_id),
    )
