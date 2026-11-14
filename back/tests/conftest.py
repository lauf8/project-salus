import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.models.user import User
from app.models.revoked_token import RevokedToken
from app.database import get_session
from app.main import app


@pytest.fixture(name="session")
def session_fixture(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine, tables=[User.__table__, RevokedToken.__table__])

    with Session(engine) as session:
        yield session

    SQLModel.metadata.drop_all(engine, tables=[RevokedToken.__table__, User.__table__])
    engine.dispose()


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()