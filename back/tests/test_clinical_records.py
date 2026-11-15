from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlmodel import SQLModel

from app.database import get_session
from app.main import app
from app.models.clinical_records import ClinicalAssessment, HealthOccurrence, MedicationUse
from app.models.health import HealthObservation
from app.models.preflight import Mission
from app.services.icd_catalog import icd_entries
from app.services.mission_rag import MissionRagService, OllamaRag
from tests.test_medicines import catalog_api


@pytest.fixture
def clinical_api(catalog_api):
    session = next(app.dependency_overrides[get_session]())
    SQLModel.metadata.create_all(session.get_bind(), tables=[HealthOccurrence.__table__, MedicationUse.__table__, ClinicalAssessment.__table__])
    yield catalog_api, session


def occurrence_body(mission_id):
    return {'mission_id': mission_id, 'condition_name': 'Headache', 'icd_code': 'R51',
        'description': 'Synthetic report', 'symptoms': 'Head pain',
        'start_at': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}


def test_who_catalog_search_and_pagination(clinical_api):
    (call, people, mission_id), session = clinical_api
    result = call('astronaut', 'GET', '/health/icd10?search=cholera&per_page=2')
    assert result['pagination']['total'] > 2
    assert len(result['data']) == 2
    assert result['data'][0]['code'] == 'A00'
    assert result['data'][0]['selectable'] is False
    assert len(icd_entries()) > 12000
    assert any(row['code'] == 'U07.1' for row in icd_entries())
    assert any(row['name'] == 'Headache' for row in call('astronaut', 'GET', '/health/icd10?search=R51')['data'])


def test_occurrence_self_report_and_doctor_recovery(clinical_api):
    (call, people, mission_id), session = clinical_api
    root = f"/health/astronauts/{people['astronaut']}/occurrences"
    record = call('astronaut', 'POST', root, {**occurrence_body(mission_id), 'condition_name': 'Untrusted name'}, 201)
    assert record['condition_name'] == 'Headache'
    assert record['status'] == 'active' and record['finish_at'] is None
    assert call('astronaut', 'GET', root + '?active=true')['pagination']['total'] == 1
    payload = {'finish_at': datetime.now(timezone.utc).isoformat(), 'resolution_note': 'Recovery confirmed'}
    path = f"{root}/{record['id']}/recover?mission_id={mission_id}"
    for actor in ('astronaut', 'admin', 'outsider'):
        call(actor, 'POST', path, payload, 403)
    call('doctor', 'POST', path, {**payload, 'finish_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}, 422)
    result = call('doctor', 'POST', path, payload)
    assert result['status'] == 'recovered' and result['resolved_by_user_id'] == people['doctor']
    assert call('astronaut', 'GET', root + '?active=true')['pagination']['total'] == 0
    assert call('astronaut', 'GET', root)['pagination']['total'] == 1
    call('doctor', 'POST', path, payload, 409)


@pytest.mark.parametrize('changes', [
    {'icd_code': 'FAKE'}, {'icd_code': 'A00'}, {'description': ' '},
    {'start_at': '2026-01-01T00:00:00'},
    {'start_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
])
def test_occurrence_validation(clinical_api, changes):
    (call, people, mission_id), session = clinical_api
    call('astronaut', 'POST', f"/health/astronauts/{people['astronaut']}/occurrences", {**occurrence_body(mission_id), **changes}, 422)


def test_clinical_permissions_and_mission_scope(clinical_api):
    (call, people, mission_id), session = clinical_api
    root = f"/health/astronauts/{people['astronaut']}"
    for resource in ('occurrences', 'medication-uses', 'clinical-report', 'assessments'):
        for actor in ('admin', 'outsider'):
            call(actor, 'GET', f'{root}/{resource}?mission_id={mission_id}', expected=403)
        call('doctor', 'GET', f'{root}/{resource}', expected=422 if resource == 'clinical-report' else 403)
        call('astronaut', 'GET', f'{root}/{resource}?mission_id=99999', expected=404)


def test_medication_history_preserves_consumption_details(clinical_api):
    (call, people, mission_id), session = clinical_api
    root = f"/health/astronauts/{people['astronaut']}"
    occurrence = call('astronaut', 'POST', root + '/occurrences', occurrence_body(mission_id), 201)
    medicine = call('doctor', 'POST', '/medicines', {'name': 'Synthetic medication', 'active_ingredient_ids': []}, 201)
    body = {'mission_id': mission_id, 'medicine_id': medicine['id'], 'taken_at': datetime.now(timezone.utc).isoformat(),
        'reason': 'Reported headache', 'instructed_by': 'Fictional flight surgeon', 'dose': 'Synthetic dose', 'occurrence_id': occurrence['id']}
    record = call('astronaut', 'POST', root + '/medication-uses', body, 201)
    assert record['astronaut_id'] == people['astronaut']
    assert record['instructed_by'] == body['instructed_by'] and record['reason'] == body['reason']
    call('doctor', 'PATCH', f"/medicines/{medicine['id']}", {'name': 'Renamed medication'})
    history = call('doctor', 'GET', root + f'/medication-uses?mission_id={mission_id}')
    assert history['data'][0]['medicine_name'] == 'Synthetic medication'
    call('astronaut', 'POST', root + '/medication-uses', {**body, 'occurrence_id': 99999}, 422)
    call('astronaut', 'POST', root + '/medication-uses', {**body, 'taken_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, 422)
    call('admin', 'POST', root + '/medication-uses', body, 403)


def test_assessment_failure_preserves_report_and_medical_gate(clinical_api, monkeypatch):
    (call, people, mission_id), session = clinical_api
    monkeypatch.setattr(MissionRagService, 'search', lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError()))
    root = f"/health/astronauts/{people['astronaut']}"
    call('astronaut', 'POST', root + '/assessments', {'mission_id': mission_id}, 403)
    record = call('doctor', 'POST', root + '/assessments', {'mission_id': mission_id}, 201)
    assert record['report']['generation_status'] == 'unavailable'
    assert record['report']['disease_probability'] is None and record['report']['missing_indicators']
    assert call('astronaut', 'GET', root + f'/assessments?mission_id={mission_id}')['data'] == []
    review = {'decision': 'approved', 'note': 'Reviewed; no inference without readings'}
    path = root + f"/assessments/{record['id']}/review?mission_id={mission_id}"
    call('astronaut', 'POST', path, review, 403)
    call('doctor', 'POST', path, review)
    approved = call('astronaut', 'GET', root + f'/assessments?mission_id={mission_id}')['data']
    assert len(approved) == 1 and approved[0]['review_note'] == review['note']
    call('doctor', 'POST', path, review, 409)


def test_report_correlates_measurements_with_mission_day(clinical_api):
    (call, people, mission_id), session = clinical_api
    mission = session.get(Mission, mission_id)
    mission.started_at = datetime.now(timezone.utc) - timedelta(days=4)
    session.add(mission)
    for hours, value in [(2, 70), (1, 90)]:
        session.add(HealthObservation(astronaut_id=people['astronaut'], mission_id=mission_id,
            indicator='heart_rate', value=value, unit='bpm', collected_at=datetime.now(timezone.utc) - timedelta(hours=hours),
            source='manual_measurement', recorded_by_user_id=people['astronaut'], signal_quality='good'))
    session.commit()
    call('astronaut', 'POST', f"/health/astronauts/{people['astronaut']}/occurrences", occurrence_body(mission_id), 201)
    report = call('doctor', 'GET', f"/health/astronauts/{people['astronaut']}/clinical-report?mission_id={mission_id}")
    assert report['mission_day'] == 5
    assert [row['value'] for row in report['measurements']] == [90, 70]
    assert report['measurements'][1]['previous']
    assert report['active_occurrences'][0]['condition'] == 'Headache'
    assert report['disease_probability'] is None


@pytest.mark.parametrize('invalid', [False, True])
def test_ai_hypothesis_citations_are_validated(clinical_api, monkeypatch, invalid):
    (call, people, mission_id), session = clinical_api
    observation = HealthObservation(astronaut_id=people['astronaut'], mission_id=mission_id,
        indicator='heart_rate', value=90, unit='bpm', collected_at=datetime.now(timezone.utc),
        source='manual_measurement', recorded_by_user_id=people['astronaut'], signal_quality='good')
    session.add(observation)
    session.commit()
    monkeypatch.setattr(MissionRagService, 'search', lambda *args, **kwargs: [{'id': 5, 'title': 'Synthetic passage', 'content': 'Synthetic evidence', 'origin': 'NASA'}])
    generated = {'hypotheses': [{'condition': 'Review signal', 'reasoning': 'Synthetic reasoning',
        'observation_ids': [observation.id], 'citation_ids': [999 if invalid else 5]}]}
    monkeypatch.setattr(OllamaRag, 'request', lambda *args, **kwargs: {'response': json.dumps(generated)})
    result = call('doctor', 'POST', f"/health/astronauts/{people['astronaut']}/assessments", {'mission_id': mission_id}, 201)
    assert result['status'] == 'pending'
    assert result['report']['generation_status'] == ('unavailable' if invalid else 'completed')
    assert len(result['report']['hypotheses']) == (0 if invalid else 1)


def test_dense_pdf_chunks_preserve_pages_and_fit_conservative_budget():
    from app.services.mission_rag import split_pages
    text = 'Table of contents\n' + '. ' * 500
    chunks = split_pages([(3, text)], 500, 150)
    assert len(chunks) > 2
    assert all(row['page_number'] == 3 for row in chunks)
    assert max(len(row['content']) for row in chunks) < 500
    assert chunks[0]['content'].startswith('Table of contents')
    assert chunks[-1]['content'].endswith('.')


def test_nurse_cannot_close_or_review(clinical_api):
    from app.models.user import User
    from app.models.preflight import MissionMember
    (call, people, mission_id), session = clinical_api
    nurse = session.get(User, people['outsider'])
    nurse.is_physician = False
    nurse.is_nurse = True
    session.add(nurse)
    session.add(MissionMember(mission_id=mission_id, user_id=nurse.id, role='nurse'))
    session.commit()
    root = f"/health/astronauts/{people['astronaut']}"
    record = call('astronaut', 'POST', root + '/occurrences', occurrence_body(mission_id), 201)
    assert call('outsider', 'GET', root + f'/occurrences?mission_id={mission_id}')['pagination']['total'] == 1
    call('outsider', 'POST', root + f"/occurrences/{record['id']}/recover?mission_id={mission_id}",
         {'finish_at': datetime.now(timezone.utc).isoformat(), 'resolution_note': 'Not authorized'}, 403)
    call('outsider', 'POST', root + '/assessments', {'mission_id': mission_id}, 403)


def test_real_ollama_clinical_assessment_in_isolated_schema(monkeypatch):
    import os
    from uuid import uuid4
    from sqlalchemy import text
    from sqlmodel import Session, create_engine
    from app.database import engine
    from app.models.user import User
    from app.models.preflight import MissionMember
    from app.services.clinical_record_service import ClinicalRecordService
    if os.getenv('MISSION_RISKS_POSTGRES_TESTS') != '1' or os.getenv('MISSION_RISKS_REAL_OLLAMA') != '1':
        pytest.skip('Requires isolated PostgreSQL schema and local Ollama')
    schema = 'clinical_test_' + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    isolated = create_engine(engine.url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        SQLModel.metadata.create_all(isolated)
        with Session(engine) as sources, Session(isolated) as session:
            real_search = MissionRagService(sources).search
            monkeypatch.setattr(MissionRagService, 'search', lambda self, *args, **kwargs: real_search(*args, **kwargs))
            astronaut = User(name='Synthetic clinical astronaut', email='clinical-astronaut@example.test', hashed_password='!', is_astronaut=True)
            doctor = User(name='Synthetic clinical physician', email='clinical-doctor@example.test', hashed_password='!', is_physician=True)
            mission = Mission(name='Synthetic clinical mission', planned_launch_at=datetime.now(timezone.utc) - timedelta(days=5), started_at=datetime.now(timezone.utc) - timedelta(days=4))
            session.add_all([astronaut, doctor, mission])
            session.flush()
            session.add_all([MissionMember(mission_id=mission.id, user_id=astronaut.id, role='astronaut'), MissionMember(mission_id=mission.id, user_id=doctor.id, role='flight_surgeon')])
            session.add(HealthObservation(astronaut_id=astronaut.id, mission_id=mission.id, indicator='heart_rate', value=72,
                unit='bpm', activity='rest', signal_quality='good', collected_at=datetime.now(timezone.utc), source='manual_measurement', recorded_by_user_id=astronaut.id))
            session.commit()
            record = ClinicalRecordService(session, doctor).create_assessment(astronaut.id, mission.id)
            assert record.status == 'pending'
            assert record.report['generation_status'] == 'completed'
            assert record.report['sources'] and all(row['origin'] == 'NASA' for row in record.report['sources'])
            assert record.report['disease_probability'] is None
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
