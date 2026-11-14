from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import engine
from app.models.nutrition import FoodProduct, FoodStockMovement, MealLog, MissionFoodLot
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.nutrition import MealCreate
from app.services.nutrition_service import NutritionService
from tests.test_nutrition import water_payload


pytestmark = pytest.mark.skipif(os.getenv('NUTRITION_POSTGRES_TESTS') != '1', reason='Requires PostgreSQL with permission to create isolated validation schemas')


def test_concurrent_consumption_cannot_overdraw_stock():
    schema = 'nutrition_' + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    isolated = create_engine(engine.url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        SQLModel.metadata.create_all(isolated, tables=[table for table in SQLModel.metadata.sorted_tables if table.name not in {'knowledge_documents', 'knowledge_passages'}])
        now = datetime.now(timezone.utc)
        with Session(isolated) as session:
            user = User(name='Astronaut', email='concurrent@nutrition.test', hashed_password='fictional', is_astronaut=True)
            mission = Mission(name='Concurrent stock', planned_launch_at=now)
            product = FoodProduct(**water_payload())
            session.add_all([user, mission, product])
            session.flush()
            member = MissionMember(mission_id=mission.id, user_id=user.id, role='astronaut')
            lot = MissionFoodLot(mission_id=mission.id, food_product_id=product.id, lot_code='Limited water', expiration_date=now.date() + timedelta(days=1), initial_quantity=500, remaining_quantity=500, stock_unit='ml')
            session.add_all([member, lot])
            session.flush()
            session.add(FoodStockMovement(lot_id=lot.id, quantity=500, stock_unit='ml', movement_type='initial', purpose='receipt', recorded_by_user_id=user.id))
            session.commit()
            user_id, mission_id, member_id, product_id, lot_id = user.id, mission.id, member.id, product.id, lot.id
        barrier = Barrier(2)
        def consume():
            with Session(isolated) as session:
                user = session.get(User, user_id)
                barrier.wait(timeout=10)
                try:
                    NutritionService(session, user).create_meal(mission_id, MealCreate(mission_member_id=member_id, consumed_at=now, meal_type='hydration', client_request_id=uuid4(), items=[{'food_product_id': product_id, 'lot_id': lot_id, 'consumed_quantity': '300', 'consumed_unit': 'ml', 'consumed_basis': 'stored'}]))
                    return 201
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: consume(), range(2)))
        assert sorted(results) == [201, 409]
        with Session(isolated) as session:
            assert session.get(MissionFoodLot, lot_id).remaining_quantity == 200
            assert session.exec(select(func.count()).select_from(MealLog)).one() == 1
            assert session.exec(select(func.sum(FoodStockMovement.quantity))).one() == 200
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))


def test_nutrition_migration_preserves_existing_data_and_seeds_water():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / 'alembic/versions/e8cd3456f708_add_mission_nutrition.py'
    spec = importlib.util.spec_from_file_location('nutrition_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = 'nutrition_migration_' + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)'))
            connection.execute(text('CREATE TABLE missions (id INTEGER PRIMARY KEY, name TEXT NOT NULL)'))
            connection.execute(text('CREATE TABLE mission_members (id INTEGER PRIMARY KEY, mission_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL, UNIQUE (id, mission_id))'))
            connection.execute(text("INSERT INTO users VALUES (1, 'Existing astronaut')"))
            connection.execute(text("INSERT INTO missions VALUES (1, 'Existing mission')"))
            connection.execute(text("INSERT INTO mission_members VALUES (1, 1, 1, 'astronaut')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            water = connection.execute(text('SELECT name, category, is_plain_water, reference_unit, energy_kcal, protein_g, carbohydrate_g, fat_g FROM food_products')).one()
            assert tuple(water[:4]) == ('Water', 'beverage', True, 'ml')
            assert list(water[4:]) == [0, 0, 0, 0]
            assert connection.execute(text('SELECT name FROM missions')).scalar_one() == 'Existing mission'
            assert connection.execute(text('SELECT role FROM mission_members')).scalar_one() == 'astronaut'
            migration.downgrade()
            assert connection.execute(text('SELECT name FROM users')).scalar_one() == 'Existing astronaut'
        finally:
            transaction.rollback()
