from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.dependencies.donki import get_donki_client
from app.models.user import User
from app.providers.donki import DonkiClient
from app.schemas.preflight import Page
from app.schemas.space_weather import EventDetailResponse, EventResponse, ExposureLimitResponse, SyncRequest, SyncResponse, SyncRunResponse
from app.services.space_weather_service import SpaceWeatherService


router = APIRouter(prefix='/space-weather', tags=['space-weather'])

EventTypeFilter = Literal['FLR', 'CME', 'SEP']


def get_space_weather_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return SpaceWeatherService(session, user)


Service = Annotated[SpaceWeatherService, Depends(get_space_weather_service)]


@router.post('/sync', response_model=SyncResponse)
def sync_events(
    payload: SyncRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    donki: DonkiClient = Depends(get_donki_client),
):
    """Importa FLR, CME e SEP do NASA DONKI. Exige médico vinculado como
    flight_surgeon ou mission_admin em alguma missão."""
    runs = SpaceWeatherService(session, user, donki).sync(payload.start_date, payload.end_date, payload.event_types)
    if runs and all(run.status == 'failed' for run in runs):
        raise HTTPException(502, {'message': 'Não foi possível consultar o DONKI', 'runs': [run.model_dump(mode='json') for run in runs]})
    return SyncResponse(runs=runs)


@router.get('/sync-runs', response_model=list[SyncRunResponse])
def list_sync_runs(service: Service, limit: int = Query(20, ge=1, le=100)):
    return service.last_sync_runs(limit)


@router.get('/events', response_model=Page[EventResponse])
def list_events(
    service: Service,
    event_type: EventTypeFilter | None = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    if start and end and end < start:
        raise HTTPException(422, 'end deve ser igual ou posterior a start')
    return service.list_events(event_type, start, end, page, per_page)


@router.get('/events/{activity_id}', response_model=EventDetailResponse)
def get_event(activity_id: str, service: Service):
    return service.get_event(activity_id)


@router.get('/missions/{mission_id}/events', response_model=Page[EventResponse])
def mission_events(
    mission_id: int,
    service: Service,
    event_type: EventTypeFilter | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    return service.mission_events(mission_id, event_type, page, per_page)


@router.get('/exposure-limits', response_model=list[ExposureLimitResponse])
def exposure_limits(service: Service, profile_id: str | None = None):
    return service.exposure_limits(profile_id)
