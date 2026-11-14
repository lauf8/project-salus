from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from app.dependencies.auth import get_current_user
from app.database import get_session
from app.models.user import User
from app.schemas.users import UserCreate, UserResponse, PaginatedUsersResponse, UserProfilesUpdate
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

SessionDep = Annotated[Session, Depends(get_session)]



@router.post("/", response_model=UserResponse)
def create_user(user_data: UserCreate, session: Session = Depends(get_session)):
    user_service = UserService(session)

    return user_service.create_user(user_data)

@router.get("/", response_model=PaginatedUsersResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    search: str | None = Query(default=None, max_length=200),
    is_astronaut: bool | None = None,
):
    repository = UserRepository(session)

    return repository.paginate(
        page=page,
        per_page=per_page,
        search=search,
        is_astronaut=is_astronaut,
    )

@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/{user_id}/profiles", response_model=UserResponse)
def update_profiles(user_id: int, payload: UserProfilesUpdate, session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    from app.services.access_service import AccessService
    return AccessService(session, user).update_profiles(user_id, payload)


@router.get("/access-audit")
def access_audit(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100), session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    from app.services.access_service import AccessService
    return AccessService(session, user).audit_history(page, per_page)
