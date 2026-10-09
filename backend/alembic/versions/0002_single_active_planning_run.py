"""add single active planning run partial unique index

Revision ID: 0002_single_active_run
Revises: 0001_planning_runs
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_single_active_run'
down_revision = '0001_planning_runs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safe, idempotent creation of partial unique index
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_single_running_planning_run
        ON planning_runs (status)
        WHERE status = 'running';
    """)


def downgrade() -> None:
    # Drop partial unique index cleanly
    op.execute("DROP INDEX IF EXISTS uq_single_running_planning_run;")
