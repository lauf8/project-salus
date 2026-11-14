from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.notifications import NotificationReadAllResponse, NotificationResponse, NotificationSummary
from app.schemas.preflight import Page
from app.services.notification_service import NotificationService


router = APIRouter(prefix='/notifications', tags=['notifications'])


def get_notification_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return NotificationService(session, user)


Service = Annotated[NotificationService, Depends(get_notification_service)]


@router.get('', response_model=Page[NotificationResponse])
def list_notifications(service: Service, status: Literal['pending', 'all'] = 'pending', mission_id: int | None = Query(None, gt=0), page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_notifications(status, mission_id, page, per_page)


@router.get('/summary', response_model=NotificationSummary)
def summary(service: Service):
    return service.summary()


@router.post('/read-all', response_model=NotificationReadAllResponse)
def read_all(service: Service):
    return service.read_all()


@router.post('/{notification_id}/read', response_model=NotificationResponse)
def read(notification_id: int, service: Service):
    return service.read(notification_id)
