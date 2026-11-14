from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Index, JSON, Text, text
from sqlmodel import Field, SQLModel


class HealthAlertSettings(SQLModel, table=True):
    __tablename__ = 'health_alert_settings'

    mission_id: int = Field(foreign_key='missions.id', primary_key=True)
    revision: int = 1
    profile_id: str = 'simulation-v2'
    timezone: str = 'UTC'
    emergency_channel: str | None = None
    oxygen_thresholds: dict | None = Field(default=None, sa_column=Column(JSON))
    high_glucose_thresholds: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    approval_note: str | None = Field(default=None, sa_type=Text)
    approved_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))


class HealthAlert(SQLModel, table=True):
    __tablename__ = 'health_alerts'
    __table_args__ = (
        CheckConstraint("severity IN ('attention','urgent','critical')", name='ck_health_alert_severity'),
        CheckConstraint("status IN ('open','acknowledged','resolved')", name='ck_health_alert_status'),
        Index('uq_health_alert_active_rule', 'astronaut_id', 'rule_id', unique=True, postgresql_where=text("status IN ('open','acknowledged')"), sqlite_where=text("status IN ('open','acknowledged')")),
    )

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: int = Field(foreign_key='users.id', index=True)
    mission_id: int | None = Field(default=None, foreign_key='missions.id')
    rule_id: str
    rule_version: str
    profile_snapshot: dict = Field(sa_column=Column(JSON, nullable=False))
    indicator: str
    severity: str
    status: str = 'open'
    reason: str = Field(sa_type=Text)
    verification_required: bool = False
    trigger_observation_id: int = Field(foreign_key='health_observations.id')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    acknowledged_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    acknowledged_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    resolved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    resolved_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    resolution_note: str | None = Field(default=None, sa_type=Text)


class HealthAlertObservation(SQLModel, table=True):
    __tablename__ = 'health_alert_observations'

    alert_id: int = Field(foreign_key='health_alerts.id', primary_key=True)
    observation_id: int = Field(foreign_key='health_observations.id', primary_key=True)


class HealthAlertEvent(SQLModel, table=True):
    __tablename__ = 'health_alert_events'

    id: int | None = Field(default=None, primary_key=True)
    alert_id: int = Field(foreign_key='health_alerts.id', index=True)
    observation_id: int | None = Field(default=None, foreign_key='health_observations.id')
    actor_user_id: int = Field(foreign_key='users.id')
    action: str
    severity: str
    status: str
    reason: str = Field(sa_type=Text)
    rule_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
