from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.main import app
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlertSettings
from app.models.mental_health import MentalHealthAuditEvent, MentalHealthCheckIn, PsychologyContactRequest
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from tests.public_identity import public_headers


@pytest.fixture
def mental_api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mental.db'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine, tables=[table for table in SQLModel.metadata.sorted_tables if table.name not in {"knowledge_documents", "knowledge_passages"}])
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        users, members = {}, {}
        for name in ("astronaut", "other", "psychologist", "outsider", "admin", "doctor"):
            user = User(name=name, email=f"{name}@mental.test", hashed_password="fictional", is_psychologist=name in ("psychologist", "outsider"), is_astronaut=name in ("astronaut", "other"), is_physician=name in ("admin", "doctor"))
            session.add(user)
            session.flush()
            users[name] = user.id
        mission = Mission(name="Mental health", planned_launch_at=now-timedelta(days=14), started_at=now-timedelta(days=14))
        other_mission = Mission(name="Other", planned_launch_at=now)
        session.add_all([mission, other_mission])
        session.flush()
        mission_id = mission.id
        for name, role in (("astronaut", "astronaut"), ("other", "astronaut"), ("psychologist", "psychologist"), ("admin", "mission_admin"), ("doctor", "flight_surgeon")):
            member = MissionMember(mission_id=mission.id, user_id=users[name], role=role)
            session.add(member)
            session.flush()
            members[name] = member.id
        session.add(MissionMember(mission_id=other_mission.id, user_id=users['outsider'], role="psychologist"))
        session.add(HealthAlertSettings(mission_id=mission.id, timezone="America/Bahia"))
        session.add(HealthObservation(astronaut_id=users['astronaut'], mission_id=mission.id, indicator="sleep_duration", value=420, unit="min", source="self_report", recorded_by_user_id=users['astronaut'], collected_at=now, note="private sleep note"))
        session.commit()
    def get_test_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = get_test_session
    try:
        with TestClient(app) as client:
            def call(method, path="", body=None, actor="astronaut", expected=200, member=None):
                url = f"/v1/missions/{mission_id}/mental-health/astronauts/{member or members['astronaut']}" + path
                response = client.request(method, url, json=body, headers=public_headers(engine, users[actor]))
                assert response.status_code == expected, response.text
                return response.json()
            yield call, engine, members, now, client, users, mission_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def follow_up(now, start=None, **changes):
    day = start or now.date()
    return dict(session_at=now.isoformat(), review_period_start=day.isoformat(), review_period_end=(day+timedelta(days=6)).isoformat(), session_summary="confidential summary", private_notes="confidential notes", agreed_actions="Take a break", next_follow_up_on=(day+timedelta(days=7)).isoformat(), **changes)


def test_check_in_edit_gaps_and_validation(mental_api):
    call, engine, members, now, *_ = mental_api
    context = call('GET')
    today = context['today']
    assert context['timezone'] == 'America/Bahia'
    assert all(day['check_in_id'] is None for day in context['days'])
    record = call('PUT', f'/check-ins/{today}', dict(happiness_level=3, satisfaction_level=4, notes='daily account'))
    updated = call('PUT', f'/check-ins/{today}', dict(happiness_level=5, satisfaction_level=2))
    assert updated['id'] == record['id']
    assert updated['notes'] is None and updated['sleep_quality'] is None
    past = (now.date()-timedelta(days=5)).isoformat()
    call('PUT', f'/check-ins/{past}', dict(happiness_level=1, satisfaction_level=1))
    context = call('GET')
    assert sum(day['check_in_id'] is not None for day in context['days']) == 2
    assert 'note' not in context['sleep_observations'][0]
    for value in (0, 6, 1.5, True, '3'):
        call('PUT', f'/check-ins/{today}', dict(happiness_level=value, satisfaction_level=3, notes='sensitive invalid input'), expected=422)
    invalid = call('PUT', f'/check-ins/{today}', dict(satisfaction_level=3, notes='sensitive invalid input'), expected=422)
    assert 'sensitive invalid input' not in str(invalid)
    call('PUT', f"/check-ins/{(now.date()+timedelta(days=2)).isoformat()}", dict(happiness_level=3, satisfaction_level=3), expected=422)
    with Session(engine) as session:
        assert len(session.exec(select(MentalHealthCheckIn)).all()) == 2
        events = session.exec(select(MentalHealthAuditEvent)).all()
        assert events and all('daily account' not in str(item.model_dump()) for item in events)


def test_request_session_link_sharing_and_consecutive_weeks(mental_api):
    call, engine, members, now, *_ = mental_api
    contact = call('POST', '/requests')
    assert call('POST', '/requests')['id'] == contact['id']
    first = call('POST', '/sessions', follow_up(now, start=now.date()-timedelta(days=14), contact_request_id=contact['id']), actor='psychologist')
    assert call('GET')['requests'][0]['status'] == 'fulfilled'
    astronaut_session = call('GET')['sessions'][0]
    assert 'private_notes' not in astronaut_session and 'session_summary' not in astronaut_session
    assert astronaut_session['agreed_actions'] is None and astronaut_session['next_follow_up_on'] is None
    call('PUT', f"/sessions/{first['id']}", follow_up(now, start=now.date()-timedelta(days=14), contact_request_id=contact['id'], share_agreed_actions=True, share_next_follow_up=True), actor='psychologist')
    assert call('GET')['sessions'][0]['agreed_actions'] == 'Take a break'
    assert call('GET')['sessions'][0]['next_follow_up_on']
    second = call('POST', '/sessions', follow_up(now, start=now.date()-timedelta(days=7)), actor='psychologist')
    call('POST', '/sessions', follow_up(now, start=now.date()-timedelta(days=7)), actor='psychologist')
    context = call('GET', actor='psychologist')
    assert len(context['sessions']) == 3
    assert any(first['id'] in week['session_ids'] for week in context['weeks'])
    assert any(second['id'] in week['session_ids'] for week in context['weeks'])
    call('POST', '/sessions', follow_up(now, contact_request_id=contact['id']), actor='psychologist', expected=409)
    new_request = call('POST', '/requests')
    assert new_request['id'] != contact['id']
    call('POST', '/sessions', {**follow_up(now), 'review_period_end':(now.date()-timedelta(days=1)).isoformat()}, actor='psychologist', expected=422)
    with Session(engine) as session:
        assert len(session.exec(select(PsychologyContactRequest).where(PsychologyContactRequest.status=='pending')).all()) == 1


def test_scope_and_direct_id_privacy(mental_api):
    call, engine, members, now, client, users, mission_id = mental_api
    today = call('GET')['today']
    call('PUT', f'/check-ins/{today}', dict(happiness_level=3, satisfaction_level=3, notes='private diary'))
    for actor in ('other', 'outsider', 'admin', 'doctor'):
        call('GET', actor=actor, expected=404 if actor=='outsider' else 403)
    call('PUT', f'/check-ins/{today}', dict(happiness_level=3, satisfaction_level=3), actor='psychologist', expected=403)
    call('GET', member=members['other'], expected=403)
    call('POST', '/sessions', follow_up(now), expected=403)
    session = call('POST', '/sessions', follow_up(now), actor='psychologist')
    call('PUT', f"/sessions/{session['id']}", follow_up(now), actor='outsider', expected=404)
    call('PUT', f"/sessions/{session['id']}", follow_up(now), actor='psychologist', member=members['other'], expected=404)
    call('PUT', f"/sessions/{session['id']}", follow_up(now), expected=403)
    other_request = call('POST', '/requests', actor='other', member=members['other'])
    call('POST', '/sessions', follow_up(now, contact_request_id=other_request['id']), actor='psychologist', expected=404)
    response = client.get(f'/v1/missions/{mission_id}/mental-health/astronauts', headers=public_headers(engine, users['psychologist']))
    assert response.status_code == 200 and len(response.json()) == 2
    assert 'private diary' not in response.text and 'confidential' not in response.text
    response = client.get(f'/v1/missions/{mission_id}', headers=public_headers(engine, users['admin']))
    assert 'private diary' not in response.text and 'confidential' not in response.text


def test_revoked_psychologist_loses_access_and_authorship_survives(mental_api):
    call, engine, members, now, client, users, mission_id = mental_api
    record = call('POST', '/sessions', follow_up(now), actor='psychologist')
    response = client.delete(f"/v1/missions/{mission_id}/members/{members['psychologist']}", headers=public_headers(engine, users['admin']))
    assert response.status_code == 204, response.text
    call('GET', actor='psychologist', expected=404)
    call('PUT', f"/sessions/{record['id']}", follow_up(now), actor='psychologist', expected=404)
    assert call('GET')['sessions'][0]['id'] == record['id']


def test_mission_day_uses_configured_timezone(mental_api, monkeypatch):
    from app.services import mental_health_service

    class MissionClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 15, 1, 30, tzinfo=timezone.utc).astimezone(tz)

    call, *_ = mental_api
    monkeypatch.setattr(mental_health_service, 'datetime', MissionClock)
    assert call('GET')['today'] == '2026-11-14'
    call('PUT', '/check-ins/2026-11-14', dict(happiness_level=3, satisfaction_level=4))
    call('PUT', '/check-ins/2026-11-15', dict(happiness_level=3, satisfaction_level=4), expected=422)
