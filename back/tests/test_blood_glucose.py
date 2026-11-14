from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models.health import HealthObservation
from app.schemas.health import ObservationCreate
from app.services.health_service import HealthService
from tests.test_medicine_service import records


def payload(value):
    return ObservationCreate(indicator='blood_glucose', value=value, collected_at=datetime.now(timezone.utc) - timedelta(minutes=1), source='manual_measurement')


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf')])
def test_glucose_rejects_nonpositive_and_nonfinite_values(value):
    with pytest.raises(ValidationError):
        payload(value)


def test_glucose_registration_summary_and_history(records):
    session, doctor, astronaut, outsider, mission = records
    HealthObservation.__table__.create(session.get_bind(), checkfirst=True)
    service = HealthService(session, astronaut)
    created = service.create(astronaut.id, payload(95.5))
    assert created.indicator == 'blood_glucose'
    summary = service.summary(astronaut.id, None)
    glucose = next(item for item in summary.indicators if item.indicator == 'blood_glucose')
    assert glucose.unit == 'mg/dL'
    assert glucose.latest.value == 95.5
    assert len(summary.indicators) == 12
    now = datetime.now(timezone.utc)
    history = service.history(astronaut.id, 'blood_glucose', None, now - timedelta(days=1), now, 1, 100)
    assert history['pagination']['total'] == 1
    assert history['data'][0].id == created.id


def test_database_rejects_zero_glucose(records):
    session, doctor, astronaut, outsider, mission = records
    HealthObservation.__table__.create(session.get_bind(), checkfirst=True)
    values = payload(95).model_dump()
    values['value'] = 0
    session.add(HealthObservation(**values, astronaut_id=astronaut.id, recorded_by_user_id=astronaut.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
