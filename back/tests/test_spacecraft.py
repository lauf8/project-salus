import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.security import create_access_token
from app.database import engine as postgres_engine, get_session
from app.main import app
from app.models.preflight import Mission, MissionMember
from app.models.revoked_token import RevokedToken
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.models.user import User


@pytest.fixture
def spacecraft_api():
    postgres = os.getenv('SPACECRAFT_POSTGRES_TESTS') == '1'
    engine = postgres_engine if postgres else create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    if not postgres:
        @event.listens_for(engine, 'connect')
        def foreign_keys(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
        SQLModel.metadata.create_all(engine, tables=[model.__table__ for model in (User, RevokedToken, Mission, MissionMember, Spacecraft, SpacecraftModule)])
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode='create_savepoint')
    people = {}
    for name in ('doctor', 'admin', 'astronaut', 'outsider'):
        user = User(name=name, email=f'spacecraft-{name}@fictional.test', hashed_password='fictional', is_physician=name != 'astronaut', is_astronaut=name == 'astronaut')
        session.add(user)
        session.flush()
        people[name] = user.id
    mission = Mission(name='Catalog permissions', planned_launch_at=datetime.now(timezone.utc))
    session.add(mission)
    session.flush()
    for name, role in (('doctor', 'flight_surgeon'), ('admin', 'mission_admin')):
        session.add(MissionMember(mission_id=mission.id, user_id=people[name], role=role))
    session.commit()

    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        with TestClient(app) as client:
            def call(method, path, payload=None, expected=200, actor='doctor'):
                headers = {'Authorization': f'Bearer {create_access_token(str(people[actor]))}'} if actor else {}
                response = client.request(method, '/v1/spacecraft' + path, json=payload, headers=headers)
                assert response.status_code == expected, response.text
                return response.json() if response.content else None
            yield call, session, connection
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()
        if not postgres:
            engine.dispose()


def specification():
    return {'dimensions_m': {'length': 4.5, 'diameter': 3.2, 'width': 2.5, 'height': 2.8}, 'dry_mass_kg': 2800, 'materials': [{'component': 'pressure_shell', 'material': 'Aluminum alloy', 'location': 'Primary structure', 'specification': '7075-T6'}, {'component': 'interior_wall_panel', 'material': 'Composite', 'contact_environment': 'cabin_air'}], 'thermal_insulation': 'Multilayer insulation', 'shielding': 'Debris shielding'}


def test_module_persistence_scoping_conflicts_and_patch(spacecraft_api):
    call, session, connection = spacecraft_api
    craft = call('POST', '', {'name': '  Explorer  ', 'manufacturer': 'Manufacturer', 'manufactured_year': 2026, 'maximum_crew_capacity': 6}, 201)
    assert craft['name'] == 'Explorer'
    assert craft['maximum_crew_capacity'] == 6
    assert call('GET', f"/{craft['id']}")['maximum_crew_capacity'] == 6
    other = call('POST', '', {'name': 'Second spacecraft'}, 201)
    base = f"/{craft['id']}/modules"
    module = call('POST', base, {'name': '  Crew cabin  ', 'code': ' crew-cabin ', 'is_pressurized': True, 'is_habitable': False, 'pressurized_volume_m3': 32, 'technical_specifications': specification()}, 201)
    path = f"{base}/{module['id']}"
    assert module['code'] == 'crew-cabin'
    assert module['spacecraft_id'] == craft['id']
    assert call('GET', path)['technical_specifications']['materials'][0]['specification'] == '7075-T6'
    call('POST', base, {'name': 'Duplicate', 'code': 'crew-cabin'}, 409)
    call('POST', f"/{other['id']}/modules", {'name': 'Allowed', 'code': 'crew-cabin'}, 201)
    for method, payload in [('GET', None), ('PATCH', {'name': 'Wrong parent'}), ('DELETE', None)]:
        call(method, f"/{other['id']}/modules/{module['id']}", payload, 404)
    call('PATCH', path, {'spacecraft_id': other['id']}, 422)
    updated = call('PATCH', path, {'purpose': 'Habitation'})
    assert updated['is_habitable'] is False
    assert updated['technical_specifications'] == module['technical_specifications']
    updated = call('PATCH', path, {'is_habitable': None, 'pressurized_volume_m3': None, 'technical_specifications': {'shielding': 'Revised shielding'}})
    assert updated['is_pressurized'] is True
    assert updated['is_habitable'] is None
    assert updated['pressurized_volume_m3'] is None
    assert updated['technical_specifications']['materials'] is None
    assert updated['technical_specifications']['shielding'] == 'Revised shielding'
    call('PATCH', path, {'technical_specifications': None})
    assert call('GET', path)['technical_specifications'] is None
    call('DELETE', f"/{craft['id']}", expected=409)
    assert call('GET', f"/{craft['id']}")['name'] == 'Explorer'
    call('PATCH', f"/{craft['id']}", {'manufacturer': None, 'maximum_crew_capacity': None})
    assert call('GET', f"/{craft['id']}")['manufacturer'] is None
    assert call('GET', f"/{craft['id']}")['maximum_crew_capacity'] is None
    call('DELETE', path, expected=204)
    call('DELETE', f"/{craft['id']}", expected=204)
    call('GET', f"/{craft['id']}", expected=404)


def test_search_pagination_and_permissions(spacecraft_api):
    call, session, connection = spacecraft_api
    first = call('POST', '', {'name': 'Explorer 100%', 'model': 'Orbiter', 'manufacturer': 'Example Aerospace'}, 201, actor='admin')
    call('POST', '', {'name': 'Explorer B'}, 201)
    for search in ('orbiter', 'aerospace', '100%'):
        found = call('GET', f'?search={search}&per_page=1')
        assert found['pagination']['total'] == 1
        assert found['data'][0]['id'] == first['id']
    assert call('GET', '?per_page=1')['pagination']['has_next'] is True
    assert call('GET', '?page=2&per_page=1')['pagination']['has_previous'] is True
    base = f"/{first['id']}/modules"
    module = call('POST', base, {'code': 'lab-100%', 'name': 'Science laboratory'}, 201)
    for search in ('science', 'lab-100%'):
        assert call('GET', base + f'?search={search}')['data'][0]['id'] == module['id']
    for actor in ('astronaut', 'outsider'):
        call('GET', '', actor=actor)
        call('POST', '', {'name': 'Denied'}, 403, actor=actor)
        call('PATCH', f"/{first['id']}", {'name': 'Denied'}, 403, actor=actor)
        call('DELETE', f"/{first['id']}", expected=403, actor=actor)
        call('POST', base, {'code': 'denied', 'name': 'Denied'}, 403, actor=actor)
        call('PATCH', f"{base}/{module['id']}", {'name': 'Denied'}, 403, actor=actor)
        call('DELETE', f"{base}/{module['id']}", expected=403, actor=actor)
    call('GET', '', expected=401, actor=None)
    call('GET', '/999999999/modules', expected=404)
    call('POST', '/999999999/modules', {'code': 'missing', 'name': 'Missing'}, 404)


@pytest.mark.parametrize('values', [
    {'name': ' '}, {'name': None}, {'manufactured_year': 0}, {'manufactured_year': -1},
    {'manufactured_year': 32768}, {'manufactured_year': 2026.5}, {'manufactured_year': 2026.0},
    {'maximum_crew_capacity': 0}, {'maximum_crew_capacity': -1}, {'maximum_crew_capacity': 6.5}, {'maximum_crew_capacity': True}, {'maximum_crew_capacity': 2147483648},
    {'manufactured_year': True}, {'technical_reference_url': 'ftp://example.com/file'},
    {'technical_reference_url': 'not-a-url'},
])
def test_invalid_spacecraft_fields(spacecraft_api, values):
    call, session, connection = spacecraft_api
    call('POST', '', {'name': 'Invalid', **values}, 422)


@pytest.mark.parametrize('values', [
    {'code': ' '}, {'name': ' '}, {'manufactured_year': 0}, {'manufactured_year': 32768},
    {'pressurized_volume_m3': 0}, {'pressurized_volume_m3': -1},
    {'technical_specifications': {'dimensions_m': {'length': 0}}},
    {'technical_specifications': {'dimensions_m': {'width': -1}}},
    {'technical_specifications': {'dimensions_m': {'height': 0}}},
    {'technical_specifications': {'dimensions_m': {'diameter': -1}}},
    {'technical_specifications': {'dry_mass_kg': 0}},
    {'technical_specifications': {'materials': [{'component': 'shell'}]}},
    {'technical_specifications': {'materials': [{'component': ' ', 'material': 'Alloy'}]}},
    {'technical_specifications': {'materials': [{'component': 'shell', 'material': ' '}]}},
    {'technical_reference_url': 'ftp://example.com/file'},
])
def test_invalid_module_fields(spacecraft_api, values):
    call, session, connection = spacecraft_api
    craft = call('POST', '', {'name': 'Validation spacecraft'}, 201)
    call('POST', f"/{craft['id']}/modules", {'name': 'Invalid', 'code': 'module', **values}, 422)


def test_patch_required_fields_and_duplicate_edit(spacecraft_api):
    call, session, connection = spacecraft_api
    craft = call('POST', '', {'name': 'Spacecraft', 'technical_reference_url': 'https://example.com/specification'}, 201)
    call('PATCH', f"/{craft['id']}", {'name': None}, 422)
    base = f"/{craft['id']}/modules"
    first = call('POST', base, {'name': 'First', 'code': 'first'}, 201)
    second = call('POST', base, {'name': 'Second', 'code': 'second'}, 201)
    path = f"{base}/{second['id']}"
    call('PATCH', path, {'code': 'first', 'purpose': 'Must roll back'}, 409)
    assert call('GET', path)['purpose'] is None
    assert call('GET', path)['code'] == 'second'
    for field in ('name', 'code'):
        call('PATCH', path, {field: None}, 422)
    call('PATCH', f"/{craft['id']}", {'technical_reference_url': None})
    assert call('GET', f"/{craft['id']}")['technical_reference_url'] is None


def test_database_constraints(spacecraft_api):
    call, session, connection = spacecraft_api
    craft = call('POST', '', {'name': 'Database spacecraft'}, 201)
    call('POST', f"/{craft['id']}/modules", {'name': 'Module', 'code': 'module'}, 201)
    statements = [
        ("INSERT INTO spacecraft_modules (spacecraft_id, name, code) VALUES (:id, 'Duplicate', 'module')", {'id': craft['id']}),
        ('DELETE FROM spacecraft WHERE id = :id', {'id': craft['id']}),
        ("INSERT INTO spacecraft_modules (spacecraft_id, name, code, pressurized_volume_m3) VALUES (:id, 'Invalid', 'invalid', 0)", {'id': craft['id']}),
        ("INSERT INTO spacecraft (name, manufactured_year) VALUES ('Invalid year', 0)", {}),
        ("INSERT INTO spacecraft (name) VALUES (' ')", {}),
        ("INSERT INTO spacecraft (name, maximum_crew_capacity) VALUES ('Invalid capacity', 0)", {}),
    ]
    for statement, params in statements:
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(text(statement), params)
                session.flush()
    assert call('GET', f"/{craft['id']}")['name'] == 'Database spacecraft'
    if connection.dialect.name == 'postgresql':
        columns = {column['name']: str(column['type']) for column in inspect(connection).get_columns('spacecraft_modules')}
        assert columns['technical_specifications'] == 'JSONB'
        assert columns['manufactured_year'] == 'SMALLINT'
        assert columns['pressurized_volume_m3'] == 'NUMERIC'
