from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.mental_health import CheckInInput, FollowUpInput
from app.services.mental_health_service import MentalHealthService


router = APIRouter(prefix="/missions/{mission_id}/mental-health", tags=["mental-health"])


def service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return MentalHealthService(session, user)


@router.get("/astronauts")
def roster(mission_id: int, manager: MentalHealthService = Depends(service)):
    return manager.roster(mission_id)


@router.get("/astronauts/{member_id}")
def overview(mission_id: int, member_id: int, start: date | None = None, end: date | None = None, manager: MentalHealthService = Depends(service)):
    return manager.overview(mission_id, member_id, start, end)


@router.put("/astronauts/{member_id}/check-ins/{check_in_date}")
def save_check_in(mission_id: int, member_id: int, check_in_date: date, payload: CheckInInput, manager: MentalHealthService = Depends(service)):
    return manager.save_check_in(mission_id, member_id, check_in_date, payload)


@router.post("/astronauts/{member_id}/requests")
def request_contact(mission_id: int, member_id: int, manager: MentalHealthService = Depends(service)):
    return manager.request_contact(mission_id, member_id)


@router.post("/astronauts/{member_id}/sessions")
def create_session(mission_id: int, member_id: int, payload: FollowUpInput, manager: MentalHealthService = Depends(service)):
    return manager.save_session(mission_id, member_id, payload)


@router.put("/astronauts/{member_id}/sessions/{record_id}")
def update_session(mission_id: int, member_id: int, record_id: int, payload: FollowUpInput, manager: MentalHealthService = Depends(service)):
    return manager.save_session(mission_id, member_id, payload, record_id)
