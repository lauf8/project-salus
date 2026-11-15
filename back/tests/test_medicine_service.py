from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.models.notifications import HealthNotification
from app.models.mission_risks import MissionRiskPlan, MissionRiskEvaluation, MissionRiskAlert, MissionRiskAction, MissionOccurrence
from app.models.nutrition import FoodProduct
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertEvent, HealthAlertObservation, HealthAlertSettings
from app.models.medicines import ActiveIngredient, CrewMemberAllergy, Medicine, MedicineActiveIngredient
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.models.spacecraft import Spacecraft
from app.schemas.medicines import AllergyUpdate, MedicineCreate, MedicinePatch, NameInput
from app.services.medicine_service import MedicineService


@pytest.fixture
def records():
    engine = create_engine('sqlite://')

    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')

    models = [Spacecraft, User, Mission, MissionMember, ActiveIngredient, Medicine, MedicineActiveIngredient, CrewMemberAllergy, HealthObservation, HealthAlertSettings, HealthAlert, HealthAlertObservation, HealthAlertEvent, FoodProduct, MissionRiskPlan, MissionRiskEvaluation, MissionRiskAlert, MissionRiskAction, MissionOccurrence, HealthNotification]
    SQLModel.metadata.create_all(engine, tables=[model.__table__ for model in models])
    with Session(engine) as session:
        doctor = User(name='Doctor', email='doctor@fictional.test', hashed_password='fictional', is_physician=True)
        astronaut = User(name='Astronaut', email='astronaut@fictional.test', hashed_password='fictional', is_astronaut=True)
        outsider = User(name='Outsider', email='outsider@fictional.test', hashed_password='fictional', is_physician=True)
        session.add_all([doctor, astronaut, outsider])
        mission = Mission(name='Fictional mission', planned_launch_at=datetime.now(timezone.utc))
        session.add(mission)
        session.flush()
        session.add_all([MissionMember(mission_id=mission.id, user_id=doctor.id, role='flight_surgeon'), MissionMember(mission_id=mission.id, user_id=astronaut.id, role='astronaut')])
        session.commit()
        yield session, doctor, astronaut, outsider, mission
    engine.dispose()


def test_composition_crud_and_atomic_validation(records):
    session, doctor, astronaut, outsider, mission = records
    service = MedicineService(session, doctor)
    first = service.save_ingredient(NameInput(name='Ingredient A'))
    second = service.save_ingredient(NameInput(name='Ingredient B'))
    medicine = service.save_medicine(MedicineCreate(name='  Combination  ', active_ingredient_ids=[first.id, second.id]))
    assert medicine.name == 'Combination'
    assert [row.id for row in medicine.active_ingredients] == [first.id, second.id]
    with pytest.raises(HTTPException) as error:
        service.save_medicine(MedicinePatch(name='Invalid update', active_ingredient_ids=[999999]), medicine.id)
    assert error.value.status_code == 422
    assert service.get_medicine(medicine.id) == medicine
    medicine = service.save_medicine(MedicinePatch(active_ingredient_ids=[second.id]), medicine.id)
    assert [row.id for row in medicine.active_ingredients] == [second.id]
    with pytest.raises(HTTPException) as error:
        service.delete_catalog(ActiveIngredient, second.id)
    assert error.value.status_code == 409
    service.delete_catalog(ActiveIngredient, first.id)
    service.delete_catalog(Medicine, medicine.id)
    service.delete_catalog(ActiveIngredient, second.id)
    assert service.list_catalog(Medicine, None, 1, 20)['pagination']['total'] == 0


def test_screening_transitions_and_atomic_allergies(records):
    session, doctor, astronaut, outsider, mission = records
    service = MedicineService(session, doctor)
    astronaut_id, mission_id = astronaut.id, mission.id
    initial = service.get_allergies(astronaut_id, mission_id)
    assert initial['allergy_screening_completed'] is False
    assert initial['active_ingredients'] == []
    ingredient = service.save_ingredient(NameInput(name='Allergen'))
    record = service.update_allergies(astronaut_id, mission_id, AllergyUpdate(allergy_screening_completed=False, active_ingredient_ids=[ingredient.id]))
    assert record['allergy_screening_completed'] is False
    assert record['active_ingredients'][0].id == ingredient.id
    with pytest.raises(HTTPException) as error:
        service.delete_catalog(ActiveIngredient, ingredient.id)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        service.update_allergies(astronaut_id, mission_id, AllergyUpdate(allergy_screening_completed=True, active_ingredient_ids=[999999]))
    assert service.get_allergies(astronaut_id, mission_id)['allergy_screening_completed'] is False
    assert service.get_allergies(astronaut_id, mission_id)['active_ingredients'][0].id == ingredient.id
    record = service.update_allergies(astronaut_id, mission_id, AllergyUpdate(allergy_screening_completed=True, active_ingredient_ids=[]))
    assert record['allergy_screening_completed'] is True
    assert record['active_ingredients'] == []
    assert MedicineService(session, astronaut).get_allergies(astronaut_id, None)['can_edit'] is False
    service.delete_catalog(ActiveIngredient, ingredient.id)


def test_search_pagination_and_permissions(records):
    session, doctor, astronaut, outsider, mission = records
    service = MedicineService(session, doctor)
    for name in ('Ingredient A', 'Ingredient B', '100% ingredient'):
        service.save_ingredient(NameInput(name=name))
    page = service.list_catalog(ActiveIngredient, 'ingredient', 1, 1)
    assert page['pagination']['total'] == 3
    assert page['pagination']['has_next'] is True
    assert service.list_catalog(ActiveIngredient, '%', 1, 20)['pagination']['total'] == 1
    assert service.list_catalog(ActiveIngredient, 'ingredient', 2, 1)['data'][0].id != page['data'][0].id
    for actor in (astronaut, outsider):
        with pytest.raises(HTTPException) as error:
            MedicineService(session, actor).save_ingredient(NameInput(name='Denied'))
        assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        MedicineService(session, outsider).get_allergies(astronaut.id, mission.id)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        MedicineService(session, astronaut).update_allergies(astronaut.id, None, AllergyUpdate(allergy_screening_completed=True))
    assert error.value.status_code == 403


def test_names_duplicate_links_and_null_updates():
    for name in ('', '   '):
        with pytest.raises(ValidationError):
            NameInput(name=name)
        with pytest.raises(ValidationError):
            MedicineCreate(name=name)
    for ids in ([1, 1], [-1], [0]):
        with pytest.raises(ValidationError):
            MedicineCreate(name='Medicine', active_ingredient_ids=ids)
        with pytest.raises(ValidationError):
            AllergyUpdate(allergy_screening_completed=True, active_ingredient_ids=ids)
    with pytest.raises(ValidationError):
        MedicinePatch(name=None)
    with pytest.raises(ValidationError):
        MedicinePatch(active_ingredient_ids=None)
