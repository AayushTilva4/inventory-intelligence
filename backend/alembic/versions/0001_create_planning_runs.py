"""create planning runs and snapshot persistence

Revision ID: 0001_planning_runs
Revises: 
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_planning_runs'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create planning_runs table
    op.execute("""
        CREATE TABLE IF NOT EXISTS planning_runs (
            run_id VARCHAR(64) PRIMARY KEY,
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE NULL,
            status VARCHAR(20) NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            error_message TEXT NULL,
            num_groups INT NOT NULL DEFAULT 0,
            num_products INT NOT NULL DEFAULT 0,
            config_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            execution_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_pruned BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)



    # 2. Seed legacy initial run record for existing historical rows
    op.execute("""
        INSERT INTO planning_runs (
            run_id, started_at, completed_at, status, config_metadata, execution_summary
        ) VALUES (
            'legacy_initial_run',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            'completed',
            '{"source": "alembic_0001_migration"}'::jsonb,
            '{"note": "Initial baseline run for pre-existing records"}'::jsonb
        ) ON CONFLICT (run_id) DO NOTHING;
    """)

    # 3. Add run_id to group_forecast_results & adjust constraints
    op.execute("""
        ALTER TABLE group_forecast_results
        ADD COLUMN IF NOT EXISTS run_id VARCHAR(64) NOT NULL DEFAULT 'legacy_initial_run';
    """)
    op.execute("""
        ALTER TABLE group_forecast_results
        DROP CONSTRAINT IF EXISTS group_forecast_results_main_product_template_id_key;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_forecast_run_template
        ON group_forecast_results (run_id, main_product_template_id);
    """)

    # 4. Add run_id to group_inventory_recommendations & adjust constraints
    op.execute("""
        ALTER TABLE group_inventory_recommendations
        ADD COLUMN IF NOT EXISTS run_id VARCHAR(64) NOT NULL DEFAULT 'legacy_initial_run';
    """)
    op.execute("""
        ALTER TABLE group_inventory_recommendations
        DROP CONSTRAINT IF EXISTS group_inventory_recommendations_main_product_template_id_key;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_recommendations_run_template
        ON group_inventory_recommendations (run_id, main_product_template_id);
    """)

    # 5. Add run_id to forecast_results & inventory_recommendations if tables exist
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'forecast_results') THEN
                ALTER TABLE forecast_results ADD COLUMN IF NOT EXISTS run_id VARCHAR(64) NOT NULL DEFAULT 'legacy_initial_run';
                CREATE INDEX IF NOT EXISTS idx_forecast_results_run_product ON forecast_results(run_id, product_id);
            END IF;

            IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'inventory_recommendations') THEN
                ALTER TABLE inventory_recommendations ADD COLUMN IF NOT EXISTS run_id VARCHAR(64) NOT NULL DEFAULT 'legacy_initial_run';
                CREATE INDEX IF NOT EXISTS idx_inventory_recommendations_run_product ON inventory_recommendations(run_id, product_id);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    conn = op.get_bind()
    # Refuse downgrade if multi-run snapshot data exists to prevent silent data destruction
    has_multi_runs = conn.execute(sa.text("""
        SELECT (
            EXISTS (
                SELECT 1
                FROM group_forecast_results
                GROUP BY main_product_template_id
                HAVING COUNT(DISTINCT run_id) > 1
            ) OR EXISTS (
                SELECT 1
                FROM planning_runs
                HAVING COUNT(DISTINCT run_id) > 1
            )
        )
    """)).scalar()

    if has_multi_runs:
        raise RuntimeError(
            "Downgrade Refused: Historical snapshot data exists across multiple planning runs. "
            "Reverting to single-run schema would delete historical snapshots. "
            "To force a downgrade, back up application data via pg_dump, export historical runs, "
            "or manually prune historical run rows prior to executing downgrade."
        )

    op.execute("""
        DROP INDEX IF EXISTS uq_single_running_planning_run;
        DROP INDEX IF EXISTS idx_inventory_recommendations_run_product;
        DROP INDEX IF EXISTS idx_forecast_results_run_product;
        DROP INDEX IF EXISTS uq_group_recommendations_run_template;
        DROP INDEX IF EXISTS uq_group_forecast_run_template;
    """)
    op.execute("""
        ALTER TABLE group_forecast_results
        ADD CONSTRAINT group_forecast_results_main_product_template_id_key UNIQUE (main_product_template_id);
    """)
    op.execute("""
        ALTER TABLE group_inventory_recommendations
        ADD CONSTRAINT group_inventory_recommendations_main_product_template_id_key UNIQUE (main_product_template_id);
    """)
    op.execute("ALTER TABLE group_forecast_results DROP COLUMN IF EXISTS run_id;")
    op.execute("ALTER TABLE group_inventory_recommendations DROP COLUMN IF EXISTS run_id;")
    op.execute("DROP TABLE IF EXISTS planning_runs CASCADE;")


