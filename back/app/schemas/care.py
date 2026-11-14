from datetime import date

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.preflight import InputModel


class NutritionPlanInput(InputModel):
    valid_from: date
    valid_until: date | None = None
    dietary_guidance: str = Field(min_length=1, max_length=20000)
    energy_target_kcal: float | None = Field(default=None, gt=0, le=20000, allow_inf_nan=False)
    hydration_target_ml: float | None = Field(default=None, gt=0, le=30000, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("The plan end cannot precede its start")
        return self


class NursingRecordInput(InputModel):
    observed_at: AwareDatetime
    observations: str = Field(min_length=1, max_length=20000)
    care_provided: str = Field(min_length=1, max_length=20000)
    sample_collection: str | None = Field(default=None, max_length=20000)
