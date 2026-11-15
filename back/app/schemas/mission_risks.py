from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.preflight import InputModel


class DailyRate(InputModel):
    food_product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    unit: str = Field(min_length=1, max_length=30)
    basis: Literal['stored', 'prepared'] = 'stored'
    per_person: bool = True


class ApprovedAction(InputModel):
    food_product_id: int = Field(gt=0)
    action: str = Field(min_length=1, max_length=2000)
    source_reference: str = Field(min_length=1, max_length=2000)


class RiskPlanInput(InputModel):
    planned_end_at: AwareDatetime
    exposure_start_at: AwareDatetime
    crew_size: int = Field(ge=1, le=1000)
    consumption_window_days: int = Field(default=7, ge=1, le=90)
    coverage_start: AwareDatetime | None = None
    coverage_end: AwareDatetime | None = None
    inventory_complete: bool = False
    consumption_complete: bool = False
    daily_rates: list[DailyRate] = Field(default_factory=list, max_length=500)
    approved_actions: list[ApprovedAction] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def validate_period(self):
        if self.planned_end_at <= self.exposure_start_at or (self.planned_end_at - self.exposure_start_at).days > 730:
            raise ValueError('Mission duration must be positive and at most 730 days')
        if (self.coverage_start is None) != (self.coverage_end is None):
            raise ValueError('Supply both coverage dates')
        if self.coverage_start and self.coverage_end < self.coverage_start:
            raise ValueError('Coverage end precedes start')
        ids = [rate.food_product_id for rate in self.daily_rates]
        if len(ids) != len(set(ids)):
            raise ValueError('Supply one daily rate per food product')
        return self


class OccurrenceInput(InputModel):
    category: Literal['food_shortage', 'sleep_fatigue', 'physical_fitness', 'well_being', 'spacecraft'] = 'food_shortage'
    food_product_id: int | None = Field(default=None, gt=0)
    phase: Literal['preflight', 'in_flight', 'postflight']
    event_at: AwareDatetime
    severity: Literal['warning', 'critical']
    source_references: list[dict[str, str]] = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=5000)
    actions: str = Field(min_length=1, max_length=5000)
    outcome: str = Field(min_length=1, max_length=5000)
    intervention: bool = False


class RiskActionInput(InputModel):
    action: Literal['read', 'execute', 'resolve', 'assign', 'approve_guidance']
    details: str = Field(min_length=1, max_length=3000)
    responsible_user_id: int | None = Field(default=None, gt=0)
    guidance_kind: Literal['operational', 'clinical'] = 'operational'


class SearchInput(InputModel):
    query: str = Field(min_length=3, max_length=1000)
    document_id: int | None = Field(default=None, gt=0)
    origin: str = Field(default='NASA', min_length=1, max_length=100)


class ReplayInput(InputModel):
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode='after')
    def validate_range(self):
        if self.end_at < self.start_at or (self.end_at - self.start_at).days > 730:
            raise ValueError('Replay range must be ordered and at most 730 days')
        return self
