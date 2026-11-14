from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.preflight import InputModel


Rating = Annotated[int, Field(strict=True, ge=1, le=5)]


class CheckInInput(InputModel):
    happiness_level: Rating
    satisfaction_level: Rating
    stress_level: Rating | None = None
    energy_level: Rating | None = None
    sleep_quality: Rating | None = None
    workload_level: Rating | None = None
    isolation_level: Rating | None = None
    crew_connection_level: Rating | None = None
    notes: str | None = Field(default=None, max_length=20000)


class FollowUpInput(InputModel):
    session_at: AwareDatetime
    review_period_start: date
    review_period_end: date
    session_summary: str = Field(min_length=1, max_length=20000)
    agreed_actions: str | None = Field(default=None, max_length=20000)
    next_follow_up_on: date | None = None
    private_notes: str | None = Field(default=None, max_length=20000)
    share_agreed_actions: bool = False
    share_next_follow_up: bool = False
    contact_request_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_period(self):
        if self.review_period_start > self.review_period_end:
            raise ValueError("Review period start must not follow its end")
        return self
