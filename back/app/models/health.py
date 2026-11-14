from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Index, JSON, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class HealthObservation(SQLModel, table=True):
    __tablename__ = "health_observations"
    __table_args__ = (
        UniqueConstraint("astronaut_id", "client_request_id", name="uq_health_observation_request"),
        UniqueConstraint("astronaut_id", "submission_hash", name="uq_health_observation_submission"),
        CheckConstraint("activity IN ('rest','exercise','unknown')", name="ck_health_activity"),
        CheckConstraint("signal_quality IN ('good','poor','unknown')", name="ck_health_signal_quality"),
        CheckConstraint("glucose_context IN ('fasting','after_meal','unknown')", name="ck_health_glucose_context"),
        CheckConstraint("symptoms_status IN ('present','absent','unknown')", name="ck_health_symptoms_status"),
        CheckConstraint("indicator IN ('heart_rate','blood_pressure','respiratory_rate','oxygen_saturation','body_temperature','consciousness','sleep_duration','sleep_quality','fatigue','mood','attention','blood_glucose')", name="ck_health_indicator"),
        CheckConstraint("source IN ('self_report','manual_measurement','device')", name="ck_health_source"),
        CheckConstraint("(indicator = 'blood_pressure' AND systolic IS NOT NULL AND diastolic IS NOT NULL AND value IS NULL AND category IS NULL AND systolic > diastolic AND diastolic > 0) OR (indicator IN ('consciousness','attention') AND category IS NOT NULL AND value IS NULL AND systolic IS NULL AND diastolic IS NULL) OR (indicator NOT IN ('blood_pressure','consciousness','attention') AND value IS NOT NULL AND category IS NULL AND systolic IS NULL AND diastolic IS NULL)", name="ck_health_value_shape"),
        CheckConstraint("indicator != 'consciousness' OR category IN ('alert','voice','pain','unresponsive')", name="ck_health_avpu"),
        CheckConstraint("indicator != 'attention' OR category IN ('better','usual','worse')", name="ck_health_attention"),
        CheckConstraint("indicator != 'consciousness' OR recorded_by_user_id != astronaut_id", name="ck_health_avpu_assessor"),
        CheckConstraint("value IS NULL OR value >= 0", name="ck_health_nonnegative"),
        CheckConstraint("indicator != 'blood_glucose' OR value > 0", name="ck_health_glucose_positive"),
        CheckConstraint("indicator != 'oxygen_saturation' OR value <= 100", name="ck_health_oxygen"),
        CheckConstraint("indicator NOT IN ('sleep_quality','mood') OR (value BETWEEN 1 AND 5 AND value = floor(value))", name="ck_health_rating"),
        CheckConstraint("indicator != 'fatigue' OR (value BETWEEN 0 AND 10 AND value = floor(value))", name="ck_health_fatigue"),
        CheckConstraint("indicator != 'sleep_duration' OR value = floor(value)", name="ck_health_sleep_minutes"),
        CheckConstraint("(sleep_started_at IS NULL AND sleep_ended_at IS NULL) OR (indicator = 'sleep_duration' AND sleep_started_at IS NOT NULL AND sleep_ended_at IS NOT NULL AND sleep_ended_at > sleep_started_at AND sleep_ended_at <= collected_at)", name="ck_health_sleep_session"),
        CheckConstraint("NOT is_preflight_reference OR mission_id IS NOT NULL", name="ck_health_reference_mission"),
        Index("ix_health_astronaut_indicator_collected", "astronaut_id", "indicator", "collected_at", "id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: int = Field(foreign_key="users.id", index=True)
    mission_id: int | None = Field(default=None, foreign_key="missions.id", index=True)
    indicator: str
    value: float | None = None
    systolic: float | None = None
    diastolic: float | None = None
    category: str | None = None
    collected_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    source: str
    recorded_by_user_id: int = Field(foreign_key="users.id")
    note: str | None = Field(default=None, sa_type=Text)
    sleep_started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    sleep_ended_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    is_preflight_reference: bool = False

    unit: str | None = None
    original_values: dict | None = Field(default=None, sa_column=Column(JSON))
    activity: str = 'unknown'
    supplemental_oxygen: bool | None = None
    signal_quality: str = 'unknown'
    glucose_context: str = 'unknown'
    symptoms_status: str = 'unknown'
    symptoms: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    acute_confusion: bool | None = None
    client_request_id: str | None = None
    submission_hash: str | None = None
    evaluation_status: str = 'not_evaluated'
    evaluation_notes: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    evaluation_profile: dict | None = Field(default=None, sa_column=Column(JSON))
