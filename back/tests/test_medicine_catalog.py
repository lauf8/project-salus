from copy import deepcopy

import pytest
from sqlalchemy import func
from sqlmodel import select

from app.models.medicines import ActiveIngredient, Medicine, MedicineActiveIngredient
from app.schemas.medicines import MedicineCreate, MedicinePatch
from app.services.medicine_service import MedicineService
from scripts.seed_medicines import load_catalog, seed_catalog
from tests.test_medicine_service import records


def count(session, model):
    return session.exec(select(func.count()).select_from(model)).one()


def test_catalog_counts_compositions_and_idempotency(records):
    session, doctor, astronaut, outsider, mission = records
    catalog = load_catalog()
    assert all(sum(market in entry['markets'] for entry in catalog['medicines']) == 100 for market in ('US', 'BR'))
    result = seed_catalog(session, catalog)
    session.commit()
    medicine_count, ingredient_count = count(session, Medicine), count(session, ActiveIngredient)
    assert medicine_count == len(catalog['medicines']) == 161
    assert result['medicines_created'] == medicine_count
    assert result['ingredients_created'] == ingredient_count
    assert count(session, MedicineActiveIngredient) == sum(len(entry['active_ingredients']) for entry in catalog['medicines'])
    result = seed_catalog(session, catalog)
    session.commit()
    assert result['medicines_created'] == result['ingredients_created'] == 0
    assert result['medicines_reused'] == medicine_count
    assert count(session, Medicine) == medicine_count
    assert count(session, ActiveIngredient) == ingredient_count
    combination = session.exec(select(Medicine).where(Medicine.name == 'Amoxicillin + Clavulanic acid')).one()
    assert len(MedicineService(session, doctor).get_medicine(combination.id).active_ingredients) == 2


def test_seed_preserves_manual_indications_and_rejects_composition_changes(records):
    session, doctor, astronaut, outsider, mission = records
    catalog = load_catalog()
    seed_catalog(session, catalog)
    session.commit()
    medicine = session.exec(select(Medicine).where(Medicine.name == 'Metformin')).one()
    medicine.main_indications = 'Description revised by the clinical team'
    session.add(medicine)
    session.commit()
    seed_catalog(session, catalog)
    session.commit()
    assert session.get(Medicine, medicine.id).main_indications == 'Description revised by the clinical team'
    altered = deepcopy(catalog)
    altered['medicines'][0]['active_ingredients'] = ['New conflicting ingredient']
    with pytest.raises(ValueError):
        seed_catalog(session, altered)
    session.rollback()
    assert not session.exec(select(ActiveIngredient).where(ActiveIngredient.name == 'New conflicting ingredient')).first()


def test_main_indications_create_patch_preserve_and_clear(records):
    session, doctor, astronaut, outsider, mission = records
    service = MedicineService(session, doctor)
    created = service.save_medicine(MedicineCreate(name='Medicine', main_indications='Dor e febre.'))
    assert created.main_indications == 'Dor e febre.'
    updated = service.save_medicine(MedicinePatch(name='Renamed'), created.id)
    assert updated.main_indications == 'Dor e febre.'
    updated = service.save_medicine(MedicinePatch(main_indications='New indication'), created.id)
    assert updated.main_indications == 'New indication'
    updated = service.save_medicine(MedicinePatch(main_indications=None), created.id)
    assert updated.main_indications is None
