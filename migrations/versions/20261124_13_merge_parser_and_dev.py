"""Join the deployed wave-two schema with the dev migration chain."""

from alembic import op

revision = "20261124_13"
down_revision = ("20261121_09", "20261123_12")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE competition SET sport = sport_type
        WHERE status = 'done' AND (sport IS NULL OR sport = 'run')
          AND sport_type IN ('ski', 'trail', 'triathlon');
        UPDATE race SET sport = sport_type
        WHERE sport IS NULL AND sport_type IN ('run', 'ski', 'trail', 'triathlon');
    """)


def downgrade() -> None:
    pass
