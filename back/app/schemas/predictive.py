from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendationFeedbackInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['accepted', 'rejected', 'executed']
    justification: str = Field(min_length=3, max_length=2000)
    executed_action: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def executed_details(self):
        if self.decision == 'executed' and not (self.executed_action or '').strip():
            raise ValueError('Describe the action that was executed')
        return self


class RecommendationOutcomeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    indicator: str = Field(min_length=1, max_length=100)
    value_before: float | None = Field(default=None, allow_inf_nan=False)
    value_after: float | None = Field(default=None, allow_inf_nan=False)
    observation_window_hours: int = Field(gt=0, le=24 * 365)
    result: Literal['improved', 'unchanged', 'worsened', 'inconclusive']
    notes: str | None = Field(default=None, max_length=4000)
