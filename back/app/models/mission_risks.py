from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index, JSON, Text, text
from sqlmodel import Field, SQLModel

from app.models.preflight import utc_now


class MissionRiskPlan(SQLModel, table=True):
    __tablename__ = 'mission_risk_plans'

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    planned_end_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    crew_size: int
    exposure_start_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    consumption_window_days: int = 7
    coverage_start: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    coverage_end: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    inventory_complete: bool = False
    consumption_complete: bool = False
    daily_rates: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    approved_actions: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    author_user_id: int = Field(foreign_key='users.id')


class MissionOccurrence(SQLModel, table=True):
    __tablename__ = 'mission_occurrences'

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    category: str = Field(index=True)
    food_product_id: int | None = Field(default=None, foreign_key='food_products.id')
    phase: str
    event_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    confirmed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    confirmed_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    author_user_id: int = Field(foreign_key='users.id')
    severity: str
    source_references: list[dict] = Field(sa_column=Column(JSON, nullable=False))
    description: str = Field(sa_type=Text)
    actions: str = Field(sa_type=Text)
    outcome: str = Field(sa_type=Text)
    intervention: bool = False


class MissionRiskEvaluation(SQLModel, table=True):
    __tablename__ = 'mission_risk_evaluations'

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    rule_version: str
    evaluated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    horizon: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    state: str
    results: dict = Field(sa_column=Column(JSON, nullable=False))


class MissionRiskAlert(SQLModel, table=True):
    __tablename__ = 'mission_risk_alerts'
    __table_args__ = (
        Index('uq_mission_risk_active', 'mission_id', 'risk_type', 'food_product_id', unique=True,
              postgresql_where=text("status != 'resolved'"), sqlite_where=text("status != 'resolved'")),
        CheckConstraint("status IN ('open', 'acknowledged', 'executed', 'resolved')", name='ck_mission_risk_status'),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    risk_type: str = 'food_shortage'
    food_product_id: int = Field(foreign_key='food_products.id')
    evaluation_id: int = Field(foreign_key='mission_risk_evaluations.id')
    severity: str
    due_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    status: str = 'open'
    responsible_user_id: int | None = Field(default=None, foreign_key='users.id')
    guidance: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    read_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    executed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    outcome: str | None = Field(default=None, sa_type=Text)


class MissionRiskAction(SQLModel, table=True):
    __tablename__ = 'mission_risk_actions'

    id: int | None = Field(default=None, primary_key=True)
    alert_id: int = Field(foreign_key='mission_risk_alerts.id', index=True)
    actor_user_id: int = Field(foreign_key='users.id')
    action: str
    details: str = Field(sa_type=Text)
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
