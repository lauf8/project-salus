from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AssessmentExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    context: str = Field(min_length=1, max_length=5000)
    confirmed_symptom_codes: list[
        Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    ] = Field(default_factory=list, max_length=32)


class AssessmentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    symptom: str = Field(min_length=1, max_length=1000)
    activity_context: str | None = Field(max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=4)
