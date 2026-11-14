from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tests.test_medicines import catalog_api


def measurement(mission_id, indicator='oxygen_saturation', value=91, **values):
    return {'indicator': indicator, 'value': value, 'collected_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), 'source': 'manual_measurement', 'mission_id': mission_id, 'signal_quality': 'good', **values}


def test_alert_http_lifecycle_history_and_permissions(catalog_api):
    call, people, mission_id = catalog_api
    base = f"/health/astronauts/{people['astronaut']}"
    query = f'?mission_id={mission_id}'
    payload = measurement(mission_id, value=95, client_request_id=str(uuid4()))
    first = call('astronaut', 'POST', base + '/observations', payload, 201)
    repeated = call('astronaut', 'POST', base + '/observations', payload, 201)
    assert first['id'] == repeated['id']
    alerts = call('astronaut', 'GET', base + '/alerts' + query)
    assert alerts['pagination']['total'] == 1
    alert_id = alerts['data'][0]['id']
    path = f'{base}/alerts/{alert_id}'
    assert call('astronaut', 'GET', path + query)['severity'] == 'attention'
    assert call('astronaut', 'POST', path + '/acknowledge' + query)['status'] == 'acknowledged'
    call('astronaut', 'POST', path + '/acknowledge' + query)
    call('astronaut', 'POST', base + '/observations', measurement(mission_id), 201)
    alert = call('doctor', 'GET', path + query)
    assert alert['severity'] == 'critical' and alert['status'] == 'open'
    assert alert['can_resolve'] is True
    assert alert['trigger_observation']['value'] == 91
    assert alert['source_count'] == 2
    assert 'protocolo de emergência' in alert['protocol_message']
    history = call('astronaut', 'GET', path + '/history' + query + '&per_page=1')
    assert history['pagination']['has_next'] is True
    assert history['data'][0]['action'] == 'escalated'
    for actor in ('outsider', 'admin'):
        call(actor, 'GET', base + '/alerts' + query, expected=403)
        call(actor, 'GET', path + '/history' + query, expected=403)
        call(actor, 'POST', path + '/acknowledge' + query, expected=403)
    call('astronaut', 'POST', path + '/resolve' + query, {'note': 'Denied'}, 403)
    call('doctor', 'POST', path + '/resolve' + query, {'note': '   '}, 422)
    resolved = call('doctor', 'POST', path + '/resolve' + query, {'note': 'Avaliação médica registrada'})
    assert resolved['status'] == 'resolved'
    assert call('astronaut', 'GET', base + '/alerts' + query)['pagination']['total'] == 0
    assert call('astronaut', 'GET', base + '/alerts' + query + '&status=resolved')['pagination']['total'] == 1
    call('astronaut', 'POST', path + '/acknowledge' + query, expected=409)


def test_http_profile_and_structured_symptoms(catalog_api):
    call, people, mission_id = catalog_api
    settings_path = f'/health/missions/{mission_id}/alert-settings'
    assert call('astronaut', 'GET', settings_path)['can_edit'] is False
    settings = call('doctor', 'PUT', settings_path, {'expected_revision': 0, 'timezone': 'America/Bahia', 'emergency_channel': 'Canal clínico 2', 'approval_note': 'Metas da simulação aprovadas'})
    assert settings['revision'] == 1
    call('astronaut', 'PUT', settings_path, {'expected_revision': 1, 'timezone': 'UTC', 'approval_note': 'Denied'}, 403)
    base = f"/health/astronauts/{people['astronaut']}"
    payload = measurement(mission_id, indicator='blood_pressure', value=None, systolic=181, diastolic=121)
    call('astronaut', 'POST', base + '/observations', payload, 201)
    query = f'?mission_id={mission_id}'
    urgent = call('astronaut', 'GET', base + '/alerts' + query)['data'][0]
    assert urgent['severity'] == 'urgent'
    assert 'Sintomas desconhecidos' in urgent['reason']
    assert urgent['trigger_observation']['symptoms_status'] == 'unknown'
    payload['symptoms'] = ['chest_pain']
    payload['client_request_id'] = str(uuid4())
    call('astronaut', 'POST', base + '/observations', payload, 201)
    critical = call('astronaut', 'GET', base + '/alerts' + query)['data'][0]
    assert critical['id'] == urgent['id']
    assert critical['severity'] == 'critical'
    assert 'Canal clínico 2' in critical['protocol_message']
    assert critical['trigger_observation']['symptoms_status'] == 'present'
    call('astronaut', 'POST', base + '/observations', measurement(mission_id, indicator='attention', value=None, category='worse', acute_confusion=True), 201)
    assert call('astronaut', 'GET', base + '/alerts' + query)['pagination']['total'] == 2
    assert call('astronaut', 'GET', base + '/alerts' + query + '&indicator=blood_pressure')['pagination']['total'] == 1
    assert call('astronaut', 'GET', base + '/alerts' + query + '&indicator=attention')['data'][0]['rule_id'] == 'acute_consciousness'
    assert call('astronaut', 'GET', base + '/alerts' + query + '&indicator=heart_rate')['data'] == []
    call('astronaut', 'POST', base + '/observations', measurement(mission_id, unit='unsupported'), 422)


def test_glucose_form_payload_save_summary_history_and_replay(catalog_api):
    call, people, mission_id = catalog_api
    base = f"/health/astronauts/{people['astronaut']}"
    payload = {
        'indicator': 'blood_glucose', 'client_request_id': str(uuid4()), 'unit': 'mg/dL',
        'activity': 'unknown', 'signal_quality': 'unknown', 'supplemental_oxygen': None,
        'glucose_context': 'unknown', 'symptoms_status': 'unknown', 'symptoms': [], 'acute_confusion': None,
        'collected_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        'mission_id': None, 'source': 'manual_measurement', 'note': None, 'is_preflight_reference': False,
        'value': 95,
    }
    saved = call('astronaut', 'POST', base + '/observations', payload, 201)
    assert saved['value'] == 95 and saved['unit'] == 'mg/dL'
    assert call('astronaut', 'POST', base + '/observations', payload, 201)['id'] == saved['id']
    summary = call('astronaut', 'GET', base + '/summary')
    glucose = next(row for row in summary['indicators'] if row['indicator'] == 'blood_glucose')
    assert glucose['latest']['id'] == saved['id']
    assert call('astronaut', 'GET', base + '/history?indicator=blood_glucose')['data'][0]['id'] == saved['id']
    assert call('astronaut', 'GET', base + '/alerts?indicator=blood_glucose')['data'] == []
    payload['client_request_id'] = None
    payload['value'] = 53
    saved = call('astronaut', 'POST', base + '/observations', payload, 201)
    assert call('astronaut', 'POST', base + '/observations', payload, 201)['id'] == saved['id']
    alerts = call('astronaut', 'GET', base + '/alerts?indicator=blood_glucose')['data']
    assert len(alerts) == 1
    assert alerts[0]['severity'] == 'critical'
    assert alerts[0]['trigger_observation']['value'] == 53


def test_glucose_400_produces_urgent_alert_in_simulation_profile(catalog_api):
    call, people, mission_id = catalog_api
    base = f"/health/astronauts/{people['astronaut']}"
    saved = call('astronaut', 'POST', base + '/observations', measurement(None, indicator='blood_glucose', value=400, unit='mg/dL', glucose_context='fasting'), 201)
    alert = call('astronaut', 'GET', base + '/alerts?indicator=blood_glucose')['data'][0]
    assert alert['severity'] == 'urgent'
    assert alert['trigger_observation']['id'] == saved['id']
    assert alert['rule_version'] == 'simulation-v2'
    assert '400' in alert['reason'] and '300' in alert['reason']


def test_alert_history_pagination_and_automatic_resolution(catalog_api):
    call, people, mission_id = catalog_api
    base = f"/health/astronauts/{people['astronaut']}"
    for index in range(5):
        call('astronaut', 'POST', base + '/observations', measurement(None, indicator='blood_glucose', value=400, glucose_context='fasting', client_request_id=str(uuid4())), 201)
        call('astronaut', 'POST', base + '/observations', measurement(None, indicator='blood_glucose', value=100, glucose_context='unknown', client_request_id=str(uuid4())), 201)
    assert call('astronaut', 'GET', base + '/alerts?indicator=blood_glucose')['data'] == []
    first = call('astronaut', 'GET', base + '/alerts?status=all&indicator=blood_glucose&per_page=3&page=1')
    second = call('astronaut', 'GET', base + '/alerts?status=all&indicator=blood_glucose&per_page=3&page=2')
    assert first['pagination']['total'] == 5
    assert first['pagination']['total_pages'] == 2
    assert first['pagination']['has_next'] is True
    assert second['pagination']['has_previous'] is True
    assert len(first['data']) == 3 and len(second['data']) == 2
    assert not ({row['id'] for row in first['data']} & {row['id'] for row in second['data']})
    assert all(row['status'] == 'resolved' for row in first['data'] + second['data'])
    alert_id = first['data'][0]['id']
    history = call('astronaut', 'GET', f'{base}/alerts/{alert_id}/history?per_page=1&page=1')
    next_page = call('astronaut', 'GET', f'{base}/alerts/{alert_id}/history?per_page=1&page=2')
    assert history['pagination']['total'] == 2
    assert history['data'][0]['action'] == 'auto_resolved'
    assert next_page['data'][0]['action'] == 'created'
