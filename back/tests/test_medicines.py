from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models.notifications import HealthNotification
from app.models.mission_risks import MissionRiskPlan, MissionRiskEvaluation, MissionRiskAlert, MissionRiskAction, MissionOccurrence
from app.models.nutrition import FoodProduct
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertEvent, HealthAlertObservation, HealthAlertSettings
from app.models.medicines import ActiveIngredient, CrewMemberAllergy, Medicine, MedicineActiveIngredient
from app.models.preflight import Mission, MissionMember
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.models.spacecraft import Spacecraft
from tests.public_identity import public_headers


@pytest.fixture
def catalog_api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')

    models = [Spacecraft, User, RevokedToken, Mission, MissionMember, ActiveIngredient, Medicine, MedicineActiveIngredient, CrewMemberAllergy, HealthObservation, HealthAlertSettings, HealthAlert, HealthAlertObservation, HealthAlertEvent, FoodProduct, MissionRiskPlan, MissionRiskEvaluation, MissionRiskAlert, MissionRiskAction, MissionOccurrence, HealthNotification]
    SQLModel.metadata.create_all(engine, tables=[model.__table__ for model in models])
    with Session(engine) as session:
        people = {}
        for name in ('doctor', 'astronaut', 'outsider', 'admin'):
            user = User(name=name, email=f'{name}@fictional.test', hashed_password='fictional', is_astronaut=name == 'astronaut', is_physician=name != 'astronaut')
            session.add(user)
            session.flush()
            people[name] = user.id
        mission = Mission(name='Fictional mission', planned_launch_at=datetime.now(timezone.utc))
        session.add(mission)
        session.flush()
        for name, role in [('doctor', 'flight_surgeon'), ('astronaut', 'astronaut'), ('admin', 'mission_admin')]:
            session.add(MissionMember(mission_id=mission.id, user_id=people[name], role=role))
        session.commit()
        mission_id = mission.id

        def get_test_session():
            yield session

        app.dependency_overrides[get_session] = get_test_session
        try:
            with TestClient(app) as client:
                def call(actor, method, path, body=None, expected=200):
                    headers = public_headers(engine, people[actor]) if actor else {}
                    response = client.request(method, '/v1' + path, json=body, headers=headers)
                    assert response.status_code == expected, response.text
                    return response.json() if response.content else None
                yield call, people, mission_id
        finally:
            app.dependency_overrides.clear()
    engine.dispose()


def ingredient(call, name):
    return call('doctor', 'POST', '/active-ingredients', {'name': name}, 201)['id']


def test_medicine_composition_crud_search_and_pagination(catalog_api):
    call, people, mission_id = catalog_api
    first, second = ingredient(call, 'Ingredient A'), ingredient(call, 'Ingredient B')
    created = call('doctor', 'POST', '/medicines', {'name': '  Combination  ', 'active_ingredient_ids': [first, second], 'main_indications': 'Indicação de teste'}, 201)
    path = f"/medicines/{created['id']}"
    assert created['name'] == 'Combination'
    assert created['main_indications'] == 'Indicação de teste'
    assert [row['id'] for row in created['active_ingredients']] == [first, second]
    result = call('astronaut', 'GET', '/medicines?search=comb&per_page=1')
    assert result['pagination']['total'] == 1
    assert result['data'][0] == created
    updated = call('doctor', 'PATCH', path, {'active_ingredient_ids': [second]})
    assert [row['id'] for row in updated['active_ingredients']] == [second]
    assert call('doctor', 'GET', path) == updated
    call('doctor', 'DELETE', f'/active-ingredients/{second}', expected=409)
    call('doctor', 'PATCH', f'/active-ingredients/{second}', {'name': 'Updated ingredient'})
    assert call('doctor', 'GET', f'/active-ingredients/{second}')['name'] == 'Updated ingredient'
    listing = call('doctor', 'GET', '/active-ingredients?per_page=1')
    assert listing['pagination']['has_next']
    assert len(call('doctor', 'GET', '/active-ingredients?page=2&per_page=1')['data']) == 1
    call('doctor', 'DELETE', path, expected=204)
    call('doctor', 'GET', path, expected=404)
    call('doctor', 'DELETE', f'/active-ingredients/{second}', expected=204)


def test_validation_and_atomic_composition(catalog_api):
    call, people, mission_id = catalog_api
    first = ingredient(call, 'Ingredient A')
    for name in ('', '   '):
        call('doctor', 'POST', '/active-ingredients', {'name': name}, 422)
        call('doctor', 'POST', '/medicines', {'name': name}, 422)
    for ids in ([first, first], [first, 999999], [-1]):
        call('doctor', 'POST', '/medicines', {'name': 'Invalid', 'active_ingredient_ids': ids}, 422)
    assert call('doctor', 'GET', '/medicines')['pagination']['total'] == 0
    medicine = call('doctor', 'POST', '/medicines', {'name': 'Original', 'active_ingredient_ids': [first]}, 201)
    path = f"/medicines/{medicine['id']}"
    for ids in ([first, first], [999999]):
        call('doctor', 'PATCH', path, {'name': 'Changed', 'active_ingredient_ids': ids}, 422)
        assert call('doctor', 'GET', path) == medicine
    call('doctor', 'PATCH', path, {'name': None}, 422)
    call('doctor', 'PATCH', path, {'active_ingredient_ids': None}, 422)
    call('doctor', 'GET', '/medicines?per_page=101', expected=422)
    call('doctor', 'GET', '/medicines?page=0', expected=422)
    call('doctor', 'PATCH', '/medicines/999999', {'name': 'Missing'}, 404)


def test_allergy_screening_and_protected_ingredient(catalog_api):
    call, people, mission_id = catalog_api
    path = f"/health/astronauts/{people['astronaut']}/allergies"
    scoped = path + f'?mission_id={mission_id}'
    record = call('astronaut', 'GET', path)
    assert record['allergy_screening_completed'] is False
    assert record['active_ingredients'] == []
    assert record['can_edit'] is False
    first = ingredient(call, 'Allergen')
    record = call('doctor', 'PUT', scoped, {'allergy_screening_completed': False, 'active_ingredient_ids': [first]})
    assert record['allergy_screening_completed'] is False
    assert record['active_ingredients'][0]['id'] == first
    assert record['can_edit'] is True
    call('doctor', 'DELETE', f'/active-ingredients/{first}', expected=409)
    for ids in ([first, first], [999999]):
        call('doctor', 'PUT', scoped, {'allergy_screening_completed': True, 'active_ingredient_ids': ids}, 422)
        assert call('doctor', 'GET', scoped) == record
    record = call('doctor', 'PUT', scoped, {'allergy_screening_completed': True, 'active_ingredient_ids': [first]})
    assert record['allergy_screening_completed'] is True
    record = call('doctor', 'PUT', scoped, {'allergy_screening_completed': True, 'active_ingredient_ids': []})
    assert record['allergy_screening_completed'] is True
    assert record['active_ingredients'] == []
    assert call('astronaut', 'GET', path)['allergy_screening_completed'] is True
    call('doctor', 'DELETE', f'/active-ingredients/{first}', expected=204)
    record = call('doctor', 'PUT', scoped, {'allergy_screening_completed': False, 'active_ingredient_ids': []})
    assert record['allergy_screening_completed'] is False


def test_catalog_and_clinical_permissions(catalog_api):
    call, people, mission_id = catalog_api
    first = ingredient(call, 'Allergen')
    medicine = call('admin', 'POST', '/medicines', {'name': 'Medicine'}, 201)
    for actor in ('astronaut', 'outsider'):
        call(actor, 'POST', '/active-ingredients', {'name': 'Denied'}, 403)
        call(actor, 'PATCH', f"/medicines/{medicine['id']}", {'name': 'Denied'}, 403)
        call(actor, 'DELETE', f'/active-ingredients/{first}', expected=403)
    call(None, 'GET', '/active-ingredients', expected=200)
    path = f"/health/astronauts/{people['astronaut']}/allergies"
    payload = {'allergy_screening_completed': True, 'active_ingredient_ids': []}
    for actor in ('outsider', 'admin'):
        call(actor, 'GET', path + f'?mission_id={mission_id}', expected=403)
        call(actor, 'PUT', path + f'?mission_id={mission_id}', payload, 403)
    call('astronaut', 'PUT', path, payload, 403)
    call('doctor', 'GET', path, expected=403)
    call('doctor', 'GET', '/health/astronauts/999999/allergies', expected=404)


def test_migration_marks_existing_records_pending():
    from pathlib import Path
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    migration_path = Path(__file__).resolve().parents[1] / 'alembic/versions/a8293b4c5d6e_add_medicines_and_allergies.py'
    spec = importlib.util.spec_from_file_location('medicines_migration', migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO users (id) VALUES (1)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(text('SELECT allergy_screening_completed FROM users WHERE id=1')).scalar_one() == 0
            connection.execute(text("INSERT INTO active_ingredients (id, name) VALUES (1, 'Allergen')"))
            connection.execute(text('INSERT INTO crew_member_allergies (crew_member_id, active_ingredient_id) VALUES (1, 1)'))
            with pytest.raises(IntegrityError):
                connection.execute(text('INSERT INTO crew_member_allergies (crew_member_id, active_ingredient_id) VALUES (1, 1)'))
            migration.downgrade()
    engine.dispose()
