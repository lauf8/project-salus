from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.data.exam_catalog import EXAMS
from app.models.preflight import AstronautExam, ExamDefinition, MissionExamRequirement, MissionMember
from app.schemas.exams import ExamCreate
from scripts.seed_exam_catalog import seed
from tests.test_preflight_postgres import api, case

pytestmark = pytest.mark.skipif(__import__('os').getenv('PREFLIGHT_POSTGRES_TESTS') != '1', reason='Requires isolated migrated PostgreSQL')


def definition(case, code='blood_panel'):
    return case['call']('doctor', 'POST', '/exams', {
        'exam_type_id': case['exam_type']['id'], 'code': code, 'name': 'Blood test',
        'source_url': 'https://www.nasa.gov/reference', 'source_section': 'Test reference', 'source_page': 19,
        'fields': [
            {'code': 'hemoglobin', 'label': 'Hemoglobina', 'type': 'number', 'unit': 'g/dL', 'required': True},
            {'code': 'fasting', 'label': 'Em jejum', 'type': 'boolean'},
            {'code': 'finding', 'label': 'Achado', 'type': 'select', 'options': [{'value': 'absent', 'label': 'Ausente'}, {'value': 'present', 'label': 'Presente'}]},
            {'code': 'notes', 'label': 'Notas', 'type': 'textarea'},
            {'code': 'date', 'label': 'Data', 'type': 'date'},
        ],
    }, 201)


def assigned(case, record):
    requirement = case['call']('doctor', 'POST', f"{case['base']}/exam-requirements", {'exam_type_id': record['exam_type_id'], 'exam_definition_id': record['id'], 'due_days_before_launch': 10}, 201)
    checklist = case['call']('astronaut', 'GET', f"{case['base']}/astronauts/{case['astronaut']['id']}/exams")['data']
    return requirement, next(row for row in checklist if row['requirement_id'] == requirement['id'])


def realization():
    return {'performed_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), 'summary': 'Test report', 'structured_values': {'hemoglobin': 14.5, 'fasting': False, 'finding': 'absent', 'date': '2026-01-01'}, 'reference_ranges': {'hemoglobin': 'As per laboratory'}, 'laboratory': 'Test laboratory', 'performer_name': 'Profissional de teste', 'sample_identifier': 'sample_001', 'method': 'Reported method', 'report_reference': 'report_001'}


def update_payload(record, **changes):
    return {key: value for key, value in record.items() if key not in {'id', 'revision'}} | {'expected_revision': record['revision']} | changes


def test_catalog_crud_search_pagination_and_protected_deletion(case):
    call = case['call']
    record = definition(case)
    assert record['revision'] == 1
    assert call('astronaut', 'GET', f"/exams/{record['id']}")['name'] == record['name']
    assert call('doctor', 'GET', '/exams?search=blood&per_page=1')['pagination']['total'] == 1
    assert call('doctor', 'GET', '/exams?search=other')['data'] == []
    other = definition(case, 'other_panel')
    assert call('doctor', 'GET', '/exams?per_page=1')['pagination']['has_next']
    changed = call('doctor', 'PATCH', f"/exams/{record['id']}", update_payload(record, name='Revised exam'))
    assert changed['revision'] == 2
    call('doctor', 'PATCH', f"/exams/{record['id']}", update_payload(record), 409)
    assigned(case, changed)
    call('doctor', 'DELETE', f"/exams/{record['id']}", expected=409)
    call('doctor', 'PATCH', f"/exams/{record['id']}", update_payload(changed, code='changed_code'), 409)
    call('doctor', 'DELETE', f"/exams/{other['id']}", expected=204)
    call('doctor', 'GET', f"/exams/{other['id']}", expected=404)
    call('doctor', 'PATCH', f"/exams/{record['id']}", update_payload(changed, is_active=False))
    assert call('doctor', 'GET', '/exams?is_active=true')['data'] == []


def test_multiple_exams_per_type_and_snapshots_preserve_history(case):
    call, base = case['call'], case['base']
    record = definition(case)
    req, exam = assigned(case, record)
    other = definition(case, 'other_panel')
    assigned(case, other)
    assert exam['exam_name'] == record['name']
    assert exam['definition_snapshot']['revision'] == 1
    call('astronaut', 'GET', f"{base}/astronauts/{case['astronaut']['id']}/exam-types/{record['exam_type_id']}/latest-accepted", expected=409)
    call('doctor', 'PATCH', f"/exams/{record['id']}", update_payload(record, fields=[{'code': 'new_field', 'label': 'Novo campo', 'type': 'text', 'required': True}]))
    path = f"{base}/astronaut-exams/{exam['id']}/results"
    result = call('doctor', 'POST', path, realization(), 201)
    assert result['exam_snapshot']['fields'][0]['code'] == 'hemoglobin'
    assert result['exam_snapshot']['revision'] == 1
    assert result['structured_values']['fasting'] is False
    assert result['reference_ranges']['hemoglobin'] == 'As per laboratory'
    call('doctor', 'PATCH', f"{base}/exam-results/{result['id']}", {'structured_values': {'hemoglobin': 15}})
    call('doctor', 'POST', f"{base}/exam-results/{result['id']}/reviews", {'decision': 'accepted'}, 201)
    accepted = call('astronaut', 'GET', f"{base}/astronauts/{case['astronaut']['id']}/exam-types/{record['exam_type_id']}/latest-accepted?exam_id={exam['id']}")
    assert accepted['latest_accepted_result']['id'] == result['id']
    call('doctor', 'PATCH', f"{base}/exam-results/{result['id']}", {'summary': 'Changed'}, 409)
    call('doctor', 'PATCH', f"{base}/exam-requirements/{req['id']}", {'exam_definition_id': other['id']}, 409)


@pytest.mark.parametrize('values', [{}, {'hemoglobin': True}, {'hemoglobin': '14'}, {'hemoglobin': []}, {'hemoglobin': 14, 'extra': 'invalid'}, {'hemoglobin': 14, 'fasting': 'true'}, {'hemoglobin': 14, 'finding': 'bad'}, {'hemoglobin': 14, 'date': '2026-02-30'}, {'hemoglobin': 14, 'notes': ['invalid']}])
def test_result_rejects_invalid_structured_values_atomically(case, values):
    record = definition(case)
    _, exam = assigned(case, record)
    path = f"{case['base']}/astronaut-exams/{exam['id']}/results"
    case['call']('doctor', 'POST', path, realization() | {'structured_values': values}, 422)
    assert case['call']('astronaut', 'GET', path)['pagination']['total'] == 0


def test_collection_dates_reference_ranges_and_partial_correction(case):
    record = definition(case)
    _, exam = assigned(case, record)
    call, path = case['call'], f"{case['base']}/astronaut-exams/{exam['id']}/results"
    call('doctor', 'POST', path, realization() | {'reference_ranges': {'fasting': 'bad'}}, 422)
    call('doctor', 'POST', path, realization() | {'reference_ranges': {'extra': 'bad'}}, 422)
    call('doctor', 'POST', path, realization() | {'collected_at': datetime.now(timezone.utc).isoformat()}, 422)
    body = realization() | {'collected_at': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    result = call('doctor', 'POST', path, body, 201)
    result_path = f"{case['base']}/exam-results/{result['id']}"
    corrected = call('doctor', 'PATCH', result_path, {'summary': 'Summary correction'})
    assert corrected['structured_values'] == body['structured_values']
    call('doctor', 'PATCH', result_path, {'structured_values': {}}, 422)
    assert call('astronaut', 'GET', result_path)['summary'] == 'Summary correction'
    assert call('astronaut', 'GET', result_path)['structured_values'] == body['structured_values']


def test_only_authorized_physician_writes_and_astronaut_reads_only_own(case):
    call, base = case['call'], case['base']
    record = definition(case)
    _, exam = assigned(case, record)
    path = f"{base}/astronaut-exams/{exam['id']}/results"
    result = call('doctor', 'POST', path, realization(), 201)
    call('admin', 'POST', f'{base}/members', {'user_id': case['people']['second_astronaut'], 'role': 'astronaut'}, 201)
    for actor in ('astronaut', 'second_astronaut', 'outsider'):
        call(actor, 'POST', '/exams', {key: value for key, value in record.items() if key not in {'id', 'revision'}}, 403)
        call(actor, 'PATCH', f"/exams/{record['id']}", update_payload(record), 403)
        call(actor, 'DELETE', f"/exams/{record['id']}", expected=403)
        call(actor, 'POST', path, realization(), 403 if actor != 'outsider' else 404)
        call(actor, 'PATCH', f"{base}/exam-results/{result['id']}", {'summary': 'Forbidden'}, 403 if actor != 'outsider' else 404)
    call('second_astronaut', 'GET', path, expected=403)
    call('second_astronaut', 'GET', f"{base}/exam-results/{result['id']}", expected=403)
    call('astronaut', 'GET', f"{base}/exam-results/{result['id']}")
    call('admin', 'GET', path, expected=403)
    call('outsider', 'GET', path, expected=404)
    call('astronaut', 'GET', f"{base}/astronauts/{case['astronaut']['id']}/exam-types/{record['exam_type_id']}/latest-accepted?exam_id={exam['id']}")
    call('second_astronaut', 'GET', f"{base}/astronauts/{case['astronaut']['id']}/exam-types/{record['exam_type_id']}/latest-accepted?exam_id={exam['id']}", expected=403)


def test_catalog_and_requirement_validation(case):
    call = case['call']
    record = definition(case)
    create = {key: value for key, value in record.items() if key not in {'id', 'revision'}}
    for changes in ({'name': '  '}, {'exam_type_id': 9999999}, {'fields': []}, {'fields': [record['fields'][0], record['fields'][0]]}, {'fields': [{'code': 'bad', 'label': 'Bad', 'type': 'select', 'options': []}]}):
        call('doctor', 'POST', '/exams', create | {'code': 'new_exam'} | changes, 404 if 'exam_type_id' in changes else 422)
    call('doctor', 'POST', '/exams', create, 409)
    call('doctor', 'POST', f"{case['base']}/exam-requirements", {'exam_type_id': record['exam_type_id'], 'exam_definition_id': 9999999, 'due_days_before_launch': 1}, 404)
    other_type = call('doctor', 'POST', '/exam-types', {'code': 'other_type', 'name': 'Other type'}, 201)
    call('doctor', 'POST', f"{case['base']}/exam-requirements", {'exam_type_id': other_type['id'], 'exam_definition_id': record['id'], 'due_days_before_launch': 1}, 422)
    with pytest.raises(IntegrityError):
        with case['session'].begin_nested():
            case['session'].add(MissionExamRequirement(mission_id=case['mid'], exam_type_id=other_type['id'], exam_definition_id=record['id'], due_days_before_launch=1))
            case['session'].flush()


def test_seed_is_valid_idempotent_and_preserves_customizations(case):
    session = case['session']
    assert seed(session) == len(EXAMS)
    record = session.exec(select(ExamDefinition).where(ExamDefinition.code == EXAMS[0]['code'])).one()
    record.name = 'Customized by the physician'
    session.add(record)
    session.flush()
    assert seed(session) == 0
    assert record.name == 'Customized by the physician'
    for item in session.exec(select(ExamDefinition)).all():
        assert ExamCreate.model_validate({key: value for key, value in item.model_dump().items() if key not in {'id', 'revision'}})
