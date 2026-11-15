from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from app.schemas.health import ObservationResponse
from app.schemas.preflight import InputModel, OutputModel


class OxygenThresholds(InputModel):
    normal_min: float = Field(ge=0, le=100, allow_inf_nan=False)
    attention_min: float = Field(ge=0, le=100, allow_inf_nan=False)
    urgent_min: float = Field(ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_order(self):
        if not self.urgent_min < self.attention_min < self.normal_min:
            raise ValueError('SpO₂ limits must increase: critical, urgent and attention')
        return self


class HighGlucoseThresholds(InputModel):
    attention: float | None = Field(default=None, ge=70, allow_inf_nan=False)
    urgent: float | None = Field(default=None, ge=70, allow_inf_nan=False)
    critical: float | None = Field(default=None, ge=70, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_order(self):
        values = [value for value in (self.attention, self.urgent, self.critical) if value is not None]
        if not values or values != sorted(set(values)):
            raise ValueError('Provide at least one increasing high glucose limit')
        return self


class AlertSettingsUpdate(InputModel):
    expected_revision: int = Field(ge=0)
    profile_id: Literal['simulation-v1', 'simulation-v2'] = 'simulation-v2'
    timezone: str = Field(min_length=1, max_length=100)
    emergency_channel: str | None = Field(default=None, max_length=500)
    oxygen_thresholds: OxygenThresholds | None = None
    high_glucose_thresholds: dict[Literal['fasting', 'after_meal', 'unknown'], HighGlucoseThresholds] = Field(default_factory=dict)
    approval_note: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def validate_timezone(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Provide a valid IANA time zone, such as America/Bahia')
        return self


class AlertSettingsResponse(OutputModel):
    mission_id: int
    revision: int
    profile_id: str
    timezone: str
    emergency_channel: str | None
    oxygen_thresholds: dict
    high_glucose_thresholds: dict
    approval_note: str | None
    approved_by_user_id: int | None
    can_edit: bool
    rule_version: str


class AlertResolve(InputModel):
    note: str = Field(min_length=1, max_length=4000)


class AlertResponse(OutputModel):
    id: int
    astronaut_id: int
    mission_id: int | None
    rule_id: str
    rule_version: str
    indicator: str
    severity: Literal['attention', 'urgent', 'critical']
    status: Literal['open', 'acknowledged', 'resolved']
    reason: str
    verification_required: bool
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None
    latest_observation: ObservationResponse | None = None
    awaiting_medical_review: bool = False
    trigger_observation: ObservationResponse
    source_count: int
    can_acknowledge: bool
    can_resolve: bool
    emergency_channel: str | None
    protocol_message: str | None


class AlertEventResponse(OutputModel):
    id: int
    action: str
    severity: str
    status: str
    reason: str
    rule_version: str
    actor_user_id: int
    created_at: datetime
    observation: ObservationResponse | None
