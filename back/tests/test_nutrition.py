from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.main import app
from app.models.nutrition import FoodStockMovement, MealLog, MealLogItem, MissionFoodLot
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from tests.public_identity import public_headers


@pytest.fixture
def nutrition_api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nutrition.db'}", connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine, tables=[table for table in SQLModel.metadata.sorted_tables if table.name not in {'knowledge_documents', 'knowledge_passages'}])
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        users = {}
        for name in ('admin', 'doctor', 'astronaut', 'other', 'outsider'):
            user = User(name=name, email=f'{name}@nutrition.test', hashed_password='fictional', is_physician=name in ('admin', 'doctor'), is_astronaut=name in ('astronaut', 'other', 'outsider'))
            session.add(user)
            session.flush()
            users[name] = user.id
        missions = [Mission(name=name, planned_launch_at=now) for name in ('Mission', 'Other mission')]
        session.add_all(missions)
        session.flush()
        mission_ids = [mission.id for mission in missions]
        members = {}
        for name, role in (('admin', 'mission_admin'), ('doctor', 'flight_surgeon'), ('astronaut', 'astronaut'), ('other', 'astronaut')):
            member = MissionMember(mission_id=mission_ids[0], user_id=users[name], role=role)
            session.add(member)
            session.flush()
            members[name] = member.id
        session.add(MissionMember(mission_id=mission_ids[1], user_id=users['admin'], role='mission_admin'))
        session.commit()
    def get_test_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = get_test_session
    try:
        with TestClient(app) as client:
            def call(method, path, body=None, expected=200, actor='admin'):
                response = client.request(method, '/v1' + path, json=body, headers=public_headers(engine, users[actor]))
                assert response.status_code == expected, response.text
                return response.json() if response.content else None
            yield call, engine, mission_ids, members, now
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def product_payload(name='Freeze dried meal', **values):
    return {'name': name, 'category': 'food', 'is_plain_water': False, 'preservation_method': 'freeze_dried', 'physical_form': 'solid',
            'reference_quantity': '100', 'reference_unit': 'g', 'reference_basis': 'stored', 'unit_equivalences': [],
            'energy_kcal': '400', 'protein_g': '20', 'carbohydrate_g': '60', 'fat_g': '10', 'fiber_g': None, 'sodium_mg': '100',
            'preparation_method': 'rehydrate', 'preparation_water_ml': '250', **values}


def water_payload():
    return product_payload('Water', category='beverage', is_plain_water=True, physical_form='liquid', preservation_method='natural_form',
                           reference_unit='ml', energy_kcal='0', protein_g='0', carbohydrate_g='0', fat_g='0', fiber_g='0', sodium_mg='0', preparation_method='ready_to_consume', preparation_water_ml=None)


@pytest.fixture
def nutrition_case(nutrition_api):
    call, engine, missions, members, now = nutrition_api
    base = f'/missions/{missions[0]}'
    food = call('POST', '/food-products', product_payload(unit_equivalences=[{'unit': 'ml', 'basis': 'prepared', 'quantity_per_reference': '250'}]), 201)
    water = call('POST', '/food-products', water_payload(), 201)
    drink = call('POST', '/food-products', product_payload('Juice', category='beverage', physical_form='liquid', preservation_method='fresh',
                 reference_unit='ml', energy_kcal='40', protein_g='0', carbohydrate_g='10', fat_g='0', fiber_g='0', preparation_method='ready_to_consume', preparation_water_ml=None), 201)
    def lot(product, code, quantity='500', days=10, mission=None, unit=None):
        return call('POST', f'/missions/{mission or missions[0]}/food-lots', {'food_product_id': product['id'], 'lot_code': code,
                     'expiration_date': (now.date() + timedelta(days=days)).isoformat(), 'initial_quantity': quantity,
                     'stock_unit': unit or product['reference_unit']}, 201)
    late = lot(food, 'Late', days=30)
    early = lot(food, 'Early')
    water_lot = lot(water, 'Water', '5000')
    drink_lot = lot(drink, 'Juice', '2000')
    def item(product, lot, quantity, **values):
        return {'food_product_id': product['id'], 'lot_id': lot['id'], 'consumed_quantity': quantity,
                'consumed_unit': product['reference_unit'], 'consumed_basis': product['reference_basis'], **values}
    def meal(items, **values):
        return {'mission_member_id': members['astronaut'], 'consumed_at': now.isoformat(), 'meal_type': 'lunch', 'items': items, **values}
    return dict(call=call, engine=engine, missions=missions, members=members, now=now, base=base, food=food, water=water, drink=drink,
                late=late, early=early, water_lot=water_lot, drink_lot=drink_lot, lot=lot, item=item, meal=meal)


def balance(case, lot):
    with Session(case['engine']) as session:
        return session.get(MissionFoodLot, lot['id']).remaining_quantity


def editable(meal):
    return {'mission_member_id': meal['mission_member_id'], 'consumed_at': meal['consumed_at'], 'meal_type': meal['meal_type'],
            'notes': meal['notes'], 'expected_revision': meal['revision'], 'items': [{key: item[key] for key in (
                'id', 'food_product_id', 'lot_id', 'consumed_quantity', 'consumed_unit', 'consumed_basis', 'stock_quantity_used', 'preparation_water_used_ml', 'preparation_water_lot_id')} for item in meal['items']]}


def test_two_lots_nutrients_packaging_and_separate_hydration(nutrition_case):
    c = nutrition_case
    listed = c['call']('GET', c['base'] + f"/food-lots?food_product_id={c['food']['id']}&status=usable")['data']
    assert [row['lot_code'] for row in listed] == ['Early', 'Late']
    items = [c['item'](c['food'], c['early'], '50', preparation_water_used_ml='125', preparation_water_lot_id=c['water_lot']['id']),
             c['item'](c['drink'], c['drink_lot'], '150', stock_quantity_used='200')]
    meal = c['call']('POST', c['base'] + '/meal-logs', c['meal'](items), 201, 'astronaut')
    assert meal['includes_plain_water'] is False
    assert Decimal(meal['totals']['nutrients']['energy_kcal']) == 260
    assert Decimal(meal['totals']['nutrients']['protein_g']) == 10
    assert Decimal(meal['totals']['nutrients']['carbohydrate_g']) == 45
    assert Decimal(meal['totals']['nutrients']['fat_g']) == 5
    assert meal['totals']['partial']['fiber_g'] is True
    assert balance(c, c['early']) == 450
    assert balance(c, c['late']) == 500
    assert balance(c, c['drink_lot']) == 1800
    assert balance(c, c['water_lot']) == 4875
    hydration = c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['water'], c['water_lot'], '250')], meal_type='hydration'), 201, 'astronaut')
    assert hydration['includes_plain_water'] is True
    assert hydration['totals']['partial']['protein_g'] is False
    assert Decimal(hydration['totals']['nutrients']['protein_g']) == 0
    daily = c['call']('GET', c['base'] + f"/nutrition/daily?mission_member_id={c['members']['astronaut']}&day={c['now'].date()}", actor='doctor')
    assert Decimal(daily['totals']['beverage_volume_ml']) == 400
    assert Decimal(daily['totals']['plain_water_volume_ml']) == 250
    assert Decimal(daily['totals']['preparation_water_used_ml']) == 125
    assert balance(c, c['water_lot']) == 4625


def test_rejected_expired_empty_wrong_mission_and_atomic_rollback(nutrition_case):
    c = nutrition_case
    expired = c['lot'](c['food'], 'Expired', days=-1)
    foreign = c['lot'](c['food'], 'Foreign', mission=c['missions'][1])
    for lot, expected in ((expired, 409), (foreign, 404)):
        c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], lot, '1')]), expected, 'astronaut')
    empty = c['lot'](c['food'], 'Empty', quantity='1')
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], empty, '1')]), 201, 'astronaut')
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], empty, '1')]), 409, 'astronaut')
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], c['early'], '50'), c['item'](c['drink'], c['drink_lot'], '9999')]), 409, 'astronaut')
    assert balance(c, c['early']) == 500
    with Session(c['engine']) as session:
        assert session.exec(select(func.count()).select_from(MealLog)).one() == 1


def test_utc_expiry_and_configurable_warning(nutrition_case, monkeypatch):
    c = nutrition_case
    monkeypatch.setenv('FOOD_EXPIRATION_WARNING_DAYS', '15')
    rows = c['call']('GET', c['base'] + '/food-lots?status=expiring_soon')['data']
    assert c['early']['id'] in [row['id'] for row in rows]
    assert c['late']['id'] not in [row['id'] for row in rows]
    expired = c['lot'](c['food'], 'Historic', days=-1)
    date = expired['expiration_date']
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], expired, '1')], consumed_at=date + 'T23:30:00-03:00'), 409, 'astronaut')
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], expired, '1')], consumed_at=date + 'T23:59:59+00:00'), 201, 'astronaut')


def test_registered_equivalences_only_and_prepared_product(nutrition_case):
    c = nutrition_case
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], c['early'], '50', consumed_unit='ml')]), 422, 'astronaut')
    c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], c['early'], '50', stock_quantity_used='49')]), 422, 'astronaut')
    meal = c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], c['early'], '125', consumed_unit='ml', consumed_basis='prepared')]), 201, 'astronaut')
    assert Decimal(meal['totals']['nutrients']['energy_kcal']) == 200
    assert balance(c, c['early']) == 450
    product = c['call']('POST', '/food-products', product_payload('Powder beverage', category='beverage', physical_form='powder', preservation_method='dehydrated', reference_basis='prepared', reference_unit='ml', reference_quantity='200', unit_equivalences=[{'unit': 'g', 'basis': 'stored', 'quantity_per_reference': '30'}]), 201)
    lot = c['lot'](product, 'Powder', '300', unit='g')
    meal = c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](product, lot, '100')]), 201, 'astronaut')
    assert Decimal(meal['items'][0]['stock_quantity_used']) == 15
    assert Decimal(meal['totals']['beverage_volume_ml']) == 100
    c['call']('POST', '/food-products', product_payload(is_plain_water=True), 422)


def test_edit_delete_snapshots_revisions_and_movement_history(nutrition_case):
    c = nutrition_case
    meal = c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['food'], c['early'], '50', preparation_water_used_ml='125', preparation_water_lot_id=c['water_lot']['id'])]), 201, 'astronaut')
    body = {key: value for key, value in c['food'].items() if key != 'id'}
    body['energy_kcal'] = '999'
    c['call']('PUT', f"/food-products/{c['food']['id']}", body)
    assert Decimal(c['call']('GET', c['base'] + f"/meal-logs/{meal['id']}", actor='astronaut')['items'][0]['nutrients']['energy_kcal']) == 200
    patch = editable(meal)
    patch['items'][0]['consumed_quantity'] = '75'
    patch['items'][0]['stock_quantity_used'] = '75'
    updated = c['call']('PUT', c['base'] + f"/meal-logs/{meal['id']}", patch, actor='astronaut')
    assert Decimal(updated['items'][0]['nutrients']['energy_kcal']) == 300
    assert balance(c, c['early']) == 425
    assert balance(c, c['water_lot']) == 4875
    c['call']('PUT', c['base'] + f"/meal-logs/{meal['id']}", patch, 409, 'astronaut')
    c['call']('DELETE', c['base'] + f"/meal-logs/{meal['id']}?expected_revision=1", expected=409, actor='astronaut')
    for _ in range(2):
        c['call']('DELETE', c['base'] + f"/meal-logs/{meal['id']}?expected_revision=2", expected=204, actor='astronaut')
    assert balance(c, c['early']) == 500
    assert balance(c, c['water_lot']) == 5000
    rows = c['call']('GET', c['base'] + f"/food-lots/{c['early']['id']}/movements")['data']
    assert len(rows) == 5
    assert sum(Decimal(row['quantity']) for row in rows) == 500
    with Session(c['engine']) as session:
        assert len(session.exec(select(MealLogItem)).all()) == 2
        assert all(not item.is_active for item in session.exec(select(MealLogItem)).all())


def test_permissions_membership_and_retry_idempotency(nutrition_case):
    c = nutrition_case
    payload = c['meal']([c['item'](c['water'], c['water_lot'], '100')], client_request_id=str(uuid4()))
    c['call']('POST', c['base'] + '/meal-logs', payload, 403)
    c['call']('POST', c['base'] + '/meal-logs', payload, 403, 'other')
    c['call']('POST', c['base'] + '/meal-logs', payload, 404, 'outsider')
    c['call']('POST', c['base'] + '/meal-logs', {**payload, 'mission_member_id': c['members']['admin']}, 404, 'doctor')
    first = c['call']('POST', c['base'] + '/meal-logs', payload, 201, 'doctor')
    second = c['call']('POST', c['base'] + '/meal-logs', payload, 201, 'doctor')
    assert first['id'] == second['id']
    assert balance(c, c['water_lot']) == 4900
    c['call']('POST', c['base'] + '/meal-logs', {**payload, 'notes': 'Changed request'}, 409, 'doctor')
    c['call']('POST', '/food-products', water_payload(), 403, 'astronaut')
    c['call']('GET', c['base'] + f"/meal-logs/{first['id']}", expected=403, actor='other')
    c['call']('GET', c['base'] + f"/food-lots/{c['water_lot']['id']}/movements", expected=403, actor='astronaut')
    c['call']('POST', c['base'] + '/food-lots', {'food_product_id': c['water']['id'], 'lot_code': 'Denied', 'expiration_date': c['water_lot']['expiration_date'], 'initial_quantity': '1', 'stock_unit': 'ml'}, 403, 'astronaut')


def test_prepared_snapshot_edit_and_membership_history_protection(nutrition_case):
    c = nutrition_case
    payload = c['meal']([c['item'](c['food'], c['early'], '125', consumed_unit='ml', consumed_basis='prepared')])
    meal = c['call']('POST', c['base'] + '/meal-logs', payload, 201, 'astronaut')
    patch = editable(meal)
    patch['notes'] = 'Snapshot preserved'
    updated = c['call']('PUT', c['base'] + f"/meal-logs/{meal['id']}", patch, actor='astronaut')
    assert Decimal(updated['totals']['nutrients']['energy_kcal']) == 200
    c['call']('PATCH', c['base'] + f"/members/{c['members']['astronaut']}", {'role': 'flight_surgeon'}, 409)
    c['call']('DELETE', c['base'] + f"/members/{c['members']['astronaut']}", expected=409)


def test_fractional_stock_and_unknown_beverage_volume(nutrition_case):
    c = nutrition_case
    meal = c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](c['water'], c['water_lot'], '0.100001')]), 201, 'astronaut')
    assert balance(c, c['water_lot']) == Decimal('4999.899999')
    assert Decimal(meal['totals']['plain_water_volume_ml']) == Decimal('0.100001')
    powder = c['call']('POST', '/food-products', product_payload('Dry beverage', category='beverage', physical_form='powder'), 201)
    lot = c['lot'](powder, 'Dry beverage')
    meal = c['call']('POST', c['base'] + '/meal-logs', c['meal']([c['item'](powder, lot, '10')]), 201, 'astronaut')
    assert Decimal(meal['totals']['beverage_volume_ml']) == 0
    assert meal['totals']['beverage_volume_partial'] is True
    assert meal['includes_plain_water'] is False
