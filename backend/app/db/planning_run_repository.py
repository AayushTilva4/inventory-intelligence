import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, Optional
from contextlib import contextmanager

from sqlalchemy import Engine, text, bindparam
from sqlalchemy.exc import IntegrityError


from app.db.connection import get_poc_engine

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_LIMIT = 30


@contextmanager
def _using_engine(engine: Engine | None = None) -> Iterator[Engine]:
    owns_engine = engine is None
    active_engine = engine or get_poc_engine()
    try:
        yield active_engine
    finally:
        if owns_engine:
            active_engine.dispose()


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    random_suffix = uuid.uuid4().hex[:8]
    return f"run_{timestamp}_{random_suffix}"


def get_active_running_run(engine: Engine | None = None) -> dict[str, Any] | None:
    query = text("""
        SELECT * FROM planning_runs
        WHERE status = 'running'
        ORDER BY started_at DESC
        LIMIT 1
    """)
    with _using_engine(engine) as active_engine:
        with active_engine.connect() as connection:
            row = connection.execute(query).mappings().first()
            return dict(row) if row else None


def mark_stale_running_runs_failed(
    stale_seconds: int = 3600,
    engine: Engine | None = None,
) -> int:
    """Marks any planning runs stuck in 'running' status longer than stale_seconds as 'failed'."""
    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            if active_engine.dialect.name == "postgresql":
                query = text("""
                    UPDATE planning_runs
                    SET status = 'failed',
                        completed_at = CURRENT_TIMESTAMP,
                        error_message = 'Interrupted: run timed out or process terminated unexpectedly',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'running'
                      AND started_at < (CURRENT_TIMESTAMP - (INTERVAL '1 second' * :stale_seconds))
                """)
            else:
                query = text("""
                    UPDATE planning_runs
                    SET status = 'failed',
                        completed_at = CURRENT_TIMESTAMP,
                        error_message = 'Interrupted: run timed out or process terminated unexpectedly',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'running'
                      AND started_at < datetime('now', '-' || :stale_seconds || ' seconds')
                """)
            result = connection.execute(query, {"stale_seconds": stale_seconds})
            return result.rowcount


def create_planning_run(
    run_id: Optional[str] = None,
    config_metadata: Optional[dict[str, Any]] = None,
    stale_seconds: int = 3600,
    engine: Engine | None = None,
) -> str:
    actual_run_id = run_id or generate_run_id()
    metadata_json = json.dumps(config_metadata or {})

    # Clear any stale interrupted runs
    mark_stale_running_runs_failed(stale_seconds=stale_seconds, engine=engine)

    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            # Check for existing running job to prevent concurrent corruption
            lock_clause = " FOR UPDATE NOWAIT" if active_engine.dialect.name == "postgresql" else ""
            existing_running = connection.execute(
                text(f"SELECT run_id FROM planning_runs WHERE status = 'running'{lock_clause}")
            ).scalars().first()



            if existing_running:
                raise RuntimeError(
                    f"Cannot start planning run '{actual_run_id}': "
                    f"Active planning run '{existing_running}' is currently in progress."
                )

            if active_engine.dialect.name == "postgresql":
                query = text("""
                    INSERT INTO planning_runs (
                        run_id, started_at, status, config_metadata, execution_summary
                    ) VALUES (
                        :run_id, CURRENT_TIMESTAMP, 'running', CAST(:config_metadata AS JSONB), '{}'::jsonb
                    )
                """)
            else:
                query = text("""
                    INSERT INTO planning_runs (
                        run_id, started_at, status, config_metadata, execution_summary
                    ) VALUES (
                        :run_id, CURRENT_TIMESTAMP, 'running', :config_metadata, '{}'
                    )
                """)
            try:
                connection.execute(
                    query,
                    {"run_id": actual_run_id, "config_metadata": metadata_json},
                )
            except IntegrityError as exc:
                err_text = str(exc).lower()
                if "uq_single_running_planning_run" in err_text or "status" in err_text:
                    raise RuntimeError(
                        f"Cannot start planning run '{actual_run_id}': "
                        "Active planning run is currently in progress."
                    ) from exc
                raise


    logger.info("Started planning run %s", actual_run_id)
    return actual_run_id


def complete_planning_run(
    run_id: str,
    num_groups: int,
    num_products: int,
    execution_summary: Optional[dict[str, Any]] = None,
    engine: Engine | None = None,
) -> None:
    summary_json = json.dumps(execution_summary or {})
    with _using_engine(engine) as active_engine:
        if active_engine.dialect.name == "postgresql":
            query = text("""
                UPDATE planning_runs
                SET status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    num_groups = :num_groups,
                    num_products = :num_products,
                    execution_summary = CAST(:execution_summary AS JSONB),
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
            """)
        else:
            query = text("""
                UPDATE planning_runs
                SET status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    num_groups = :num_groups,
                    num_products = :num_products,
                    execution_summary = :execution_summary,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
            """)

        with active_engine.begin() as connection:
            result = connection.execute(
                query,
                {
                    "run_id": run_id,
                    "num_groups": num_groups,
                    "num_products": num_products,
                    "execution_summary": summary_json,
                },
            )
            if result.rowcount == 0:
                raise ValueError(f"Planning run '{run_id}' not found")

    logger.info("Completed planning run %s (groups=%d, products=%d)", run_id, num_groups, num_products)


def fail_planning_run(
    run_id: str,
    error_message: str,
    execution_summary: Optional[dict[str, Any]] = None,
    engine: Engine | None = None,
) -> None:
    summary_json = json.dumps(execution_summary or {})
    safe_error = (error_message or "Unknown error")[:1000]
    with _using_engine(engine) as active_engine:
        if active_engine.dialect.name == "postgresql":
            query = text("""
                UPDATE planning_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = :error_message,
                    execution_summary = CAST(:execution_summary AS JSONB),
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
            """)
        else:
            query = text("""
                UPDATE planning_runs
                SET status = 'failed',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = :error_message,
                    execution_summary = :execution_summary,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = :run_id
            """)

        with active_engine.begin() as connection:
            result = connection.execute(
                query,
                {
                    "run_id": run_id,
                    "error_message": safe_error,
                    "execution_summary": summary_json,
                },
            )
            if result.rowcount == 0:
                raise ValueError(f"Planning run '{run_id}' not found")

    logger.warning("Failed planning run %s: %s", run_id, safe_error)



def get_planning_run(
    run_id: str,
    engine: Engine | None = None,
) -> dict[str, Any] | None:
    query = text("SELECT * FROM planning_runs WHERE run_id = :run_id")
    with _using_engine(engine) as active_engine:
        with active_engine.connect() as connection:
            row = connection.execute(query, {"run_id": run_id}).mappings().first()
            if not row:
                return None
            result = dict(row)
            result["is_pruned"] = bool(result.get("is_pruned"))
            return result


def list_planning_runs(
    status: Optional[str] = None,
    limit: int = 50,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    if status:
        query = text("""
            SELECT * FROM planning_runs
            WHERE status = :status
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        params = {"status": status, "limit": limit}
    else:
        query = text("""
            SELECT * FROM planning_runs
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        params = {"limit": limit}

    with _using_engine(engine) as active_engine:
        with active_engine.connect() as connection:
            rows = connection.execute(query, params).mappings().all()
            return [dict(row) for row in rows]


def get_latest_completed_run_id(engine: Engine | None = None) -> str | None:
    query = text("""
        SELECT run_id FROM planning_runs
        WHERE status = 'completed'
        ORDER BY completed_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """)
    with _using_engine(engine) as active_engine:
        with active_engine.connect() as connection:
            return connection.execute(query).scalars().first()


def apply_retention_policy(
    retention_limit: int = DEFAULT_RETENTION_LIMIT,
    engine: Engine | None = None,
) -> int:
    """
    Retain the latest `retention_limit` completed runs.
    Older completed runs are transactionally pruned (details removed, metadata marked is_pruned=True).
    Currently running runs and the latest completed run are never pruned.
    """
    if retention_limit < 1:
        retention_limit = 1

    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            # Get all completed run_ids sorted newest first
            completed_runs = connection.execute(text("""
                SELECT run_id FROM planning_runs
                WHERE status = 'completed'
                ORDER BY completed_at DESC NULLS LAST, created_at DESC
            """)).scalars().all()

            if len(completed_runs) <= retention_limit:
                return 0

            # Prune runs beyond retention limit
            runs_to_prune = completed_runs[retention_limit:]
            if not runs_to_prune:
                return 0

            # Prune detail rows from primary group tables
            connection.execute(
                text("DELETE FROM group_forecast_results WHERE run_id IN :run_ids").bindparams(
                    bindparam("run_ids", expanding=True)
                ),
                {"run_ids": list(runs_to_prune)},
            )
            connection.execute(
                text("DELETE FROM group_inventory_recommendations WHERE run_id IN :run_ids").bindparams(
                    bindparam("run_ids", expanding=True)
                ),
                {"run_ids": list(runs_to_prune)},
            )

            # Check if optional single-product tables exist and prune
            if active_engine.dialect.name == "postgresql":
                has_forecast = connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'forecast_results')")
                ).scalar()
            else:
                has_forecast = connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='forecast_results')")
                ).scalar()

            if has_forecast:
                connection.execute(
                    text("DELETE FROM forecast_results WHERE run_id IN :run_ids").bindparams(
                        bindparam("run_ids", expanding=True)
                    ),
                    {"run_ids": list(runs_to_prune)},
                )

            if active_engine.dialect.name == "postgresql":
                has_recommendations = connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'inventory_recommendations')")
                ).scalar()
            else:
                has_recommendations = connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_recommendations')")
                ).scalar()

            if has_recommendations:
                connection.execute(
                    text("DELETE FROM inventory_recommendations WHERE run_id IN :run_ids").bindparams(
                        bindparam("run_ids", expanding=True)
                    ),
                    {"run_ids": list(runs_to_prune)},
                )

            # Update metadata in planning_runs
            connection.execute(
                text("""
                    UPDATE planning_runs
                    SET is_pruned = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE run_id IN :run_ids
                """).bindparams(bindparam("run_ids", expanding=True)),
                {"run_ids": list(runs_to_prune)},
            )


            logger.info("Pruned %d historical planning runs (kept latest %d completed)", len(runs_to_prune), retention_limit)
            return len(runs_to_prune)
