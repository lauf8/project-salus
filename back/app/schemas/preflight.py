from datetime import datetime
from typing import ClassVar, Generic, Literal, Self, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.users import PaginationMeta


Role = Literal["astronaut", "flight_surgeon", "mission_admin", "psychologist"]
Decision = Literal["accepted", "repeat_requested"]
ExamState = Literal["pending", "scheduled", "awaiting_review", "repeat_requested", "completed"]
T = TypeVar("T")


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatchInput(InputModel):
    non_null_fields: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def reject_null_fields(self) -> Self:
        for name in self.model_fields_set & self.non_null_fields:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    data: list[T]
    pagination: PaginationMeta


class MissionCreate(InputModel):
    crew_size: int | None = Field(default=None, gt=0, le=2147483647)
    astronaut_ids: list[int] = Field(default_factory=list, max_length=1000)
    spacecraft_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=200)
    planned_launch_at: AwareDatetime
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if len(self.astronaut_ids) != len(set(self.astronaut_ids)) or any(value <= 0 for value in self.astronaut_ids):
            raise ValueError("Astronaut IDs must be positive and unique")
        if self.ended_at and (not self.started_at or self.ended_at < self.started_at):
            raise ValueError("Mission end requires a start and cannot precede it")
        return self


class MissionPatch(PatchInput):
    crew_size: int | None = Field(default=None, gt=0, le=2147483647)
    non_null_fields = {"name", "planned_launch_at", "status"}
    spacecraft_id: int | None = Field(default=None, gt=0)
    status: Literal["planned", "in_progress", "completed"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    planned_launch_at: AwareDatetime | None = None
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None


class MissionResponse(OutputModel):
    crew_size: int | None
    spacecraft_id: int | None
    status: Literal["planned", "in_progress", "completed"]
    id: int
    name: str
    planned_launch_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class MemberCreate(InputModel):
    user_id: int = Field(gt=0)
    role: Role


class MemberPatch(InputModel):
    role: Role


class MemberResponse(OutputModel):
    id: int
    mission_id: int
    user_id: int
    role: Role


class ExamTypeCreate(InputModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool = True


class ExamTypePatch(PatchInput):
    non_null_fields = {"code", "name", "is_active"}
    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


class ExamTypeResponse(OutputModel):
    id: int
    code: str
    name: str
    description: str | None
    is_active: bool


class RequirementCreate(InputModel):
    exam_type_id: int = Field(gt=0)
    exam_definition_id: int | None = Field(default=None, gt=0)
    is_required: bool = True
    due_days_before_launch: int = Field(ge=0, le=2147483647)


class RequirementPatch(PatchInput):
    non_null_fields = {"exam_type_id", "is_required", "due_days_before_launch"}
    exam_type_id: int | None = Field(default=None, gt=0)
    exam_definition_id: int | None = Field(default=None, gt=0)
    is_required: bool | None = None
    due_days_before_launch: int | None = Field(default=None, ge=0, le=2147483647)


class RequirementResponse(OutputModel):
    exam_definition_id: int | None = None
    id: int
    mission_id: int
    exam_type_id: int
    is_required: bool
    due_days_before_launch: int


class SchedulePatch(InputModel):
    scheduled_at: AwareDatetime | None


class ChecklistResponse(OutputModel):
    exam_definition_id: int | None = None
    exam_name: str | None = None
    definition_snapshot: dict | None = None
    id: int
    mission_id: int
    mission_member_id: int
    requirement_id: int
    exam_type_id: int
    is_required: bool
    scheduled_at: datetime | None
    due_at: datetime
    state: ExamState
    is_overdue: bool


class ResultCreate(InputModel):
    structured_values: dict[str, object] = Field(default_factory=dict, max_length=100)
    reference_ranges: dict[str, str] = Field(default_factory=dict, max_length=100)
    laboratory: str | None = Field(default=None, max_length=200)
    performer_name: str | None = Field(default=None, max_length=200)
    sample_identifier: str | None = Field(default=None, max_length=200)
    method: str | None = Field(default=None, max_length=500)
    report_reference: str | None = Field(default=None, max_length=500)
    collected_at: AwareDatetime | None = None
    performed_at: AwareDatetime
    summary: str = Field(min_length=1, max_length=20000)


class ResultPatch(PatchInput):
    non_null_fields = {"performed_at", "summary", "structured_values", "reference_ranges"}
    structured_values: dict[str, object] | None = Field(default=None, max_length=100)
    reference_ranges: dict[str, str] | None = Field(default=None, max_length=100)
    laboratory: str | None = Field(default=None, max_length=200)
    performer_name: str | None = Field(default=None, max_length=200)
    sample_identifier: str | None = Field(default=None, max_length=200)
    method: str | None = Field(default=None, max_length=500)
    report_reference: str | None = Field(default=None, max_length=500)
    collected_at: AwareDatetime | None = None
    performed_at: AwareDatetime | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=20000)


class ResultResponse(OutputModel):
    structured_values: dict = Field(default_factory=dict)
    reference_ranges: dict = Field(default_factory=dict)
    exam_snapshot: dict | None = None
    laboratory: str | None = None
    performer_name: str | None = None
    sample_identifier: str | None = None
    method: str | None = None
    report_reference: str | None = None
    collected_at: datetime | None = None
    id: int
    astronaut_exam_id: int
    performed_at: datetime
    recorded_at: datetime
    recorded_by_user_id: int
    summary: str


class ReviewCreate(InputModel):
    decision: Decision
    notes: str | None = Field(default=None, max_length=20000)


class ReviewResponse(OutputModel):
    id: int
    exam_result_id: int
    reviewer_member_id: int
    decision: Decision
    notes: str | None
    reviewed_at: datetime


class AcceptedExamResponse(BaseModel):
    latest_accepted_result: ResultResponse | None
    latest_result: ResultResponse | None
    latest_review: ReviewResponse | None
    latest_result_state: ExamState
    newer_result_requires_review: bool
