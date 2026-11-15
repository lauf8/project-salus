from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.dependencies.donki import get_swpc_client
from app.models.user import User
from app.providers.swpc import SwpcClient
from app.schemas.preflight import Page
from app.schemas.radiation import (
    CrewActivityCreate, CrewActivityEnd, CrewActivityResponse, DoseCreate, DoseResponse, DoseSimulationRequest,
    DoseSimulationResponse, DoseSummary, EnergyChannel, FollowUpClose, FollowUpResponse, ProtonFluxReadingResponse,
    ProtonFluxSimulationRequest, ProtonFluxSimulationResponse, ProtonFluxSyncRequest, ProtonFluxSyncResponse,
    RadiationAlertResolve, RadiationAlertResponse, SepProcessResponse, SymptomReportCreate, TimelineResponse,
)
from app.services.radiation_service import DEFAULT_LIMIT_PROFILE, RadiationService


router = APIRouter(prefix='/radiation', tags=['radiation'])


def get_radiation_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return RadiationService(session, user)


Service = Annotated[RadiationService, Depends(get_radiation_service)]
PageNumber = Annotated[int, Query(ge=1)]
PerPage = Annotated[int, Query(ge=1, le=100)]


# --- Timeline ----------------------------------------------------------------------------------

@router.get('/missions/{mission_id}/timeline', response_model=TimelineResponse)
def timeline(mission_id: int, service: Service):
    """Events in the mission period, flare → CME → SEP chains, crew activities
    and, for those allowed to see them, follow-ups and active alerts."""
    return service.timeline(mission_id)


# --- Crew activity --------------------------------------------------------------------------------

@router.get('/missions/{mission_id}/crew-activities', response_model=Page[CrewActivityResponse])
def list_activities(mission_id: int, service: Service, astronaut_id: int | None = None, page: PageNumber = 1, per_page: PerPage = 50):
    return service.list_activities(mission_id, astronaut_id, page, per_page)


@router.post('/missions/{mission_id}/crew-activities', response_model=CrewActivityResponse, status_code=201)
def create_activity(mission_id: int, payload: CrewActivityCreate, service: Service):
    """IVA, EVA or shelter. An EVA that overlaps an imported SEP opens the follow-up."""
    return service.create_activity(mission_id, payload)


@router.post('/missions/{mission_id}/crew-activities/{activity_id}/end', response_model=CrewActivityResponse)
def end_activity(mission_id: int, activity_id: int, payload: CrewActivityEnd, service: Service):
    return service.end_activity(mission_id, activity_id, payload)


# --- Doses ------------------------------------------------------------------------------------------

@router.get('/missions/{mission_id}/doses', response_model=Page[DoseResponse])
def list_doses(mission_id: int, service: Service, astronaut_id: int | None = None, page: PageNumber = 1, per_page: PerPage = 50):
    return service.list_doses(mission_id, astronaut_id, page, per_page)


@router.post('/missions/{mission_id}/doses', response_model=DoseResponse, status_code=201)
def create_dose(mission_id: int, payload: DoseCreate, service: Service):
    """Dose measured (dosimeter) or estimated by an external model. Requires the flight surgeon."""
    return service.create_dose(mission_id, payload)


@router.post('/missions/{mission_id}/doses/simulate', response_model=DoseSimulationResponse)
def simulate_doses(mission_id: int, payload: DoseSimulationRequest, service: Service):
    """Generates simulated doses from the ≥10 MeV proton flux and each crew member's activity."""
    return service.simulate_doses(mission_id, payload)


@router.get('/missions/{mission_id}/astronauts/{astronaut_id}/dose-summary', response_model=DoseSummary)
def dose_summary(mission_id: int, astronaut_id: int, service: Service, profile_id: str = DEFAULT_LIMIT_PROFILE, as_of: AwareDatetime | None = None):
    return service.dose_summary(mission_id, astronaut_id, profile_id, as_of)


# --- Post-event follow-up ----------------------------------------------------------------------------

@router.get('/missions/{mission_id}/follow-ups', response_model=list[FollowUpResponse])
def list_follow_ups(mission_id: int, service: Service, status: Literal['open', 'completed', 'cancelled', 'all'] = 'all', astronaut_id: int | None = None):
    return service.list_follow_ups(mission_id, status, astronaut_id)


@router.get('/missions/{mission_id}/follow-ups/{follow_up_id}', response_model=FollowUpResponse)
def get_follow_up(mission_id: int, follow_up_id: int, service: Service):
    return service.get_follow_up(mission_id, follow_up_id)


@router.post('/missions/{mission_id}/follow-ups/{follow_up_id}/reports', response_model=FollowUpResponse, status_code=201)
def add_report(mission_id: int, follow_up_id: int, payload: SymptomReportCreate, service: Service):
    """Symptom report by the astronaut or by the flight surgeon."""
    return service.add_report(mission_id, follow_up_id, payload)


@router.post('/missions/{mission_id}/follow-ups/{follow_up_id}/close', response_model=FollowUpResponse)
def close_follow_up(mission_id: int, follow_up_id: int, payload: FollowUpClose, service: Service):
    return service.close_follow_up(mission_id, follow_up_id, payload)


# --- Alerts -----------------------------------------------------------------------------------------------

@router.get('/missions/{mission_id}/alerts', response_model=Page[RadiationAlertResponse])
def list_alerts(
    mission_id: int, service: Service, status: Literal['active', 'open', 'acknowledged', 'resolved', 'all'] = 'active',
    astronaut_id: int | None = None, page: PageNumber = 1, per_page: PerPage = 50,
):
    return service.list_alerts(mission_id, status, astronaut_id, page, per_page)


@router.post('/missions/{mission_id}/alerts/{alert_id}/acknowledge', response_model=RadiationAlertResponse)
def acknowledge_alert(mission_id: int, alert_id: int, service: Service):
    return service.acknowledge_alert(mission_id, alert_id)


@router.post('/missions/{mission_id}/alerts/{alert_id}/resolve', response_model=RadiationAlertResponse)
def resolve_alert(mission_id: int, alert_id: int, payload: RadiationAlertResolve, service: Service):
    return service.resolve_alert(mission_id, alert_id, payload)


# --- Events and proton flux ----------------------------------------------------------------------------------

@router.post('/events/{activity_id}/process', response_model=SepProcessResponse)
def reprocess_event(activity_id: str, service: Service):
    """Reassesses an imported SEP (e.g. after correcting an EVA record)."""
    return service.reprocess_event(activity_id)


@router.get('/proton-flux', response_model=list[ProtonFluxReadingResponse])
def list_flux(
    service: Service, channel: EnergyChannel = '>=10 MeV', start: AwareDatetime | None = None, end: AwareDatetime | None = None,
    limit: int = Query(2000, ge=1, le=5000),
):
    if start and end and end < start:
        raise HTTPException(422, 'end must be equal to or after start')
    return service.list_flux(channel, start, end, limit)


@router.post('/proton-flux/sync', response_model=ProtonFluxSyncResponse)
def sync_flux(payload: ProtonFluxSyncRequest, service: Service, swpc: SwpcClient = Depends(get_swpc_client)):
    """Imports the GOES integral proton flux from NOAA SWPC (recent data only)."""
    return service.sync_proton_flux(swpc, payload.window)


@router.post('/proton-flux/simulate', response_model=ProtonFluxSimulationResponse)
def simulate_flux(payload: ProtonFluxSimulationRequest, service: Service):
    """Generates a synthetic ≥10 MeV flux profile for an SEP (source 'simulation')."""
    return service.simulate_proton_flux(payload)
