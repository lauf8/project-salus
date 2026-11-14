"""Fluxo de radiação: atividade da tripulação, SEP em EVA, acompanhamento de 48 h,
sintomas, alertas, fluxo de prótons (NOAA SWPC e simulado), doses e linha do tempo."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.security import create_access_token
from app.database import get_session
from app.dependencies.donki import get_donki_client, get_swpc_client
from app.main import app
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertEvent, HealthAlertObservation, HealthAlertSettings
from app.models.notifications import HealthNotification
from app.models.preflight import Mission, MissionMember
from app.models.revoked_token import RevokedToken
from app.models.space_weather import (
    CrewActivity, ProtonFluxReading, RadiationAlert, RadiationDoseRecord, RadiationExposureLimit, RadiationFollowUp,
    RadiationSymptomReport, SpaceWeatherEvent, SpaceWeatherEventLink, SpaceWeatherSyncRun,
)
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.models.user import User
from app.providers.donki import DonkiClient, DonkiSettings
from app.providers.swpc import SwpcClient, SwpcSettings
from app.services.radiation_service import parse_swpc_reading, simulated_flux
from tests.test_space_weather import CME, FLARE, SEP, FakeDonki


UTC = timezone.utc
SEP_TIME = datetime(2024, 10, 26, 19, 2, tzinfo=UTC)
OCTOBER = {'start_date': '2024-10-01', 'end_date': '2024-11-14'}
LIMITS = [
    ('skin', '30_day', 1500), ('skin', '1_year', 3000), ('skin', 'career', 6000),
    ('bfo', '30_day', 250), ('bfo', '1_year', 500),
    ('lens', '30_day', 1000), ('heart', '30_day', 250), ('cns', '30_day', 500),
]


def iso(value: datetime) -> str:
    return value.isoformat().replace('+00:00', 'Z')


class FakeSwpc:
    def __init__(self):
        self.items = []
        self.status = 200
        self.urls = []

    def handler(self, request: httpx.Request):
        self.urls.append(str(request.url))
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, content=json.dumps(self.items))


@pytest.fixture
def radiation_api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')

    models = (
        User, RevokedToken, Spacecraft, Mission, MissionMember, SpacecraftModule, SpaceWeatherEvent, SpaceWeatherEventLink,
        SpaceWeatherSyncRun, ProtonFluxReading, CrewActivity, RadiationExposureLimit, RadiationDoseRecord, RadiationFollowUp,
        HealthObservation, HealthAlertSettings, HealthAlert, HealthAlertObservation, HealthAlertEvent, HealthNotification,
        RadiationSymptomReport, RadiationAlert,
    )
    SQLModel.metadata.create_all(engine, tables=[model.__table__ for model in models])
    session = Session(engine)
    people = {}
    for name in ('doctor', 'admin', 'eva', 'iva', 'outsider'):
        user = User(
            name=name, email=f'rad-{name}@fictional.test', hashed_password='fictional',
            is_physician=name in ('doctor', 'admin', 'outsider'), is_astronaut=name in ('eva', 'iva'),
        )
        session.add(user)
        session.flush()
        people[name] = user.id
    mission = Mission(
        name='Missão de outubro', status='completed', planned_launch_at=datetime(2024, 10, 20, tzinfo=UTC),
        started_at=datetime(2024, 10, 20, tzinfo=UTC), ended_at=datetime(2024, 11, 5, tzinfo=UTC),
    )
    session.add(mission)
    session.flush()
    for name, role in (('doctor', 'flight_surgeon'), ('admin', 'mission_admin'), ('eva', 'astronaut'), ('iva', 'astronaut')):
        session.add(MissionMember(mission_id=mission.id, user_id=people[name], role=role))
    for organ, period, value in LIMITS:
        session.add(RadiationExposureLimit(profile_id='nasa-sp-2009-3405-table-5-1', organ=organ, period=period, value=value, unit='mGy-Eq', source_reference='Tabela 5-1'))
    session.commit()

    donki, swpc = FakeDonki(), FakeSwpc()
    donki_http = httpx.Client(transport=httpx.MockTransport(donki.handler))
    swpc_http = httpx.Client(transport=httpx.MockTransport(swpc.handler))

    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_donki_client] = lambda: DonkiClient(donki_http, DonkiSettings(api_key='TEST_KEY', base_url='https://donki.test/DONKI'))
    app.dependency_overrides[get_swpc_client] = lambda: SwpcClient(swpc_http, SwpcSettings(base_url='https://swpc.test/json/goes'))
    try:
        with TestClient(app) as client:
            def call(method, path, payload=None, expected=200, actor='doctor', params=None):
                headers = {'Authorization': f'Bearer {create_access_token(str(people[actor]))}'}
                response = client.request(method, '/v1' + path, json=payload, params=params, headers=headers)
                assert response.status_code == expected, response.text
                return response.json() if response.content else None

            base = f'/radiation/missions/{mission.id}'
            yield call, session, people, base, swpc
    finally:
        app.dependency_overrides.clear()
        donki_http.close()
        swpc_http.close()
        session.close()
        engine.dispose()


def eva_during_sep(call, people, base, actor='eva'):
    return call('POST', f'{base}/crew-activities', {
        'astronaut_id': people['eva'], 'activity_type': 'eva',
        'started_at': iso(SEP_TIME - timedelta(hours=2)), 'ended_at': iso(SEP_TIME + timedelta(hours=4)),
    }, expected=201, actor=actor)


def active_alerts(call, base, actor='doctor', **params):
    return call('GET', f'{base}/alerts', actor=actor, params=params)['data']


# --- Funções puras -------------------------------------------------------------------------------

def test_swpc_parsing_and_simulated_profile():
    assert parse_swpc_reading({'time_tag': '2024-10-26T19:05:00Z', 'satellite': 18, 'flux': 12.5, 'energy': '>=10 MeV'}) == (
        datetime(2024, 10, 26, 19, 5, tzinfo=UTC), '>=10 MeV', 'GOES-18', 12.5)
    assert parse_swpc_reading({'time_tag': '2024-10-26T19:05:00Z', 'satellite': 18, 'flux': -1, 'energy': '>=10 MeV'}) is None
    assert parse_swpc_reading({'time_tag': 'x', 'flux': 1, 'energy': '>=10 MeV'}) is None
    assert parse_swpc_reading({'time_tag': '2024-10-26T19:05:00Z', 'flux': 1, 'energy': '>=2 MeV'}) is None
    assert simulated_flux(0, 1000, 4, 12) == pytest.approx(0.5)
    assert simulated_flux(4, 1000, 4, 12) == pytest.approx(1000)
    assert simulated_flux(16, 1000, 4, 12) < simulated_flux(8, 1000, 4, 12) < 1000


# --- Atividade e SEP -----------------------------------------------------------------------------

def test_sep_sync_opens_48h_window_only_for_crew_on_eva(radiation_api):
    call, session, people, base, _ = radiation_api
    eva_during_sep(call, people, base)
    call('POST', f'{base}/crew-activities', {
        'astronaut_id': people['iva'], 'activity_type': 'iva',
        'started_at': iso(SEP_TIME - timedelta(hours=8)), 'ended_at': iso(SEP_TIME + timedelta(hours=8)),
    }, expected=201, actor='iva')

    call('POST', '/space-weather/sync', OCTOBER)
    follow_ups = call('GET', f'{base}/follow-ups')
    assert len(follow_ups) == 1
    follow_up = follow_ups[0]
    assert follow_up['astronaut_id'] == people['eva'] and follow_up['was_on_eva'] is True
    assert follow_up['event_activity_id'] == SEP['sepID'] and follow_up['status'] == 'open'
    assert follow_up['opened_at'].startswith('2024-10-26T19:02') and follow_up['window_ends_at'].startswith('2024-10-28T19:02')
    assert follow_up['window_active'] is False  # a janela de 2024 já passou

    alerts = active_alerts(call, base)
    assert [(alert['rule_id'], alert['severity'], alert['astronaut_id']) for alert in alerts] == [('sep_during_eva', 'urgent', people['eva'])]

    # Nova sincronização não duplica acompanhamento nem alerta.
    call('POST', '/space-weather/sync', OCTOBER)
    assert len(session.exec(select(RadiationFollowUp)).all()) == 1
    assert len(session.exec(select(RadiationAlert)).all()) == 1


def test_eva_recorded_after_sep_import_also_opens_follow_up(radiation_api):
    call, session, people, base, _ = radiation_api
    call('POST', '/space-weather/sync', OCTOBER)
    assert call('GET', f'{base}/follow-ups') == []

    # EVA aberta (sem fim) que começou 1 h antes do SEP; o administrador registra.
    activity = call('POST', f'{base}/crew-activities', {
        'astronaut_id': people['eva'], 'activity_type': 'eva', 'started_at': iso(SEP_TIME - timedelta(hours=1)),
    }, expected=201, actor='admin')
    assert len(call('GET', f'{base}/follow-ups')) == 1
    ended = call('POST', f"{base}/crew-activities/{activity['id']}/end", {'ended_at': iso(SEP_TIME + timedelta(hours=3))}, actor='eva')
    assert ended['ended_at'].startswith('2024-10-26T22:02')
    call('POST', f"{base}/crew-activities/{activity['id']}/end", {'ended_at': iso(SEP_TIME + timedelta(hours=4))}, expected=409)

    sep = session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.event_type == 'SEP')).one()
    assert call('POST', f"/radiation/events/{sep.activity_id}/process") == {'event_activity_id': SEP['sepID'], 'follow_ups_opened': 0, 'alerts_created': 0}
    call('POST', f"/radiation/events/{FLARE['flrID']}/process", expected=422)
    call('POST', f"/radiation/events/{sep.activity_id}/process", actor='eva', expected=403)


def test_activity_validation_and_permissions(radiation_api):
    call, _, people, base, _ = radiation_api
    payload = {'astronaut_id': people['eva'], 'activity_type': 'eva', 'started_at': iso(SEP_TIME), 'ended_at': iso(SEP_TIME + timedelta(hours=2))}
    call('POST', f'{base}/crew-activities', payload, actor='iva', expected=403)
    call('POST', f'{base}/crew-activities', payload, actor='outsider', expected=404)
    call('POST', f'{base}/crew-activities', {**payload, 'astronaut_id': people['doctor']}, expected=404)
    call('POST', f'{base}/crew-activities', {**payload, 'ended_at': iso(SEP_TIME)}, expected=422)
    call('POST', f'{base}/crew-activities', {**payload, 'started_at': '2024-10-01T00:00:00Z'}, expected=422)  # antes da missão
    call('POST', f'{base}/crew-activities', {**payload, 'started_at': '2024-10-26T19:02:00'}, expected=422)  # sem fuso
    call('POST', f'{base}/crew-activities', payload, expected=201, actor='eva')
    call('POST', f'{base}/crew-activities', {**payload, 'activity_type': 'storm_shelter'}, expected=409)  # sobreposta
    listed = call('GET', f'{base}/crew-activities', actor='iva')
    assert listed['pagination']['total'] == 1


# --- Sintomas e alertas -----------------------------------------------------------------------------

def test_symptom_reports_raise_prodromal_alerts(radiation_api):
    call, _, people, base, _ = radiation_api
    eva_during_sep(call, people, base)
    call('POST', '/space-weather/sync', OCTOBER)
    follow_up = call('GET', f'{base}/follow-ups', actor='eva')[0]
    reports = f"{base}/follow-ups/{follow_up['id']}/reports"

    call('POST', reports, {'symptoms': ['nausea'], 'reported_at': iso(SEP_TIME + timedelta(hours=6))}, actor='iva', expected=403)
    call('POST', reports, {'symptoms': []}, actor='eva', expected=422)
    call('POST', reports, {'symptoms': ['chest_pain']}, actor='eva', expected=422)
    call('POST', reports, {'symptoms': ['nausea'], 'reported_at': iso(SEP_TIME - timedelta(hours=1))}, actor='eva', expected=422)

    updated = call('POST', reports, {'symptoms': ['nausea', 'anorexia'], 'reported_at': iso(SEP_TIME + timedelta(hours=6))}, actor='eva', expected=201)
    assert updated['symptoms'] == ['anorexia', 'nausea'] and len(updated['reports']) == 1
    call('POST', reports, {'symptoms': ['vomiting', 'skin_erythema'], 'reported_at': iso(SEP_TIME + timedelta(hours=10)), 'note': 'Vomitou duas vezes'}, expected=201)
    call('POST', reports, {'symptoms': ['fatigue'], 'reported_at': iso(SEP_TIME + timedelta(hours=60))}, actor='eva', expected=201)

    alerts = {alert['rule_id']: alert for alert in active_alerts(call, base, actor='eva')}
    assert {rule: alert['severity'] for rule, alert in alerts.items()} == {
        'prodromal_vomiting': 'critical', 'prodromal_symptoms': 'urgent', 'skin_reaction': 'urgent',
        'sep_during_eva': 'urgent', 'late_symptoms': 'attention',
    }
    assert 'EVA' in alerts['skin_reaction']['reason']
    # Ordem: crítico primeiro.
    assert active_alerts(call, base)[0]['rule_id'] == 'prodromal_vomiting'
    assert active_alerts(call, base, actor='iva') == []

    # Astronauta reconhece, mas só o médico de voo resolve.
    vomiting = alerts['prodromal_vomiting']
    assert vomiting['can_resolve'] is False
    acknowledged = call('POST', f"{base}/alerts/{vomiting['id']}/acknowledge", actor='eva')
    assert acknowledged['status'] == 'acknowledged'
    call('POST', f"{base}/alerts/{vomiting['id']}/acknowledge", actor='iva', expected=403)
    call('POST', f"{base}/alerts/{vomiting['id']}/resolve", {'note': 'Avaliado'}, actor='eva', expected=403)
    resolved = call('POST', f"{base}/alerts/{vomiting['id']}/resolve", {'note': 'Avaliado, sem sinais de dose alta'})
    assert resolved['status'] == 'resolved' and resolved['can_resolve'] is False
    call('POST', f"{base}/alerts/{vomiting['id']}/acknowledge", expected=409)

    # Encerramento pelo médico de voo.
    close = f"{base}/follow-ups/{follow_up['id']}/close"
    call('POST', close, {'status': 'completed', 'notes': 'Sem sintomas novos'}, actor='eva', expected=403)
    closed = call('POST', close, {'status': 'completed', 'notes': 'Sem sintomas novos'})
    assert closed['status'] == 'completed' and closed['closed_at'] is not None
    call('POST', reports, {'symptoms': ['nausea']}, actor='eva', expected=409)


def test_health_observation_with_radiation_symptom_feeds_open_follow_up(radiation_api):
    call, session, people, base, _ = radiation_api
    recent = datetime.now(UTC) - timedelta(hours=3)
    mission = session.get(Mission, int(base.rsplit('/', 1)[-1]))
    mission.status, mission.ended_at = 'in_progress', None
    session.add(mission)
    sep = SpaceWeatherEvent(activity_id=f'{iso(recent)[:16]}:00-SEP-001', event_type='SEP', start_time=recent, raw={}, instruments=[])
    session.add(sep)
    session.commit()
    call('POST', f'{base}/crew-activities', {
        'astronaut_id': people['eva'], 'activity_type': 'eva', 'started_at': iso(recent - timedelta(hours=1)),
        'ended_at': iso(recent + timedelta(hours=1)),
    }, expected=201, actor='eva')
    follow_up = call('GET', f'{base}/follow-ups')[0]
    assert follow_up['window_active'] is True

    call('POST', f"/health/astronauts/{people['eva']}/observations", {
        'mission_id': mission.id, 'indicator': 'fatigue', 'value': 6, 'source': 'self_report',
        'collected_at': iso(datetime.now(UTC) - timedelta(minutes=5)), 'symptoms': ['nausea', 'vomiting'],
    }, actor='eva', expected=201)
    follow_up = call('GET', f"{base}/follow-ups/{follow_up['id']}", actor='eva')
    assert follow_up['symptoms'] == ['nausea', 'vomiting']
    assert follow_up['reports'][0]['observation_id'] is not None
    assert {alert['rule_id'] for alert in active_alerts(call, base)} >= {'prodromal_vomiting', 'prodromal_symptoms'}

    # Sintomas de radiação numa medição sem acompanhamento aberto não geram relato.
    call('POST', f"/health/astronauts/{people['iva']}/observations", {
        'mission_id': mission.id, 'indicator': 'fatigue', 'value': 3, 'source': 'self_report',
        'collected_at': iso(datetime.now(UTC) - timedelta(minutes=5)), 'symptoms': ['nausea'],
    }, actor='iva', expected=201)
    assert len(session.exec(select(RadiationSymptomReport)).all()) == 1


# --- Fluxo de prótons ---------------------------------------------------------------------------------

def test_swpc_import_is_idempotent_and_flags_flux_during_eva(radiation_api):
    call, session, people, base, swpc = radiation_api
    eva_during_sep(call, people, base)
    swpc.items = [
        {'time_tag': iso(SEP_TIME + timedelta(minutes=5 * index)), 'satellite': 18, 'flux': flux, 'energy': '>=10 MeV'}
        for index, flux in enumerate([5.0, 40.0, 150.0])
    ] + [
        {'time_tag': iso(SEP_TIME), 'satellite': 18, 'flux': 2.0, 'energy': '>=100 MeV'},
        {'time_tag': iso(SEP_TIME), 'satellite': 18, 'flux': 1.0, 'energy': '>=2 MeV'},  # canal desconhecido
    ]
    call('POST', '/radiation/proton-flux/sync', {'window': '3-day'}, actor='eva', expected=403)
    result = call('POST', '/radiation/proton-flux/sync', {'window': '3-day'})
    assert result == {'fetched_count': 5, 'stored_count': 4, 'skipped_count': 1, 'alerts_created': 1}
    assert swpc.urls[-1] == 'https://swpc.test/json/goes/primary/integral-protons-3-day.json'
    again = call('POST', '/radiation/proton-flux/sync', {'window': '3-day'})
    assert again['stored_count'] == 0 and again['alerts_created'] == 0

    alert = active_alerts(call, base)[0]
    assert (alert['rule_id'], alert['severity'], alert['details']['peak_flux_pfu']) == ('proton_flux_during_eva', 'urgent', 150.0)
    series = call('GET', '/radiation/proton-flux', actor='iva', params={'start': iso(SEP_TIME - timedelta(hours=1))})
    assert [item['flux_pfu'] for item in series] == [5.0, 40.0, 150.0]
    assert call('GET', '/radiation/proton-flux', params={'channel': '>=100 MeV'})[0]['satellite'] == 'GOES-18'

    swpc.status = 503
    call('POST', '/radiation/proton-flux/sync', {}, expected=502)


def test_simulated_flux_and_doses_raise_dose_limit_alerts(radiation_api):
    call, session, people, base, _ = radiation_api
    call('POST', '/space-weather/sync', OCTOBER)
    eva_during_sep(call, people, base)

    simulation = {'event_activity_id': SEP['sepID'], 'peak_pfu': 20000, 'rise_hours': 2, 'decay_hours': 6, 'duration_hours': 24}
    call('POST', '/radiation/proton-flux/simulate', {**simulation, 'onset': iso(SEP_TIME)}, expected=422)
    call('POST', '/radiation/proton-flux/simulate', {**simulation, 'event_activity_id': FLARE['flrID']}, expected=422)
    flux = call('POST', '/radiation/proton-flux/simulate', simulation)
    assert flux['stored_count'] == 49 and flux['peak_at'].startswith('2024-10-26T21:02')
    # Pico ≥ S3 durante a EVA: o alerta do SEP sobe para crítico.
    severities = {alert['rule_id']: alert['severity'] for alert in active_alerts(call, base)}
    assert severities == {'sep_during_eva': 'critical', 'proton_flux_during_eva': 'critical'}

    window = {'start': iso(SEP_TIME), 'end': iso(SEP_TIME + timedelta(hours=24)), 'event_activity_id': SEP['sepID']}
    call('POST', f'{base}/doses/simulate', window, actor='eva', expected=403)
    call('POST', f'{base}/doses/simulate', {**window, 'start': '2024-10-21T00:00:00Z', 'end': '2024-10-22T00:00:00Z'}, expected=422)
    result = call('POST', f'{base}/doses/simulate', window)
    assert result['readings_used'] == 49 and len(result['records']) == 10
    skin = {record['astronaut_id']: record['dose'] for record in result['records'] if record['organ'] == 'skin'}
    # A EVA (4 h após o SEP, inclusive o pico) recebe mais dose que a IVA o dia todo.
    assert skin[people['eva']] > skin[people['iva']] > 0
    assert all(record['source'] == 'simulation' for record in result['records'])

    # Repetir a simulação substitui os registros.
    call('POST', f'{base}/doses/simulate', window)
    assert len(session.exec(select(RadiationDoseRecord)).all()) == 10

    summary = call('GET', f"{base}/astronauts/{people['eva']}/dose-summary", actor='eva')
    bfo = next(item for item in summary['items'] if item['organ'] == 'bfo' and item['period'] == '30_day')
    assert bfo['total'] == pytest.approx(skin[people['eva']] * 0.3, rel=1e-3)
    assert summary['as_of'].startswith('2024-11-05')
    dose_alerts = {
        (alert['details']['organ'], alert['details']['period']): alert['severity']
        for alert in active_alerts(call, base, astronaut_id=people['eva']) if alert['rule_id'] == 'dose_limit'
    }
    assert dose_alerts[('bfo', '30_day')] == ('critical' if bfo['fraction'] >= 1 else 'urgent' if bfo['fraction'] >= 0.75 else 'attention')
    assert bfo['fraction'] >= 0.5
    call('GET', f"{base}/astronauts/{people['eva']}/dose-summary", actor='iva', expected=403)


def test_manual_dose_records_and_visibility(radiation_api):
    call, _, people, base, _ = radiation_api
    dose = {
        'astronaut_id': people['iva'], 'organ': 'bfo', 'dose': 200, 'source': 'dosimeter',
        'period_start': iso(SEP_TIME), 'period_end': iso(SEP_TIME + timedelta(hours=12)),
    }
    call('POST', f'{base}/doses', dose, actor='iva', expected=403)
    call('POST', f'{base}/doses', {**dose, 'source': 'simulation'}, expected=422)
    call('POST', f'{base}/doses', {**dose, 'unit': 'mGy'}, expected=422)
    call('POST', f'{base}/doses', {**dose, 'event_activity_id': 'inexistente'}, expected=404)
    created = call('POST', f'{base}/doses', dose, expected=201)
    assert created['source'] == 'dosimeter' and created['event_id'] is None

    alerts = active_alerts(call, base, actor='iva')
    assert [(alert['rule_id'], alert['severity']) for alert in alerts] == [('dose_limit', 'urgent')]  # 200/250 = 80%
    call('POST', f'{base}/doses', {**dose, 'dose': 60}, expected=201)
    alerts = active_alerts(call, base, actor='iva')
    # 260/250 no período de 30 dias (escalou, sem duplicar) e 260/500 em 1 ano.
    assert [(alert['severity'], alert['details']['period']) for alert in alerts] == [('critical', '30_day'), ('attention', '1_year')]

    assert call('GET', f'{base}/doses', actor='iva')['pagination']['total'] == 2
    assert call('GET', f'{base}/doses', actor='eva')['pagination']['total'] == 0
    call('GET', f'{base}/doses', actor='eva', params={'astronaut_id': people['iva']}, expected=403)
    call('GET', f'{base}/doses', actor='admin', expected=403)
    assert call('GET', f'{base}/doses', params={'astronaut_id': people['iva']})['pagination']['total'] == 2


# --- Linha do tempo ---------------------------------------------------------------------------------

def test_timeline_builds_flare_cme_sep_chain(radiation_api):
    call, _, people, base, _ = radiation_api
    eva_during_sep(call, people, base)
    call('POST', '/space-weather/sync', OCTOBER)

    timeline = call('GET', f'{base}/timeline')
    assert timeline['start'].startswith('2024-10-20') and timeline['end'].startswith('2024-11-05')
    assert [event['event_type'] for event in timeline['events']] == ['FLR', 'CME', 'SEP']
    assert len(timeline['chains']) == 1
    chain = timeline['chains'][0]
    assert [item['activity_id'] for item in chain['flares']] == [FLARE['flrID']]
    assert [item['activity_id'] for item in chain['cmes']] == [CME['activityID']]
    assert [item['activity_id'] for item in chain['seps']] == [SEP['sepID']]
    assert chain['other_linked'] == ['2024-10-26T15:34:00-IPS-001', '2024-10-28T04:13:00-IPS-001']
    assert len(timeline['activities']) == 1 and len(timeline['follow_ups']) == 1 and len(timeline['alerts']) == 1
    assert timeline['can_manage'] is True

    own = call('GET', f'{base}/timeline', actor='iva')
    assert own['can_view_clinical'] is True and own['follow_ups'] == [] and own['alerts'] == []
    admin = call('GET', f'{base}/timeline', actor='admin')
    assert admin['can_view_clinical'] is False and admin['follow_ups'] == [] and len(admin['chains']) == 1
    call('GET', f'{base}/timeline', actor='outsider', expected=404)
