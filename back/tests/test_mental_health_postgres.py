from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import engine
from app.models.mental_health import MentalHealthCheckIn, PsychologyContactRequest
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.mental_health import CheckInInput
from app.services.mental_health_service import MentalHealthService


pytestmark = pytest.mark.skipif(os.getenv('MENTAL_HEALTH_POSTGRES_TESTS') != '1', reason='Requires isolated PostgreSQL validation schemas')


def test_full_migration_chain_and_mental_health_downgrade():
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'alembic'))
    scripts = ScriptDirectory.from_config(config)
    schema = 'mental_migration_' + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
            connection.execute(text(f'SET LOCAL search_path TO {schema}'))
            revisions = list(reversed(list(scripts.walk_revisions())))
            for revision in revisions:
                revision.module.op = Operations(MigrationContext.configure(connection))
                revision.module.upgrade()
            assert connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema=:schema AND table_name IN ('mental_health_check_ins','psychology_contact_requests','psychology_follow_ups','mental_health_audit_events')"), {'schema': schema}).scalar_one() == 4
            connection.execute(text("INSERT INTO users (id,name,email,hashed_password,is_astronaut,is_physician,allergy_screening_completed) VALUES (1,'Existing','existing@mental.test','fictional',true,false,false)"))
            assert connection.execute(text('SELECT is_psychologist FROM users WHERE id=1')).scalar_one() is False
            revisions[-1].module.downgrade()
            assert connection.execute(text('SELECT name FROM users WHERE id=1')).scalar_one() == 'Existing'
            revisions[-1].module.upgrade()
        finally:
            transaction.rollback()


def test_concurrent_daily_upsert_and_contact_request_are_unique():
    schema = 'mental_concurrency_' + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    isolated = create_engine(engine.url, connect_args={'options':f'-csearch_path={schema}'})
    try:
        SQLModel.metadata.create_all(isolated, tables=[table for table in SQLModel.metadata.sorted_tables if table.name not in {'knowledge_documents', 'knowledge_passages'}])
        with Session(isolated) as session:
            user = User(name='Astronaut', email='concurrent@mental.test', hashed_password='fictional', is_astronaut=True)
            mission = Mission(name='Concurrent mental health', planned_launch_at=datetime.now(timezone.utc))
            session.add_all([user, mission])
            session.flush()
            member = MissionMember(mission_id=mission.id, user_id=user.id, role='astronaut')
            session.add(member)
            session.flush()
            user_id, mission_id, member_id = user.id, mission.id, member.id
            session.commit()
        barrier = Barrier(2)
        def submit(_):
            with Session(isolated) as session:
                service = MentalHealthService(session, session.get(User, user_id))
                barrier.wait(timeout=10)
                check_in = service.save_check_in(mission_id, member_id, datetime.now(timezone.utc).date(), CheckInInput(happiness_level=3, satisfaction_level=4))
                contact = service.request_contact(mission_id, member_id)
                return check_in['id'], contact['id']
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        assert results[0] == results[1]
        with Session(isolated) as session:
            assert len(session.exec(select(MentalHealthCheckIn)).all()) == 1
            assert len(session.exec(select(PsychologyContactRequest)).all()) == 1
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
