from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.security import create_access_token
from app.database import get_session
from app.main import app
from app.models.preflight import Mission
from app.models.spacecraft import Spacecraft
from app.models.user import User


@pytest.fixture
def crew_api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'crew.db'}", connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine, tables=[table for table in SQLModel.metadata.sorted_tables if table.name not in {'knowledge_documents', 'knowledge_passages'}])
    with Session(engine) as session:
        people = [User(name=name, email=f'{index}@crew.test', hashed_password='fictional', is_physician=index == 0, is_astronaut=index in (1, 2, 3)) for index, name in enumerate(('Admin', 'Alice Alpha', 'Alice Beta', 'Bruno', 'Ground staff'))]
        session.add_all(people)
        session.add_all([Spacecraft(name='Explorer', maximum_crew_capacity=2), Spacecraft(name='Small', maximum_crew_capacity=1), Spacecraft(name='Unknown')])
        session.commit()
        ids = [user.id for user in people]
    def session_override():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            def call(method, path, body=None, expected=200):
                response = client.request(method, '/v1' + path, json=body, headers={'Authorization': f'Bearer {create_access_token(str(ids[0]))}'})
                assert response.status_code == expected, response.text
                return response.json() if response.content else None
            yield call, engine, ids
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def mission_payload(**values):
    return {'name': 'Crew mission', 'planned_launch_at': datetime.now(timezone.utc).isoformat(), 'spacecraft_id': 1, 'crew_size': 2, **values}


def test_creation_respects_capacity_and_is_atomic(crew_api):
    call, engine, ids = crew_api
    call('POST', '/missions', mission_payload(crew_size=3), 409)
    call('POST', '/missions', mission_payload(crew_size=1, astronaut_ids=ids[1:3]), 409)
    call('POST', '/missions', mission_payload(astronaut_ids=[ids[4]]), 422)
    call('POST', '/missions', mission_payload(astronaut_ids=[99999]), 404)
    call('POST', '/missions', mission_payload(astronaut_ids=[ids[1], ids[1]]), 422)
    call('POST', '/missions', mission_payload(crew_size=0), 422)
    assert call('GET', '/spacecraft/1')['status'] == 'available'
    with Session(engine) as session:
        assert session.exec(select(Mission)).all() == []
    mission = call('POST', '/missions', mission_payload(astronaut_ids=ids[1:3]), 201)
    assert mission['crew_size'] == 2
    members = call('GET', f"/missions/{mission['id']}/members")['data']
    assert len([member for member in members if member['role'] == 'astronaut']) == 2
    assert len([member for member in members if member['role'] == 'mission_admin']) == 1


def test_add_remove_and_role_changes_obey_crew_limit(crew_api):
    call, _, ids = crew_api
    mission = call('POST', '/missions', mission_payload(crew_size=1), 201)
    path = f"/missions/{mission['id']}"
    first = call('POST', path + '/members', {'user_id': ids[1], 'role': 'astronaut'}, 201)
    assert call('POST', path + '/members', {'user_id': ids[1], 'role': 'astronaut'}, 201)['id'] == first['id']
    call('POST', path + '/members', {'user_id': ids[2], 'role': 'astronaut'}, 409)
    ground = call('POST', path + '/members', {'user_id': ids[2], 'role': 'flight_surgeon'}, 201)
    call('PATCH', path + f"/members/{ground['id']}", {'role': 'astronaut'}, 409)
    call('DELETE', path + f"/members/{first['id']}", expected=204)
    call('PATCH', path + f"/members/{ground['id']}", {'role': 'astronaut'})
    call('PATCH', path, {'crew_size': 2})
    call('POST', path + '/members', {'user_id': ids[3], 'role': 'astronaut'}, 201)
    call('PATCH', path, {'crew_size': 1}, 409)
    call('PATCH', path, {'crew_size': 3}, 409)
    call('PATCH', path, {'spacecraft_id': 2}, 409)
    call('PATCH', '/spacecraft/1', {'maximum_crew_capacity': 1}, 409)
    call('PATCH', path, {'crew_size': None})
    call('POST', path + '/members', {'user_id': ids[1], 'role': 'astronaut'}, 409)
    call('POST', path + '/members', {'user_id': ids[4], 'role': 'astronaut'}, 422)


def test_unknown_capacity_and_legacy_mission(crew_api):
    call, _, ids = crew_api
    body = mission_payload(spacecraft_id=None)
    del body['crew_size']
    mission = call('POST', '/missions', body, 201)
    assert mission['crew_size'] is None
    call('POST', f"/missions/{mission['id']}/members", {'user_id': ids[1], 'role': 'astronaut'}, 201)
    other = call('POST', '/missions', mission_payload(spacecraft_id=3, crew_size=10, astronaut_ids=ids[2:4]), 201)
    assert other['crew_size'] == 10


def test_astronaut_search_filters_names_profiles_and_paginates(crew_api):
    call, _, _ = crew_api
    result = call('GET', '/users/?search=ALICE&is_astronaut=true&per_page=1')
    assert result['pagination']['total'] == 2
    assert result['pagination']['has_next'] is True
    assert result['data'][0]['name'] == 'Alice Alpha'
    assert call('GET', '/users/?search=ALICE&is_astronaut=true&per_page=1&page=2')['data'][0]['name'] == 'Alice Beta'
    assert call('GET', '/users/?search=Ground&is_astronaut=true')['data'] == []
    assert call('GET', '/users/?search=%25&is_astronaut=true')['data'] == []
