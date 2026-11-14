from fastapi import Depends
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.preflight_service import PreflightService


def get_preflight_service(
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> PreflightService:
    return PreflightService(session, user)
