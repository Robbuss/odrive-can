"""Initial Timescale setup: runs, run_events, joint_samples + policies + CAGG"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, BIGINT

# revision identifiers, used by Alembic.
revision = "20250820_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # runs
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("config_snapshot", JSONB, nullable=True),
    )

    # run_events (optional but requested)
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("joint_id", sa.String(32), nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=True),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])

    # joint_samples (raw telemetry)
    op.create_table(
        "joint_samples",
        # identity/serial column (NOT a primary key by itself)
        sa.Column("id", sa.BigInteger, sa.Identity(always=False), nullable=False),

        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("joint_id", sa.String(32), nullable=False),

        # kinematics
        sa.Column("position", sa.Float, nullable=False),
        sa.Column("velocity", sa.Float, nullable=True),
        sa.Column("accel", sa.Float, nullable=True),

        # actuation
        sa.Column("torque", sa.Float, nullable=True),
        sa.Column("supply_v", sa.Float, nullable=True),
        sa.Column("motor_temp", sa.Float, nullable=True),
        sa.Column("controller_temp", sa.Float, nullable=True),

        # controller state
        sa.Column("mode", sa.Text, nullable=True),
        sa.Column("fault_code", sa.Integer, nullable=True),
        sa.Column("error_flags", BIGINT, nullable=True),

        # targets
        sa.Column("target_position", sa.Float, nullable=True),
        sa.Column("target_velocity", sa.Float, nullable=True),
        sa.Column("target_accel", sa.Float, nullable=True),
        sa.Column("target_torque", sa.Float, nullable=True),

        # run-link
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("runs.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # ✅ composite primary key includes the time column
        sa.PrimaryKeyConstraint("ts", "joint_id", "id", name="pk_joint_samples"),
    )

    # simple helper indexes
    op.create_index("ix_joint_samples_joint_id", "joint_samples", ["joint_id"])
    op.create_index("ix_joint_samples_ts", "joint_samples", ["ts"])

    # Convert to hypertable (idempotent)
    op.execute(
        "SELECT create_hypertable('joint_samples', 'ts', if_not_exists => TRUE)"
    )

    # Composite index for common query pattern (joint_id, ts DESC) — idempotent
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'ix_joint_samples_joint_ts_desc'
                  AND n.nspname = 'public'
            ) THEN
                CREATE INDEX ix_joint_samples_joint_ts_desc
                    ON joint_samples (joint_id, ts DESC);
            END IF;
        END$$;
        """
    )

    # Enable compression + segmentby
    op.execute(
        """
        ALTER TABLE joint_samples
        SET (
          timescaledb.compress = TRUE,
          timescaledb.compress_segmentby = 'joint_id,run_id'
        )
        """
    )

    # Continuous aggregate (create view)
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS joint_samples_1s
        WITH (timescaledb.continuous) AS
        SELECT
          time_bucket('1 second', ts) AS bucket,
          joint_id,
          run_id,
          AVG(position) AS avg_position,
          MIN(position) AS min_position,
          MAX(position) AS max_position,
          AVG(velocity) AS avg_velocity,
          AVG(torque)   AS avg_torque,
          AVG(supply_v) AS avg_supply_v
        FROM joint_samples
        GROUP BY bucket, joint_id, run_id
        WITH NO DATA;
        """
    )

    # Compression policy (7d), idempotent
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_compression'
              AND hypertable_schema = 'public'
              AND hypertable_name = 'joint_samples'
          ) THEN
            PERFORM add_compression_policy('joint_samples', INTERVAL '7 days');
          END IF;
        END$$;
        """
    )

    # Retention policy (30d), idempotent
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_retention'
              AND hypertable_schema = 'public'
              AND hypertable_name = 'joint_samples'
          ) THEN
            PERFORM add_retention_policy('joint_samples', INTERVAL '30 days');
          END IF;
        END$$;
        """
    )

    # Continuous aggregate refresh policy, idempotent
    op.execute(
        """
        DO $$
        DECLARE
          mat_schema TEXT;
          mat_name   TEXT;
        BEGIN
          SELECT materialization_hypertable_schema, materialization_hypertable_name
            INTO mat_schema, mat_name
          FROM timescaledb_information.continuous_aggregates
          WHERE view_schema='public' AND view_name='joint_samples_1s';

          IF mat_schema IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_refresh_continuous_aggregate'
              AND hypertable_schema = mat_schema
              AND hypertable_name   = mat_name
          ) THEN
            PERFORM add_continuous_aggregate_policy(
              'joint_samples_1s',
              start_offset => INTERVAL '1 hour',
              end_offset   => INTERVAL '1 minute',
              schedule_interval => INTERVAL '1 minute'
            );
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # Remove CAGG refresh policy if present
    op.execute(
        """
        DO $$
        DECLARE
          job_id INTEGER;
        BEGIN
          SELECT j.job_id INTO job_id
          FROM timescaledb_information.jobs j
          JOIN timescaledb_information.continuous_aggregates c
            ON j.hypertable_schema = c.materialization_hypertable_schema
           AND j.hypertable_name   = c.materialization_hypertable_name
          WHERE j.proc_name = 'policy_refresh_continuous_aggregate'
            AND c.view_schema='public' AND c.view_name='joint_samples_1s';

          IF job_id IS NOT NULL THEN
            PERFORM remove_continuous_aggregate_policy('joint_samples_1s');
          END IF;
        END$$;
        """
    )

    # Drop the CAGG view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS joint_samples_1s")

    # Remove compression policy if present
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM timescaledb_information.jobs
            WHERE proc_name='policy_compression'
              AND hypertable_schema='public'
              AND hypertable_name='joint_samples'
          ) THEN
            PERFORM remove_compression_policy('joint_samples');
          END IF;
        END$$;
        """
    )

    # Remove retention policy if present
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM timescaledb_information.jobs
            WHERE proc_name='policy_retention'
              AND hypertable_schema='public'
              AND hypertable_name='joint_samples'
          ) THEN
            PERFORM remove_retention_policy('joint_samples');
          END IF;
        END$$;
        """
    )

    # Drop indexes (idempotent)
    op.execute("DROP INDEX IF EXISTS ix_joint_samples_joint_ts_desc")
    op.execute("DROP INDEX IF EXISTS ix_joint_samples_joint_id")
    op.execute("DROP INDEX IF EXISTS ix_joint_samples_ts")
    op.execute("DROP INDEX IF EXISTS ix_run_events_run_id")

    # Drop tables (children first)
    op.drop_table("joint_samples")
    op.drop_table("run_events")
    op.drop_table("runs")