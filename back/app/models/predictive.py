from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Index, JSON, LargeBinary, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.models.preflight import utc_now


SUBJECT_TYPES = ('astronaut', 'mission', 'spacecraft')
MODEL_KINDS = ('rule', 'anomaly', 'supervised')
MODEL_STATUSES = ('candidate', 'rejected', 'approved', 'active', 'retired')
RUN_STATUSES = ('running', 'completed', 'failed')
PREDICTION_KINDS = ('rule', 'anomaly', 'ml', 'insufficient_data')
RISK_LEVELS = ('none', 'low', 'moderate', 'high', 'undetermined')
EVENT_STATUSES = ('pending', 'accepted', 'rejected', 'executed', 'superseded')


def _in(values):
    return ', '.join(f"'{value}'" for value in values)


class PredictionModel(SQLModel, table=True):
    __tablename__ = 'prediction_models'
    __table_args__ = (
        UniqueConstraint('name', 'version', name='uq_prediction_models_name_version'),
        CheckConstraint(f'kind IN ({_in(MODEL_KINDS)})', name='ck_prediction_models_kind'),
        CheckConstraint(f'status IN ({_in(MODEL_STATUSES)})', name='ck_prediction_models_status'),
        CheckConstraint(f'subject_type IN ({_in(SUBJECT_TYPES)})', name='ck_prediction_models_subject'),
        Index('uq_prediction_models_active_name', 'name', unique=True, postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'")),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_type=Text, index=True)
    kind: str
    subject_type: str
    risk_type: str = Field(sa_type=Text)
    version: str = Field(sa_type=Text)
    predicted_outcome: str = Field(sa_type=Text)
    horizon_hours: int | None = None
    status: str = 'candidate'
    validation_metrics: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    model_metadata: dict = Field(default_factory=dict, sa_column=Column('metadata', JSON, nullable=False))
    artifact: bytes | None = Field(default=None, sa_column=Column(LargeBinary))
    artifact_sha256: str | None = None
    trained_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    activated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    approved_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class FeatureSnapshot(SQLModel, table=True):
    __tablename__ = 'feature_snapshots'
    __table_args__ = (
        UniqueConstraint('subject_type', 'subject_id', 'as_of', 'feature_set_version', 'input_fingerprint', name='uq_feature_snapshots_input'),
        CheckConstraint(f'subject_type IN ({_in(SUBJECT_TYPES)})', name='ck_feature_snapshots_subject'),
        Index('ix_feature_snapshots_subject_time', 'subject_type', 'subject_id', 'as_of'),
    )

    id: int | None = Field(default=None, primary_key=True)
    subject_type: str
    subject_id: int
    mission_id: int | None = Field(default=None, foreign_key='missions.id', index=True)
    as_of: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    feature_set_version: str
    input_fingerprint: str
    features: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    quality: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_references: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class PredictionRun(SQLModel, table=True):
    __tablename__ = 'prediction_runs'
    __table_args__ = (
        UniqueConstraint('idempotency_key', name='uq_prediction_runs_idempotency'),
        CheckConstraint(f'subject_type IN ({_in(SUBJECT_TYPES)})', name='ck_prediction_runs_subject'),
        CheckConstraint(f'status IN ({_in(RUN_STATUSES)})', name='ck_prediction_runs_status'),
        CheckConstraint("trigger IN ('manual', 'scheduled', 'new_data')", name='ck_prediction_runs_trigger'),
        Index('ix_prediction_runs_subject_time', 'subject_type', 'subject_id', 'as_of'),
    )

    id: int | None = Field(default=None, primary_key=True)
    subject_type: str
    subject_id: int
    mission_id: int | None = Field(default=None, foreign_key='missions.id', index=True)
    as_of: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    horizon_hours: int | None = None
    feature_snapshot_id: int | None = Field(default=None, foreign_key='feature_snapshots.id')
    model_versions: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    engine_version: str
    trigger: str = 'manual'
    status: str = 'running'
    idempotency_key: str
    attempts: int = 1
    error: str | None = Field(default=None, sa_type=Text)
    requested_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    started_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class RiskPrediction(SQLModel, table=True):
    __tablename__ = 'risk_predictions'
    __table_args__ = (
        CheckConstraint(f'prediction_kind IN ({_in(PREDICTION_KINDS)})', name='ck_risk_predictions_kind'),
        CheckConstraint(f'risk_level IN ({_in(RISK_LEVELS)})', name='ck_risk_predictions_level'),
        CheckConstraint('calibrated_probability IS NULL OR (calibrated_probability >= 0 AND calibrated_probability <= 1)', name='ck_risk_predictions_probability'),
        CheckConstraint("calibrated_probability IS NULL OR prediction_kind = 'ml'", name='ck_risk_predictions_probability_kind'),
        Index('ix_risk_predictions_run_type', 'run_id', 'risk_type'),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key='prediction_runs.id', index=True)
    model_id: int | None = Field(default=None, foreign_key='prediction_models.id')
    domain: str
    risk_type: str = Field(sa_type=Text)
    title: str = Field(sa_type=Text)
    prediction_kind: str
    score: float | None = None
    score_meaning: str | None = Field(default=None, sa_type=Text)
    calibrated_probability: float | None = None
    risk_level: str = 'undetermined'
    horizon_hours: int | None = None
    factors: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    data_quality: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    uncertainty: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    explanation: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RecommendationAction(SQLModel, table=True):
    __tablename__ = 'recommendation_actions'
    __table_args__ = (
        UniqueConstraint('code', 'version', name='uq_recommendation_actions_code_version'),
        CheckConstraint("approval_status IN ('draft', 'approved', 'retired')", name='ck_recommendation_actions_approval'),
        CheckConstraint("action_category IN ('clinical_review', 'monitoring', 'operational', 'psychological_support', 'nutrition_review')", name='ck_recommendation_actions_category'),
        CheckConstraint('priority BETWEEN 1 AND 5', name='ck_recommendation_actions_priority'),
    )

    id: int | None = Field(default=None, primary_key=True)
    code: str
    version: int = 1
    name: str = Field(sa_type=Text)
    description: str = Field(sa_type=Text)
    risk_types: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    action_category: str
    responsible_roles: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    eligibility: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    contraindications: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    priority: int = 3
    evidence_quality: str = 'documented_guidance'
    feasibility: float = 1.0
    source_references: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    rag_query: str | None = Field(default=None, sa_type=Text)
    approval_status: str = 'approved'
    approved_by: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RecommendationEvent(SQLModel, table=True):
    __tablename__ = 'recommendation_events'
    __table_args__ = (
        CheckConstraint(f'status IN ({_in(EVENT_STATUSES)})', name='ck_recommendation_events_status'),
        CheckConstraint(f'subject_type IN ({_in(SUBJECT_TYPES)})', name='ck_recommendation_events_subject'),
        Index('uq_recommendation_events_open', 'subject_type', 'subject_id', 'action_id', unique=True, postgresql_where=text("status IN ('pending', 'accepted')"), sqlite_where=text("status IN ('pending', 'accepted')")),
        Index('ix_recommendation_events_mission_status', 'mission_id', 'status'),
    )

    id: int | None = Field(default=None, primary_key=True)
    prediction_id: int = Field(foreign_key='risk_predictions.id', index=True)
    action_id: int = Field(foreign_key='recommendation_actions.id')
    subject_type: str
    subject_id: int
    mission_id: int | None = Field(default=None, foreign_key='missions.id')
    rationale: str = Field(sa_type=Text)
    rank_score: float
    ranking: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    priority: int
    urgency: str
    status: str = 'pending'
    decided_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    decided_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    sources: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    explanation: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RecommendationFeedback(SQLModel, table=True):
    __tablename__ = 'recommendation_feedback'
    __table_args__ = (
        CheckConstraint("decision IN ('accepted', 'rejected', 'executed')", name='ck_recommendation_feedback_decision'),
    )

    id: int | None = Field(default=None, primary_key=True)
    recommendation_id: int = Field(foreign_key='recommendation_events.id', index=True)
    user_id: int = Field(foreign_key='users.id')
    decision: str
    justification: str = Field(sa_type=Text)
    executed_action: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class RecommendationOutcome(SQLModel, table=True):
    __tablename__ = 'recommendation_outcomes'
    __table_args__ = (
        CheckConstraint("result IN ('improved', 'unchanged', 'worsened', 'inconclusive')", name='ck_recommendation_outcomes_result'),
        CheckConstraint('observation_window_hours > 0', name='ck_recommendation_outcomes_window'),
    )

    id: int | None = Field(default=None, primary_key=True)
    recommendation_id: int = Field(foreign_key='recommendation_events.id', index=True)
    indicator: str
    value_before: float | None = None
    value_after: float | None = None
    observation_window_hours: int
    result: str
    notes: str | None = Field(default=None, sa_type=Text)
    recorded_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    evaluated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
