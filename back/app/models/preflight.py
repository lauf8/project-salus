from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, JSON, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Mission(SQLModel, table=True):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint("crew_size IS NULL OR crew_size > 0", name="ck_missions_crew_size"),
        CheckConstraint("status IN ('planned', 'in_progress', 'completed')", name="ck_missions_status"),
        Index("uq_missions_open_spacecraft", "spacecraft_id", unique=True, postgresql_where=text("status != 'completed' AND spacecraft_id IS NOT NULL"), sqlite_where=text("status != 'completed' AND spacecraft_id IS NOT NULL")),
        CheckConstraint("ended_at IS NULL OR (started_at IS NOT NULL AND ended_at >= started_at)", name="ck_missions_dates"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str
    crew_size: int | None = None
    spacecraft_id: int | None = Field(default=None, foreign_key="spacecraft.id", index=True)
    status: str = Field(default="planned")
    planned_launch_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    ended_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class MissionMember(SQLModel, table=True):
    __tablename__ = "mission_members"
    __table_args__ = (
        UniqueConstraint("mission_id", "user_id", name="uq_mission_members_mission_user"),
        UniqueConstraint("id", "mission_id", name="uq_mission_members_id_mission"),
        CheckConstraint("role IN ('astronaut', 'flight_surgeon', 'mission_admin', 'psychologist')", name="ck_mission_members_role"),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    role: str


class ExamType(SQLModel, table=True):
    __tablename__ = "exam_types"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True)
    name: str
    description: str | None = Field(default=None, sa_type=Text)
    is_active: bool = True


class ExamDefinition(SQLModel, table=True):
    __tablename__ = "exam_definitions"
    __table_args__ = (UniqueConstraint("id", "exam_type_id", name="uq_exam_definition_id_type"),)

    id: int | None = Field(default=None, primary_key=True)
    exam_type_id: int = Field(foreign_key="exam_types.id", index=True)
    code: str = Field(unique=True)
    name: str = Field(index=True)
    description: str | None = Field(default=None, sa_type=Text)
    specimen: str | None = None
    preparation: str | None = Field(default=None, sa_type=Text)
    applicability_notes: str | None = Field(default=None, sa_type=Text)
    source_url: str | None = None
    source_section: str | None = None
    source_page: int | None = None
    fields: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    revision: int = 1
    is_active: bool = True


class MissionExamRequirement(SQLModel, table=True):
    __tablename__ = "mission_exam_requirements"
    __table_args__ = (
        Index("uq_requirements_legacy_type", "mission_id", "exam_type_id", unique=True, postgresql_where=text("exam_definition_id IS NULL"), sqlite_where=text("exam_definition_id IS NULL")),
        UniqueConstraint("mission_id", "exam_definition_id", name="uq_requirements_mission_definition"),
        ForeignKeyConstraint(["exam_definition_id", "exam_type_id"], ["exam_definitions.id", "exam_definitions.exam_type_id"], name="fk_requirement_definition_type"),
        UniqueConstraint("id", "mission_id", name="uq_requirements_id_mission"),
        CheckConstraint("due_days_before_launch >= 0", name="ck_requirements_due_days"),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    exam_type_id: int = Field(foreign_key="exam_types.id", index=True)
    exam_definition_id: int | None = Field(default=None, index=True)
    is_required: bool = True
    due_days_before_launch: int


class AstronautExam(SQLModel, table=True):
    __tablename__ = "astronaut_exams"
    __table_args__ = (
        UniqueConstraint("mission_member_id", "requirement_id", name="uq_astronaut_exams_member_requirement"),
        ForeignKeyConstraint(
            ["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"],
            name="fk_astronaut_exams_member_mission",
        ),
        ForeignKeyConstraint(
            ["requirement_id", "mission_id"], ["mission_exam_requirements.id", "mission_exam_requirements.mission_id"],
            name="fk_astronaut_exams_requirement_mission",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    mission_member_id: int = Field(index=True)
    requirement_id: int = Field(index=True)
    scheduled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    due_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    definition_snapshot: dict | None = Field(default=None, sa_column=Column(JSON))


class ExamResult(SQLModel, table=True):
    __tablename__ = "exam_results"

    id: int | None = Field(default=None, primary_key=True)
    astronaut_exam_id: int = Field(foreign_key="astronaut_exams.id", index=True)
    performed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    recorded_by_user_id: int = Field(foreign_key="users.id", index=True)
    summary: str = Field(sa_type=Text)
    structured_values: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    reference_ranges: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    exam_snapshot: dict | None = Field(default=None, sa_column=Column(JSON))
    laboratory: str | None = None
    performer_name: str | None = None
    sample_identifier: str | None = None
    method: str | None = None
    report_reference: str | None = None
    collected_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class ExamResultReview(SQLModel, table=True):
    __tablename__ = "exam_result_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('accepted', 'repeat_requested')", name="ck_exam_result_reviews_decision"),
    )

    id: int | None = Field(default=None, primary_key=True)
    exam_result_id: int = Field(foreign_key="exam_results.id", index=True)
    reviewer_member_id: int = Field(foreign_key="mission_members.id", index=True)
    decision: str
    notes: str | None = Field(default=None, sa_type=Text)
    reviewed_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
