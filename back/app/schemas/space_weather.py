from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.preflight import InputModel, OutputModel


EventType = Literal['FLR', 'CME', 'SEP']
HealthRelevance = Literal['precursor', 'exposure']

# Cap. 5 do NASA SP-2009-3405: flares e CMEs antecedem/acompanham os SEPs;
# os prótons do SEP é que podem causar dose relevante.
HEALTH_RELEVANCE: dict[str, HealthRelevance] = {'FLR': 'precursor', 'CME': 'precursor', 'SEP': 'exposure'}
MAX_SYNC_DAYS = 366


class SyncRequest(InputModel):
    start_date: date
    end_date: date
    event_types: list[EventType] = Field(default_factory=lambda: ['FLR', 'CME', 'SEP'], min_length=1)

    @model_validator(mode='after')
    def check_range(self):
        if self.end_date < self.start_date:
            raise ValueError('end_date deve ser igual ou posterior a start_date')
        if (self.end_date - self.start_date).days + 1 > MAX_SYNC_DAYS:
            raise ValueError(f'O intervalo máximo por sincronização é de {MAX_SYNC_DAYS} dias')
        if len(set(self.event_types)) != len(self.event_types):
            raise ValueError('event_types não pode ter tipos repetidos')
        return self


class SyncRunResponse(OutputModel):
    id: int
    event_type: EventType
    start_date: date
    end_date: date
    status: str
    fetched_count: int
    created_count: int
    updated_count: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class SyncResponse(OutputModel):
    runs: list[SyncRunResponse]


class EventResponse(OutputModel):
    id: int
    activity_id: str
    event_type: EventType
    health_relevance: HealthRelevance
    catalog: str | None
    start_time: datetime
    peak_time: datetime | None
    end_time: datetime | None
    source_location: str | None
    active_region_num: int | None
    flare_class: str | None
    flare_peak_flux_wm2: float | None
    cme_speed_kms: float | None
    cme_half_angle_deg: float | None
    cme_type: str | None
    cme_latitude: float | None
    cme_longitude: float | None
    cme_time_21_5: datetime | None
    instruments: list[str]
    note: str | None
    link: str | None
    version_id: int | None
    last_synced_at: datetime


class LinkedEventResponse(OutputModel):
    activity_id: str
    event_type: str | None
    stored: bool
    event: EventResponse | None = None


class EventDetailResponse(EventResponse):
    linked_events: list[LinkedEventResponse]


class ExposureLimitResponse(OutputModel):
    profile_id: str
    organ: str
    period: str
    value: float
    unit: str
    source_reference: str
