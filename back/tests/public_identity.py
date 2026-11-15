"""Cabeçalhos de identidade pública para os testes.

Desde a remoção do login, a API escolhe o usuário pelos cabeçalhos X-Public-User e
X-Public-Profile (ver USER_ACCESS.md). O perfil precisa ser um que o usuário tenha.
"""

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.core.roles import PROFILE_FIELDS
from app.models.user import User


def public_headers(db: Session | Engine, user_id, profile: str | None = None) -> dict[str, str]:
    """db pode ser a sessão do teste ou o engine (abre uma sessão só para a consulta)."""
    if profile is None:
        if isinstance(db, Engine):
            with Session(db) as session:
                user = session.get(User, int(user_id))
        else:
            user = db.get(User, int(user_id))
        assert user is not None, f'Usuário {user_id} não existe'
        profile = next((field for field in PROFILE_FIELDS if getattr(user, field, False)), None)
        assert profile is not None, f'O usuário {user_id} não tem nenhum perfil para ser selecionado'
    return {'X-Public-User': str(user_id), 'X-Public-Profile': profile}
