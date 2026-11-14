from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from sqlalchemy import func
from sqlmodel import select

from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertEvent, HealthAlertObservation
from app.schemas.health import ObservationCreate
from app.schemas.health_alerts import AlertResolve, AlertSettingsUpdate
from app.services.health_alert_rules import evaluate_reading, profile_for
from app.services.health_alert_service import HealthAlertService
from app.services.health_service import HealthService
from tests.test_medicine_service import records


def reading(indicator, value=None, **context):
    return ObservationCreate(indicator=indicator, value=value, collected_at=context.pop('collected_at', datetime.now(timezone.utc) - timedelta(seconds=2)), source='manual_measurement', **context)


def observation(indicator, value=None, **context):
    payload = reading(indicator, value, **context)
    return HealthObservation(**payload.model_dump(), astronaut_id=1, recorded_by_user_id=2)


def severity(indicator, value, **context):
    results = evaluate_reading(observation(indicator, value, **context), profile_for())
    rank = {'attention': 1, 'urgent': 2, 'critical': 3}
    return max((result['severity'] for result in results), key=rank.get) if results else None


@pytest.mark.parametrize('value,expected', [
    (39.999, 'critical'), (40, 'critical'), (40.001, 'attention'), (50, 'attention'), (50.001, None),
    (90, None), (90.001, 'attention'), (110, 'attention'), (110.001, 'urgent'), (130, 'urgent'), (130.001, 'critical'),
])
def test_heart_rate_boundaries(value, expected):
    assert severity('heart_rate', value, activity='rest') == expected


@pytest.mark.parametrize('value,expected', [
    (7.999, 'critical'), (8, 'critical'), (8.001, 'attention'), (11.999, 'attention'), (12, None),
    (20, None), (20.001, 'attention'), (24.999, 'attention'), (25, 'critical'), (25.001, 'critical'),
])
def test_respiratory_boundaries(value, expected):
    assert severity('respiratory_rate', value, activity='rest') == expected


@pytest.mark.parametrize('value,expected', [
    (91, 'critical'), (91.999, 'critical'), (92, 'urgent'), (93.999, 'urgent'),
    (94, 'attention'), (95.999, 'attention'), (96, None), (96.001, None),
])
def test_oxygen_boundaries(value, expected):
    assert severity('oxygen_saturation', value) == expected


@pytest.mark.parametrize('value,expected', [
    (34.999, 'critical'), (35, 'critical'), (35.001, 'attention'), (36, 'attention'), (36.001, None),
    (38, None), (38.001, 'attention'), (39, 'attention'), (39.001, 'urgent'),
])
def test_temperature_boundaries(value, expected):
    assert severity('body_temperature', value) == expected


@pytest.mark.parametrize('value,expected', [(89.999, 'critical'), (90, 'critical'), (90.001, 'urgent'), (100, 'urgent'), (100.001, 'attention'), (110, 'attention'), (110.001, None)])
def test_systolic_boundaries(value, expected):
    assert severity('blood_pressure', None, systolic=value, diastolic=60) == expected


@pytest.mark.parametrize('value,expected', [(53, 'critical'), (53.999, 'critical'), (54, 'urgent'), (69, 'urgent'), (69.999, 'urgent'), (70, None), (70.001, None)])
def test_glucose_boundaries(value, expected):
    assert severity('blood_glucose', value) == expected


@pytest.mark.parametrize('systolic,diastolic,expected', [(180, 120, None), (180.001, 80, 'urgent'), (170, 120.001, 'urgent'), (181, 121, 'urgent')])
def test_high_pressure_without_symptoms(systolic, diastolic, expected):
    assert severity('blood_pressure', None, systolic=systolic, diastolic=diastolic) == expected


@pytest.mark.parametrize('symptom', ['chest_pain', 'shortness_of_breath', 'sudden_weakness', 'visual_changes', 'speech_difficulty'])
def test_high_pressure_with_each_structured_symptom(symptom):
    assert severity('blood_pressure', None, systolic=181, diastolic=80, symptoms=[symptom]) == 'critical'


@pytest.mark.parametrize('category', ['voice', 'pain', 'unresponsive'])
def test_avpu_critical(category):
    assert severity('consciousness', None, category=category) == 'critical'


def test_acute_confusion_and_rest_context():
    assert severity('attention', None, category='worse', acute_confusion=True) == 'critical'
    assert severity('attention', None, category='worse', acute_confusion=False) is None
    assert severity('consciousness', None, category='alert', acute_confusion=True) == 'critical'
    assert severity('heart_rate', 115) is None
    assert severity('heart_rate', 150) == 'urgent'
    assert severity('heart_rate', 150, activity='exercise') is None
    assert severity('heart_rate', 150, activity='exercise', signal_quality='poor') == 'urgent'
    result = evaluate_reading(observation('oxygen_saturation', 91, signal_quality='poor', supplemental_oxygen=True), profile_for())[0]
    assert result['severity'] == 'critical'
    assert result['verification_required'] is True
    assert 'imediatamente' in result['reason']
    assert 'oxigênio suplementar' in result['reason']


def count(session, model):
    return session.exec(select(func.count()).select_from(model)).one()


def create(records, indicator, value=None, **context):
    session, doctor, astronaut, outsider, mission = records
    return HealthService(session, astronaut).create(astronaut.id, reading(indicator, value, mission_id=mission.id, **context))


def active(records):
    session, doctor, astronaut, outsider, mission = records
    return HealthAlertService(session, astronaut).list_alerts(astronaut.id, mission.id, 'active', 1, 100)['data']


def test_replay_escalation_acknowledgment_quality_and_resolution(records):
    session, doctor, astronaut, outsider, mission = records
    request_id = uuid4()
    payload = reading('oxygen_saturation', 95, mission_id=mission.id, signal_quality='good', client_request_id=request_id)
    health = HealthService(session, astronaut)
    first = health.create(astronaut.id, payload)
    assert health.create(astronaut.id, payload).id == first.id
    assert count(session, HealthObservation) == 1
    assert count(session, HealthAlert) == 1
    assert count(session, HealthAlertEvent) == 1
    same = payload.model_copy(update={'client_request_id': None})
    assert health.create(astronaut.id, same).id == first.id
    alerts = HealthAlertService(session, astronaut)
    initial = active(records)[0]
    alerts.acknowledge(astronaut.id, mission.id, initial.id)
    assert active(records)[0].status == 'acknowledged'
    create(records, 'oxygen_saturation', 91, signal_quality='good')
    current = active(records)[0]
    assert current.id == initial.id
    assert current.severity == 'critical'
    assert current.status == 'open'
    create(records, 'oxygen_saturation', 99, signal_quality='poor')
    current = active(records)[0]
    assert current.severity == 'critical' and current.status == 'open'
    assert current.source_count == 3
    with pytest.raises(HTTPException) as error:
        alerts.resolve(astronaut.id, mission.id, current.id, AlertResolve(note='Denied'))
    assert error.value.status_code == 403
    history = alerts.history(astronaut.id, mission.id, current.id, 1, 100)['data']
    assert {'created', 'acknowledged', 'escalated', 'measurement_added'} <= {event.action for event in history}
    assert any('não encerra' in event.reason for event in history)
    medical = HealthAlertService(session, doctor)
    resolved = medical.resolve(astronaut.id, mission.id, current.id, AlertResolve(note='Verificação concluída pela equipe médica'))
    assert resolved.status == 'resolved'
    assert active(records) == []
    create(records, 'oxygen_saturation', 91)
    assert active(records)[0].id != current.id
    assert count(session, HealthAlert) == 2


def test_request_id_conflict_and_quality_state(records):
    session, doctor, astronaut, outsider, mission = records
    request_id = uuid4()
    create(records, 'blood_glucose', 53, client_request_id=request_id, signal_quality='poor')
    with pytest.raises(HTTPException) as error:
        create(records, 'blood_glucose', 70, client_request_id=request_id)
    assert error.value.status_code == 409
    summary = HealthService(session, astronaut).summary(astronaut.id, mission.id)
    glucose = next(item for item in summary.indicators if item.indicator == 'blood_glucose')
    heart = next(item for item in summary.indicators if item.indicator == 'heart_rate')
    assert glucose.measurement_status == 'insufficient_quality'
    assert heart.measurement_status == 'no_measurement'
    assert active(records)[0].verification_required is True


def test_stale_unknown_and_evaluated_states(records):
    session, doctor, astronaut, outsider, mission = records
    create(records, 'heart_rate', 75, collected_at=datetime.now(timezone.utc) - timedelta(hours=2))
    summary = HealthService(session, astronaut).summary(astronaut.id, mission.id)
    heart = next(item for item in summary.indicators if item.indicator == 'heart_rate')
    assert heart.measurement_status == 'stale'
    create(records, 'heart_rate', 75, signal_quality='good')
    heart = next(item for item in HealthService(session, astronaut).summary(astronaut.id, mission.id).indicators if item.indicator == 'heart_rate')
    assert heart.measurement_status == 'evaluated'
    assert any('Falta contexto' in note for note in heart.evaluation_notes)


@pytest.mark.parametrize('indicator,value,days,category', [('sleep_duration', 400, 2, None), ('sleep_quality', 2, 2, None), ('mood', 2, 3, None), ('fatigue', 8, 2, None), ('attention', None, 2, 'worse')])
def test_distinct_consecutive_days_for_all_trends(records, indicator, value, days, category):
    base = datetime.now(timezone.utc) - timedelta(days=days + 1)
    kwargs = {'category': category} if category else {}
    for day in range(days):
        create(records, indicator, value, collected_at=base + timedelta(days=day), **kwargs)
    assert len(active(records)) == 1
    assert active(records)[0].severity == 'attention'
    assert active(records)[0].source_count == days


@pytest.mark.parametrize('indicator,value,category', [('sleep_duration', 400, None), ('sleep_quality', 1, None), ('fatigue', 9, None), ('attention', None, 'better')])
def test_missing_day_interrupts_trends(records, indicator, value, category):
    base = datetime.now(timezone.utc) - timedelta(days=5)
    kwargs = {'category': category} if category else {}
    create(records, indicator, value, collected_at=base, **kwargs)
    create(records, indicator, value, collected_at=base + timedelta(hours=2), **kwargs)
    create(records, indicator, value, collected_at=base + timedelta(days=2), **kwargs)
    assert active(records) == []


def test_mood_gap_latest_daily_value_and_poor_signal(records):
    base = datetime.now(timezone.utc) - timedelta(days=8)
    create(records, 'mood', 1, collected_at=base)
    create(records, 'mood', 1, collected_at=base + timedelta(days=1))
    create(records, 'mood', 1, collected_at=base + timedelta(days=3))
    assert active(records) == []
    create(records, 'mood', 1, collected_at=base + timedelta(days=4))
    create(records, 'mood', 4, collected_at=base + timedelta(days=4, hours=1))
    create(records, 'mood', 1, collected_at=base + timedelta(days=5))
    assert active(records) == []
    create(records, 'mood', 1, collected_at=base + timedelta(days=6), signal_quality='poor')
    assert active(records) == []


def test_mission_timezone_and_sleep_night_anchors(records):
    session, doctor, astronaut, outsider, mission = records
    settings = HealthAlertService(session, doctor)
    settings.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, timezone='America/Bahia', emergency_channel='Canal médico 3', approval_note='Configuração de simulação aprovada'))
    base = (datetime.now(timezone.utc) - timedelta(days=5)).replace(hour=23, minute=0, second=0, microsecond=0)
    create(records, 'fatigue', 8, collected_at=base)
    create(records, 'fatigue', 8, collected_at=base + timedelta(hours=2))
    assert active(records) == []
    create(records, 'fatigue', 8, collected_at=base + timedelta(days=1))
    assert len(active(records)) == 1
    assert 'America/Bahia' in active(records)[0].reason
    now = datetime.now(timezone.utc) - timedelta(seconds=3)
    for delta in (3, 2):
        end = now - timedelta(days=delta)
        create(records, 'sleep_duration', None, collected_at=now - timedelta(seconds=delta), sleep_started_at=end - timedelta(hours=6), sleep_ended_at=end)
    sleep_alert = next(item for item in active(records) if item.rule_id == 'short_sleep')
    assert sleep_alert.source_count == 2


def test_unit_normalization_original_values_and_custom_goals(records):
    session, doctor, astronaut, outsider, mission = records
    temperature = create(records, 'body_temperature', 102.2, unit='°F')
    assert temperature.value == 39
    assert temperature.unit == '°C'
    assert temperature.original_values == {'value': 102.2, 'unit': '°F', 'systolic': None, 'diastolic': None}
    glucose = create(records, 'blood_glucose', 3, unit='mmol/L')
    assert abs(glucose.value - 54.0546) < 0.00001
    assert next(item for item in active(records) if item.indicator == 'blood_glucose').severity == 'urgent'
    settings = HealthAlertService(session, doctor)
    settings.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, timezone='UTC', oxygen_thresholds={'normal_min': 94, 'attention_min': 90, 'urgent_min': 88}, high_glucose_thresholds={'fasting': {'attention': 126, 'urgent': 200, 'critical': 300}}, emergency_channel='Canal médico', approval_note='Metas aprovadas para a simulação'))
    create(records, 'oxygen_saturation', 91, supplemental_oxygen=True)
    oxygen = next(item for item in active(records) if item.indicator == 'oxygen_saturation')
    assert oxygen.severity == 'attention'
    assert ':r1' in oxygen.rule_version
    create(records, 'blood_glucose', 400, glucose_context='unknown')
    assert not any(item.rule_id.startswith('high_blood_glucose') for item in active(records))
    create(records, 'blood_glucose', 200, glucose_context='fasting')
    assert next(item for item in active(records) if item.rule_id == 'high_blood_glucose_fasting').severity == 'urgent'
    with pytest.raises(HTTPException) as error:
        settings.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, timezone='UTC', approval_note='Versão antiga'))
    assert error.value.status_code == 409


def test_profile_visibility_permissions_and_critical_channel(records):
    session, doctor, astronaut, outsider, mission = records
    medical = HealthAlertService(session, doctor)
    medical.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, timezone='UTC', emergency_channel='Voz médica 7', approval_note='Aprovado'))
    create(records, 'blood_glucose', 53)
    alert = active(records)[0]
    assert 'Voz médica 7' in alert.protocol_message
    assert alert.can_acknowledge is True and alert.can_resolve is False
    assert medical.list_alerts(astronaut.id, mission.id, 'active', 1, 20)['data'][0].can_resolve is True
    for actor in (outsider,):
        service = HealthAlertService(session, actor)
        for operation in (lambda: service.list_alerts(astronaut.id, mission.id, 'active', 1, 20), lambda: service.history(astronaut.id, mission.id, alert.id, 1, 20), lambda: service.acknowledge(astronaut.id, mission.id, alert.id)):
            with pytest.raises(HTTPException) as error:
                operation()
            assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        HealthAlertService(session, astronaut).update_settings(mission.id, AlertSettingsUpdate(expected_revision=1, timezone='UTC', approval_note='Denied'))


@pytest.mark.parametrize('values', [
    {'timezone': 'Invalid/Zone'},
    {'timezone': 'UTC', 'oxygen_thresholds': {'normal_min': 92, 'attention_min': 94, 'urgent_min': 96}},
    {'timezone': 'UTC', 'high_glucose_thresholds': {'fasting': {'attention': 200, 'urgent': 126}}},
])
def test_settings_validation(values):
    with pytest.raises(ValidationError):
        AlertSettingsUpdate(expected_revision=0, approval_note='Aprovado', **values)


def test_resolved_trend_does_not_reopen_for_unrelated_backdated_reading(records):
    session, doctor, astronaut, outsider, mission = records
    base = datetime.now(timezone.utc) - timedelta(days=5)
    create(records, 'sleep_quality', 1, collected_at=base)
    create(records, 'sleep_quality', 1, collected_at=base + timedelta(days=1))
    alert = active(records)[0]
    HealthAlertService(session, doctor).resolve(astronaut.id, mission.id, alert.id, AlertResolve(note='Avaliação médica registrada'))
    create(records, 'sleep_quality', 5, collected_at=base - timedelta(days=5))
    assert active(records) == []


def test_active_alert_uses_current_emergency_channel_and_preserves_rule_snapshot(records):
    session, doctor, astronaut, outsider, mission = records
    service = HealthAlertService(session, doctor)
    service.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, timezone='UTC', emergency_channel='Canal 1', approval_note='Aprovado'))
    create(records, 'oxygen_saturation', 91)
    alert = active(records)[0]
    old_version = alert.rule_version
    service.update_settings(mission.id, AlertSettingsUpdate(expected_revision=1, timezone='UTC', emergency_channel='Canal 2', approval_note='Canal atualizado'))
    alert = active(records)[0]
    assert alert.rule_version == old_version
    assert 'Canal 2' in alert.protocol_message
    stored = session.get(HealthAlert, alert.id)
    assert stored.profile_snapshot['emergency_channel'] == 'Canal 1'


def test_backdated_equal_severity_does_not_replace_current_trigger(records):
    session, doctor, astronaut, outsider, mission = records
    first = create(records, 'oxygen_saturation', 91)
    create(records, 'oxygen_saturation', 90, collected_at=datetime.now(timezone.utc) - timedelta(days=1))
    alert = active(records)[0]
    assert alert.trigger_observation.id == first.id
    assert alert.source_count == 2


def test_legacy_readings_use_canonical_units_in_alert_reasons():
    row = observation('sleep_duration', 400)
    row.unit = None
    from app.services.health_alert_rules import display_reading
    assert '400 min' in display_reading(row)


@pytest.mark.parametrize('context', ['fasting', 'after_meal', 'unknown'])
@pytest.mark.parametrize('value,expected', [(299.999, None), (300, 'urgent'), (400, 'urgent')])
def test_simulation_v2_high_glucose_by_context(context, value, expected):
    assert profile_for()['version'] == 'simulation-v2'
    assert severity('blood_glucose', value, glucose_context=context) == expected


def test_simulation_v1_and_custom_targets_are_not_overwritten():
    from types import SimpleNamespace
    settings = SimpleNamespace(profile_id='simulation-v1', mission_id=1, revision=1, timezone='UTC', emergency_channel=None, oxygen_thresholds=None, high_glucose_thresholds={}, approved_by_user_id=1, approval_note='Preservado')
    profile = profile_for(settings)
    assert profile['high_glucose_thresholds'] == {}
    assert evaluate_reading(observation('blood_glucose', 400, glucose_context='fasting'), profile) == []


def test_reassessment_preserves_previous_profile_and_original_measurement(records):
    session, doctor, astronaut, outsider, mission = records
    service = HealthAlertService(session, doctor)
    service.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, profile_id='simulation-v1', timezone='UTC', approval_note='Perfil original'))
    saved = create(records, 'blood_glucose', 400, glucose_context='fasting')
    original_id = saved.id
    assert active(records) == []
    service.update_settings(mission.id, AlertSettingsUpdate(expected_revision=1, profile_id='simulation-v2', timezone='UTC', high_glucose_thresholds={context: {'urgent': 300} for context in ('fasting','after_meal','unknown')}, approval_note='Perfil atualizado de simulação'))
    service.evaluate(saved, preserve_previous=True)
    session.commit()
    alert = active(records)[0]
    assert alert.severity == 'urgent'
    assert alert.trigger_observation.id == original_id
    assert alert.trigger_observation.value == 400
    assert alert.trigger_observation.evaluation_profile['previous_evaluation']['profile']['version'] == 'simulation-v1'


@pytest.mark.parametrize('acknowledged', [False, True])
def test_normal_glucose_auto_resolves_noncritical_alert(records, acknowledged):
    session, doctor, astronaut, outsider, mission = records
    create(records, 'blood_glucose', 400, glucose_context='fasting', signal_quality='good')
    alert = active(records)[0]
    service = HealthAlertService(session, astronaut)
    if acknowledged:
        service.acknowledge(astronaut.id, mission.id, alert.id)
    normal = create(records, 'blood_glucose', 100, glucose_context='unknown')
    assert active(records) == []
    resolved = session.get(HealthAlert, alert.id)
    assert resolved.status == 'resolved'
    assert 'automaticamente' in resolved.resolution_note
    events = service.history(astronaut.id, mission.id, alert.id, 1, 100)['data']
    assert events[0].action == 'auto_resolved'
    assert events[0].observation.id == normal.id
    assert service.response(resolved, False).source_count == 2


def test_poor_context_stale_and_backdated_readings_do_not_auto_resolve(records):
    session, doctor, astronaut, outsider, mission = records
    create(records, 'blood_glucose', 400, glucose_context='fasting')
    create(records, 'blood_glucose', 100, signal_quality='poor')
    create(records, 'blood_glucose', 100, collected_at=datetime.now(timezone.utc) - timedelta(days=1))
    assert len(active(records)) == 1
    service = HealthAlertService(session, doctor)
    service.update_settings(mission.id, AlertSettingsUpdate(expected_revision=0, timezone='UTC', high_glucose_thresholds={'fasting': {'urgent': 300}}, approval_note='Metas específicas'))
    create(records, 'blood_glucose', 100, glucose_context='unknown')
    assert len(active(records)) == 1
    create(records, 'blood_glucose', 100, glucose_context='fasting')
    assert active(records) == []


def test_resting_alert_requires_confirmed_rest_to_auto_resolve(records):
    create(records, 'heart_rate', 115, activity='rest')
    create(records, 'heart_rate', 75, activity='unknown')
    assert len(active(records)) == 1
    create(records, 'heart_rate', 75, activity='exercise')
    assert len(active(records)) == 1
    create(records, 'heart_rate', 75, activity='rest')
    assert active(records) == []


def test_critical_normalization_remains_explicit_and_shows_current_value(records):
    create(records, 'blood_glucose', 30, signal_quality='good')
    normal = create(records, 'blood_glucose', 100, signal_quality='good')
    alert = active(records)[0]
    assert alert.status == 'open' and alert.severity == 'critical'
    assert alert.awaiting_medical_review is True
    assert alert.latest_observation.id == normal.id
    assert alert.trigger_observation.value == 30
    assert alert.latest_observation.value == 100


def test_trend_needs_a_normal_new_day_not_just_a_gap(records):
    now = datetime.now(timezone.utc) - timedelta(minutes=2)
    create(records, 'fatigue', 9, collected_at=now - timedelta(days=4))
    create(records, 'fatigue', 9, collected_at=now - timedelta(days=3))
    assert len(active(records)) == 1
    create(records, 'fatigue', 9, collected_at=now)
    assert len(active(records)) == 1
    create(records, 'fatigue', 3)
    assert active(records) == []
