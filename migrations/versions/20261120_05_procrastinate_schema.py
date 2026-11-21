from pathlib import Path

from alembic import op

revision = "20261120_05"
down_revision = "20261119_04"
branch_labels = None
depends_on = None


def _execute_script(sql_text):
    # asyncpg prepares each execute call and requires a single SQL statement.
    # A DO block keeps the DDL script and its dollar-quoted function bodies
    # intact while using the same connection and transaction as Alembic.
    op.get_bind().exec_driver_sql(
        f"DO $procrastinate_migration$ BEGIN\n{sql_text}\n"
        "END; $procrastinate_migration$;"
    )


def upgrade():
    sql_text = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    _execute_script(sql_text)


def downgrade():
    _execute_script("""
        DROP FUNCTION IF EXISTS procrastinate_defer_periodic_job_v3;
        DROP FUNCTION IF EXISTS procrastinate_defer_jobs_v2;
        DROP FUNCTION IF EXISTS procrastinate_fetch_job_v2;
        DROP FUNCTION IF EXISTS procrastinate_finish_job_v1;
        DROP FUNCTION IF EXISTS procrastinate_cancel_job_v1;
        DROP FUNCTION IF EXISTS procrastinate_retry_job_v1;
        DROP FUNCTION IF EXISTS procrastinate_retry_job_v2;
        DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE;
        DROP TABLE IF EXISTS procrastinate_events CASCADE;
        DROP TABLE IF EXISTS procrastinate_jobs CASCADE;
        DROP TABLE IF EXISTS procrastinate_workers CASCADE;
        DROP FUNCTION IF EXISTS procrastinate_notify_queue_job_inserted_v1;
        DROP FUNCTION IF EXISTS procrastinate_notify_queue_abort_job_v1;
        DROP FUNCTION IF EXISTS procrastinate_trigger_function_status_events_insert_v1;
        DROP FUNCTION IF EXISTS procrastinate_trigger_function_status_events_update_v1;
        DROP FUNCTION IF EXISTS procrastinate_trigger_function_scheduled_events_v1;
        DROP FUNCTION IF EXISTS procrastinate_trigger_abort_requested_events_procedure_v1;
        DROP FUNCTION IF EXISTS procrastinate_unlink_periodic_defers_v1;
        DROP FUNCTION IF EXISTS procrastinate_register_worker_v1;
        DROP FUNCTION IF EXISTS procrastinate_unregister_worker_v1;
        DROP FUNCTION IF EXISTS procrastinate_update_heartbeat_v1;
        DROP FUNCTION IF EXISTS procrastinate_prune_stalled_workers_v1;
        DROP TYPE IF EXISTS procrastinate_job_to_defer_v2;
        DROP TYPE IF EXISTS procrastinate_lock_mode;
        DROP TYPE IF EXISTS procrastinate_job_event_type;
        DROP TYPE IF EXISTS procrastinate_job_status;
    """)
