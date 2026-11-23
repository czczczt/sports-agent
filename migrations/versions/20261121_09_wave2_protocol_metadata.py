"""Persist source-specific values independently of internal scoring."""
from alembic import op

revision = "20261121_09"
down_revision = "20261121_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE race ADD COLUMN source_distance_class text")
    op.execute("ALTER TABLE result ADD COLUMN toplist_points double precision")


def downgrade() -> None:
    op.execute("ALTER TABLE result DROP COLUMN toplist_points")
    op.execute("ALTER TABLE race DROP COLUMN source_distance_class")
