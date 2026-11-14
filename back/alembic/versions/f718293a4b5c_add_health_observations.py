from alembic import op
import sqlalchemy as sa

revision = "f718293a4b5c"
down_revision = "e6f718293a4b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "health_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("astronaut_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("missions.id"), nullable=True),
        sa.Column("indicator", sa.String(), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("systolic", sa.Float()),
        sa.Column("diastolic", sa.Float()),
        sa.Column("category", sa.String()),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("sleep_started_at", sa.DateTime(timezone=True)),
        sa.Column("sleep_ended_at", sa.DateTime(timezone=True)),
        sa.Column("is_preflight_reference", sa.Boolean(), nullable=False),
        sa.CheckConstraint("indicator IN ('heart_rate','blood_pressure','respiratory_rate','oxygen_saturation','body_temperature','consciousness','sleep_duration','sleep_quality','fatigue','mood','attention')", name='ck_health_indicator'),
        sa.CheckConstraint("source IN ('self_report','manual_measurement','device')", name='ck_health_source'),
        sa.CheckConstraint("(indicator = 'blood_pressure' AND systolic IS NOT NULL AND diastolic IS NOT NULL AND value IS NULL AND category IS NULL AND systolic > diastolic AND diastolic > 0) OR (indicator IN ('consciousness','attention') AND category IS NOT NULL AND value IS NULL AND systolic IS NULL AND diastolic IS NULL) OR (indicator NOT IN ('blood_pressure','consciousness','attention') AND value IS NOT NULL AND category IS NULL AND systolic IS NULL AND diastolic IS NULL)", name='ck_health_value_shape'),
        sa.CheckConstraint("indicator != 'consciousness' OR category IN ('alert','voice','pain','unresponsive')", name='ck_health_avpu'),
        sa.CheckConstraint("indicator != 'attention' OR category IN ('better','usual','worse')", name='ck_health_attention'),
        sa.CheckConstraint("indicator != 'consciousness' OR recorded_by_user_id != astronaut_id", name='ck_health_avpu_assessor'),
        sa.CheckConstraint('value IS NULL OR value >= 0', name='ck_health_nonnegative'),
        sa.CheckConstraint("indicator != 'oxygen_saturation' OR value <= 100", name='ck_health_oxygen'),
        sa.CheckConstraint("indicator NOT IN ('sleep_quality','mood') OR (value BETWEEN 1 AND 5 AND value = floor(value))", name='ck_health_rating'),
        sa.CheckConstraint("indicator != 'fatigue' OR (value BETWEEN 0 AND 10 AND value = floor(value))", name='ck_health_fatigue'),
        sa.CheckConstraint("indicator != 'sleep_duration' OR value = floor(value)", name='ck_health_sleep_minutes'),
        sa.CheckConstraint("(sleep_started_at IS NULL AND sleep_ended_at IS NULL) OR (indicator = 'sleep_duration' AND sleep_started_at IS NOT NULL AND sleep_ended_at IS NOT NULL AND sleep_ended_at > sleep_started_at AND sleep_ended_at <= collected_at)", name='ck_health_sleep_session'),
        sa.CheckConstraint('NOT is_preflight_reference OR mission_id IS NOT NULL', name='ck_health_reference_mission'),
    )
    op.create_index("ix_health_observations_astronaut_id", "health_observations", ["astronaut_id"])
    op.create_index("ix_health_observations_mission_id", "health_observations", ["mission_id"])
    op.create_index("ix_health_astronaut_indicator_collected", "health_observations", ["astronaut_id", "indicator", "collected_at", "id"])


def downgrade():
    op.drop_index("ix_health_astronaut_indicator_collected", table_name="health_observations")
    op.drop_index("ix_health_observations_mission_id", table_name="health_observations")
    op.drop_index("ix_health_observations_astronaut_id", table_name="health_observations")
    op.drop_table("health_observations")
