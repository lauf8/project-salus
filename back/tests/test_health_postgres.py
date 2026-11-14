import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.models.health import HealthObservation
from app.models.user import User
from tests.test_preflight_postgres import api, case


pytestmark = pytest.mark.skipif(os.getenv('PREFLIGHT_POSTGRES_TESTS') != '1', reason='Requires an isolated migrated PostgreSQL database')


def observation(indicator='heart_rate', **values):
    return {'indicator': indicator, 'collected_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), 'source': 'manual_measurement', **values}


def health_path(case):
    return f"/health/astronauts/{case['people']['astronaut']}"


@pytest.mark.parametrize('indicator,values', [
    ('blood_glucose', {'value': 95}), ('heart_rate', {'value': 72}), ('blood_pressure', {'systolic': 120, 'diastolic': 80}),
    ('respiratory_rate', {'value': 16}), ('oxygen_saturation', {'value': 98}),
    ('body_temperature', {'value': 36.5}), ('sleep_duration', {'value': 450}),
    ('sleep_quality', {'value': 4}), ('fatigue', {'value': 3}), ('mood', {'value': 4}),
    ('attention', {'category': 'usual'}),
])
def test_self_registration_and_summary(case, indicator, values):
    call, path = case['call'], health_path(case)
    payload = observation(indicator, mission_id=case['mid'], note='Observação fictícia', **values)
    created = call('astronaut', 'POST', path + '/observations', payload, 201)
    summary = call('astronaut', 'GET', path + '/summary')
    assert len(summary['indicators']) == 12
    item = next(item for item in summary['indicators'] if item['indicator'] == indicator)
    assert item['latest']['id'] == created['id']
    assert item['latest']['recorded_by_user_id'] == case['people']['astronaut']
    assert item['latest']['note'] == 'Observação fictícia'
    history = call('astronaut', 'GET', path + f'/history?indicator={indicator}')
    assert history['data'][0]['id'] == created['id']
    empty = next(item for item in summary['indicators'] if item['indicator'] != indicator)
    assert empty['latest'] is None
    assert empty['previous_delta'] is None
    assert empty['preflight_reference'] is None


def test_backdated_record_and_period_filters(case):
    call, path = case['call'], health_path(case)
    recent = call('astronaut', 'POST', path + '/observations', observation(value=72), 201)
    old = call('astronaut', 'POST', path + '/observations', observation(value=65, collected_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat()), 201)
    item = next(item for item in call('astronaut', 'GET', path + '/summary')['indicators'] if item['indicator'] == 'heart_rate')
    assert item['latest']['id'] == recent['id']
    assert item['previous']['id'] == old['id']
    assert item['previous_delta'] == {'value': 7}
    assert item['trend'] == 'increasing'
    history = call('astronaut', 'GET', path + '/history?indicator=heart_rate&per_page=1')
    assert history['data'][0]['id'] == old['id']
    assert history['pagination']['has_next']
    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace('+00:00', 'Z')
    filtered = call('astronaut', 'GET', path + f'/history?indicator=heart_rate&start={start}')
    assert [item['id'] for item in filtered['data']] == [recent['id']]


def test_sleep_duration_is_derived_and_utc_normalized(case):
    payload = observation('sleep_duration', source='self_report', collected_at='2026-01-02T10:00:00-03:00', sleep_started_at='2026-01-01T23:00:00-03:00', sleep_ended_at='2026-01-02T06:30:00-03:00')
    result = case['call']('astronaut', 'POST', health_path(case) + '/observations', payload, 201)
    assert result['value'] == 450
    assert datetime.fromisoformat(result['collected_at']).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(result['sleep_started_at']).hour == 2
    case['call']('astronaut', 'POST', health_path(case) + '/observations', {**payload, 'value': 300}, 422)


@pytest.mark.parametrize('payload', [
    observation('blood_pressure', systolic=120), observation('blood_pressure', systolic=70, diastolic=80),
    observation('blood_pressure', systolic=120, diastolic=80, value=100),
    observation('blood_glucose', value=0), observation('blood_glucose', value=-1),
    observation('oxygen_saturation', value=101), observation('heart_rate', value=0),
    observation('sleep_quality', value=0), observation('sleep_quality', value=3.5),
    observation('mood', value=6), observation('fatigue', value=11), observation('fatigue', value=-1),
    observation('attention', category='unknown'), observation('consciousness', category='alert', source='self_report'),
    observation('heart_rate', value=70, source='device'), observation('heart_rate', value=70, collected_at='2025-01-01T10:00:00'),
    observation('heart_rate', value=70, collected_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
    observation('sleep_duration', sleep_started_at='2026-01-01T00:00:00Z'),
    observation('mood', value=3, systolic=100), observation('heart_rate', value=70, astronaut_id=999),
])
def test_indicator_validation_rejects_invalid_payloads(case, payload):
    case['call']('astronaut', 'POST', health_path(case) + '/observations', payload, 422)


def test_authorization_and_avpu(case):
    call, path = case['call'], health_path(case)
    payload = observation('consciousness', category='alert', mission_id=case['mid'])
    call('astronaut', 'POST', path + '/observations', payload, 403)
    call('admin', 'POST', path + '/observations', payload, 403)
    call('outsider', 'POST', path + '/observations', payload, 403)
    call('doctor', 'POST', path + '/observations', observation('consciousness', category='alert'), 403)
    result = call('doctor', 'POST', path + '/observations', payload, 201)
    assert result['recorded_by_user_id'] == case['people']['doctor']
    for actor in ('second_astronaut', 'outsider'):
        call(actor, 'GET', path + '/summary', expected=403)
        call(actor, 'GET', path + '/history?indicator=heart_rate', expected=403)
        call(actor, 'POST', path + '/observations', observation(value=70), 403)
    summary = call('doctor', 'GET', path + f"/summary?mission_id={case['mid']}")
    assert summary['can_record_consciousness']
    self_summary = call('astronaut', 'GET', path + '/summary')
    assert not self_summary['can_record_consciousness']
    call('astronaut', 'DELETE', path + f"/observations/{result['id']}", expected=404)


def test_individual_reference_and_bp_delta(case):
    call, path = case['call'], health_path(case)
    old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    reference = observation('blood_pressure', systolic=115, diastolic=75, mission_id=case['mid'], is_preflight_reference=True, collected_at=old_time)
    call('astronaut', 'POST', path + '/observations', reference, 403)
    baseline = call('doctor', 'POST', path + '/observations', reference, 201)
    latest = call('astronaut', 'POST', path + '/observations', observation('blood_pressure', systolic=120, diastolic=80, mission_id=case['mid']), 201)
    summary = call('astronaut', 'GET', path + f"/summary?mission_id={case['mid']}")
    item = next(item for item in summary['indicators'] if item['indicator'] == 'blood_pressure')
    assert item['latest']['id'] == latest['id']
    assert item['preflight_reference']['id'] == baseline['id']
    assert item['reference_delta'] == {'systolic': 5, 'diastolic': 5}
    assert case['session'].exec(select(HealthObservation).where(HealthObservation.id == baseline['id'])).one().systolic == 115


def test_categories_have_sequences_without_numeric_deltas(case):
    call, path = case['call'], health_path(case)
    for category in ('usual', 'worse', 'better'):
        call('astronaut', 'POST', path + '/observations', observation('attention', category=category), 201)
    item = next(item for item in call('astronaut', 'GET', path + '/summary')['indicators'] if item['indicator'] == 'attention')
    assert [row['category'] for row in item['sequence']] == ['usual', 'worse', 'better']
    assert item['previous_delta'] is None
    assert item['reference_delta'] is None
    assert item['trend'] is None


def test_mission_scope_does_not_leak_unscoped_or_other_mission_data(case):
    call, path = case['call'], health_path(case)
    call('astronaut', 'POST', path + '/observations', observation(value=62), 201)
    scoped = call('astronaut', 'POST', path + '/observations', observation(value=70, mission_id=case['mid']), 201)
    history = call('doctor', 'GET', path + f"/history?indicator=heart_rate&mission_id={case['mid']}")
    assert [item['id'] for item in history['data']] == [scoped['id']]
    call('doctor', 'GET', path + '/summary', expected=403)
    call('astronaut', 'POST', path + '/observations', observation(value=70, mission_id=999999), 404)


def test_physician_astronaut_cannot_self_assess_avpu(case):
    session, call = case['session'], case['call']
    doctor = session.get(User, case['people']['doctor'])
    doctor.is_astronaut = True
    session.add(doctor)
    session.commit()
    path = f"/health/astronauts/{doctor.id}"
    call('doctor', 'POST', path + '/observations', observation(value=70, mission_id=case['mid']), 201)
    call('doctor', 'POST', path + '/observations', observation('consciousness', category='alert', mission_id=case['mid']), 403)


def test_context_uses_mission_authorization_and_legacy_astronaut_membership(case):
    call, session = case['call'], case['session']
    astronaut = session.get(User, case['people']['astronaut'])
    astronaut.is_astronaut = False
    session.add(astronaut)
    session.commit()
    assert call('astronaut', 'GET', '/health/context')['is_astronaut']
    assert not call('astronaut', 'GET', '/health/context')['supervised_astronauts']
    supervised = call('doctor', 'GET', '/health/context')['supervised_astronauts']
    assert [record['id'] for record in supervised] == [astronaut.id]
    assert not call('outsider', 'GET', '/health/context')['supervised_astronauts']
    assert not call('admin', 'GET', '/health/context')['supervised_astronauts']


def test_summary_requires_authentication_and_invalid_history_period_is_rejected(case):
    path = health_path(case)
    case['call'](None, 'GET', path + '/summary', expected=401)
    case['call']('astronaut', 'GET', path + '/history?indicator=unknown', expected=422)
    case['call']('astronaut', 'GET', path + '/history?indicator=heart_rate&start=2026-01-02T00:00:00Z&end=2026-01-01T00:00:00Z', expected=422)
