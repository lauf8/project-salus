from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, JSON, Text
from sqlmodel import Field, SQLModel


def utc_now():
    return datetime.now(timezone.utc)


class HealthOccurrence(SQLModel, table=True):
    __tablename__ = 'health_occurrences'
    __table_args__ = (
        CheckConstraint("status IN ('active','recovered')", name='ck_health_occurrence_status'),
        CheckConstraint("(status = 'active' AND finish_at IS NULL AND resolved_by_user_id IS NULL) OR (status = 'recovered' AND finish_at >= start_at AND resolved_by_user_id IS NOT NULL AND resolution_note IS NOT NULL)", name='ck_health_occurrence_resolution'),
    )

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: int = Field(foreign_key='users.id', index=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    icd_code: str | None = None
    condition_name: str
    description: str = Field(sa_type=Text)
    symptoms: str = Field(sa_type=Text)
    start_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    finish_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    status: str = 'active'
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    resolved_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    resolution_note: str | None = Field(default=None, sa_type=Text)
    resolved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class MedicationUse(SQLModel, table=True):
    __tablename__ = 'medication_uses'

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: int = Field(foreign_key='users.id', index=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    medicine_id: int = Field(foreign_key='medicines.id')
    medicine_name: str
    taken_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    reason: str = Field(sa_type=Text)
    instructed_by: str
    dose: str
    occurrence_id: int | None = Field(default=None, foreign_key='health_occurrences.id')
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class ClinicalAssessment(SQLModel, table=True):
    __tablename__ = 'clinical_assessments'
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected')", name='ck_clinical_assessment_status'),)

    id: int | None = Field(default=None, primary_key=True)
    astronaut_id: int = Field(foreign_key='users.id', index=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    report: dict = Field(sa_column=Column(JSON, nullable=False))
    status: str = 'pending'
    created_by_user_id: int = Field(foreign_key='users.id')
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    reviewed_by_user_id: int | None = Field(default=None, foreign_key='users.id')
    reviewed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    review_note: str | None = Field(default=None, sa_type=Text)
