import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.database import engine


pytestmark = pytest.mark.skipif(os.getenv('MISSION_POSTGRES_TESTS') != '1', reason='Requires an isolated PostgreSQL validation database')


def test_migration_preserves_existing_missions_and_spacecraft():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / 'alembic/versions/c6ab1234d5e6_link_missions_spacecraft.py'
    spec = importlib.util.spec_from_file_location('mission_spacecraft_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = 'migration_' + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            connection.execute(text('CREATE TABLE spacecraft (id INTEGER PRIMARY KEY, name TEXT NOT NULL)'))
            connection.execute(text('CREATE TABLE missions (id INTEGER PRIMARY KEY, name TEXT NOT NULL, planned_launch_at TIMESTAMPTZ NOT NULL, started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ)'))
            connection.execute(text("INSERT INTO spacecraft VALUES (1, 'Explorer')"))
            now = datetime.now(timezone.utc)
            connection.execute(text("INSERT INTO missions VALUES (1, 'Planned', :now, NULL, NULL), (2, 'Started', :now, :now, NULL), (3, 'Ended', :now, :now, :now)"), {'now': now})
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            rows = connection.execute(text('SELECT id, name, status, spacecraft_id, planned_launch_at FROM missions ORDER BY id')).all()
            assert [row.status for row in rows] == ['planned', 'in_progress', 'completed']
            assert all(row.spacecraft_id is None and row.planned_launch_at == now for row in rows)
            assert connection.execute(text('SELECT status FROM spacecraft')).scalar_one() == 'available'
            connection.execute(text('UPDATE missions SET spacecraft_id = 1 WHERE id = 1'))
            connection.execute(text("UPDATE spacecraft SET status = 'in_use' WHERE id IN (SELECT spacecraft_id FROM missions WHERE status != 'completed' AND spacecraft_id IS NOT NULL)"))
            assert connection.execute(text('SELECT status FROM spacecraft')).scalar_one() == 'in_use'
            migration.downgrade()
            assert connection.execute(text('SELECT count(*) FROM missions')).scalar_one() == 3
            assert connection.execute(text('SELECT name FROM spacecraft')).scalar_one() == 'Explorer'
        finally:
            transaction.rollback()


def test_crew_size_migration_preserves_and_counts_existing_astronauts():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / 'alembic/versions/d7bc2345e6f7_add_mission_crew_size.py'
    spec = importlib.util.spec_from_file_location('mission_crew_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = 'migration_' + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            connection.execute(text('CREATE TABLE missions (id INTEGER PRIMARY KEY, name TEXT NOT NULL)'))
            connection.execute(text('CREATE TABLE mission_members (id INTEGER PRIMARY KEY, mission_id INTEGER NOT NULL, role TEXT NOT NULL)'))
            connection.execute(text("INSERT INTO missions VALUES (1, 'Legacy empty'), (2, 'Crew mission')"))
            connection.execute(text("INSERT INTO mission_members VALUES (1, 1, 'mission_admin'), (2, 2, 'mission_admin'), (3, 2, 'astronaut'), (4, 2, 'astronaut'), (5, 2, 'flight_surgeon')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            assert connection.execute(text('SELECT crew_size FROM missions ORDER BY id')).scalars().all() == [None, 2]
            assert connection.execute(text('SELECT count(*) FROM mission_members')).scalar_one() == 5
            migration.downgrade()
            assert connection.execute(text('SELECT name FROM missions ORDER BY id')).scalars().all() == ['Legacy empty', 'Crew mission']
        finally:
            transaction.rollback()
