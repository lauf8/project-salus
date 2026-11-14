from datetime import date, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.models.preflight import utc_now


RATING_FIELDS = ("happiness_level", "satisfaction_level", "stress_level", "energy_level", "sleep_quality", "workload_level", "isolation_level", "crew_connection_level")


class MentalHealthCheckIn(SQLModel, table=True):
    __tablename__ = "mental_health_check_ins"
    __table_args__ = (
        UniqueConstraint("mission_member_id", "check_in_date", name="uq_mental_check_in_day"),
        ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),
        *(CheckConstraint(f"{field} BETWEEN 1 AND 5", name=f"ck_mental_{field}") for field in RATING_FIELDS),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    mission_member_id: int = Field(index=True)
    check_in_date: date
    happiness_level: int
    satisfaction_level: int
    stress_level: int | None = None
    energy_level: int | None = None
    sleep_quality: int | None = None
    workload_level: int | None = None
    isolation_level: int | None = None
    crew_connection_level: int | None = None
    notes: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_by_user_id: int = Field(foreign_key="users.id")


class PsychologyContactRequest(SQLModel, table=True):
    __tablename__ = "psychology_contact_requests"
    __table_args__ = (
        ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),
        UniqueConstraint("id", "mission_member_id", "mission_id", name="uq_psychology_request_scope"),
        CheckConstraint("status IN ('pending', 'fulfilled')", name="ck_psychology_request_status"),
        Index("uq_psychology_pending_request", "mission_member_id", unique=True, postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'")),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    mission_member_id: int
    author_user_id: int = Field(foreign_key="users.id")
    status: str = "pending"
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_by_user_id: int = Field(foreign_key="users.id")


class PsychologyFollowUp(SQLModel, table=True):
    __tablename__ = "psychology_follow_ups"
    __table_args__ = (
        ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),
        ForeignKeyConstraint(["contact_request_id", "mission_member_id", "mission_id"], ["psychology_contact_requests.id", "psychology_contact_requests.mission_member_id", "psychology_contact_requests.mission_id"]),
        CheckConstraint("review_period_start <= review_period_end", name="ck_psychology_review_period"),
        UniqueConstraint("contact_request_id", name="uq_psychology_session_request"),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    mission_member_id: int = Field(index=True)
    psychologist_user_id: int = Field(foreign_key="users.id")
    contact_request_id: int | None = None
    session_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    review_period_start: date
    review_period_end: date
    session_summary: str = Field(sa_type=Text)
    agreed_actions: str | None = Field(default=None, sa_type=Text)
    next_follow_up_on: date | None = None
    private_notes: str | None = Field(default=None, sa_type=Text)
    share_agreed_actions: bool = False
    share_next_follow_up: bool = False
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_by_user_id: int = Field(foreign_key="users.id")


class MentalHealthAuditEvent(SQLModel, table=True):
    __tablename__ = "mental_health_audit_events"

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    actor_user_id: int = Field(foreign_key="users.id")
    resource_type: str
    resource_id: int
    action: str
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
