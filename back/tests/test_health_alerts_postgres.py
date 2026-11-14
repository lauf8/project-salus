from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import engine
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertEvent, HealthAlertObservation
from app.models.notifications import HealthNotification
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.health import ObservationCreate
from app.services.health_service import HealthService


pytestmark = pytest.mark.skipif(os.getenv('ALERT_CONCURRENCY_TESTS') != '1', reason='Requires an isolated alert verification database')


def test_concurrent_replays_and_severity_escalation():
    assert os.environ['PGDATABASE'].startswith('nasa_alerts_verify_')
    with Session(engine) as session:
        user = User(name='Concurrency astronaut', email=f'{uuid4()}@fictional.test', hashed_password='fictional', is_astronaut=True)
        session.add(user)
        doctor = User(name='Concurrency doctor', email=f'{uuid4()}@fictional.test', hashed_password='fictional', is_physician=True)
        mission = Mission(name='Concurrency mission', planned_launch_at=datetime.now(timezone.utc))
        session.add_all([doctor, mission])
        session.flush()
        session.add_all([MissionMember(mission_id=mission.id, user_id=user.id, role='astronaut'), MissionMember(mission_id=mission.id, user_id=doctor.id, role='flight_surgeon')])
        session.commit()
        astronaut_id = user.id
        mission_id = mission.id
        doctor_id = doctor.id
    collected_at = datetime.now(timezone.utc) - timedelta(seconds=3)
    request_id = str(uuid4())

    def run(values):
        with Session(engine) as session:
            user = session.get(User, astronaut_id)
            payload = ObservationCreate(indicator='oxygen_saturation', mission_id=mission_id, collected_at=collected_at, source='manual_measurement', signal_quality='good', **values)
            return HealthService(session, user).create(astronaut_id, payload).id

    barrier = Barrier(4)

    def replay(_):
        barrier.wait(timeout=20)
        return run({'value': 95, 'client_request_id': request_id})

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(replay, range(4)))
    assert len(set(ids)) == 1
    barrier = Barrier(2)

    def escalate(value):
        barrier.wait(timeout=20)
        return run({'value': value, 'client_request_id': str(uuid4())})

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(escalate, [93, 91]))
    with Session(engine) as session:
        alerts = session.exec(select(HealthAlert).where(HealthAlert.astronaut_id == astronaut_id)).all()
        assert len(alerts) == 1
        assert alerts[0].severity == 'critical'
        assert session.exec(select(func.count()).select_from(HealthObservation).where(HealthObservation.astronaut_id == astronaut_id)).one() == 3
        assert session.exec(select(func.count()).select_from(HealthAlertObservation).where(HealthAlertObservation.alert_id == alerts[0].id)).one() == 3
        assert session.exec(select(func.count()).select_from(HealthAlertEvent).where(HealthAlertEvent.alert_id == alerts[0].id)).one() == 3

        assert session.exec(select(func.count()).select_from(HealthNotification).where(HealthNotification.recipient_user_id == doctor_id)).one() == 1
