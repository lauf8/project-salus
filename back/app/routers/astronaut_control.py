"""Mission-scoped radiation records for the astronaut control workspace."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.space_weather import CrewActivity, RadiationDoseRecord, RadiationFollowUp, SpaceWeatherEvent
from app.models.spacecraft import SpacecraftModule
from app.models.preflight import Mission
from app.models.access import AccessAuditEvent
from app.schemas.preflight import InputModel
from app.services.health_service import HealthService

router = APIRouter(prefix='/missions/{mission_id}/astronauts/{astronaut_id}/radiation', tags=['astronaut-control'])


class DoseInput(InputModel):
    organ: Literal['lens', 'skin', 'bfo', 'heart', 'cns', 'cns_z_ge_10']
    dose: float = Field(ge=0, allow_inf_nan=False)
    unit: Literal['mGy-Eq', 'mGy'] = 'mGy-Eq'
    source: Literal['dosimeter', 'model_estimate', 'simulation']
    period_start: AwareDatetime
    period_end: AwareDatetime
    event_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def dates(self):
        if self.period_end < self.period_start or self.period_end > datetime.now(timezone.utc):
            raise ValueError('Select an ordered observation period ending in the past')
        return self


class ActivityInput(InputModel):
    activity_type: Literal['iva', 'eva', 'storm_shelter']
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    spacecraft_module_id: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=20000)

    @model_validator(mode='after')
    def dates(self):
        now = datetime.now(timezone.utc)
        if self.started_at > now or self.ended_at and (self.ended_at <= self.started_at or self.ended_at > now):
            raise ValueError('Activity dates must be ordered and cannot be in the future')
        return self


@router.get('')
def overview(mission_id: int, astronaut_id: int, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    can_record_dose = HealthService(session, user).authorize(astronaut_id, mission_id)
    doses = session.exec(select(RadiationDoseRecord).where(RadiationDoseRecord.mission_id == mission_id, RadiationDoseRecord.astronaut_id == astronaut_id).order_by(RadiationDoseRecord.period_end.desc(), RadiationDoseRecord.id.desc()).limit(100)).all()
    totals = session.exec(select(RadiationDoseRecord.organ, RadiationDoseRecord.unit, RadiationDoseRecord.source, func.sum(RadiationDoseRecord.dose), func.count()).where(RadiationDoseRecord.mission_id == mission_id, RadiationDoseRecord.astronaut_id == astronaut_id).group_by(RadiationDoseRecord.organ, RadiationDoseRecord.unit, RadiationDoseRecord.source)).all()
    activities = session.exec(select(CrewActivity).where(CrewActivity.mission_id == mission_id, CrewActivity.astronaut_id == astronaut_id).order_by(CrewActivity.started_at.desc(), CrewActivity.id.desc()).limit(100)).all()
    follow_ups = session.exec(select(RadiationFollowUp).where(RadiationFollowUp.mission_id == mission_id, RadiationFollowUp.astronaut_id == astronaut_id).order_by(RadiationFollowUp.opened_at.desc()).limit(100)).all()
    return dict(can_record_dose=can_record_dose, totals=[dict(organ=o, unit=u, source=src, dose=d, count=n) for o,u,src,d,n in totals], doses=doses, activities=activities, follow_ups=follow_ups, history_limit=100)


@router.post('/doses', status_code=201)
def record_dose(mission_id: int, astronaut_id: int, payload: DoseInput, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    if not HealthService(session, user).authorize(astronaut_id, mission_id):
        raise HTTPException(403, 'An assigned flight surgeon must record radiation dose')
    if payload.event_id is not None and session.get(SpaceWeatherEvent, payload.event_id) is None:
        raise HTTPException(404, 'Space weather event not found')
    row = RadiationDoseRecord(mission_id=mission_id, astronaut_id=astronaut_id, recorded_by_user_id=user.id, **payload.model_dump())
    session.add(row)
    session.flush()
    session.add(AccessAuditEvent(actor_user_id=user.id, resource_type='radiation_dose_records', resource_id=row.id, action='created', changed_fields=list(payload.model_fields_set)))
    session.commit()
    session.refresh(row)
    return row


@router.post('/activities', status_code=201)
def record_activity(mission_id: int, astronaut_id: int, payload: ActivityInput, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    HealthService(session, user).authorize(astronaut_id, mission_id)
    if payload.spacecraft_module_id:
        module = session.get(SpacecraftModule, payload.spacecraft_module_id)
        mission = session.get(Mission, mission_id)
        if module is None or module.spacecraft_id != mission.spacecraft_id:
            raise HTTPException(422, 'The module must belong to this mission spacecraft')
    # Serializing on the astronaut prevents concurrent overlapping location entries.
    session.exec(select(User).where(User.id == astronaut_id).with_for_update()).one()
    overlap = select(CrewActivity).where(CrewActivity.astronaut_id == astronaut_id,
        (CrewActivity.ended_at.is_(None)) | (CrewActivity.ended_at > payload.started_at))
    if payload.ended_at:
        overlap = overlap.where(CrewActivity.started_at < payload.ended_at)
    if session.exec(overlap).first():
        raise HTTPException(409, 'This activity overlaps an existing crew location record')
    row = CrewActivity(mission_id=mission_id, astronaut_id=astronaut_id, recorded_by_user_id=user.id, **payload.model_dump())
    session.add(row)
    session.flush()
    session.add(AccessAuditEvent(actor_user_id=user.id, resource_type='crew_activities', resource_id=row.id, action='created', changed_fields=list(payload.model_fields_set)))
    session.commit()
    session.refresh(row)
    return row


class ActivityEndInput(InputModel):
    ended_at: AwareDatetime


@router.patch('/activities/{activity_id}')
def close_activity(mission_id: int, astronaut_id: int, activity_id: int, payload: ActivityEndInput, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    HealthService(session, user).authorize(astronaut_id, mission_id)
    session.exec(select(User).where(User.id == astronaut_id).with_for_update()).one()
    row = session.get(CrewActivity, activity_id)
    if row is None or row.mission_id != mission_id or row.astronaut_id != astronaut_id:
        raise HTTPException(404, 'Activity not found for this astronaut and mission')
    if row.ended_at is not None:
        raise HTTPException(409, 'The activity is already closed')
    start = row.started_at if row.started_at.tzinfo else row.started_at.replace(tzinfo=timezone.utc)
    if payload.ended_at <= start or payload.ended_at > datetime.now(timezone.utc):
        raise HTTPException(422, 'End time must follow the activity start and cannot be in the future')
    row.ended_at = payload.ended_at
    session.add(row)
    session.add(AccessAuditEvent(actor_user_id=user.id, resource_type='crew_activities', resource_id=row.id, action='closed', changed_fields=['ended_at']))
    session.commit()
    session.refresh(row)
    return row
