from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.main import app
from app.models.preflight import Mission
from app.models.spacecraft import Spacecraft
from app.models.user import User
from app.schemas.preflight import MissionCreate, MissionPatch, MissionResponse
from app.schemas.spacecraft import SpacecraftResponse
from app.services.preflight_service import PreflightService
from tests.public_identity import public_headers


@pytest.fixture(params=["service", "api"])
def mission_api(tmp_path, request):
    engine = create_engine(f"sqlite:///{tmp_path / 'missions.db'}", connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine, tables=[table for table in SQLModel.metadata.sorted_tables if table.name not in {'knowledge_documents', 'knowledge_passages'}])
    with Session(engine) as session:
        user = User(name='Admin', email='mission@example.com', hashed_password='fictional', is_physician=True)
        session.add(user)
        session.add_all([Spacecraft(name='Explorer'), Spacecraft(name='Voyager')])
        session.commit()
        user_id = user.id
    def get_test_session():
        with Session(engine) as session:
            yield session
    if request.param == "service":
        def call(method, path, body=None, expected=200):
            with Session(engine) as session:
                service = PreflightService(session, session.get(User, user_id))
                try:
                    if path.startswith('/spacecraft/'):
                        result = SpacecraftResponse.model_validate(session.get(Spacecraft, int(path.split('/')[-1])))
                    elif method == 'POST':
                        result = MissionResponse.model_validate(service.create_mission(MissionCreate(**body)))
                    elif method == 'PATCH':
                        result = MissionResponse.model_validate(service.update_mission(int(path.split('/')[-1]), MissionPatch(**body)))
                    else:
                        service.delete_mission(int(path.split('/')[-1]))
                        result = None
                    assert expected == (201 if method == 'POST' else 204 if method == 'DELETE' else 200)
                    return result.model_dump() if result else None
                except HTTPException as exc:
                    assert exc.status_code == expected, exc.detail
        yield call, engine, user_id
        engine.dispose()
        return
    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as client:
        def call(method, path, body=None, expected=200):
            response = client.request(method, '/v1' + path, json=body, headers=public_headers(engine, user_id))
            assert response.status_code == expected, response.text
            return response.json() if response.content else None
        yield call, engine, user_id
    app.dependency_overrides.clear()
    engine.dispose()


def payload(spacecraft_id=None):
    return {'name': 'Mission', 'planned_launch_at': datetime.now(timezone.utc).isoformat(), 'spacecraft_id': spacecraft_id}


def test_create_complete_and_repeat_after_reassignment(mission_api):
    call, engine, _ = mission_api
    first = call('POST', '/missions', payload(1), 201)
    assert first['status'] == 'planned'
    assert call('GET', '/spacecraft/1')['status'] == 'in_use'
    call('POST', '/missions', payload(1), 409)
    call('POST', '/missions', payload(999), 404)
    completed = call('PATCH', f"/missions/{first['id']}", {'status': 'completed'})
    assert completed['spacecraft_id'] == 1
    assert call('GET', '/spacecraft/1')['status'] == 'available'
    second = call('POST', '/missions', payload(1), 201)
    call('PATCH', f"/missions/{first['id']}", {'status': 'completed'})
    call('DELETE', f"/missions/{first['id']}", expected=204)
    assert call('GET', '/spacecraft/1')['status'] == 'in_use'
    call('DELETE', f"/missions/{second['id']}", expected=204)
    assert call('GET', '/spacecraft/1')['status'] == 'available'


def test_optional_spacecraft_and_completion(mission_api):
    call, _, _ = mission_api
    for omit in (True, False):
        body = payload()
        if omit:
            del body['spacecraft_id']
        mission = call('POST', '/missions', body, 201)
        assert mission['spacecraft_id'] is None
        assert call('PATCH', f"/missions/{mission['id']}", {'status': 'completed'})['status'] == 'completed'
    assert call('GET', '/spacecraft/1')['status'] == 'available'


def test_swap_reopen_and_rollback(mission_api):
    call, _, _ = mission_api
    first = call('POST', '/missions', payload(1), 201)
    second = call('POST', '/missions', payload(2), 201)
    path = f"/missions/{first['id']}"
    call('PATCH', path, {'spacecraft_id': 2}, 409)
    assert call('GET', '/spacecraft/1')['status'] == 'in_use'
    call('PATCH', f"/missions/{second['id']}", {'status': 'completed'})
    call('PATCH', path, {'spacecraft_id': 2})
    assert call('GET', '/spacecraft/1')['status'] == 'available'
    call('PATCH', f"/missions/{second['id']}", {'status': 'planned'}, 409)
    call('PATCH', path, {'spacecraft_id': None})
    assert call('GET', '/spacecraft/2')['status'] == 'available'
    assert call('PATCH', f"/missions/{second['id']}", {'status': 'in_progress'})['status'] == 'in_progress'


def test_concurrent_reservation(mission_api):
    _, engine, user_id = mission_api
    barrier = Barrier(2)
    def reserve():
        with Session(engine) as session:
            user = session.get(User, user_id)
            session.commit()
            barrier.wait()
            try:
                PreflightService(session, user).create_mission(MissionCreate(**payload(1)))
                return 201
            except Exception as exc:
                return getattr(exc, 'status_code', str(exc))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve(), range(2)))
    assert sorted(results) == [201, 409]
    with Session(engine) as session:
        assert len(session.exec(select(Mission).where(Mission.spacecraft_id == 1)).all()) == 1


def test_date_transitions_and_completed_metadata_edits(mission_api):
    call, _, _ = mission_api
    mission = call('POST', '/missions', payload(1), 201)
    path = f"/missions/{mission['id']}"
    now = datetime.now(timezone.utc).isoformat()
    assert call('PATCH', path, {'started_at': now})['status'] == 'in_progress'
    assert call('PATCH', path, {'ended_at': now})['status'] == 'completed'
    assert call('GET', '/spacecraft/1')['status'] == 'available'
    assert call('PATCH', path, {'ended_at': None})['status'] == 'in_progress'
    call('PATCH', path, {'status': 'completed'})
    call('POST', '/missions', payload(1), 201)
    assert call('PATCH', path, {'name': 'Historical mission', 'ended_at': None})['status'] == 'completed'
    assert call('GET', '/spacecraft/1')['status'] == 'in_use'
