"""Public workspace identity: selecting a user does not require authentication."""
from fastapi import Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User

from app.core.roles import PROFILE_FIELDS


def get_current_user(
    public_user: int | None = Header(default=None, alias="X-Public-User"),
    public_profile: str = Header(default="is_global_admin", alias="X-Public-Profile"),
    session: Session = Depends(get_session),
) -> User:
    if public_profile not in PROFILE_FIELDS:
        raise HTTPException(422, "Unknown profile")
    if public_user is not None:
        user = session.get(User, public_user)
        if user is None or not user.is_active:
            raise HTTPException(404, "Active user not found")
        if not getattr(user, public_profile):
            raise HTTPException(422, "Choose a user with the selected profile")
        return user
    user = session.exec(select(User).where(
        User.is_active == True, getattr(User, public_profile) == True,
    ).order_by(User.id)).first()
    if user is not None:
        return user
    # Keep a real database identity for record ownership and audit foreign keys.
    email = f"public-{public_profile}@workspace.local"
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        user = User(name="Public " + public_profile.removeprefix("is_").replace("_", " "),
                    email=email, hashed_password="!public-access", **{public_profile: True})
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            user = session.exec(select(User).where(User.email == email)).one()
    else:
        user.is_active = True
        setattr(user, public_profile, True)
        session.add(user)
        session.commit()
    session.refresh(user)
    return user
