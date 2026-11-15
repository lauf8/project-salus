from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.preflight import InputModel, OutputModel


class OccurrenceCreate(InputModel):
    mission_id: int = Field(gt=0)
    icd_code: str | None = Field(default=None, max_length=12)
    condition_name: str = Field(min_length=1, max_length=2000)
    description: str = Field(min_length=1, max_length=6000)
    symptoms: str = Field(min_length=1, max_length=4000)
    start_at: AwareDatetime

    @model_validator(mode='after')
    def validate_time(self):
        if self.start_at > datetime.now(timezone.utc):
            raise ValueError('Start cannot be in the future')
        return self


class OccurrenceResolve(InputModel):
    finish_at: AwareDatetime
    resolution_note: str = Field(min_length=1, max_length=6000)

    @model_validator(mode='after')
    def validate_time(self):
        if self.finish_at > datetime.now(timezone.utc):
            raise ValueError('Recovery cannot be in the future')
        return self


class OccurrenceResponse(OutputModel):
    id: int
    astronaut_id: int
    mission_id: int
    icd_code: str | None
    condition_name: str
    description: str
    symptoms: str
    start_at: datetime
    finish_at: datetime | None
    status: str
    recorded_by_user_id: int
    recorded_at: datetime
    resolved_by_user_id: int | None
    resolved_at: datetime | None
    resolution_note: str | None


class MedicationUseCreate(InputModel):
    mission_id: int = Field(gt=0)
    medicine_id: int = Field(gt=0)
    taken_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=4000)
    instructed_by: str = Field(min_length=1, max_length=250)
    dose: str = Field(min_length=1, max_length=250)
    occurrence_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def validate_time(self):
        if self.taken_at > datetime.now(timezone.utc):
            raise ValueError('Consumption cannot be in the future')
        return self


class MedicationUseResponse(OutputModel):
    id: int
    astronaut_id: int
    mission_id: int
    medicine_id: int
    medicine_name: str
    taken_at: datetime
    reason: str
    instructed_by: str
    dose: str
    occurrence_id: int | None
    recorded_by_user_id: int
    recorded_at: datetime


class AssessmentCreate(InputModel):
    mission_id: int = Field(gt=0)


class AssessmentReview(InputModel):
    decision: Literal['approved', 'rejected']
    note: str = Field(min_length=1, max_length=6000)


class AssessmentResponse(OutputModel):
    id: int
    astronaut_id: int
    mission_id: int
    report: dict
    status: str
    created_by_user_id: int
    created_at: datetime
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    review_note: str | None


class ClinicalHypothesis(InputModel):
    condition: str = Field(min_length=1, max_length=250)
    reasoning: str = Field(min_length=1, max_length=2000)
    observation_ids: list[int] = Field(min_length=1, max_length=30)
    citation_ids: list[int] = Field(min_length=1, max_length=10)


class ClinicalGeneration(InputModel):
    hypotheses: list[ClinicalHypothesis] = Field(max_length=6)
