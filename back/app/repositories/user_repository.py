from fastapi import APIRouter, Query
from sqlmodel import Session, select, func

from app.database import engine
from app.models.user import User
class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def paginate(
        self,
        page: int,
        per_page: int,
        search: str | None = None,
        is_astronaut: bool | None = None,
    ):
        offset = (page - 1) * per_page
        statement = select(User)
        if search and search.strip():
            statement = statement.where(User.name.icontains(search.strip(), autoescape=True))
        if is_astronaut is not None:
            statement = statement.where(User.is_astronaut == is_astronaut)
        total_statement = select(func.count()).select_from(statement.subquery())
        total = self.session.exec(total_statement).one()
        users_statement = (
            statement
            .order_by(User.name, User.id)
            .offset(offset)
            .limit(per_page)
        )
        users = self.session.exec(users_statement).all()
        return {
            "data": users,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page,
                "has_next": page * per_page < total,
                "has_previous": page > 1,
            },
        }