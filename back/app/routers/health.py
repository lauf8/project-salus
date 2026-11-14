from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.health import HealthSummary, Indicator, ObservationCreate, ObservationResponse
from app.schemas.preflight import Page
from app.services.health_service import HealthService
from app.services.health_alert_service import HealthAlertService
from app.schemas.health_alerts import AlertResponse, AlertEventResponse, AlertResolve, AlertSettingsResponse, AlertSettingsUpdate


router = APIRouter(prefix='/health', tags=['health'])


def get_health_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return HealthService(session, user)


Service = Annotated[HealthService, Depends(get_health_service)]


@router.post('/astronauts/{astronaut_id}/observations', response_model=ObservationResponse, status_code=201)
def create_observation(astronaut_id: int, payload: ObservationCreate, service: Service):
    return service.create(astronaut_id, payload)


@router.get('/astronauts/{astronaut_id}/summary', response_model=HealthSummary)
def get_summary(astronaut_id: int, service: Service, mission_id: int | None = Query(default=None, gt=0)):
    return service.summary(astronaut_id, mission_id)


@router.get('/astronauts/{astronaut_id}/history', response_model=Page[ObservationResponse])
def get_history(
    astronaut_id: int, indicator: Indicator, service: Service,
    mission_id: int | None = Query(default=None, gt=0),
    start: AwareDatetime | None = None, end: AwareDatetime | None = None,
    page: int = Query(default=1, ge=1), per_page: int = Query(default=100, ge=1, le=100),
):
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=30)
    return service.history(astronaut_id, indicator, mission_id, start, end, page, per_page)


@router.get('/context')
def get_context(service: Service):
    return service.context()


@router.get('/astronauts/{astronaut_id}/alerts', response_model=Page[AlertResponse])
def list_alerts(astronaut_id: int, service: Service, mission_id: int | None = Query(None, gt=0), status: Literal['active', 'all', 'open', 'acknowledged', 'resolved'] = 'active', page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), indicator: Indicator | None = None):
    return HealthAlertService(service.session, service.user).list_alerts(astronaut_id, mission_id, status, page, per_page, indicator)


@router.get('/astronauts/{astronaut_id}/alerts/{alert_id}', response_model=AlertResponse)
def get_alert(astronaut_id: int, alert_id: int, service: Service, mission_id: int | None = Query(None, gt=0)):
    alerts = HealthAlertService(service.session, service.user)
    alert, can_resolve = alerts.get_alert(astronaut_id, mission_id, alert_id)
    return alerts.response(alert, can_resolve)


@router.get('/astronauts/{astronaut_id}/alerts/{alert_id}/history', response_model=Page[AlertEventResponse])
def alert_history(astronaut_id: int, alert_id: int, service: Service, mission_id: int | None = Query(None, gt=0), page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return HealthAlertService(service.session, service.user).history(astronaut_id, mission_id, alert_id, page, per_page)


@router.post('/astronauts/{astronaut_id}/alerts/{alert_id}/acknowledge', response_model=AlertResponse)
def acknowledge_alert(astronaut_id: int, alert_id: int, service: Service, mission_id: int | None = Query(None, gt=0)):
    return HealthAlertService(service.session, service.user).acknowledge(astronaut_id, mission_id, alert_id)


@router.post('/astronauts/{astronaut_id}/alerts/{alert_id}/resolve', response_model=AlertResponse)
def resolve_alert(astronaut_id: int, alert_id: int, payload: AlertResolve, service: Service, mission_id: int | None = Query(None, gt=0)):
    return HealthAlertService(service.session, service.user).resolve(astronaut_id, mission_id, alert_id, payload)


@router.get('/missions/{mission_id}/alert-settings', response_model=AlertSettingsResponse)
def get_alert_settings(mission_id: int, service: Service):
    return HealthAlertService(service.session, service.user).settings(mission_id)


@router.put('/missions/{mission_id}/alert-settings', response_model=AlertSettingsResponse)
def update_alert_settings(mission_id: int, payload: AlertSettingsUpdate, service: Service):
    return HealthAlertService(service.session, service.user).update_settings(mission_id, payload)
