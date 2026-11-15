from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func
from sqlmodel import select

from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert
from app.models.notifications import HealthNotification
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.health import ObservationCreate
from app.schemas.health_alerts import AlertResolve
from app.services.health_alert_service import HealthAlertService
from app.services.health_service import HealthService
from app.services.notification_service import NotificationService
from tests.test_medicine_service import records
from tests.test_medicines import catalog_api


def payload(mission_id, value=53, **context):
    return ObservationCreate(indicator='blood_glucose', value=value, mission_id=mission_id, source='manual_measurement', collected_at=context.pop('collected_at', datetime.now(timezone.utc) - timedelta(seconds=1)), **context)


def count(session):
    return session.exec(select(func.count()).select_from(HealthNotification)).one()


def test_only_critical_alerts_notify_assigned_doctor_and_replay_is_idempotent(records):
    session, doctor, astronaut, outsider, mission = records
    health = HealthService(session, astronaut)
    health.create(astronaut.id, payload(mission.id, value=65))
    health.create(astronaut.id, payload(mission.id, value=400, glucose_context='fasting'))
    assert count(session) == 0
    critical = payload(mission.id, client_request_id=uuid4())
    first = health.create(astronaut.id, critical)
    assert health.create(astronaut.id, critical).id == first.id
    assert count(session) == 1
    notification = session.exec(select(HealthNotification)).one()
    assert notification.recipient_user_id == doctor.id
    assert notification.mission_id == mission.id
    health.create(astronaut.id, payload(mission.id, value=50))
    assert count(session) == 1
    service = NotificationService(session, doctor)
    inbox = service.list_notifications('pending', None, 1, 20)
    assert inbox['pagination']['total'] == 1
    assert inbox['data'][0].astronaut_id == astronaut.id
    assert inbox['data'][0].alert_status == 'open'
    assert service.summary()['pending_count'] == 1
    assert NotificationService(session, outsider).summary()['pending_count'] == 0


def test_poor_stale_and_superseded_critical_readings_do_not_notify(records):
    session, doctor, astronaut, outsider, mission = records
    health = HealthService(session, astronaut)
    health.create(astronaut.id, payload(mission.id, signal_quality='poor'))
    assert count(session) == 0
    health.create(astronaut.id, payload(mission.id, signal_quality='good', collected_at=datetime.now(timezone.utc) - timedelta(hours=3)))
    assert count(session) == 0
    health.create(astronaut.id, payload(mission.id, value=100, signal_quality='good'))
    health.create(astronaut.id, payload(mission.id, signal_quality='good', collected_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
    assert count(session) == 0
    health.create(astronaut.id, payload(mission.id, signal_quality='good'))
    assert count(session) == 1


def test_without_mission_routes_only_to_a_unique_active_astronaut_mission(records):
    session, doctor, astronaut, outsider, mission = records
    HealthService(session, astronaut).create(astronaut.id, payload(None))
    assert session.exec(select(HealthNotification)).one().mission_id == mission.id
    other = Mission(name='Other mission', planned_launch_at=datetime.now(timezone.utc))
    session.add(other)
    session.flush()
    session.add(MissionMember(mission_id=other.id, user_id=astronaut.id, role='astronaut'))
    session.commit()
    HealthService(session, astronaut).create(astronaut.id, payload(None, value=52))
    assert count(session) == 1


def test_ended_missions_and_doctors_without_flight_surgeon_role_are_excluded(records):
    session, doctor, astronaut, outsider, mission = records
    doctor_member = session.exec(select(MissionMember).where(MissionMember.user_id == doctor.id)).one()
    doctor_member.role = 'mission_admin'
    session.add(doctor_member)
    session.commit()
    health = HealthService(session, astronaut)
    health.create(astronaut.id, payload(mission.id))
    assert count(session) == 0
    doctor_member.role = 'flight_surgeon'
    session.add(doctor_member)
    mission.started_at = datetime.now(timezone.utc) - timedelta(days=1)
    mission.ended_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.add(mission)
    session.commit()
    health.create(astronaut.id, payload(mission.id, value=52))
    assert count(session) == 0


def test_read_is_separate_from_acknowledgment_and_resolution(records):
    session, doctor, astronaut, outsider, mission = records
    HealthService(session, astronaut).create(astronaut.id, payload(mission.id))
    service = NotificationService(session, doctor)
    notification = service.list_notifications('pending', None, 1, 20)['data'][0]
    service.read(notification.id)
    alert = session.get(HealthAlert, notification.alert_id)
    assert alert.status == 'open'
    assert service.summary()['pending_count'] == 0
    assert service.list_notifications('all', None, 1, 20)['data'][0].read_at is not None
    assert service.read_all()['marked_count'] == 0
    resolved = HealthAlertService(session, doctor).resolve(astronaut.id, mission.id, alert.id, AlertResolve(note='Avaliação registrada'))
    assert resolved.status == 'resolved'
    assert service.list_notifications('all', None, 1, 20)['data'][0].alert_status == 'resolved'


def test_resolved_alert_does_not_remain_in_pending_badge(records):
    session, doctor, astronaut, outsider, mission = records
    HealthService(session, astronaut).create(astronaut.id, payload(mission.id))
    notification = session.exec(select(HealthNotification)).one()
    HealthAlertService(session, doctor).resolve(astronaut.id, mission.id, notification.alert_id, AlertResolve(note='Avaliação registrada'))
    summary = NotificationService(session, doctor).summary()
    assert summary == {'unread_count': 1, 'pending_count': 0}
    assert NotificationService(session, doctor).list_notifications('pending', None, 1, 20)['data'] == []


def test_revoked_mission_access_and_recipient_isolation(records):
    session, doctor, astronaut, outsider, mission = records
    HealthService(session, astronaut).create(astronaut.id, payload(mission.id))
    notification = session.exec(select(HealthNotification)).one()
    with pytest.raises(HTTPException) as error:
        NotificationService(session, outsider).read(notification.id)
    assert error.value.status_code == 404
    member = session.exec(select(MissionMember).where(MissionMember.user_id == doctor.id)).one()
    member.role = 'mission_admin'
    session.add(member)
    session.commit()
    service = NotificationService(session, doctor)
    assert service.summary()['pending_count'] == 0
    assert service.list_notifications('all', None, 1, 20)['data'] == []
    with pytest.raises(HTTPException) as error:
        service.read(notification.id)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        NotificationService(session, astronaut).summary()
    assert error.value.status_code == 403


def test_read_all_is_limited_to_the_current_recipient(records):
    session, doctor, astronaut, outsider, mission = records
    session.add(MissionMember(mission_id=mission.id, user_id=outsider.id, role='flight_surgeon'))
    session.commit()
    HealthService(session, astronaut).create(astronaut.id, payload(mission.id))
    assert count(session) == 2
    assert NotificationService(session, doctor).read_all()['marked_count'] == 1
    assert NotificationService(session, doctor).summary()['pending_count'] == 0
    assert NotificationService(session, outsider).summary()['pending_count'] == 1


def test_notification_failure_rolls_back_the_measurement_and_alert(records):
    session, doctor, astronaut, outsider, mission = records
    with patch.object(NotificationService, 'notify_critical', side_effect=RuntimeError('Failure')):
        with pytest.raises(RuntimeError):
            HealthService(session, astronaut).create(astronaut.id, payload(mission.id))
    assert count(session) == 0
    assert session.exec(select(func.count()).select_from(HealthAlert)).one() == 0
    assert session.exec(select(func.count()).select_from(HealthObservation)).one() == 0


def test_notification_http_pagination_visibility_and_read_actions(catalog_api):
    call, people, mission_id = catalog_api
    base = f"/health/astronauts/{people['astronaut']}"
    for index in range(3):
        body = payload(mission_id).model_dump(mode='json')
        call('astronaut', 'POST', base + '/observations', body, 201)
        alert_id = call('doctor', 'GET', base + f'/alerts?mission_id={mission_id}')['data'][0]['id']
        if index < 2:
            call('doctor', 'POST', base + f'/alerts/{alert_id}/resolve?mission_id={mission_id}', {'note': 'Avaliação registrada'})
    first = call('doctor', 'GET', '/notifications?status=all&page=1&per_page=2')
    second = call('doctor', 'GET', '/notifications?status=all&page=2&per_page=2')
    assert first['pagination']['total'] == 3
    assert len(first['data']) == 2 and len(second['data']) == 1
    assert first['pagination']['has_next'] is True
    assert call('doctor', 'GET', '/notifications/summary')['pending_count'] == 1
    notification_id = first['data'][0]['id']
    assert call('outsider', 'GET', '/notifications')['data'] == []
    call('outsider', 'POST', f'/notifications/{notification_id}/read', expected=404)
    call('astronaut', 'GET', '/notifications', expected=403)
    call(None, 'GET', '/notifications', expected=403)
    call('doctor', 'POST', f'/notifications/{notification_id}/read')
    assert call('doctor', 'GET', '/notifications/summary')['pending_count'] == 0
    assert call('doctor', 'POST', '/notifications/read-all')['marked_count'] == 2
