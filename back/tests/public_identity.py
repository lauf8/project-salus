"""Public identity headers for the tests.

Since login was removed, the API selects the user through the X-Public-User and
X-Public-Profile headers (see USER_ACCESS.md). The profile must be one the user has.
"""

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.core.roles import PROFILE_FIELDS
from app.models.user import User


def public_headers(db: Session | Engine, user_id, profile: str | None = None) -> dict[str, str]:
    """db can be the test session or the engine (opens a session just for the query)."""
    if profile is None:
        if isinstance(db, Engine):
            with Session(db) as session:
                user = session.get(User, int(user_id))
        else:
            user = db.get(User, int(user_id))
        assert user is not None, f'User {user_id} does not exist'
        profile = next((field for field in PROFILE_FIELDS if getattr(user, field, False)), None)
        assert profile is not None, f'User {user_id} has no profile that can be selected'
    return {'X-Public-User': str(user_id), 'X-Public-Profile': profile}
